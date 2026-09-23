from __future__ import annotations

from .. import filters, locations
from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, request

API = "https://api.smartrecruiters.com/v1/companies"


def fetch(board: Board) -> list[RawJob]:
    out = []
    with client() as c:
        offset = 0
        postings = []
        while True:
            page = request(c, "GET", f"{API}/{board.key}/postings", params={"limit": 100, "offset": offset}).json()
            postings += page.get("content", [])
            offset += 100
            if offset >= page.get("totalFound", 0) or offset >= 2000:
                break

        for p in postings:
            loc = p.get("location") or {}
            loc_str = ", ".join(x for x in (loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()) if x)
            ext_id = f"{board.key}:{p['id']}"
            title = (p.get("name") or "").strip()
            # Only pay for the detail request when the job could be a match.
            if not filters.title_passes(title):
                continue
            loc_ok = locations.match([loc_str], bool(loc.get("remote")), board.options.get("allow_remote_us", False))
            if not loc_ok.ok:
                continue
            base = RawJob(
                source="smartrecruiters", external_id=ext_id, company=board.company, title=title,
                url=f"https://jobs.smartrecruiters.com/{board.key}/{p['id']}",
                locations=[loc_str], posted_at=parse_dt(p.get("releasedDate")),
                employment_type=(p.get("typeOfEmployment") or {}).get("label") or "",
                remote=bool(loc.get("remote")),
                seniority_hint=(p.get("experienceLevel") or {}).get("id") or "",
            )
            if ext_id in board.known_ids:
                base.seen_only = True
                out.append(base)
                continue
            d = request(c, "GET", f"{API}/{board.key}/postings/{p['id']}").json()
            sections = ((d.get("jobAd") or {}).get("sections") or {})
            base.description = "\n\n".join(
                html_to_text((sections.get(k) or {}).get("text")) for k in ("jobDescription", "qualifications", "additionalInformation")
            )
            base.url = d.get("postingUrl") or base.url
            out.append(base)
    return out
