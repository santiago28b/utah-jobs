"""Decide whether a posting is an entry-level tech role, and score it."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters: first match wins.
CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("QA / Test", re.compile(r"\bqa (engineer|analyst|tester|automation|intern)|quality assurance (engineer|analyst|tester|automation|intern)|software tester|\btester\b|\bsdet\b|test (automation|engineer)|software (test|quality)|automation (test|engineer)", re.I)),
    ("Security", re.compile(r"cyber|\bsecurity (engineer|analyst|specialist|developer|operations)|\bsoc\b analyst|\bsoc analyst|penetration|appsec|infosec|information security|detection engineer|vulnerability", re.I)),
    ("Cloud / DevOps", re.compile(r"devops|dev ops|site reliability|\bsre\b|cloud (engineer|developer|operations|ops|support engineer)|platform engineer|infrastructure engineer|devsecops|kubernetes|database administrator|\bdba\b|network engineer|systems? engineer", re.I)),
    ("Data / AI", re.compile(r"\bdata\b|analytics|business intelligence|\bbi\b|machine learning|\bml\b|\bmlops\b|"
                             r"\b(ai|llm|genai|agentic)\b.{0,30}\b(engineer|developer|scientist|research|intern)|"
                             r"\b(engineer|developer|scientist)\b.{0,30}\b(ai|llm|genai)\b|artificial intelligence|"
                             r"\bnlp\b|computer vision|deep learning|data scien|quantitative|statistic|actuar", re.I)),
    ("Solutions / Implementation", re.compile(r"solutions? engineer|forward deployed|implementation (engineer|consultant)|integration engineer|technical consultant|customer engineer", re.I)),
    ("Software", re.compile(r"software|developer|programmer|full[- ]?stack|front[- ]?end|back[- ]?end|\bweb (dev|engineer)|\bios\b|android|mobile (engineer|developer)|\bswe\b|firmware|embedded|application engineer|applications engineer|engineer,? (software|platform|product)|product engineer|game (dev|programmer)|salesforce (developer|admin)|technical (analyst|product)|\bit (analyst|intern)|information technology|computer scien|computer engineer|\bit specialist\b|systems analyst|\brpa\b|automation (developer|engineer)", re.I)),
]

# Roles we never want even if they match a tech keyword.
EXCLUDE_TITLE = re.compile(
    r"\bsales\b|account executive|account manager|business development|\bsdr\b|\bbdr\b|"
    r"recruit|marketing (manager|specialist|coordinator)|help ?desk|desktop support|it support|service desk|"
    r"technical support (specialist|representative|rep)|call center|customer (service|success|support) (rep|representative|specialist|associate)|"
    r"mechanical|civil|structural|chemical|manufacturing|process engineer|hvac|electrical engineer|"
    r"nurse|nursing|physician|pharmac|clinical|medical assistant|dental|therapist|"
    r"data entry|driver|warehouse|technician|machinist|attorney|counsel|paralegal|accountant|"
    r"teacher|instructor|tutor|payroll|\bhr\b|human resources|custspt",
    re.I,
)

SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|lead|leader|principal|manager|mgr|director|head|vp|vice president|"
    r"architect|chief|distinguished|fellow|president|supervisor|expert|specialist lead)\b|"
    r"\b(ii|iii|iv|v|2|3|4|5)\s*$|\b(engineer|developer|analyst|scientist|programmer)\s+(ii|iii|iv|v|2|3|4|5)\b|"
    r"\blevel\s*[2-9]\b|\bl[4-9]\b|\bp[3-9]\b",
    re.I,
)
# "II" is borderline (often 1-3 yrs). Tracked separately so it lowers the score instead of hiding it.
LEVEL_TWO = re.compile(r"\b(ii|2)\s*$|\b(engineer|developer|analyst|scientist|programmer)\s+(ii|2)\b|\blevel\s*2\b", re.I)

ENTRY_TITLE = re.compile(
    r"\bintern(ship)?s?\b|co-?op\b|\bjunior\b|\bjr\.?\b|entry[- ]level|\bentry\b|new grad|graduate|"
    r"\bassociate\b|apprentice|early career|university|campus|\bstudent\b|part[- ]time|"
    r"\b(engineer|developer|analyst|scientist|programmer)\s+(i|1)\b|\blevel\s*1\b|\bi\s*$|resident|fellowship|trainee",
    re.I,
)
INTERN_TITLE = re.compile(r"\bintern(ship)?s?\b|co-?op\b|\bstudent\b|summer 20\d\d", re.I)
PART_TIME = re.compile(r"part[- ]time|\bpt\b|hourly", re.I)

ENTRY_DESC = re.compile(
    r"new grad|recent grad|entry[- ]level|early[- ]career|no (prior )?experience (is )?required|"
    r"0\s*(-|–|to)\s*[12]\s*years?|students?|pursuing a (bachelor|degree|master)|currently enrolled|junior",
    re.I,
)

# "3+ years", "3 - 5 years", "minimum of 4 years", "five years"
_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10}
YEARS_RE = re.compile(
    r"(?:(?:minimum|at least|min\.?)\s+(?:of\s+)?)?"
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|ten)\s*\+?\s*(?:(?:-|–|to)\s*(\d{1,2})\s*\+?\s*)?"
    r"(?:years?|yrs?)\b(?:'|’)?(?:\s+of)?(?:\s+\w+){0,5}?\s+(?:experience|exp\b|work)",
    re.I,
)


@dataclass
class Verdict:
    ok: bool
    category: str = ""
    score: int = 0
    level: str = ""  # "strong" | "possible"
    job_type: str = ""  # "Internship" | "Part-time" | "Full-time"
    min_years: int | None = None
    reason: str = ""


def categorize(title: str) -> str | None:
    if EXCLUDE_TITLE.search(title):
        return None
    for name, rx in CATEGORIES:
        if rx.search(title):
            return name
    # Generic "Engineering Intern" / "Technology Intern"
    if INTERN_TITLE.search(title) and re.search(r"engineer|technology|computer|\bit\b|tech\b", title, re.I):
        return "Software"
    return None


def title_passes(title: str) -> bool:
    """Cheap check used before fetching descriptions (e.g. Workday detail pages)."""
    return categorize(title) is not None and not _is_senior(title)


def _is_senior(title: str) -> bool:
    if not SENIOR_TITLE.search(title):
        return False
    # "Senior" in e.g. "Associate Engineer - Senior Living" is rare; II/2 handled by score instead.
    stripped = LEVEL_TWO.sub("", title)
    return bool(SENIOR_TITLE.search(stripped))


def min_years_required(text: str) -> int | None:
    found = []
    for m in YEARS_RE.finditer(text or ""):
        a = m.group(1).lower()
        n = _WORDNUM.get(a) if a in _WORDNUM else int(a)
        if n is not None and n <= 20:
            found.append(n)
    return min(found) if found else None


def job_type(title: str, employment_type: str) -> str:
    blob = f"{title} {employment_type}"
    if INTERN_TITLE.search(blob) or re.search(r"\bintern", employment_type, re.I):
        return "Internship"
    if PART_TIME.search(blob):
        return "Part-time"
    return "Full-time"


def evaluate(title: str, description: str = "", employment_type: str = "", seniority_hint: str = "") -> Verdict:
    cat = categorize(title)
    if not cat:
        return Verdict(False, reason="not a tech title")
    if _is_senior(title):
        return Verdict(False, category=cat, reason="senior title")

    jt = job_type(title, employment_type)
    strong_title = bool(ENTRY_TITLE.search(title)) or jt != "Full-time"
    years = min_years_required(description)
    hint = seniority_hint.lower()

    if hint in ("senior", "mid_senior_level", "director", "executive") and not strong_title:
        return Verdict(False, category=cat, reason=f"source says {hint}")
    if years is not None and years >= 3 and not strong_title:
        return Verdict(False, category=cat, min_years=years, reason=f"{years}+ years required")

    score = 50
    if strong_title:
        score += 30
    if jt == "Internship":
        score += 10
    if hint in ("entry", "entry_level", "internship", "student"):
        score += 30
    if years is not None:
        score += {0: 15, 1: 15, 2: 5}.get(years, -15)
    if ENTRY_DESC.search(description or ""):
        score += 10
    if LEVEL_TWO.search(title):
        score -= 20
    score = max(0, min(100, score))
    level = "strong" if score >= 75 else "possible"
    return Verdict(True, cat, score, level, jt, years)
