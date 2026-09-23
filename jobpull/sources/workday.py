"""Workday career sites (the public JSON API behind *.myworkdayjobs.com)."""
from __future__ import annotations

from .. import filters
from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, parse_relative, request

PAGE = 20
MAX_JOBS = 2000


def fetch(board: Board) -> list[RawJob]:
    o = board.options
    tenant, wd, site = o["tenant"], o["wd"], o["site"]
    host = f"https://{tenant}.wd{wd}.myworkdayjobs.com"
    api = f"{host}/wday/cxs/{tenant}/{site}"
    searches = o.get("searches") or ["Utah"]
    aliases = {k.lower(): v for k, v in (o.get("location_aliases") or {}).items()}

    listing: dict[str, dict] = {}
    with client() as c:
        for q in searches:
            offset = 0
            while offset < MAX_JOBS:
                page = request(c, "POST", f"{api}/jobs", json={"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": q}).json()
                posts = page.get("jobPostings") or []
                for p in posts:
                    if p.get("externalPath"):
                        listing.setdefault(p["externalPath"], p)
                offset += PAGE
                if not posts or offset >= (page.get("total") or 0):
                    break

        out = []
        for path, p in listing.items():
            title = (p.get("title") or "").strip()
            if not filters.title_passes(title):
                continue
            ext_id = f"{board.key}:{path.rsplit('_', 1)[-1] if '_' in path else path}"
            if ext_id in board.known_ids:
                out.append(RawJob(source="workday", external_id=ext_id, company=board.company, title=title,
                                  url=f"{host}/{site}{path}", seen_only=True))
                continue
            info = request(c, "GET", f"{api}{path}").json().get("jobPostingInfo") or {}
            locs = [info.get("location") or p.get("locationsText") or ""] + list(info.get("additionalLocations") or [])
            locs = [_alias(l, aliases) for l in locs if l]
            out.append(RawJob(
                source="workday",
                external_id=ext_id,
                company=board.company,
                title=info.get("title") or title,
                url=info.get("externalUrl") or f"{host}/{site}{path}",
                locations=locs,
                description=html_to_text(info.get("jobDescription")),
                posted_at=parse_dt(info.get("startDate")) or parse_relative(p.get("postedOn")),
                closes_at=parse_dt(info.get("endDate")),
                employment_type=info.get("timeType") or "",
            ))
    return out


def _alias(loc: str, aliases: dict[str, str]) -> str:
    low = loc.lower()
    for k, v in aliases.items():
        if k in low:
            return f"{v} ({loc})"
    return loc
