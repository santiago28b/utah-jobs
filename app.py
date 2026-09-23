"""Dashboard: streamlit run app.py  (needs DATABASE_URL in env or .streamlit/secrets.toml)"""
from __future__ import annotations


import pandas as pd
import streamlit as st

from jobpull import db

st.set_page_config(page_title="Utah Tech Jobs", page_icon="💼", layout="wide")

TZ = "America/Denver"
STATUS_LABELS = {
    "new": "—", "interested": "⭐ interested", "applied": "✅ applied", "interviewing": "🗣 interviewing",
    "offer": "🎉 offer", "rejected": "✖ rejected", "not_interested": "🚫 not interested",
}
LABEL_TO_STATUS = {v: k for k, v in STATUS_LABELS.items()}


def _db_url() -> str:
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return db.database_url()


def query(sql: str, params=None) -> list[dict]:
    with db.connect(_db_url()) as conn:
        return conn.execute(sql, params).fetchall()


@st.cache_resource
def _init_schema() -> bool:
    with db.connect(_db_url()) as conn:
        db.init(conn)
    return True


def save_status(changes: dict[int, dict]) -> None:
    with db.connect(_db_url()) as conn:
        for job_id, ch in changes.items():
            conn.execute(
                """
                insert into applications (job_id, status, notes, applied_at, updated_at)
                values (%(id)s, %(status)s, %(notes)s, case when %(status)s = 'applied' then now() end, now())
                on conflict (job_id) do update set
                    status = excluded.status, notes = excluded.notes, updated_at = now(),
                    applied_at = case when excluded.status = 'applied' and applications.applied_at is null
                                      then now() else applications.applied_at end
                """,
                {"id": job_id, **ch},
            )
        conn.commit()


