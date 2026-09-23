"""USAJobs search API. Free key: https://developer.usajobs.gov/apirequest/"""
from __future__ import annotations

import os

from ..models import RawJob
from . import Board, client, parse_dt, request, log

# OPM occupational series: IT mgmt, computer science, computer engineering, data science,
# operations research, mathematical statistics, electronics engineering (often software), telecom
SERIES = "2210;1550;0854;1560;1515;1529;0391"


def fetch(board: Board) -> list[RawJob]:
    key, email = os.getenv("USAJOBS_API_KEY"), os.getenv("USAJOBS_EMAIL")
    if not (key and email):
        log.info("usajobs: USAJOBS_API_KEY/USAJOBS_EMAIL not set, skipping")
        return []
    headers = {"Host": "data.usajobs.gov", "User-Agent": email, "Authorization-Key": key}
    out: dict[str, RawJob] = {}
    with client() as c:
        for loc in ("Salt Lake City, Utah", "Provo, Utah"):
            data = request(c, "GET", "https://data.usajobs.gov/api/search", headers=headers, params={
                "LocationName": loc, "Radius": 30, "JobCategoryCode": SERIES, "ResultsPerPage": 250,
            }).json()
            for item in (data.get("SearchResult") or {}).get("SearchResultItems", []):
                d = item.get("MatchedObjectDescriptor") or {}
                details = (d.get("UserArea") or {}).get("Details") or {}
                grade = str(details.get("LowGrade") or "")
                hint = "entry" if grade.isdigit() and int(grade) <= 9 else ("senior" if grade.isdigit() and int(grade) >= 12 else "")
                sched = ", ".join(s.get("Name", "") for s in d.get("PositionSchedule") or [])
                hiring = " ".join(details.get("HiringPath") or [])
                if "student" in hiring or "graduates" in hiring:
                    hint = "entry"
                ext = d.get("PositionID") or item.get("MatchedObjectId")
                out[ext] = RawJob(
                    source="usajobs",
                    external_id=str(ext),
                    company=d.get("OrganizationName") or d.get("DepartmentName") or "US Government",
                    title=(d.get("PositionTitle") or "").strip(),
                    url=d.get("PositionURI", ""),
                    locations=[l.get("LocationName", "") for l in d.get("PositionLocation") or []],
                    description="\n".join([d.get("QualificationSummary") or "", details.get("JobSummary") or ""]),
                    posted_at=parse_dt(d.get("PublicationStartDate")),
                    closes_at=parse_dt(d.get("ApplicationCloseDate")),
                    employment_type=sched + (f" · GS-{grade}" if grade else ""),
                    seniority_hint=hint,
                )
    return list(out.values())
