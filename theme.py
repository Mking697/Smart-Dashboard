"""Visual system for the dashboard - a Power BI grade look, applied in one place.

The design system came from the ui-ux-pro-max skill for a
"business intelligence analytics dashboard, data-dense, professional" product:

    Pattern     Real-Time / Operations
    Style       Data-Dense Dashboard  (minimal padding, KPI tiles, grid layout)
    Type        Fira Sans body / Fira Code for figures and labels
    Motion      Standard - staggered entrance, 300-450ms
    Density     8/10 - dashboard spacing scale

Two deliberate decisions:

* **Everything is CSS, nothing is a rewrite.** Streamlit's own widgets are
  restyled through their stable `data-testid` hooks, so `st.metric` becomes a
  Power BI tile without a single call site changing. If a future Streamlit
  renames a hook, that rule stops applying - the app still runs.
* **One Plotly template.** Registering it as the default restyles every chart in
  the app at once, instead of thirty `update_layout` calls that drift apart.
"""

import re

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st


def html(markup):
    """Collapse a multi-line HTML block onto one line before rendering it.

    Streamlit renders markdown, and markdown turns any line indented by four or
    more spaces into a code block. Pretty-printed markup therefore arrives on
    screen as its own source code. Collapsing the whitespace costs nothing -
    HTML collapses it anyway - and removes the whole class of bug.
    """
    return re.sub(r"\s*\n\s*", " ", markup).strip()

# --------------------------------------------------------------------------- #
# Tokens - the single source of colour
# --------------------------------------------------------------------------- #

PRIMARY = "#1E40AF"
SECONDARY = "#3B82F6"
ACCENT = "#D97706"          # amber, WCAG-adjusted by the skill from #F59E0B
BACKGROUND = "#F8FAFC"
SURFACE = "#FFFFFF"
HEADING = "#1E3A8A"
BODY = "#2C3E5D"            # blue-biased neutral, ~9:1 on the background
MUTED_TEXT = "#64748B"
MUTED = "#E9EEF6"
BORDER = "#DBEAFE"
BORDER_STRONG = "#C7DAF7"
POSITIVE = "#047857"
DESTRUCTIVE = "#DC2626"

# Categorical sequence for charts. Ordered so neighbouring series stay
# distinguishable for the most common colour-vision deficiencies.
CATEGORICAL = [
    "#1E40AF", "#0E9488", "#D97706", "#7C3AED", "#DC2626",
    "#0891B2", "#65A30D", "#DB2777", "#475569", "#B45309",
]

SEQUENTIAL = [
    [0.0, "#EEF4FF"], [0.25, "#BFD4F7"], [0.5, "#7BA3EA"],
    [0.75, "#3B6FD4"], [1.0, "#1E3A8A"],
]

FONT_BODY = "'Fira Sans', -apple-system, 'Segoe UI', Roboto, sans-serif"
FONT_DATA = "'Fira Code', ui-monospace, Consolas, monospace"


# --------------------------------------------------------------------------- #
# Plotly template - restyles every chart in the app
# --------------------------------------------------------------------------- #

def _build_template():
    template = go.layout.Template()

    template.layout = go.Layout(
        font=dict(family=FONT_BODY, size=13, color=BODY),
        title=dict(font=dict(family=FONT_BODY, size=15, color=HEADING), x=0, xanchor="left", pad=dict(b=14)),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=CATEGORICAL,
        margin=dict(l=8, r=8, t=48, b=8),
        # Gridlines stay quiet so they never compete with the data.
        xaxis=dict(
            gridcolor=MUTED, linecolor=BORDER_STRONG, zerolinecolor=MUTED,
            tickfont=dict(family=FONT_DATA, size=11, color=MUTED_TEXT),
            title=dict(font=dict(size=12, color=MUTED_TEXT)),
            automargin=True,
        ),
        yaxis=dict(
            gridcolor=MUTED, linecolor=BORDER_STRONG, zerolinecolor=MUTED,
            tickfont=dict(family=FONT_DATA, size=11, color=MUTED_TEXT),
            title=dict(font=dict(size=12, color=MUTED_TEXT)),
            automargin=True,
        ),
        legend=dict(
            font=dict(size=12), bgcolor="rgba(0,0,0,0)",
            orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
        ),
        hoverlabel=dict(
            bgcolor=HEADING, bordercolor=HEADING,
            font=dict(family=FONT_BODY, size=12, color="#FFFFFF"),
        ),
        colorscale=dict(sequential=SEQUENTIAL),
        coloraxis=dict(colorscale=SEQUENTIAL),
        geo=dict(bgcolor="rgba(0,0,0,0)", lakecolor=SURFACE),
        separators=".,",
    )

    template.data.bar = [go.Bar(marker=dict(line=dict(width=0)), textfont=dict(family=FONT_DATA, size=11))]
    template.data.pie = [go.Pie(textfont=dict(family=FONT_BODY, size=12),
                                marker=dict(line=dict(color=SURFACE, width=2)))]
    template.data.scatter = [go.Scatter(line=dict(width=2.5))]

    return template


