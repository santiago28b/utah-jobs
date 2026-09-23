"""Decide whether a job's location is in Salt Lake County or Utah County."""
from __future__ import annotations

import re
from dataclasses import dataclass

SALT_LAKE_COUNTY = [
    "salt lake city", "slc", "west valley city", "west valley", "sandy", "south jordan", "west jordan",
    "draper", "murray", "midvale", "cottonwood heights", "holladay", "millcreek", "taylorsville",
    "herriman", "riverton", "bluffdale", "south salt lake", "kearns", "magna", "salt lake",
]
UTAH_COUNTY = [
    "provo", "orem", "lehi", "american fork", "pleasant grove", "lindon", "vineyard",
    "saratoga springs", "eagle mountain", "springville", "spanish fork", "payson", "highland",
    "alpine", "cedar hills", "mapleton", "santaquin", "utah county", "thanksgiving point",
]
# Cities whose name exists in other states: only count them when Utah is also mentioned.
AMBIGUOUS = {
    "sandy", "murray", "midvale", "holladay", "millcreek", "taylorsville", "riverton", "kearns",
    "magna", "vineyard", "springville", "payson", "highland", "alpine", "mapleton", "slc",
    "west valley", "salt lake",
}

_CITY_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, SALT_LAKE_COUNTY + UTAH_COUNTY), key=len, reverse=True)) + r")\b"
)
_UTAH_RE = re.compile(r"\butah\b|\bUT\b|,\s*ut\b|\bu\.?s\.?-ut\b|united states-utah", re.I)
_REMOTE_RE = re.compile(r"\bremote\b|\banywhere\b|\bwork from home\b|\bwfh\b", re.I)
_NON_US_RE = re.compile(
    r"\b(canada|uk|united kingdom|england|india|mexico|brazil|germany|ireland|poland|philippines|"
    r"europe|emea|apac|latam|australia|japan|singapore|israel|argentina|colombia|costa rica|"
    r"netherlands|france|spain|portugal|romania|ukraine|serbia|london|toronto|bangalore|bengaluru|"
    r"dublin|vancouver|berlin|amsterdam|sydney|tokyo|chile|peru)\b",
    re.I,
)
_SLOPES_RE = re.compile(r"silicon slopes", re.I)


@dataclass
class LocationMatch:
    ok: bool
    remote: bool = False
    label: str = ""  # human friendly, e.g. "Lehi, UT"


def match(locations: list[str], remote_flag: bool = False, allow_remote_us: bool = False) -> LocationMatch:
    """Return whether any of the job's location strings is in SL County / Utah County.

    allow_remote_us: accept fully-remote US roles (used for Utah-based companies' own boards).
    """
    texts = [t for t in (locations or []) if t]
    joined = " | ".join(texts)
    remote = remote_flag or bool(_REMOTE_RE.search(joined))

    for t in texts:
        low = t.lower()
        if _SLOPES_RE.search(t):
            return LocationMatch(True, remote, t)
        for m in _CITY_RE.finditer(low):
            city = m.group(1)
            if city in AMBIGUOUS and not _UTAH_RE.search(t):
                continue
            return LocationMatch(True, remote or bool(_REMOTE_RE.search(t)), _label(t))

    # "Remote - Utah", "Remote Utah", "Utah" (statewide) count too
    for t in texts:
        if _UTAH_RE.search(t) and (_REMOTE_RE.search(t) or t.strip().lower() in ("utah", "ut", "utah, us", "utah, united states")):
            return LocationMatch(True, True, t)

    if allow_remote_us and remote:
        # e.g. "Remote", "Remote - US", "United States (Remote)"; not "Remote - Canada"
        remote_texts = [t for t in texts if _REMOTE_RE.search(t)] or texts or ["Remote"]
        if any(not _NON_US_RE.search(t) for t in remote_texts):
            return LocationMatch(True, True, "Remote (US)")

    return LocationMatch(False, remote, texts[0] if texts else "")


def _label(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()
