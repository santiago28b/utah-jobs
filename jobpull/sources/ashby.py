from __future__ import annotations

from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, request


def fetch(board: Board) -> list[RawJob]:
    with client() as c:
        data = request(c, "GET", f"https://api.ashbyhq.com/posting-api/job-board/{board.key}").json()
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        addr = ((j.get("address") or {}).get("postalAddress") or {})
        if addr.get("addressLocality"):
            locs.append(f"{addr.get('addressLocality')}, {addr.get('addressRegion', '')}")
        out.append(RawJob(
            source="ashby",
            external_id=f"{board.key}:{j['id']}",
            company=board.company,
            title=j.get("title", "").strip(),
            url=j.get("jobUrl", ""),
            locations=[l for l in locs if l],
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            posted_at=parse_dt(j.get("publishedAt")),
            employment_type=j.get("employmentType") or "",
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
        ))
    return out
