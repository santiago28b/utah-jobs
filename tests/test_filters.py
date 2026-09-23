import pytest

from jobpull import filters, locations
from jobpull.db import dedupe_key


@pytest.mark.parametrize("title,category", [
    ("Back-End Software Engineer Intern", "Software"),
    ("Software Engineer Intern 2027", "Software"),
    ("Jr DevOps Engineer- Interoperability", "Cloud / DevOps"),
    ("Data Engineer Intern", "Data / AI"),
    ("Data Analyst", "Data / AI"),
    ("Associate Data Scientist", "Data / AI"),
    ("AI Engineer", "Data / AI"),
    ("Agentic AI Engineer, Salt Lake City", "Data / AI"),
    ("Machine Learning Engineer I", "Data / AI"),
    ("Software Test Engineer Intern", "QA / Test"),
    ("QA Analyst - LOIS for Word", "QA / Test"),
    ("SDET", "QA / Test"),
    ("Cybersecurity Analyst", "Security"),
    ("Site Reliability Engineer", "Cloud / DevOps"),
    ("Cloud Engineer - Associate", "Cloud / DevOps"),
    ("Solutions Engineer", "Solutions / Implementation"),
    ("Legal Solutions Engineer", "Solutions / Implementation"),
    ("Forward Deployed Engineer", "Solutions / Implementation"),
    ("Frontend Developer", "Software"),
    ("Full Stack Web Developer (Part-Time)", "Software"),
    ("iOS Engineer", "Software"),
    ("Engineering Intern - Summer 2027", "Software"),
    ("Business Intelligence Developer", "Data / AI"),
])
def test_tech_titles_are_categorized(title, category):
    assert filters.categorize(title) == category


@pytest.mark.parametrize("title", [
    "Account Executive",
    "Sales Engineer",
    "Sales Development Representative",
    "Strategic Inbound Account Executive",
    "Mechanical Engineer",
    "Manufacturing Engineer I",
    "Registered Nurse",
    "IT Help Desk Technician",
    "Desktop Support Specialist",
    "Technical Recruiter",
    "Customer Success Manager",
    "Creative Designer",
    "AI Onboarding Specialist - Automotive",
    "Customer Implementation Specialist, Multi Location",
    "Legal Counsel",
    "Data Entry Clerk",
    "Quality Assurance Specialist, FIU",
])
def test_non_target_titles_rejected(title):
    assert filters.categorize(title) is None


@pytest.mark.parametrize("title", [
    "Senior Software Engineer",
    "Sr. Data Analyst",
    "Staff Machine Learning Engineer",
    "Principal Engineer, Platform",
    "Engineering Manager",
    "Lead Data Scientist",
    "Software Engineer III",
    "Data Engineer 3",
    "Director, Software Development",
    "Solutions Architect",
    "Head of Data",
])
def test_senior_titles_rejected(title):
    v = filters.evaluate(title)
    assert not v.ok


@pytest.mark.parametrize("title", [
    "Software Engineer Intern",
    "Junior Software Developer",
    "Associate Software Engineer",
    "Software Engineer I",
    "Data Analyst - New Grad 2027",
    "Entry Level Developer",
])
def test_entry_titles_are_strong(title):
    v = filters.evaluate(title, "We're hiring!")
    assert v.ok and v.level == "strong", v


def test_software_engineer_ii_kept_but_lower():
    v1 = filters.evaluate("Software Engineer", "")
    v2 = filters.evaluate("Software Engineer II", "")
    assert v2.ok and v2.score < v1.score


@pytest.mark.parametrize("desc,expected", [
    ("Requires 3+ years of professional experience building APIs.", 3),
    ("3-5 years of experience in data analysis", 3),
    ("Minimum of five years related work experience", 5),
    ("1+ years of software development experience, or a relevant internship", 1),
    ("0-2 years experience", 0),
    ("Bachelor's in CS, 5+ years of experience; or Master's with 2 years experience", 2),
    ("Founded 15 years ago, we're a great team.", None),
    ("No experience needed; we train you.", None),
])
def test_min_years(desc, expected):
    assert filters.min_years_required(desc) == expected


def test_years_requirement_filters_plain_titles():
    assert not filters.evaluate("Software Engineer", "5+ years of experience with Go").ok
    assert filters.evaluate("Software Engineer", "1-2 years of experience with Go").ok
    # an internship that mentions "3+ years of college coursework experience" stays in
    assert filters.evaluate("Software Engineer Intern", "3+ years of college experience").ok


def test_source_seniority_hint():
    assert not filters.evaluate("Software QA Engineer", "", seniority_hint="mid_senior_level").ok
    assert filters.evaluate("IT Specialist (APPSW)", "", seniority_hint="entry").ok
    assert filters.categorize("IT Specialist (CUSTSPT)") is None
    v = filters.evaluate("Data Analyst", "", seniority_hint="entry_level")
    assert v.ok and v.level == "strong"


@pytest.mark.parametrize("title,etype,expected", [
    ("Software Engineer Intern", "", "Internship"),
    ("Software Engineer", "Intern", "Internship"),
    ("Web Developer", "Part-time", "Part-time"),
    ("Data Analyst", "Full-time", "Full-time"),
])
def test_job_type(title, etype, expected):
    assert filters.job_type(title, etype) == expected


# ---- locations ----

@pytest.mark.parametrize("locs", [
    ["Lindon, Utah"],
    ["Lehi, UT"],
    ["Weave - Headquarters (Lehi, UT)"],
    ["USA - Salt Lake City, UT"],
    ["Salt Lake City"],
    ["Provo, Utah, United States"],
    ["Sandy, UT"],
    ["United States-Utah-Salt Lake City"],
    ["Draper, UT", "Remote"],
    ["Remote Utah"],
    ["Utah"],
    ["Silicon Slopes"],
    ["South Jordan, UT, US"],
    ["American Fork"],
])
def test_locations_in_area(locs):
    assert locations.match(locs).ok


@pytest.mark.parametrize("locs", [
    ["Sandy, OR"],
    ["Murray, KY"],
    ["Logan, UT"],
    ["United States-Utah-Roy"],
    ["Ogden, Utah"],
    ["St. George, UT"],
    ["San Francisco, CA"],
    ["Remote"],
    ["Remote - US"],
    ["Pune, India"],
    ["Budge Clinic"],
])
def test_locations_outside_area(locs):
    assert not locations.match(locs).ok


def test_remote_us_only_when_allowed():
    assert locations.match(["Remote; United States"], allow_remote_us=True).ok
    assert locations.match(["Remote"], allow_remote_us=True).ok
    assert not locations.match(["Remote - Canada"], allow_remote_us=True).ok
    assert not locations.match(["Remote, Brazil", "São Paulo, Brazil"], allow_remote_us=True).ok
    assert not locations.match(["Seattle, Washington"], allow_remote_us=True).ok
    m = locations.match(["Remote Utah"])
    assert m.ok and m.remote


def test_dedupe_key_normalizes_company():
    assert dedupe_key("Adobe Inc.", "Data Scientist", "Lehi, UT") == dedupe_key("Adobe", "Data  Scientist", "Lehi")
