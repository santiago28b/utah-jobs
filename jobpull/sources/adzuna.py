"""Adzuna job search API (aggregates many job boards). Free key: https://developer.adzuna.com

Free tier is roughly 250 requests/day, so collect.py only runs this every couple of hours.
"""
from __future__ import annotations

import os

from ..models import RawJob, html_to_text
from . import Board, client, parse_dt, request, log

URL = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"

# Each entry is one request per center (what_or = any of these words).
QUERIES = [
    "software developer programmer",
    "data analyst analytics scientist",
    "intern internship",
    "junior entry associate graduate",
    "devops cloud security cybersecurity qa",
    "engineer machine learning ai",
]
CENTERS = ["Salt Lake City, Utah", "Provo, Utah"]


def fetch(board: Board) -> list[RawJob]:
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        log.info("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not set, skipping")
        return []
    out: dict[str, RawJob] = {}
    with client() as c:
        for where in CENTERS:
            for what_or in QUERIES:
                data = request(c, "GET", URL.format(page=1), params={
                    "app_id": app_id, "app_key": app_key, "where": where, "distance": 35,  # km
                    "what_or": what_or, "max_days_old": 7, "sort_by": "date", "results_per_page": 50,
                }).json()
                for j in data.get("results", []):
                    loc = j.get("location") or {}
                    area = ", ".join(reversed(loc.get("area") or []))  # "Lehi, Utah County, Utah, US"
                    ext = str(j["id"])
                    ctype = j.get("contract_time") or ""
                    out[ext] = RawJob(
                        source="adzuna",
                        external_id=ext,
                        company=(j.get("company") or {}).get("display_name") or "Unknown",
                        title=html_to_text(j.get("title")),
                        url=j.get("redirect_url", ""),
                        locations=[x for x in (loc.get("display_name"), area) if x],
                        description=html_to_text(j.get("description")),
                        posted_at=parse_dt(j.get("created")),
                        employment_type=ctype.replace("_", "-"),
                    )
    return list(out.values())