def apply_plotly_theme():
    """Register the template and make every px/go chart use it by default."""
    pio.templates["autolyst"] = _build_template()
    pio.templates.default = "autolyst"
    px.defaults.template = "autolyst"
    px.defaults.color_discrete_sequence = CATEGORICAL


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #

def _css():
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root {{
  --c-primary: {PRIMARY};
  --c-secondary: {SECONDARY};
  --c-accent: {ACCENT};
  --c-bg: {BACKGROUND};
  --c-surface: {SURFACE};
  --c-heading: {HEADING};
  --c-body: {BODY};
  --c-muted-text: {MUTED_TEXT};
  --c-muted: {MUTED};
  --c-border: {BORDER};
  --c-border-strong: {BORDER_STRONG};
  --c-positive: {POSITIVE};
  --c-danger: {DESTRUCTIVE};

  /* Density 8/10 - dashboard scale */
  --s-1: 4px;  --s-2: 8px;  --s-3: 12px; --s-4: 16px;
  --s-5: 20px; --s-6: 24px; --s-8: 32px;

  --radius: 10px;
  --shadow-1: 0 1px 2px rgba(15,35,80,.06), 0 1px 3px rgba(15,35,80,.04);
  --shadow-2: 0 4px 12px -2px rgba(15,35,80,.10), 0 2px 6px -2px rgba(15,35,80,.06);
  --ease: cubic-bezier(.22,.61,.36,1);
}}

html, body, [class*="css"] {{ font-family: {FONT_BODY}; }}

.stApp {{ background: var(--c-bg); }}

/* Wider working area - dashboards need the pixels */
.block-container {{
  padding-top: var(--s-6) !important;
  padding-bottom: var(--s-8) !important;
  max-width: 1560px;
}}

/* ---- Typography ------------------------------------------------------- */
h1, h2, h3, h4, h5 {{ font-family: {FONT_BODY}; color: var(--c-heading); letter-spacing: -.01em; }}
h1 {{ font-weight: 700; font-size: 2rem !important; }}
h2 {{ font-weight: 650; font-size: 1.4rem !important; }}
h3 {{ font-weight: 600; font-size: 1.12rem !important; }}
p, li, label, .stMarkdown {{ color: var(--c-body); }}

