# AI Developer Context & Memory

> Read this file first. It tells you exactly what exists, why it is built that way,
> and what to build next. Everything below is verified working, not aspirational.

## Project Overview

"Autonomous AI-Powered Smart Dashboard" — a SaaS product that behaves like Power BI
but reads and explains the data instead of only plotting it.

**Stack:** Python 3.13, Streamlit, Pandas, Plotly, Google Gemini API.
**Virtualenv:** `venv/` in the project root (`venv/Scripts/python.exe` on Windows).

### It is live — treat it as production

| | |
|---|---|
| **URL** | https://autolyst.online (HTTPS, auto-renewing Let's Encrypt cert) |
| **Host** | AWS EC2 `t3.micro`, Ubuntu 24.04, `ap-south-1` |
| **Instance** | `i-0de3279fe8e742bcc` — named `smart-dashboard` |
| **Elastic IP** | `3.7.191.122` |
| **Service** | `systemd` unit `dashboard`, Nginx in front on :80/:443 |
| **Deploy** | `cd ~/Smart-Dashboard && git pull && sudo systemctl restart dashboard` |
| **Email** | Brevo API, sender `noreply@autolyst.online` (domain authenticated) |

> A second EC2 instance, `admetics` (`i-086da987a1253e557`, Elastic IP
> `15.252.150.220`), belongs to a different project. **Never touch it.**
> `deploy/aws-setup.sh` refuses to run where another Nginx site already exists.

Real people can sign up. Anything merged to `main` and pulled is live.

---

## Repo Map — what lives where

| File | Responsibility |
|---|---|
| `app.py` | Orchestrator only: data-source panels, cleaning report, workspace/tabs, manual dashboard, AI deep-dive + chat. |
| `auth.py` | Signup, email OTP verification, login, and the Streamlit gate in front of everything. |
| `data_cleaner.py` | Turns an unmanaged sheet into a usable table, and reports every change it made. |
| `data_table.py` | The raw rows: filters, a pivot builder, a fixed-size scrollable grid, CSV export. |
| `theme.py` | The whole visual system - design tokens, Streamlit component CSS, Plotly template. |
| `sample_data.py` | Deterministic demo workbook so the product can be seen without uploading. |
| `report_export.py` | Renders the reports to PDF via Kaleido + fpdf2. Built from the same code as the page. |
| `google_sheets.py` | Google Sheets connector. Public sheets via XLSX export, private sheets via service account. Raises `SheetAccessError(msg, hint)`. |
| `geo_maps.py` | All map rendering. Detects what a location column *is*, then draws the right map. |
| `geo_assets.py` | India boundary data + name resolution (states, districts, country codes, centroids). |
| `auto_analyst.py` | Profiles the data, decides which dashboards to build, builds them. |
| `assets/india_districts.geojson` | 4 MB district-level India boundaries. **Includes Jammu & Kashmir and Ladakh.** |
| `deploy/aws-setup.sh` | One-command provision of a fresh Ubuntu box. Refuses to run where a site exists. |
| `deploy/add-domain.sh` | Points Nginx at a domain and obtains the HTTPS certificate. Checks DNS first. |
| `tests/` | Eight suites plus `run_all.py`. No framework — plain scripts that stub Streamlit. |

**Import direction:** `app.py` → `auto_analyst` → `geo_maps` → `geo_assets`.
Never import backwards; `geo_assets` must stay Streamlit-free.

---

## What Is Built (all verified)

### 1. Data sources
- Multi-sheet Excel & CSV upload with per-sheet dashboards + master concatenation.
- Auto header detection and cleaning (`auto_fix_headers` in `app.py`) — unchanged, do not touch.
- **Google Sheets Live Sync**: paste a link, hit Sync. Public sheets need nothing;
  private sheets use a service account JSON (uploaded in the UI, or
  `[gcp_service_account]` in `.streamlit/secrets.toml`). Cached 5 min, refresh
  token busts the cache. Every failure has a friendly `hint`.

### 1a. Accounts (`auth.py`)
One account per email. Sign up with name, email and password, confirm a six-digit
code emailed through **Brevo**, then log in with email and password from then on.
`require_login()` renders the gate and `st.stop()`s, so nothing else in `app.py`
runs for a signed-out visitor.

Storage is SQLite at `data/users.db` (gitignored - it holds real emails and
password hashes). Passwords are PBKDF2-HMAC-SHA256, 600k iterations, per-user
salt. **PBKDF2 is deliberate**: it ships with Python, so there is no compiled
dependency that can fail to build on a small server.

