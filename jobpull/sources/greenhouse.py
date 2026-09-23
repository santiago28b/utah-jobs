from __future__ import annotations

from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, request


def fetch(board: Board) -> list[RawJob]:
    with client() as c:
        data = request(c, "GET", f"https://boards-api.greenhouse.io/v1/boards/{board.key}/jobs", params={"content": "true"}).json()
    out = []
    for j in data.get("jobs", []):
        locs = [(j.get("location") or {}).get("name") or ""]
        locs += [o.get("location") or o.get("name") or "" for o in j.get("offices") or []]
        out.append(RawJob(
            source="greenhouse",
            external_id=f"{board.key}:{j['id']}",
            company=board.company,
            title=j.get("title", "").strip(),
            url=j.get("absolute_url", ""),
            locations=[l for l in locs if l],
            description=html_to_text(j.get("content")),
            posted_at=parse_dt(j.get("first_published")) or parse_dt(j.get("updated_at")),
            closes_at=parse_dt(j.get("application_deadline")),
        ))
    return out