/* ---- Sidebar ---------------------------------------------------------- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #10224B 0%, #14275A 100%);
  border-right: 1px solid rgba(255,255,255,.06);
}}
[data-testid="stSidebar"] * {{ color: #DCE6FA !important; }}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: #FFFFFF !important; font-size: .82rem !important;
  text-transform: uppercase; letter-spacing: .10em; font-weight: 600; opacity: .72; }}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{ font-size: .85rem; opacity: .9; }}
[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div,
[data-testid="stSidebar"] input {{
  background: rgba(255,255,255,.07) !important;
  border-color: rgba(255,255,255,.16) !important;
}}

/* ---- KPI tiles: st.metric restyled, no call site touched --------------- */
[data-testid="stMetric"] {{
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-4) var(--s-5);
  box-shadow: var(--shadow-1);
  position: relative;
  overflow: hidden;
  transition: box-shadow .22s var(--ease), transform .22s var(--ease);
}}
/* The accent rail is what makes it read as a BI tile rather than a box. */
[data-testid="stMetric"]::before {{
  content: ""; position: absolute; inset-block: 0; inset-inline-start: 0;
  width: 3px; background: linear-gradient(180deg, var(--c-primary), var(--c-secondary));
}}
[data-testid="stMetric"]:hover {{ box-shadow: var(--shadow-2); transform: translateY(-2px); }}
[data-testid="stMetricLabel"] p {{
  font-size: .74rem !important; font-weight: 600; letter-spacing: .07em;
  text-transform: uppercase; color: var(--c-muted-text) !important;
}}
[data-testid="stMetricValue"] {{
  font-family: {FONT_DATA}; font-weight: 600; font-size: 1.85rem !important;
  color: var(--c-heading); font-variant-numeric: tabular-nums; line-height: 1.15;
}}
[data-testid="stMetricDelta"] {{ font-family: {FONT_DATA}; font-size: .82rem !important; }}

/* ---- Cards: charts, tables, expanders ---------------------------------- */
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"] {{
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--s-2);
  box-shadow: var(--shadow-1);
}}
[data-testid="stExpander"] {{
  background: var(--c-surface);
  border: 1px solid var(--c-border) !important;
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow-1);
}}
[data-testid="stExpander"] summary:hover {{ color: var(--c-primary); }}

/* ---- Tabs: BI-style underline, not browser tabs ------------------------ */
.stTabs [data-baseweb="tab-list"] {{
  gap: var(--s-1);
  border-bottom: 1px solid var(--c-border);
  overflow-x: auto;
  scrollbar-width: thin;
}}
.stTabs [data-baseweb="tab"] {{
  height: 42px; padding: 0 var(--s-4);
  font-size: .92rem; font-weight: 500; color: var(--c-muted-text);
  border-radius: 8px 8px 0 0;
  transition: color .18s var(--ease), background .18s var(--ease);
}}
.stTabs [data-baseweb="tab"]:hover {{ color: var(--c-primary); background: var(--c-muted); }}
.stTabs [aria-selected="true"] {{ color: var(--c-primary) !important; font-weight: 650; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--c-primary); height: 3px; }}

/* ---- Controls ---------------------------------------------------------- */
.stButton > button {{
  border-radius: 8px; font-weight: 550; letter-spacing: .01em;
  border: 1px solid var(--c-border-strong); background: var(--c-surface); color: var(--c-heading);
  transition: transform .16s var(--ease), box-shadow .16s var(--ease), background .16s var(--ease);
}}
.stButton > button:hover {{ border-color: var(--c-primary); color: var(--c-primary); box-shadow: var(--shadow-1); }}
.stButton > button:active {{ transform: scale(.985); }}
.stButton > button[kind="primary"] {{
  background: linear-gradient(135deg, var(--c-primary), #2B52C8);
  border: none; color: #fff;
}}
.stButton > button[kind="primary"]:hover {{ box-shadow: 0 6px 16px -4px rgba(30,64,175,.45); color: #fff; }}

/* Keyboard focus must stay visible - never trade a11y for looks. */
.stButton > button:focus-visible,
input:focus-visible, select:focus-visible, textarea:focus-visible,
.stTabs [data-baseweb="tab"]:focus-visible {{
  outline: 3px solid rgba(30,64,175,.35) !important;
  outline-offset: 2px !important;
}}

div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  border-radius: 8px !important; border-color: var(--c-border-strong) !important;
  background: var(--c-surface) !important;
}}
div[data-baseweb="select"] > div:focus-within, .stTextInput input:focus {{
  border-color: var(--c-primary) !important;
}}

/* Segmented control - the app's main view switcher */
[data-testid="stSegmentedControl"] button {{ font-weight: 550; }}

/* ---- Messages ---------------------------------------------------------- */
[data-testid="stAlert"] {{ border-radius: var(--radius); border-left-width: 3px; }}

/* ---- Dataframe --------------------------------------------------------- */
[data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}

/* ---- Motion: Standard tier -------------------------------------------- */
@keyframes rise {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: none; }} }}