Abuse guards: OTP expires in 10 minutes, dies after 5 wrong attempts, 60-second
resend cooldown; login locks for 15 minutes after 5 failures; wrong password and
unknown email return the *same* message so the form cannot be used to discover
which addresses are registered.

### 1b. Cleaning (`data_cleaner.py`)
Runs after `auto_fix_headers`, before anything is charted. Only rows that carry
data survive — a 1,000-row sheet with 100 real records is charted as 100 records.

Two row rules, both switchable from the sidebar:
* **Key column** (`require_key_column`, default on) — the first column is the key
  (Order ID, Invoice No). Blank key, not a record. Auto-skipped when that column
  is itself under 50% filled, since it is then a notes column.
* **Nearly-empty rows** (`drop_sparse_rows`, default on) — drops rows under 25%
  filled, *and* rows whose only value is the key. That second check is exact
  rather than percentage-based, so it behaves the same on a 4-column sheet and a
  40-column one.

Both rules back off if they would remove more than half the remaining rows.
It trims stray spaces, treats `N/A` / `-` / `NULL` as blank, drops empty columns,
blank rows, lone `END`/`Total` footer rows, and rows too sparse to be a record.
Duplicates are reported, never deleted silently. `render_cleaning_panel` in
`app.py` shows the user exactly what happened.

### 2. Geographical engine (`geo_maps.py`)
Detects a location column as one of: `country`, `india-states`, `india-districts`,
`usa-states`, or `None`. Column-name hints win first, then value matching.

- **Region Map** — filled choropleth.
- **Pin Map (Blinking)** — pulsing markers, hover values, scroll zoom. Coordinates
  come from Lat/Long columns if present, otherwise from bundled India centroids,
  so **city names alone are enough**.
- **Treemap Drill-Down** — the original view, preserved behind a toggle.

### 3. Auto Analyst (`auto_analyst.py`)
Profiles each column into a role (`measure`, `category`, `date`, `geo`, `flag`,
`identifier`) and builds only the scenarios the data can support:
Executive Summary · Trends · Rankings & 80/20 · Distribution & Outliers ·
Relationships · Cross-Tab Heatmap · Geography · Data Quality.
Each tab shows a "why this view" line. AI briefing sends **stats only, never raw rows**.

### 4. Data Table (`data_table.py`)
Per sheet: a search box matching every column, per-column filters that pick their
control from the column type (range slider / date range / checklist), a column
chooser, and a **pivot** checkbox with row and column totals. The grid is a fixed
height that scrolls inside itself — a 400-row sheet rendered in full pushes the
filters off screen. Whatever is on screen exports as CSV.

### 5. Look and feel (`theme.py`)
Design system from the `ui-ux-pro-max` skill: Data-Dense Dashboard style, blue and
amber palette adjusted for WCAG, Fira Sans with Fira Code for figures, dashboard
density, standard motion tier. See details 13 and 15 for why it is all CSS and how
it broke twice.

### 6. Sample data (`sample_data.py`)
A deterministic year of Indian sales orders behind **Try it with sample data**, so
a visitor with no spreadsheet can see the whole product. Shaped to exercise
everything: measures, dimensions, a timeline with a festive lift, and cities and
states the map can actually place.

### 7. PDF export (`report_export.py`)
Scope is either one report or all of them. Reports run inside
`auto_analyst.capturing()`, a thread-local buffer that collects headings, charts,
KPIs and the plain-English lines instead of drawing them — so the PDF is built by
the same code as the page and cannot drift from it. Kaleido renders each chart
through a headless browser at roughly **4 seconds each** (9s for one report, 44s
for all eight locally, slower on the t3.micro), hence the progress bar and the
single-report default.

### 8. Gemini AI
Sidebar model picker, micro-level column deep dive, free-form chat, and the
Auto Analyst briefing. All calls wrapped in try/except.

Both the deep dive and the chat are **grounded**: they receive
`auto_analyst.build_data_digest()` — real distributions, totals and value counts —
plus `DATA_ONLY_RULES`, which forbids outside knowledge, Excel/SQL/Python
tutorials and asking the user to paste their data. Before this the chat was sent
nothing but column names, so it could not answer and explained how to do it
yourself in Excel instead.

---

## Hard-Won Details — do not regress these

1. **India includes J&K and Ladakh.** Plotly's default world outline cuts them off.
   `_country_figure()` in `geo_maps.py` adds a second trace that repaints India from
   `geo_assets.load_india_outline()`. If you touch the country map, keep that overlay.
