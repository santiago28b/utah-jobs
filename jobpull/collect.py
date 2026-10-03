"""Pull jobs from every source, keep entry-level tech roles in SL/Utah County, save to the DB.

    python -m jobpull.collect            # normal run (needs DATABASE_URL)
    python -m jobpull.collect --dry-run  # no DB; print what would be saved
    python -m jobpull.collect --only greenhouse --verbose
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import db, filters, locations
from .models import RawJob
from .sources import Board, adzuna, ashby, greenhouse, lever, smartrecruiters, usajobs, workday

log = logging.getLogger("jobpull")

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workday": workday.fetch,
    "adzuna": adzuna.fetch,
    "usajobs": usajobs.fetch,
}
# Aggregators with API quotas: minimum minutes between runs.
MIN_INTERVAL = {"adzuna": 110, "usajobs": 55}
AGGREGATORS = {"adzuna", "usajobs"}
# Only save jobs whose fit score is above this.
MIN_SCORE = 70

ROOT = Path(__file__).resolve().parent.parent


def load_boards(path: Path = ROOT / "companies.yaml") -> list[Board]:
    cfg = yaml.safe_load(path.read_text()) or {}
    boards = []
    for source in ("greenhouse", "lever", "ashby", "smartrecruiters"):
        for e in cfg.get(source) or []:
            boards.append(Board(source, e["token"], e["company"], options=e))
    for e in cfg.get("workday") or []:
        boards.append(Board("workday", f"{e['tenant']}/{e['site']}", e["company"], options=e))
    boards.append(Board("adzuna", "adzuna", "", complete_listing=False))
    boards.append(Board("usajobs", "usajobs", "", complete_listing=False))
    return boards


@dataclass
class BoardResult:
    board: Board
    started: datetime
    fetched: list[RawJob] = field(default_factory=list)
    matched: list[dict] = field(default_factory=list)
    seen_only: list[str] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (title, reason)
    error: str | None = None


def to_record(raw: RawJob, board: Board) -> tuple[dict | None, str]:
    """Apply location + role filters. Returns (db row, reject reason)."""
    loc = locations.match(raw.locations, raw.remote, board.options.get("allow_remote_us", False))
    if not loc.ok:
        return None, f"location: {'; '.join(raw.locations)[:80]}"
    v = filters.evaluate(raw.title, raw.description, raw.employment_type, raw.seniority_hint)
    if not v.ok:
        return None, v.reason
    if v.score <= MIN_SCORE:
        return None, f"score {v.score} <= {MIN_SCORE}"
    return {
        "source": raw.source,
        "external_id": raw.external_id,
        "company": raw.company,
        "title": raw.title,
        "location": loc.label,
        "remote": loc.remote,
        "url": raw.url,
        "description": raw.description[:20000],
        "category": v.category,
        "job_type": v.job_type,
        "employment_type": raw.employment_type,
        "level": v.level,
        "score": v.score,
        "min_years": v.min_years,
        "posted_at": raw.posted_at,
        "closes_at": raw.closes_at,
        "dedupe_key": db.dedupe_key(raw.company, raw.title, loc.label),
    }, ""


def run_board(board: Board) -> BoardResult:
    res = BoardResult(board, datetime.now(timezone.utc))
    try:
        res.fetched = FETCHERS[board.source](board)
    except Exception as e:  # one broken board never stops the run
        res.error = f"{type(e).__name__}: {e}"
        log.warning("%s/%s failed: %s", board.source, board.key, res.error)
        log.debug(traceback.format_exc())
        return res
    for raw in res.fetched:
        if raw.seen_only:
            res.seen_only.append(raw.external_id)
            continue
        rec, reason = to_record(raw, board)
        if rec:
            res.matched.append(rec)
        else:
            res.rejected.append((raw.title, reason))
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="don't touch the database; print matches")
    ap.add_argument("--only", help="comma-separated sources to run, e.g. greenhouse,lever")
    ap.add_argument("--show-rejected", action="store_true", help="with --dry-run, also print rejected tech titles")
    ap.add_argument("--force", action="store_true", help="ignore per-source minimum intervals")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    boards = load_boards()
    if args.only:
        wanted = set(args.only.split(","))
        boards = [b for b in boards if b.source in wanted]

    conn_cm = None if args.dry_run else db.connect()
    conn = conn_cm.__enter__() if conn_cm else None
    try:
        if conn:
            db.init(conn)
            now = datetime.now(timezone.utc)
            keep = []
            for b in boards:
                last = db.last_success(conn, b.source) if b.source in MIN_INTERVAL else None
                if last and not args.force and now - last < timedelta(minutes=MIN_INTERVAL[b.source]):
                    log.info("%s: ran %s ago, skipping this time", b.source, now - last)
                    continue
                b.known_ids = db.known_ids(conn, b.source)
                keep.append(b)
            boards = keep

        with ThreadPoolExecutor(max_workers=12) as ex:
            results = [f.result() for f in as_completed([ex.submit(run_board, b) for b in boards])]
        results.sort(key=lambda r: (r.board.source, r.board.key))

        total_new = 0
        for r in results:
            new = 0
            if conn:
                for rec in r.matched:
                    new += db.upsert_job(conn, rec, prefer_other_sources=r.board.source in AGGREGATORS)
                db.touch(conn, r.board.source, r.seen_only)
                if r.error is None and r.board.complete_listing:
                    db.mark_missing(conn, r.board.source, r.board.key, r.started)
                db.record_run(conn, source=r.board.source, board=r.board.key, started_at=r.started, ok=r.error is None,
                              fetched=len(r.fetched), matched=len(r.matched) + len(r.seen_only), new_jobs=new, error=r.error)
                conn.commit()
            total_new += new
            status = "ERROR " + r.error if r.error else f"fetched {len(r.fetched)}, matched {len(r.matched) + len(r.seen_only)}" + (f", new {new}" if conn else "")
            log.info("%-15s %-40s %s", r.board.source, r.board.key, status)
            if args.dry_run:
                for m in sorted(r.matched, key=lambda m: -m["score"]):
                    print(f"   [{m['score']:3d} {m['level']:8s}] {m['title']}  @ {m['company']} — {m['location']}"
                          f"{' (remote)' if m['remote'] else ''} [{m['category']}; {m['job_type']}] {m['url']}")
                if args.show_rejected:
                    for t, why in r.rejected:
                        if filters.categorize(t):
                            print(f"      x {t}  ({why})")
        if conn:
            db.expire_stale(conn)
            conn.commit()
        errors = sum(1 for r in results if r.error)
        log.info("done: %d boards, %d errors, %d new jobs", len(results), errors, total_new)
        # Only fail the workflow if everything broke (e.g. network down), not for one flaky board.
        return 1 if results and errors == len(results) else 0
    finally:
        if conn_cm:
            conn_cm.__exit__(*sys.exc_info())


if __name__ == "__main__":
    sys.exit(main())