[data-testid="stMetric"], [data-testid="stPlotlyChart"] {{
  animation: rise .42s var(--ease) both;
}}
/* Stagger across a KPI row - the wave reads as one group, not six boxes. */
[data-testid="stHorizontalBlock"] > div:nth-child(1) [data-testid="stMetric"] {{ animation-delay: .00s; }}
[data-testid="stHorizontalBlock"] > div:nth-child(2) [data-testid="stMetric"] {{ animation-delay: .06s; }}
[data-testid="stHorizontalBlock"] > div:nth-child(3) [data-testid="stMetric"] {{ animation-delay: .12s; }}
[data-testid="stHorizontalBlock"] > div:nth-child(4) [data-testid="stMetric"] {{ animation-delay: .18s; }}
[data-testid="stHorizontalBlock"] > div:nth-child(5) [data-testid="stMetric"] {{ animation-delay: .24s; }}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
  [data-testid="stMetric"]:hover {{ transform: none; }}
}}

/* ---- Brand header ------------------------------------------------------ */
.al-brand {{ display: flex; align-items: center; gap: var(--s-3); }}
.al-brand__mark {{ flex: none; }}
.al-brand__name {{
  font-size: 1.5rem; font-weight: 700; color: var(--c-heading);
  letter-spacing: -.02em; line-height: 1;
}}
.al-brand__tag {{ font-size: .82rem; color: var(--c-muted-text); margin-top: 2px; }}

/* ---- Hero: what a first-time visitor sees instead of a blank page ------ */
.al-hero {{
  background:
    radial-gradient(120% 140% at 100% 0%, #E8F0FF 0%, rgba(232,240,255,0) 58%),
    linear-gradient(135deg, #0F2557 0%, #1E40AF 52%, #2B62D6 100%);
  border-radius: 16px;
  padding: var(--s-8) var(--s-8);
  color: #EAF1FF;
  box-shadow: 0 18px 40px -22px rgba(15,37,87,.65);
  animation: rise .5s var(--ease) both;
}}
.al-hero h2 {{
  color: #FFFFFF !important;
  font-size: clamp(1.5rem, 2.6vw, 2.05rem) !important;
  font-weight: 700; line-height: 1.16; margin: 0 0 var(--s-3);
  letter-spacing: -.02em; text-wrap: balance;
}}
.al-hero p {{ color: #C6D8FA; font-size: 1.02rem; margin: 0; max-width: 60ch; }}
.al-hero__badge {{
  display: inline-flex; align-items: center; gap: 7px;
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.22);
  color: #DDE9FF; font-family: {FONT_DATA}; font-size: .72rem; font-weight: 500;
  letter-spacing: .08em; text-transform: uppercase;
  padding: 5px 11px; border-radius: 999px; margin-bottom: var(--s-4);
}}

/* Feature cards */
.al-cards {{
  display: grid; gap: var(--s-3);
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  margin-top: var(--s-4);
}}
.al-card {{
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 12px;
  padding: var(--s-4) var(--s-5);
  box-shadow: var(--shadow-1);
  animation: rise .45s var(--ease) both;
  transition: transform .22s var(--ease), box-shadow .22s var(--ease), border-color .22s var(--ease);
}}
.al-card:nth-child(1) {{ animation-delay: .06s; }}
.al-card:nth-child(2) {{ animation-delay: .12s; }}
.al-card:nth-child(3) {{ animation-delay: .18s; }}
.al-card:nth-child(4) {{ animation-delay: .24s; }}
.al-card:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-2); border-color: var(--c-border-strong); }}
.al-card__icon {{
  width: 34px; height: 34px; border-radius: 9px;
  background: var(--c-muted); color: var(--c-primary);
  display: grid; place-items: center; margin-bottom: var(--s-3);
}}
.al-card h4 {{ margin: 0 0 4px; font-size: .96rem; font-weight: 650; color: var(--c-heading); }}
.al-card p {{ margin: 0; font-size: .86rem; line-height: 1.5; color: var(--c-muted-text); }}

