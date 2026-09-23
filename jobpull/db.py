"""Postgres access (Supabase in production, any Postgres locally). Set DATABASE_URL."""
from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
create table if not exists jobs (
    id              bigserial primary key,
    source          text not null,
    external_id     text not null,
    company         text not null,
    title           text not null,
    location        text,
    remote          boolean not null default false,
    url             text not null,
    description     text,
    category        text,
    job_type        text,
    employment_type text,
    level           text,
    score           int,
    min_years       int,
    posted_at       timestamptz,
    closes_at       timestamptz,
    first_seen_at   timestamptz not null default now(),
    last_seen_at    timestamptz not null default now(),
    is_active       boolean not null default true,
    missed_runs     int not null default 0,
    emailed_at      timestamptz,
    dedupe_key      text,
    unique (source, external_id)
);
create index if not exists jobs_first_seen_idx on jobs (first_seen_at desc);
create index if not exists jobs_dedupe_idx on jobs (dedupe_key);

create table if not exists applications (
    job_id      bigint primary key references jobs(id) on delete cascade,
    status      text not null default 'new',
    applied_at  timestamptz,
    notes       text,
    updated_at  timestamptz not null default now()
);

create table if not exists source_runs (
    id          bigserial primary key,
    source      text not null,
    board       text not null,
    started_at  timestamptz not null,
    finished_at timestamptz,
    ok          boolean,
    fetched     int,
    matched     int,
    new_jobs    int,
    error       text
);
create index if not exists source_runs_idx on source_runs (source, board, started_at desc);
"""

STATUSES = ["new", "interested", "applied", "interviewing", "offer", "rejected", "not_interested"]


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (see README).")
    return url


@contextmanager
def connect(url: str | None = None):
    # prepare_threshold=None: Supabase's pooler (pgbouncer, transaction mode) can't use prepared statements.
    with psycopg.connect(url or database_url(), row_factory=dict_row, prepare_threshold=None, connect_timeout=15) as conn:
        yield conn


def init(conn) -> None:
    conn.execute(SCHEMA)
    conn.commit()


_CO_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|incorporated|the)\b\.?", re.I)


def dedupe_key(company: str, title: str, location: str) -> str:
    def norm(s: str) -> str:
        s = _CO_SUFFIX.sub(" ", (s or "").lower())
        return re.sub(r"[^a-z0-9]+", " ", s).strip()
    city = norm((location or "").split(",")[0].split("(")[0])
    return f"{norm(company)}|{norm(title)}|{city}"


def known_ids(conn, source: str) -> set[str]:
    rows = conn.execute("select external_id from jobs where source = %s and is_active", (source,)).fetchall()
    return {r["external_id"] for r in rows}


def upsert_job(conn, job: dict, prefer_other_sources: bool = False) -> bool:
    """Insert or refresh a job. Returns True when it is new.

    prefer_other_sources: for aggregators, skip if the same job already exists from a company board.
    """
    if prefer_other_sources:
        dup = conn.execute(
            "select 1 from jobs where dedupe_key = %s and source <> %s and is_active limit 1",
            (job["dedupe_key"], job["source"]),
        ).fetchone()
        if dup:
            return False
    row = conn.execute(
        """
        insert into jobs (source, external_id, company, title, location, remote, url, description, category,
                          job_type, employment_type, level, score, min_years, posted_at, closes_at, dedupe_key)
        values (%(source)s, %(external_id)s, %(company)s, %(title)s, %(location)s, %(remote)s, %(url)s,
                %(description)s, %(category)s, %(job_type)s, %(employment_type)s, %(level)s, %(score)s,
                %(min_years)s, %(posted_at)s, %(closes_at)s, %(dedupe_key)s)
        on conflict (source, external_id) do update set
            title = excluded.title, location = excluded.location, remote = excluded.remote, url = excluded.url,
            description = excluded.description, category = excluded.category, job_type = excluded.job_type,
            employment_type = excluded.employment_type, level = excluded.level, score = excluded.score,
            min_years = excluded.min_years, posted_at = coalesce(jobs.posted_at, excluded.posted_at),
            closes_at = excluded.closes_at, dedupe_key = excluded.dedupe_key,
            last_seen_at = now(), is_active = true, missed_runs = 0
        returning (xmax = 0) as inserted
        """,
        job,
    ).fetchone()
    return bool(row["inserted"])


def touch(conn, source: str, external_ids: list[str]) -> None:
    if external_ids:
        conn.execute(
            "update jobs set last_seen_at = now(), is_active = true, missed_runs = 0 "
            "where source = %s and external_id = any(%s)",
            (source, external_ids),
        )


def mark_missing(conn, source: str, board_key: str, run_started: datetime, runs_before_closed: int = 2) -> None:
    """For full listings: jobs not seen this run count a miss; after N misses they're closed.

    Board jobs have external_id "<board_key>:<id>".
    """
    conn.execute(
        """
        update jobs set missed_runs = missed_runs + 1,
                        is_active = (missed_runs + 1) < %s
        where source = %s and external_id like %s and is_active and last_seen_at < %s
        """,
        (runs_before_closed, source, board_key.replace("%", r"\%").replace("_", r"\_") + ":%", run_started),
    )


def expire_stale(conn, days: int = 10) -> None:
    """Aggregator results aren't complete listings; close them once they stop showing up."""
    conn.execute(
        "update jobs set is_active = false where is_active and source in ('adzuna', 'usajobs') "
        "and last_seen_at < now() - make_interval(days => %s)",
        (days,),
    )
    conn.execute("update jobs set is_active = false where is_active and closes_at < now()")


def last_success(conn, source: str) -> datetime | None:
    r = conn.execute(
        "select max(started_at) as t from source_runs where source = %s and ok", (source,)
    ).fetchone()
    return r["t"] if r else None


def record_run(conn, **kw) -> None:
    conn.execute(
        """insert into source_runs (source, board, started_at, finished_at, ok, fetched, matched, new_jobs, error)
           values (%(source)s, %(board)s, %(started_at)s, now(), %(ok)s, %(fetched)s, %(matched)s, %(new_jobs)s, %(error)s)""",
        kw,
    )
    conn.execute("delete from source_runs where started_at < now() - interval '14 days'")
