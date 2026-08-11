# 🚀 AI-Powered Master Dashboard (SaaS)

An autonomous, multi-tenant data analysis dashboard built with Python, Streamlit and
Google Gemini AI. It acts like a smart Power BI that doesn't just plot your data —
it profiles it, decides what is worth showing, builds the dashboards, and explains
what it found.

### 🔴 Live: **[autolyst.online](https://autolyst.online)**

Running on AWS EC2 with HTTPS and open signups. Deployment steps are in
[DEPLOY.md](DEPLOY.md).

---

## 🔥 Key Features

### 🔐 Accounts
- **Sign up once** with your name, email and password.
- **Email verification** — a six-digit code is sent through Brevo; the account is
  inactive until it is confirmed.
- **Log in** with email and password from then on. One account per email address.
- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never in the clear.
  Codes expire, wrong guesses are limited, and repeated failed logins lock the
  account for 15 minutes.

### 📥 Data In
- **Messy file support** — upload Excel/CSV; headers are detected and repaired automatically.
- **Unmanaged sheets get managed** — only rows that actually contain data are used.
  A 1,000-row sheet holding 100 real records is charted as 100 records. Blank rows,
  lone `END`/`Total` footers, empty columns, stray spaces (`" Noida"`) and
  placeholders (`N/A`, `-`, `NULL`) are cleaned, and the app shows you a report of
  everything it changed.
- **Multi-sheet workspaces** — every sheet gets its **own complete set of reports**,
  analysed on its own data. Sheets are never merged into one table, because sheets
  with different columns produce a mostly-blank result and broken totals. When more
  than one sheet is loaded, a final **⚖️ Auto Compare** section stacks them up:
  sizes, headline numbers, shared columns and the same breakdown side by side.
- **Google Sheets Live Sync** — paste a sheet link and pull live data. Public sheets
  work instantly; private sheets connect through a Google service account.

### 🤖 Auto Analyst
Point it at any sheet and it builds the reports for you — no axis picking. Each
report answers one business question:

| Report | The question it answers |
|---|---|
| 📊 Business Overview | How is the business doing overall, and who contributes most? |
| 📈 Growth Over Time | Are we growing, flat or falling — and when were our best periods? |
| 🏆 Top Performers | Who are our best performers, and how dependent are we on them? |
| 📉 What Is Normal | What is a normal value here, and which records look wrong? |
| 🔗 What Affects What | When one number changes, which others change with it? |
| 🧮 Best Combinations | Which combination of groups performs best, and where are the gaps? |
| 🌍 Location Map | Which places bring the most business, and where are we absent? |
| 🧪 Can You Trust This Data | Are there gaps or duplicates making these charts unreliable? |

**Written for people who are not analysts.** Column names are humanised
(`Q_TaxAmount` reads as *Tax Amount*), every chart has a heading, a **"how to read
this"** line, and a plain-English **"what it means"** takeaway stating the actual
finding — for example *"4 of 8 Sales Reps generate 80% of all Total Amount."*

It also shows a **"What this data can show you"** panel — every column labelled with
the role it plays (measure, dimension, timeline, geography, flag, identifier) and why
that matters.

### 📄 PDF Export
Export **one report or all of them** as a PDF — the charts as images, the KPIs, and
the plain-English "what it means" lines underneath each one. It is built from the
same code that draws the page, so the document always matches what you saw.

### 📋 Data Table
The rows behind the reports, per sheet — search every column at once, filter on any
column with the right control for its type, hide columns you don't need, and tick
one box to turn the whole thing into a **pivot table** with row and column totals.
The grid is a fixed height that scrolls inside itself, so the filters never get
pushed off screen. Export whatever you are looking at as CSV.

### 🌍 Geographical Intelligence
- **Region maps** for countries, Indian states, Indian districts and US states —
  detected automatically from the column.
- **🇮🇳 Correct India map** — Jammu & Kashmir and Ladakh are always drawn as part of
  India, using bundled official district boundaries rather than Plotly's default outline.
