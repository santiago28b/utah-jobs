from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

log = logging.getLogger("jobpull")

USER_AGENT = "utah-jobs-tracker/1.0 (personal job search tool)"


def client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def request(c: httpx.Client, method: str, url: str, tries: int = 3, **kw) -> httpx.Response:
    for attempt in range(tries):
        try:
            r = c.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except (httpx.TransportError,) as e:
            if attempt == tries - 1:
                raise
            log.debug("retrying %s after %s", url, e)
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


@dataclass
class Board:
    """One job listing to pull: a company's ATS board, or an aggregator query."""
    source: str
    key: str  # unique per source, e.g. greenhouse board token
    company: str
    options: dict = field(default_factory=dict)
    # A full listing (company boards) lets us mark missing jobs as closed; search results can't.
    complete_listing: bool = True
    known_ids: set[str] = field(default_factory=set)


def parse_dt(s) -> datetime | None:
    if s in (None, "", 0):
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s / 1000 if s > 1e11 else s, tz=timezone.utc)
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_relative(s: str | None) -> datetime | None:
    """Workday style: 'Posted Today', 'Posted Yesterday', 'Posted 3 Days Ago', 'Posted 30+ Days Ago'."""
    if not s:
        return None
    now = datetime.now(timezone.utc)
    low = s.lower()
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*day", low)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None
