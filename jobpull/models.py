from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawJob:
    source: str  # e.g. "greenhouse", "adzuna"
    external_id: str
    company: str
    title: str
    url: str
    locations: list[str] = field(default_factory=list)
    description: str = ""  # plain text
    posted_at: datetime | None = None
    closes_at: datetime | None = None
    employment_type: str = ""  # free text from the source ("Full-time", "Intern", ...)
    remote: bool = False
    # Hint from the source itself (e.g. USAJobs GS grade, SmartRecruiters experienceLevel)
    seniority_hint: str = ""
    # True when the source only confirmed the job still exists (already in DB, details skipped)
    seen_only: bool = False


_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)  # greenhouse double-escapes
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = _WS.sub(" ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