2. **One country, one region.** Raw data had `India`, `IND`, `IN` as three separate
   regions. `geo_assets.normalize_country()` (pycountry + alias table) folds them to
   `IND`, then `render_region_map` groups by the normalized code before plotting.
3. **Floats are not identifiers.** `Revenue` was misclassified as an `identifier`
   because continuous floats are nearly all unique. Fixed: a column is only an
   identifier if it holds whole numbers (`is_integer_dtype` or `% 1 == 0`) **and**
   is not a named measure. Do not loosen this.
4. **City aliases matter.** Real data says Bangalore/Gurgaon/Kochi; the boundary file
   says Bengaluru Urban/Gurugram/Ernakulam. `CITY_ALIASES` + prefix fallback in
   `geo_assets.match_district()` handles it.
5. **The blink is CSS.** Plotly cannot autoplay an animation without a click, so
   `PULSE_CSS` in `geo_maps.py` animates `path.point`, which only matches scatter
   markers. If blinking ever stops working, check that selector first.
6. **`auto_fix_headers` and `generate_dashboard` are legacy-stable.** Features get
   added around them, not inside them.
7. **Every `st.plotly_chart` needs an explicit `key`.** Two tabs rendering the same
   figure produced identical auto-generated element IDs and Streamlit aborted the
   whole page with `StreamlitDuplicateElementId`.
8. **Coerce before you aggregate.** One stray date in a numeric column left the
   whole column as text, which dropped it from every chart and made Plotly colour
   maps as categories instead of a scale. `data_cleaner.coerce_numeric_columns`
   applies the 80%-numeric rule; map aggregation coerces again defensively.
9. **The sparse-row filter must back off.** If more than half the rows look sparse
   the data genuinely is sparse, so nothing is dropped. Without that guard the
   cleaner would delete real datasets.
10. **Never merge sheets for analysis.** Concatenating three sheets with different
    columns produced 80 columns that were 68% blank, and the headline charts came
    out empty. `render_sheet_sections` gives each sheet its own section and adds an
    Auto Compare section at the end. The merged `master_df` is only for the manual
    dashboard's Source_Sheet comparison and the free-form AI chat.
11. **Auto Compare matches columns by their readable name**, not the raw header, so
    `TotalAmount` and `Total_Amount` line up. When sheets share nothing, it still
    compares row counts and each sheet's headline measure.
12. **Never hand multi-line HTML to `st.markdown`.** Streamlit renders markdown,
    and markdown turns any line indented by four or more spaces into a code block -
    so pretty-printed markup appears on screen as its own source code. This shipped
    once: the login screen showed its own `<div class="al-brand__name">`. Every HTML
    block now goes through `theme.html()`, which collapses it to one line.
13. **The look is CSS over Streamlit's `data-testid` hooks.** `theme.py` restyles
    `st.metric`, tabs, buttons and cards without touching a call site, and registers
    one Plotly template as the default so all ~30 charts follow it. A Streamlit
    upgrade that renames a hook degrades the styling; it does not break the app.
    Never scatter `update_layout` colour calls - change the template instead.
14. **Button labels need their colour stated on the button's children.** Streamlit
    wraps a label in a `<p>`, so a global paragraph colour beats the button's own
    and the text vanishes into the background. This shipped: "Log in" was dark navy
    on a dark navy gradient. All three kinds must be covered — `.stButton`,
    `stDownloadButton` and `stFormSubmitButton`; the login button is the third kind,
    which the first fix missed. Never put a blanket `[data-testid="stSidebar"] *`
    colour rule back — it repaints button labels too.
15. **A regex that rewrites call sites will rewrite the function it defines.**
    Routing `st.markdown("##### …")` through a new `chart_heading()` helper also
    rewrote the line *inside* `chart_heading`, so it called itself — every report
    died with `RecursionError`. The test caught it. Check the definition after any
    mechanical rewrite.
16. **fpdf2's core fonts are Latin-1 only.** One em dash in a running header
    aborts the export on page two. Everything written to the PDF goes through
    `report_export._ascii()`, including the title held for the header.
17. **Never raise inside `auth._connect()`.** The context manager commits only when
    the block exits cleanly, so raising after a write rolls it back. This silently
    disabled the OTP attempt counter - every wrong guess reported "4 attempts left"
    and a six-digit code was open to unlimited brute force. `verify_otp` now decides
    the outcome inside the transaction and raises after it closes. Any new write
    followed by an error must do the same.

