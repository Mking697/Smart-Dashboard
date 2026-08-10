# 🚀 AI-Powered Master Dashboard (SaaS)

An autonomous, multi-tenant data analysis dashboard built with Python, Streamlit and
Google Gemini AI. It acts like a smart Power BI that doesn't just plot your data —
it profiles it, decides what is worth showing, builds the dashboards, and explains
what it found.

---

## 🔥 Key Features

### 📥 Data In
- **Messy file support** — upload Excel/CSV; headers are detected and repaired automatically.
- **Multi-sheet workspaces** — every sheet gets its own dashboard, plus a master comparison view.
- **Google Sheets Live Sync** — paste a sheet link and pull live data. Public sheets
  work instantly; private sheets connect through a Google service account.

### 🤖 Auto Analyst
Point it at any dataset and it builds the dashboards for you — no axis picking:

| Dashboard | What it answers |
|---|---|
| 📊 Executive Summary | The headline numbers and the breakdown that explains them |
| 📈 Trends | How the numbers move over time, with period-on-period growth |
| 🏆 Rankings & 80/20 | Who leads, and how concentrated the business really is |
| 📉 Distribution & Outliers | Typical values, spread, and suspicious extremes |
| 🔗 Relationships | Which measures move together, and how strongly |
| 🧮 Cross-Tab Heatmap | Where volume concentrates across two dimensions |
| 🌍 Geography | The data drawn on a real map |
| 🧪 Data Quality | Missing values, duplicates and dead columns |

It also shows a **"What this data can show you"** panel — every column labelled with
the role it plays (measure, dimension, timeline, geography, flag, identifier) and why
that matters.

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
GEMINI_API_KEY=your_key_here
```

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
auto_analyst.py                 Profiling engine + automatic dashboards
geo_maps.py                     Map detection and rendering
geo_assets.py                   India boundaries, name matching, geocoding
google_sheets.py                Google Sheets connector (public + service account)
assets/india_districts.geojson  Official India boundaries (incl. J&K and Ladakh)
```

See [DEPLOY.md](DEPLOY.md) for hosting and [CLAUDE.md](CLAUDE.md) for development context.

---

## 🛣️ Roadmap

- [x] Smart cleaning, multi-sheet dashboards, AI deep dive
- [x] Google Sheets live sync
- [x] India-accurate geography + automatic dashboard generation
- [ ] 1-click PDF report export
- [ ] Scheduled email reports (hourly / daily / monthly)
- [ ] Multi-tenant authentication