def load_jobs(active_only: bool = True) -> pd.DataFrame:
    rows = query(
        f"""
        select j.id, j.score, j.level, j.title, j.company, j.location, j.remote, j.category, j.job_type,
               j.posted_at, j.first_seen_at, j.closes_at, j.url, j.source, j.min_years, j.is_active,
               coalesce(a.status, 'new') as status, coalesce(a.notes, '') as notes, a.applied_at
        from jobs j left join applications a on a.job_id = j.id
        {"where j.is_active" if active_only else ""}
        order by j.first_seen_at desc, j.score desc
        """
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for c in ("posted_at", "first_seen_at", "closes_at", "applied_at"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.tz_convert(TZ)
    now = pd.Timestamp.now(tz=TZ)
    df["new"] = (now - df["first_seen_at"]) < pd.Timedelta(hours=24)
    df["age"] = df["posted_at"].apply(lambda d: "" if pd.isna(d) else _ago(now - d))
    df["seen"] = df["first_seen_at"].apply(lambda d: _ago(now - d))
    df["closes"] = df["closes_at"].apply(lambda d: "" if pd.isna(d) else f"{d:%b %d} ({max((d - now).days, 0)}d)")
    df["status_label"] = df["status"].map(STATUS_LABELS)
    return df


def _ago(td: pd.Timedelta) -> str:
    s = td.total_seconds()
    if s < 3600:
        return f"{max(int(s // 60), 0)}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    return f"{int(s // 86400)}d ago"


def editable_table(df: pd.DataFrame, key: str) -> None:
    view = df[["id", "new", "score", "title", "company", "location", "category", "job_type", "age", "seen",
               "closes", "url", "status_label", "notes"]].copy()
    view["new"] = view["new"].map({True: "🆕", False: ""})
    edited = st.data_editor(
        view,
        key=key,
        hide_index=True,
        width="stretch",
        height=min(38 * len(view) + 40, 900),
        disabled=[c for c in view.columns if c not in ("status_label", "notes")],
        column_order=["new", "score", "title", "company", "location", "category", "job_type", "age", "seen",
                      "closes", "url", "status_label", "notes"],
        column_config={
            "new": st.column_config.TextColumn("", width=30),
            "score": st.column_config.ProgressColumn("Fit", min_value=0, max_value=100, format="%d", width="small"),
            "title": st.column_config.TextColumn("Title", width="large"),
            "job_type": "Type",
            "category": "Category",
            "age": "Posted",
            "seen": st.column_config.TextColumn("First seen", help="When this tracker first found it"),
            "closes": "Closes",
            "url": st.column_config.LinkColumn("Link", display_text="Open ↗", width="small"),
            "status_label": st.column_config.SelectboxColumn("Status", options=list(STATUS_LABELS.values()), required=True),
            "notes": st.column_config.TextColumn("Notes", width="medium"),
        },
    )
    before = view.set_index("id")[["status_label", "notes"]]
    after = edited.set_index("id")[["status_label", "notes"]]
    diff = (before != after).any(axis=1)
    if diff.any():
        changes = {
            int(i): {"status": LABEL_TO_STATUS.get(after.at[i, "status_label"], "new"), "notes": after.at[i, "notes"] or ""}
            for i in after.index[diff]
        }
        save_status(changes)
        # Drop the editor's pending edits so they can't re-apply to other rows after filters change.
        st.session_state.pop(key, None)
        st.toast(f"Saved {len(changes)} change(s)")
        st.rerun()


# ---------------------------------------------------------------- UI
_init_schema()
st.title("💼 Entry-level tech jobs · Salt Lake & Utah County")

df_all = load_jobs(active_only=False)
if df_all.empty:
    st.info("No jobs yet. Run `python -m jobpull.collect` (or wait for the GitHub Action).")
    st.stop()
df = df_all[df_all["is_active"]]

with st.sidebar:
    st.header("Filters")
    q = st.text_input("Search title / company")
    window = st.radio("First seen", ["Any time", "24 hours", "3 days", "7 days"], horizontal=True)
    cats = st.multiselect("Category", sorted(df["category"].dropna().unique()))
    types = st.multiselect("Type", ["Full-time", "Internship", "Part-time"])
    strong_only = st.toggle("Strong entry-level only", False)
    include_remote = st.toggle("Include remote roles", True, help="Remote roles at Utah companies, or 'Remote - Utah'")
    hide_done = st.toggle("Hide rejected / not interested", True)
    companies = st.multiselect("Company", sorted(df["company"].unique()))

f = df
if q:
    f = f[f["title"].str.contains(q, case=False, regex=False) | f["company"].str.contains(q, case=False, regex=False)]
if window != "Any time":
    hours = {"24 hours": 24, "3 days": 72, "7 days": 168}[window]
    f = f[f["first_seen_at"] > pd.Timestamp.now(tz=TZ) - pd.Timedelta(hours=hours)]
if cats:
    f = f[f["category"].isin(cats)]
if types:
    f = f[f["job_type"].isin(types)]
if strong_only:
    f = f[f["level"] == "strong"]
if not include_remote:
    f = f[~f["remote"]]
if hide_done:
    f = f[~f["status"].isin(["rejected", "not_interested"])]
if companies:
    f = f[f["company"].isin(companies)]

tab_jobs, tab_apps, tab_detail, tab_sources = st.tabs(["Open jobs", "My applications", "Job details", "Sources"])

with tab_jobs:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("New (24h)", int(df["new"].sum()))
    c2.metric("Strong entry-level", int((df["level"] == "strong").sum()))
    c3.metric("Open jobs tracked", len(df))
    c4.metric("Applied", int(df_all["status"].isin(["applied", "interviewing", "offer"]).sum()))
    st.caption(f"Showing {len(f)} jobs · edit **Status** / **Notes** right in the table; changes save automatically.")
    editable_table(f, "jobs_table")

with tab_apps:
    apps = df_all[df_all["status"] != "new"]
    if apps.empty:
        st.info("Mark a job as interested/applied in the Open jobs tab and it shows up here.")
    else:
        counts = apps["status"].value_counts()
        cols = st.columns(len(STATUS_LABELS) - 1)
        for col, s in zip(cols, [s for s in STATUS_LABELS if s != "new"]):
            col.metric(STATUS_LABELS[s], int(counts.get(s, 0)))
        order = {s: i for i, s in enumerate(STATUS_LABELS)}
        apps = apps.sort_values(by=["status", "first_seen_at"], key=lambda c: c.map(order) if c.name == "status" else c)
        closed = ~apps["is_active"]
        if closed.any():
            st.caption(f"{int(closed.sum())} of these postings are no longer listed.")
        editable_table(apps, "apps_table")

with tab_detail:
    options = {f"{r.title} — {r.company} ({r.location})": r.id for r in f.itertuples()}
    pick = st.selectbox("Job", list(options), index=None, placeholder="Pick a job to read the description")
    if pick:
        jid = options[pick]
        j = query("select * from jobs where id = %s", (jid,))[0]
        st.subheader(j["title"])
        st.write(f"**{j['company']}** · {j['location']} · {j['job_type']} · {j['category']} · fit {j['score']} ({j['level']})"
                 + (f" · asks for {j['min_years']}+ yrs" if j["min_years"] is not None else ""))
        st.link_button("Open posting ↗", j["url"])
        st.text(j["description"] or "(no description)")

with tab_sources:
    runs = query(
        """
        select distinct on (source, board) source, board, started_at, ok, fetched, matched, new_jobs, error
        from source_runs order by source, board, started_at desc
        """
    )
    if runs:
        r = pd.DataFrame(runs)
        r["started_at"] = pd.to_datetime(r["started_at"], utc=True).dt.tz_convert(TZ).dt.strftime("%b %d %H:%M")
        st.caption("Last run per board. `fetched` = postings read, `matched` = entry-level tech jobs in the area.")
        st.dataframe(r, hide_index=True, width="stretch")
    by_source = df.groupby(["source"]).size().rename("open jobs")
    st.dataframe(by_source, width="stretch")
