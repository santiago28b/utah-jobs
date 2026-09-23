# Utah entry-level tech job tracker

Every 30 minutes this tracker pulls entry-level tech jobs in **Salt Lake County and Utah County**: software, data/AI, security, cloud/DevOps, QA and solutions engineering, including internships and part-time roles. It stores them in Postgres, shows them in a dashboard where you track your applications, and emails you a digest every morning.

```
GitHub Actions (every 30 min) ─> python -m jobpull.collect ─> Supabase Postgres <─> Streamlit dashboard
GitHub Actions (7am MT daily) ─> python -m jobpull.digest  ─> Gmail ─> your inbox
```

**Sources**

| Source | What | Needs |
|---|---|---|
| Company boards (`companies.yaml`) | ~35 Utah employers' Greenhouse / Lever / Ashby / SmartRecruiters / Workday boards. Often earlier than job sites. | nothing |
| Adzuna | Aggregator covering many job boards (the widest net) | free API key |
| USAJobs | Federal IT / data / CS roles, with real closing dates | free API key |

Everything runs on free tiers. Adzuna and USAJobs skip themselves until their keys are set.

## Setup (about 20 minutes, one time)

### 1. Database: Supabase
1. Create a free project at <https://supabase.com>. Save the database password.
2. Click **Connect** (top of the project page) and copy the **Transaction pooler** URI (port `6543`). Replace `[YOUR-PASSWORD]` in it.
   That URI is your `DATABASE_URL`. The tables are created automatically on the first run.

The 30-minute collector keeps the free project active, so Supabase won't pause it for inactivity.

### 2. API keys (optional but recommended)
- **Adzuna**: sign up at <https://developer.adzuna.com/signup> to get an `app_id` and `app_key`. The free tier allows about 250 calls/day, so the collector runs Adzuna only every ~2 hours (about 12 calls each time).
- **USAJobs**: request a key at <https://developer.usajobs.gov/apirequest/>. It arrives by email and uses the email you signed up with.

### 3. Gmail for the digest
1. Turn on 2-Step Verification for your Google account.
2. Create an app password at <https://myaccount.google.com/apppasswords>. It's 16 characters.

### 4. GitHub
1. Create a **public** repo (Actions minutes are unlimited on public repos; your secrets stay private) and push this folder:
   ```
   git add -A && git commit -m "Utah job tracker"
   git remote add origin git@github.com:<you>/utah-jobs.git && git push -u origin main
   ```
2. Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Secret | Value |
   |---|---|
   | `DATABASE_URL` | Supabase pooler URI |
   | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | from Adzuna |
   | `USAJOBS_API_KEY` | from USAJobs |
   | `USAJOBS_EMAIL` | email you registered with USAJobs |
   | `GMAIL_USER` | your gmail address |
   | `GMAIL_APP_PASSWORD` | the app password |
   | `DIGEST_TO` | where to send the digest (defaults to `GMAIL_USER`) |

   Optional: under the **Variables** tab, add `DASHBOARD_URL` (from step 5) so the email links to the dashboard.
3. Go to **Actions → collect → Run workflow** to do the first pull right away. After that it runs every 30 minutes.

### 5. Dashboard: Streamlit Community Cloud
1. At <https://share.streamlit.io>, click **Create app** and pick the repo. Main file: `app.py`.
2. Under **Advanced settings → Secrets**, paste:
   ```toml
   DATABASE_URL = "postgresql://postgres.xxxx:PASSWORD@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
   ```
3. After it deploys, go to **Settings → Sharing** and make the app **private** (only your email), since it can edit your tracker.

## Using it

- **Open jobs**: newest first. 🆕 marks jobs first seen in the last 24h. **Fit** is the entry-level score: *strong* (≥75) means the title or source says intern/junior/new grad/entry, or the posting asks for ≤1 year. *Possible* means nothing disqualifying was found. Set **Status** and **Notes** right in the table; they save immediately.
- **My applications**: everything you've marked, grouped by status. It still shows postings that have since closed.
- **Job details**: the full description for any job.
- **Sources**: the last run of every board. Use it to spot a board that broke.

**Posted** is the date the company reports. **First seen** is when this tracker found the job. The **Closes** column is filled only when the source gives a deadline (USAJobs, some Greenhouse/Workday postings). Jobs that vanish from a company's board for two runs in a row are marked closed.

## Local use

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
pytest -q                                   # filter/location tests
python -m jobpull.collect --dry-run         # no DB: print what would be saved
python -m jobpull.collect --dry-run --show-rejected --only workday   # debug why jobs were dropped

export DATABASE_URL=...                     # Supabase URI, or any local Postgres
python -m jobpull.collect                   # real run
python -m jobpull.digest --preview digest.html   # render the email without sending
streamlit run app.py
```

## Tuning

- **Add a company**: add one line to `companies.yaml`. The file's comments show how to find the board token from a careers page link. Use `allow_remote_us: true` only for Utah-headquartered companies.
- **Which roles count as tech**: the regexes in `jobpull/filters.py` (`CATEGORIES`, `EXCLUDE_TITLE`, `SENIOR_TITLE`). A posting is dropped when its title is senior or its description's minimum years of experience is 3 or more, unless the title clearly says intern/junior/entry.
- **Which cities count**: `jobpull/locations.py`.
- After editing the filters, run `pytest` and `python -m jobpull.collect --dry-run --show-rejected`.
