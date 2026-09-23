from __future__ import annotations

from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, request


def fetch(board: Board) -> list[RawJob]:
    with client() as c:
        data = request(c, "GET", f"https://api.lever.co/v0/postings/{board.key}", params={"mode": "json"}).json()
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = [cat.get("location") or ""] + list(cat.get("allLocations") or [])
        desc = j.get("descriptionPlain") or html_to_text(j.get("description"))
        for lst in j.get("lists") or []:
            desc += "\n" + (lst.get("text") or "") + "\n" + html_to_text(lst.get("content"))
        desc += "\n" + (j.get("additionalPlain") or "")
        out.append(RawJob(
            source="lever",
            external_id=f"{board.key}:{j['id']}",
            company=board.company,
            title=j.get("text", "").strip(),
            url=j.get("hostedUrl", ""),
            locations=[l for l in dict.fromkeys(locs) if l],
            description=desc.strip(),
            posted_at=parse_dt(j.get("createdAt")),
            employment_type=cat.get("commitment") or "",
            remote=(j.get("workplaceType") == "remote"),
        ))
    return out