---

## Current State

Live, in production, with signups open. **All 8 test suites pass**, the app boots
clean, and https://autolyst.online serves 200 over a valid certificate.

Everything under "What Is Built" is done and verified. Delivered in this order:
Google Sheets sync → India-accurate maps → Auto Analyst → layman-readable reports
→ data cleaning → per-sheet sections and Auto Compare → guide book → AWS
deployment with domain and HTTPS → accounts with email OTP → BI visual system →
hero and sample data → data table with pivot.

---

## Next Steps

**Agreed with the user as the next piece of work: 1-Click PDF Report Export.**

1. ~~1-Click PDF Report Export~~ — **done**. See `report_export.py`.
   **Not yet verified on the server:** Kaleido spawns a Chrome process, and the
   t3.micro has 1 GB of RAM plus 2 GB of swap. Watch `journalctl -u dashboard`
   for an OOM kill the first time someone exports all reports there. If it does
   fall over, the fix is to export one report at a time, or move the box up a
   size.
2. **Automated Email Reporting (Triggers).** User picks Hourly/Daily/Monthly + an
   email address. Streamlit reruns per interaction and cannot host a scheduler, so
   run **APScheduler in a separate `scheduler.py` process** that re-fetches the
   Google Sheet, regenerates the PDF, and mails it via SMTP. Store jobs in a small
   local DB/JSON so they survive restarts.
3. **Subscriptions.** Accounts already exist, so this is a plan/limit layer on top:
   a `plan` column on `users`, usage counters, and a payment provider. Nothing in
   `auth.py` needs restructuring for it.
4. Per-user saved workspaces (uploads are in-session only today, so no data is
   shared between accounts).

### Known gaps — say these out loud rather than discovering them later

- **A browser refresh logs the user out.** Streamlit session state does not survive
  a reload. Fixing it properly needs a signed cookie or token, and it is the
  strongest single argument for eventually leaving Streamlit.
- **The look rides on Streamlit's internal `data-testid` hooks.** A major Streamlit
  upgrade can degrade the styling. The app keeps working.
- **No usage limits.** Any signed-up account can spend the owner's Gemini quota.
  Limits belong with the subscription work.
- **`users.db` has no automated backup.** The command is in DEPLOY.md; nothing runs
  it on a schedule.
- **The user asked whether Streamlit could be dropped.** Answer given: the VPS and
  the domain are a different layer, and removing Streamlit means replacing it —
  3-5 weeks for FastAPI + React, producing the same features. Recommended keeping
  it until there are paying customers. Roughly 60% of the code is Streamlit-coupled
  (`app.py`, `auto_analyst`, `geo_maps`, `theme`, `data_table`); `geo_assets`,
  `data_cleaner`, `google_sheets` and the core of `auth` would carry over.

**Rules:** deliver in modular steps and wait for approval between them; keep the UI
premium and clean; handle every error gracefully with an actionable hint; and never
break the existing AI or charting logic.

---

## Run & Test

```bash
venv/Scripts/python.exe -m pip install -r requirements.txt
venv/Scripts/streamlit.exe run app.py        # http://localhost:8501
venv/Scripts/python.exe tests/run_all.py     # all eight suites, one line each
```

**Run `tests/run_all.py` before every push.** No framework to install — each suite
is a plain script that installs `tests/st_stub.py` as a fake Streamlit, executes
the real code paths, and asserts on what comes out: the Plotly figures, the cleaned
frames, the column roles, the pivot totals, the auth guards.

| Suite | Covers |
|---|---|
| `test_full` | Geo detection, country merging, the J&K overlay, every auto scenario |
| `test_real` | The whole pipeline on a genuinely messy workbook |
| `test_cleaner` | Row rules, placeholder text, the sparse-data back-off |
| `test_sheets` | Per-sheet sections and Auto Compare |
| `test_keyrule` | Key column vs nearly-empty rows, and their guards |
| `test_auth` | Signup, OTP expiry and attempt limits, login lockout |
| `test_table` | Filters, pivot totals checked against the source, export |
| `test_html` | Markup renders as HTML, button labels stay readable |

Four suites want a messy workbook. They skip cleanly without one; set
`SAMPLE_WORKBOOK` to an `.xlsx` path to run them.

To check the deployed app rather than the code:

```bash
curl -sI https://autolyst.online | head -1
sudo journalctl -u dashboard -n 50 --no-pager     # on the server
```