.al-authcard {{
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: var(--s-8) var(--s-8) var(--s-6);
  box-shadow: var(--shadow-2);
  animation: rise .5s var(--ease) both;
}}

/* Hide Streamlit's own chrome so it reads as a product, not a notebook */
#MainMenu, footer {{ visibility: hidden; }}
</style>
"""


# Inline SVG rather than an emoji: it scales, it takes the brand colour, and it
# renders identically on every OS.
LOGO_SVG = html("""
<svg class="al-brand__mark" width="34" height="34" viewBox="0 0 32 32" fill="none"
     role="img" aria-label="Autolyst logo">
  <rect width="32" height="32" rx="8" fill="url(#alg)"/>
  <rect x="8"  y="16" width="3.4" height="8"  rx="1.3" fill="#fff" opacity=".95"/>
  <rect x="14.3" y="11" width="3.4" height="13" rx="1.3" fill="#fff" opacity=".8"/>
  <rect x="20.6" y="7"  width="3.4" height="17" rx="1.3" fill="#fff"/>
  <defs>
    <linearGradient id="alg" x1="0" y1="0" x2="32" y2="32">
      <stop stop-color="#1E40AF"/><stop offset="1" stop-color="#3B82F6"/>
    </linearGradient>
  </defs>
</svg>
""")


def brand_header(name="Autolyst", tagline="Your sheet in. Ready-made reports out."):
    """Logo + wordmark, used on the login screen and the dashboard header."""
    st.markdown(
        html(f"""
            <div class="al-brand">{LOGO_SVG}
              <div>
                <div class="al-brand__name">{name}</div>
                <div class="al-brand__tag">{tagline}</div>
              </div>
            </div>
        """),
        unsafe_allow_html=True,
    )


def _icon(path):
    """Lucide-style stroked glyph. SVG, not an emoji - it takes the brand colour
    and renders identically on every OS."""
    return html(
        f'<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f'{path}</svg>'
    )


FEATURES = [
    (_icon('<path d="M3 3v18h18"/><path d="m7 14 4-4 3 3 5-6"/>'),
     "8 ready-made reports",
     "Growth, top performers, outliers, correlations — built from your columns, not a template."),
    (_icon('<path d="M12 22s8-4.5 8-11a8 8 0 1 0-16 0c0 6.5 8 11 8 11Z"/><circle cx="12" cy="11" r="3"/>'),
     "Maps that know India",
     "City and state names alone are enough. Jammu &amp; Kashmir and Ladakh drawn correctly."),
    (_icon('<path d="M3 6h18"/><path d="M7 12h10"/><path d="M10 18h4"/>'),
     "Messy sheets, cleaned",
     "Blank rows, stray spaces and placeholder text removed — and it tells you what it removed."),
    (_icon('<path d="M12 3a6 6 0 0 0-6 6c0 2 1 3 1 5h10c0-2 1-3 1-5a6 6 0 0 0-6-6Z"/><path d="M9 18h6"/><path d="M10 21h4"/>'),
     "Plain-English answers",
     "Every chart says how to read it, and what it actually means for your business."),
]


def hero():
    """The welcome panel shown before any data is loaded."""
    st.markdown(
        html("""
            <div class="al-hero">
              <span class="al-hero__badge">No formulas required</span>
              <h2>Turn a spreadsheet into a boardroom-ready report.</h2>
              <p>Upload an Excel file or connect a Google Sheet. The data is cleaned,
                 profiled and turned into reports that explain themselves — in about
                 ten seconds.</p>
            </div>
        """),
        unsafe_allow_html=True,
    )

    cards = "".join(
        f'<div class="al-card"><div class="al-card__icon">{icon}</div>'
        f'<h4>{title}</h4><p>{body}</p></div>'
        for icon, title, body in FEATURES
    )
    st.markdown(html(f'<div class="al-cards">{cards}</div>'), unsafe_allow_html=True)


def apply():
    """Call once, immediately after st.set_page_config."""
    st.markdown(_css(), unsafe_allow_html=True)
    apply_plotly_theme()