- **Smart country merging** — `India`, `IND` and `IN` are recognised as one country
  instead of three separate regions.
- **Blinking pin maps** — pulsing markers with hover values and scroll zoom. City
  names alone are enough; coordinates are resolved from the bundled boundaries when
  the data has no Latitude/Longitude columns. Everyday names like *Bangalore*,
  *Gurgaon* and *Kochi* are matched to their official districts.
- **Treemap drill-down** for hierarchical Country ➡️ State ➡️ City exploration.

### 🧠 AI (Google Gemini)
- **AI Analyst Briefing** — what this data is, the three things to look at first,
  risks, the business questions it can answer, and what column is missing.
- **Micro-level deep dive** — pick any column and get patterns, anomalies, business
  impact and a recommendation.
- **Chat with your data** — ask anything in plain language.

> Privacy note: the AI briefing sends **column statistics only** — never your raw rows.

---

## ⚙️ Installation & Setup

```bash
git clone https://github.com/Mking697/Smart-Dashboard.git
cd Smart-Dashboard

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
# Gemini - powers the AI briefing, deep dive and chat
GEMINI_API_KEY=your_key_here

# Brevo - sends signup verification codes
BREVO_API_KEY=your_brevo_key
BREVO_SENDER_EMAIL=noreply@yourdomain.com
BREVO_SENDER_NAME=AI Smart Dashboard
```

> The Brevo sender address must be **verified in your Brevo account**, or the
> emails are rejected.

Run it:

```bash
streamlit run app.py
```

### Optional — private Google Sheets

1. Google Cloud Console → enable the **Google Sheets API**.
2. Create a **Service Account** and download its JSON key.
3. Either upload that JSON in the app's *Private sheet?* panel, or add it to
   `.streamlit/secrets.toml` under `[gcp_service_account]`.
4. Share your sheet with the service account email as **Viewer**.

---

## 🗂️ Project Structure

```
app.py                          Orchestrator: data sources, workspace, AI panels
auth.py                         Signup, email OTP, login, session gate
data_cleaner.py                 Cleans unmanaged sheets, reports every change
auto_analyst.py                 Profiling engine + automatic reports
data_table.py                   Filters, pivot builder, scrollable grid, CSV export
geo_maps.py                     Map detection and rendering
geo_assets.py                   India boundaries, name matching, geocoding
google_sheets.py                Google Sheets connector (public + service account)
theme.py                        Design tokens, component CSS, Plotly template
sample_data.py                  Deterministic demo workbook
assets/india_districts.geojson  Official India boundaries (incl. J&K and Ladakh)
deploy/                         AWS provisioning and HTTPS scripts
report_export.py                Renders the reports to PDF (Kaleido + fpdf2)
tests/                          Nine suites — run tests/run_all.py
```

## 🧪 Tests

```bash
venv/Scripts/python.exe tests/run_all.py
```

No framework to install. Each suite stubs Streamlit, runs the real code paths and
asserts on what comes out — the figures, the cleaned frames, the column roles, the
pivot totals, the auth guards. Run it before every push.

New here? Start with the **[Guide Book](GUIDE.md)** — a step-by-step walkthrough written for
non-technical users. See [DEPLOY.md](DEPLOY.md) for hosting and [CLAUDE.md](CLAUDE.md) for
development context.

---

## 🛣️ Roadmap

- [x] Smart cleaning, multi-sheet dashboards, AI deep dive
- [x] Google Sheets live sync
- [x] India-accurate geography + automatic dashboard generation
- [x] Accounts: signup, email OTP verification, login
- [x] Data table with filters and pivot
- [x] Deployed on AWS with a custom domain and HTTPS
- [x] 1-click PDF report export
- [ ] Scheduled email reports (hourly / daily / monthly) ← **next**
- [ ] Scheduled email reports (hourly / daily / monthly)
- [ ] Subscription plans and billing
