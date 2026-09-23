"""Daily email with jobs first seen since the last digest.

    python -m jobpull.digest               # send (needs DATABASE_URL, GMAIL_USER, GMAIL_APP_PASSWORD)
    python -m jobpull.digest --preview out.html   # write the email to a file, don't send or mark
"""
from __future__ import annotations

import argparse
import html
import os
import smtplib
import sys
from collections import defaultdict
from datetime import datetime, timezone
from email.message import EmailMessage

from . import db

MAX_JOBS = 150


def fetch_new(conn) -> list[dict]:
    return conn.execute(
        """
        select j.* from jobs j
        left join applications a on a.job_id = j.id
        where j.is_active and j.emailed_at is null
          and coalesce(a.status, 'new') <> 'not_interested'
        order by j.score desc, j.first_seen_at desc
        """
    ).fetchall()


def _ago(dt: datetime | None) -> str:
    if not dt:
        return ""
    days = (datetime.now(timezone.utc) - dt).days
    return "today" if days <= 0 else f"{days}d ago"


def render(jobs: list[dict], dashboard_url: str = "") -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for j in jobs[:MAX_JOBS]:
        groups[j["category"] or "Other"].append(j)
    parts = [
        "<div style='font-family:-apple-system,Segoe UI,Arial,sans-serif;font-size:14px;color:#222;max-width:760px'>",
        f"<h2 style='margin:0 0 4px'>{len(jobs)} new entry-level tech job{'s' if len(jobs) != 1 else ''} in SL / Utah County</h2>",
    ]
    if dashboard_url:
        parts.append(f"<p style='margin:0 0 16px'><a href='{html.escape(dashboard_url)}'>Open dashboard</a></p>")
    for cat in sorted(groups, key=lambda c: -len(groups[c])):
        parts.append(f"<h3 style='margin:18px 0 6px;border-bottom:1px solid #ddd'>{html.escape(cat)} ({len(groups[cat])})</h3>")
        parts.append("<table style='border-collapse:collapse;width:100%'>")
        for j in groups[cat]:
            badge = "#1a7f37" if j["level"] == "strong" else "#9a6700"
            extra = [j["job_type"] if j["job_type"] != "Full-time" else "", "remote" if j["remote"] else "",
                     f"posted {_ago(j['posted_at'])}" if j["posted_at"] else "",
                     f"<b>closes {j['closes_at']:%b %d}</b>" if j["closes_at"] else ""]
            parts.append(
                "<tr><td style='padding:4px 8px 4px 0;vertical-align:top;white-space:nowrap'>"
                f"<span style='color:{badge};font-weight:600'>{j['score']}</span></td>"
                f"<td style='padding:4px 0'><a href='{html.escape(j['url'])}' style='font-weight:600'>{html.escape(j['title'])}</a>"
                f" — {html.escape(j['company'])}<br><span style='color:#666'>{html.escape(j['location'] or '')}"
                f"{' · ' + ' · '.join(e for e in extra if e) if any(extra) else ''}</span></td></tr>"
            )
        parts.append("</table>")
    if len(jobs) > MAX_JOBS:
        parts.append(f"<p>…and {len(jobs) - MAX_JOBS} more on the dashboard.</p>")
    parts.append("</div>")
    return "\n".join(parts)


def send(subject: str, body_html: str, to: str) -> None:
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.set_content("This email is HTML; open it in an HTML-capable client.")
    msg.add_alternative(body_html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(user, pw.replace(" ", ""))
        s.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", help="write HTML to this file instead of sending")
    ap.add_argument("--to", default=os.getenv("DIGEST_TO") or os.getenv("GMAIL_USER"))
    args = ap.parse_args(argv)

    with db.connect() as conn:
        db.init(conn)
        jobs = fetch_new(conn)
        if not jobs:
            print("no new jobs; nothing to send")
            return 0
        body = render(jobs, os.getenv("DASHBOARD_URL", ""))
        if args.preview:
            open(args.preview, "w").write(body)
            print(f"wrote {args.preview} ({len(jobs)} jobs)")
            return 0
        if not args.to:
            raise SystemExit("set DIGEST_TO or GMAIL_USER")
        strong = sum(1 for j in jobs if j["level"] == "strong")
        send(f"{len(jobs)} new Utah tech jobs ({strong} strong entry-level) — {datetime.now():%b %d}", body, args.to)
        conn.execute("update jobs set emailed_at = now() where id = any(%s)", ([j["id"] for j in jobs],))
        conn.commit()
        print(f"sent {len(jobs)} jobs to {args.to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
