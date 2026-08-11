"""Automated analyst - reads the data, decides what is worth showing, builds it.

The idea: instead of the user picking axes, we profile every column, work out the
role it plays (measure, dimension, date, geography, identifier, flag), and then
assemble the scenarios a human analyst would actually build for that shape of
data - trends, rankings, Pareto, distributions, correlations, cross-tabs,
geography and data quality.

Every scenario carries a "why" line, so the dashboard also explains itself.
"""

import re

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import capture
import geo_maps
import theme

# Column names that usually signal a real business measure worth totalling.
MEASURE_HINTS = (
    'amount', 'revenue', 'sales', 'price', 'cost', 'profit', 'margin', 'qty',
    'quantity', 'total', 'value', 'score', 'rating', 'salary', 'budget',
    'spend', 'income', 'balance', 'units', 'volume', 'weight', 'duration',
)

IDENTIFIER_HINTS = ('id', 'code', 'uuid', 'guid', 'ref', 'number', 'no', 'key', 'sr', 'srno')

DATE_HINTS = ('date', 'time', 'day', 'month', 'year', 'created', 'updated', 'timestamp', 'dob')

# Measures that describe a rate rather than an amount. Adding them up produces a
# number nobody can act on - the headline once read "Total Unit Price 784,275",
# which is the sum of a per-unit figure and means nothing at all. These are
# averaged instead. Kept deliberately narrow: "Discount" and "Margin" are just
# as often absolute amounts, so they stay summed.
RATE_HINTS = (
    'unit price', 'unit cost', 'unit rate', 'per unit', 'price per', 'cost per',
    'rate', 'percent', 'percentage', 'ratio', 'rating', 'score', 'average', 'avg',
)

PROFILE_SAMPLE_ROWS = 50_000
PALETTE = theme.CATEGORICAL


# --------------------------------------------------------------------------- #
# Plain-English helpers
# --------------------------------------------------------------------------- #

def humanize(name):
    """Turn a raw column name into something a non-technical person can read.

    'Q_TaxAmount' -> 'Tax Amount', 'w_sales_rep' -> 'Sales Rep'. Real sheets are
    full of ordering prefixes and camelCase; the dashboard should not be.
    """
    text = str(name).strip()
    text = re.sub(r'^[A-Za-z]_(?=[A-Za-z])', '', text)     # drop A_ / B_ ordering prefixes
    text = text.replace('_', ' ').replace('-', ' ')
    text = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', text)    # camelCase -> spaced
    text = re.sub(r'\s+', ' ', text).strip()

    if not text:
        return str(name)

    return " ".join(word if word.isupper() else word[:1].upper() + word[1:] for word in text.split())


def metric_label(metric):
    """Readable name for a chosen metric, including the count pseudo-metric."""
    return "Number of Records" if metric in ("Record count", "Count (Frequency)") else humanize(metric)


# --------------------------------------------------------------------------- #
# Capture: the same report code either draws to the page or fills a buffer
# --------------------------------------------------------------------------- #
#
# Every scenario writes through the helpers below. The buffer itself lives in
# `capture` so that `geo_maps` can fill it too without importing this module.

capturing = capture.capturing
_sink = capture.sink                    # kept for the tests, which assert on it


def chart_heading(text):
    """The question a chart answers, above it."""
    if not capture.add("heading", text):
        st.markdown(f"##### {text}")


def show_chart(fig, key):
    if not capture.add("chart", fig):
        st.plotly_chart(fig, use_container_width=True, key=key)


def show_kpi(slot, label, value, help_text=None):
    if not capture.add("kpi", (label, value)):
        slot.metric(label, value, help=help_text)


def explain(text):
    """One plain-English line under a chart telling the user how to read it."""
    if not capture.add("explain", text):
        st.caption(f"📖 **How to read this:** {text}")


def takeaway(text):
    """The finding the chart actually shows, stated in words."""
    if not capture.add("takeaway", text):
        st.success(f"💡 **What it means:** {text}")


def warn(text):
    """A problem worth acting on.

    Renders as a warning on screen but is captured exactly like a takeaway, so
    the findings reach the PDF instead of being lost - the exported data-quality
    report used to be a chart with no conclusions under it.
    """
    if not capture.add("takeaway", text):
        st.warning("⚠️ " + text)


def pick(label, options, key, format_func=str):
    """A selectbox that stands aside during an export.

    A captured report must not draw widgets - they would appear on the page
    while the PDF is being built - so the first option, which is what the
    selectbox would show anyway, is returned instead.
    """
    if not options:
        return None
    if capture.active():
        return options[0]
    return st.selectbox(label, options, format_func=format_func, key=key)


def pct(part, whole):
    return 0.0 if not whole else round(100 * part / whole, 1)


# --------------------------------------------------------------------------- #
# Profiling
# --------------------------------------------------------------------------- #

def parse_dates(series):
    """Parse to datetime, tolerating mixed formats and already-parsed columns."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    try:
        return pd.to_datetime(series, errors='coerce', format='mixed')
    except (ValueError, TypeError):
        return pd.to_datetime(series, errors='coerce')


def _looks_like_dates(series):
    """True when most non-null values parse as dates."""
    sample = series.dropna().head(500)
    if sample.empty:
        return False
    return parse_dates(sample).notna().mean() > 0.8


def profile_column(series, name):
    """Describe one column: its role, quality and the stats that matter."""
    total = len(series)
    non_null = series.dropna()
    lower = str(name).lower()

    info = {
        'name': name,
        'missing_pct': round(100 * (1 - len(non_null) / total), 1) if total else 100.0,
        'n_unique': int(non_null.nunique()) if len(non_null) else 0,
        'role': 'empty',
    }
    info['unique_ratio'] = round(info['n_unique'] / len(non_null), 3) if len(non_null) else 0

    if non_null.empty:
        return info

    is_datetime = pd.api.types.is_datetime64_any_dtype(series)
    is_numeric = pd.api.types.is_numeric_dtype(series)

    if is_datetime or (not is_numeric and any(h in lower for h in DATE_HINTS) and _looks_like_dates(non_null)):
        parsed = parse_dates(non_null).dropna()
        info.update(role='date', min=parsed.min(), max=parsed.max(),
                    span_days=int((parsed.max() - parsed.min()).days) if len(parsed) > 1 else 0)
        return info

    if is_numeric:
        named_measure = any(hint in lower for hint in MEASURE_HINTS)
        # Match on whole words of the readable name, so "D_PhoneNumber" and
        # "H_ZipCode" are recognised as labels rather than things to total up.
        words = {word.lower() for word in humanize(name).split()}
        named_id = bool(words & set(IDENTIFIER_HINTS)) or any(
            h == lower or lower.endswith('_' + h) or lower.startswith(h + '_')
            for h in IDENTIFIER_HINTS)
        # A continuous measure is nearly all-unique by nature, so "mostly unique"
        # alone is not enough - a row id is a whole number and never a named measure.
        whole_numbers = pd.api.types.is_integer_dtype(series) or (non_null % 1 == 0).all()
        serial_like = whole_numbers and info['unique_ratio'] > 0.99 and info['n_unique'] > 20

        if not named_measure and ((named_id and info['unique_ratio'] > 0.5) or serial_like):
            info['role'] = 'identifier'
            return info

        if info['n_unique'] <= 2:
            info['role'] = 'flag'
            return info

        info.update(
            role='measure',
            total=float(non_null.sum()),
            mean=float(non_null.mean()),
            median=float(non_null.median()),
            std=float(non_null.std()) if info['n_unique'] > 1 else 0.0,
            minimum=float(non_null.min()),
            maximum=float(non_null.max()),
            zeros=int((non_null == 0).sum()),
            negatives=int((non_null < 0).sum()),
            named_measure=any(h in lower for h in MEASURE_HINTS),
            rate=is_rate(name),
        )
        return info

    # Text-like column
    if info['n_unique'] <= 2:
        info['role'] = 'flag'
        return info

    geo_mode = geo_maps.detect_map_mode(non_null, name)
    if geo_mode:
        info.update(role='geo', geo_mode=geo_mode)
        return info

    if info['unique_ratio'] > 0.9 and info['n_unique'] > 30:
        info['role'] = 'identifier'
        return info

    counts = non_null.astype(str).value_counts()
    info.update(
        role='category',
        top_value=str(counts.index[0]),
        top_share=round(100 * counts.iloc[0] / len(non_null), 1),
    )
    return info


def profile_dataframe(dataframe):
    """Profile every column. Large frames are sampled to keep this instant."""
    frame = dataframe.sample(PROFILE_SAMPLE_ROWS, random_state=0) if len(dataframe) > PROFILE_SAMPLE_ROWS else dataframe
    return [profile_column(frame[col], col) for col in frame.columns]


def by_role(profiles, *roles):
    return [p for p in profiles if p['role'] in roles]


def is_rate(name):
    """True for a measure that is a rate, where a total means nothing.

    Matched on the readable name, so 'Q_UnitPrice' is caught the same as
    'unit_price'. Word boundaries matter: 'rate' must not fire on 'Corporate'.
    """
    words = humanize(name).lower()
    padded = f" {words} "
    return any(
        hint in words if " " in hint else f" {hint} " in padded
        for hint in RATE_HINTS
    )


def agg_for(profiles, metric):
    """'mean' for a rate column, 'sum' for a real measure.

    Everything that groups a measure asks this first, so a per-unit price is
    averaged across a group instead of being added up into a meaningless total.
    """
    profile = next((p for p in profiles if p['name'] == metric), None)
    return 'mean' if profile and profile.get('rate') else 'sum'


def agg_word(how):
    """'Total' or 'Average', for chart titles and KPI labels."""
    return "Average" if how == 'mean' else "Total"


MAX_DATE_TRIM = 0.05        # never drop more than this share to tidy an axis


def usable_date_window(dates):
    """The date range worth plotting, or None when the whole range is fine.

    One 1900 placeholder in an order-date column turns a year of trading into a
    single spike at the right-hand edge: the axis spans a century, the monthly
    grouper manufactures 1,400 empty buckets, and the real shape of the data
    disappears. This finds the range the records actually live in.

    It only fires when an axis is genuinely being distorted, and never discards
    more than a twentieth of the rows - data that really is spread over decades
    is left exactly as it is.
    """
    if len(dates) < 20:
        return None

    low, high = dates.quantile(0.01), dates.quantile(0.99)
    inner_span = (high - low).days
    full_span = (dates.max() - dates.min()).days

    # Stragglers have to stretch the axis by a lot before it is worth cutting
    # them: three times the span the bulk of the data occupies, and at least an
    # extra year on top.
    if inner_span <= 0 or full_span < max(inner_span * 3, inner_span + 365):
        return None

    # The quantiles find the bulk of the data, but cutting exactly there would
    # also throw away the newest few days - and the trend chart's headline is
    # "the most recent period", so those are the last rows that may be lost.
    # Widening by a full inner span keeps everything near the real data and
    # still leaves a placeholder from another century far outside.
    margin = pd.Timedelta(days=max(inner_span, 30))
    low, high = low - margin, high + margin

    outside = int(((dates < low) | (dates > high)).sum())
    if outside == 0 or outside > len(dates) * MAX_DATE_TRIM:
        return None

    return low, high


def rank_measures(profiles):
    """Most business-relevant measures first.

    Rates sort last however well named they are: a report headlined by an
    average unit price tells the reader far less than one headlined by revenue.
    """
    measures = by_role(profiles, 'measure')
    return sorted(
        measures,
        key=lambda p: (not p.get('rate', False), p.get('named_measure', False), p.get('std', 0)),
        reverse=True,
    )


def rank_categories(profiles):
    """Dimensions that actually split the data usefully (2-50 buckets)."""
    categories = [p for p in by_role(profiles, 'category', 'geo', 'flag') if 2 <= p['n_unique'] <= 50]
    return sorted(categories, key=lambda p: abs(p['n_unique'] - 8))


# --------------------------------------------------------------------------- #
# "What this data can show you"
# --------------------------------------------------------------------------- #

ROLE_LABELS = {
    'measure': ('📈 Measure', 'Can be summed, averaged and trended'),
    'category': ('🏷️ Dimension', 'Good for grouping, ranking and filtering'),
    'date': ('📅 Timeline', 'Unlocks trends, growth and seasonality'),
    'geo': ('🌍 Geography', 'Can be drawn on a map'),
    'flag': ('🔘 Flag', 'Two-state field - good for split comparisons'),
    'identifier': ('🔑 Identifier', 'Unique per row - used for counting, not charting'),
    'empty': ('🚫 Empty', 'No usable values'),
}


def render_data_story(profiles, dataframe, key_prefix=""):
    """The 'here is what your data can show' panel.

    Collapsed by default: it is reference material you consult once, and left
    open it pushes the actual reports below the fold.
    """
    rows = []
    for profile in profiles:
        label, meaning = ROLE_LABELS.get(profile['role'], ('❔ Unknown', ''))
        rows.append({
            'Column (as shown)': humanize(profile['name']),
            'Original name': profile['name'],
            'Detected as': label,
            'Why it matters': meaning,
            'Distinct values': profile['n_unique'],
            'Missing %': profile['missing_pct'],
        })

    show = st.toggle("🧭 What this data can show you", value=False,
                     key=f"story_{key_prefix}",
                     help="Every column, what the app decided it is, and why that matters")
    if show:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    measures = rank_measures(profiles)
    categories = rank_categories(profiles)
    dates = by_role(profiles, 'date')
    geos = by_role(profiles, 'geo')

    summary = [
        f"**{len(dataframe):,}** rows × **{len(dataframe.columns)}** columns",
        f"**{len(measures)}** measure(s)",
        f"**{len(categories)}** usable dimension(s)",
    ]
    if dates:
        summary.append(f"**{len(dates)}** date column(s)")
    if geos:
        summary.append(f"**{len(geos)}** geography column(s)")

    st.info("📌 " + " · ".join(summary))


# --------------------------------------------------------------------------- #
# Scenario builders
# --------------------------------------------------------------------------- #

def _kpi_row(dataframe, profiles):
    measures = rank_measures(profiles)[:3]
    categories = rank_categories(profiles)

    tiles = st.columns(1 + len(measures) + (1 if categories else 0))
    show_kpi(tiles[0], "📊 Records", f"{len(dataframe):,}")

    for slot, measure in zip(tiles[1:], measures):
        name = humanize(measure['name'])
        if measure.get('rate'):
            # A per-unit figure has no meaningful total, so headline the average.
            value, word, note = measure.get('mean', 0), "Average", f"Highest: {measure.get('maximum', 0):,.2f}"
        else:
            value, word, note = measure.get('total', 0), "Total", f"Average per record: {measure.get('mean', 0):,.2f}"
        # "Total Total Amount" reads badly - do not prefix a name that already says it.
        label = name if name.lower().startswith(word.lower()) else f"{word} {name}"
        show_kpi(slot, label, f"{value:,.0f}", note)

    if categories:
        primary = categories[0]
        show_kpi(tiles[-1], f"Different {humanize(primary['name'])}s", f"{primary['n_unique']:,}",
                 f"Most common: {primary.get('top_value', '-')}")


def scenario_executive(dataframe, profiles, key_prefix):
    """Headline numbers plus the single most important breakdown."""
    _kpi_row(dataframe, profiles)
    st.divider()

    categories = rank_categories(profiles)
    measures = rank_measures(profiles)

    if not categories:
        st.info("No grouping dimension found, so there is nothing to break the totals down by.")
        return

    dimension = categories[0]['name']
    left, right = st.columns(2)

    dim_label = humanize(dimension)

    # This section splits a whole into shares, so it needs a measure that can be
    # added up. A rate has no total to divide - "35% of the average unit price"
    # is not a sentence - so fall back to counting records instead.
    totalable = [m for m in measures if not m.get('rate')]

    if totalable:
        measure = totalable[0]['name']
        agg = dataframe.groupby(dimension, dropna=True)[measure].sum().sort_values(ascending=False).head(12).reset_index()
        value_col = measure
        value_label = humanize(measure)
    else:
        agg = dataframe[dimension].value_counts().head(12).reset_index()
        agg.columns = [dimension, 'Records']
        value_col = 'Records'
        value_label = "Number of Records"

    with left:
        chart_heading(f"📊 Chart 1 — Which {dim_label} brings the most {value_label}?")
        fig = px.bar(agg, x=dimension, y=value_col, color=dimension, text_auto='.2s',
                     title=f"{value_label} by {dim_label}", color_discrete_sequence=PALETTE,
                     labels={dimension: dim_label, value_col: value_label})
        fig.update_layout(showlegend=False, xaxis_tickangle=-40, height=420)
        show_chart(fig, f"exec_bar_{key_prefix}")
        explain(f"Each bar is one {dim_label}. Taller bar = more {value_label}. "
                "The tallest bar on the left is your biggest contributor.")

    with right:
        chart_heading(f"🥧 Chart 2 — How is {value_label} split across {dim_label}?")
        fig = px.pie(agg, names=dimension, values=value_col, hole=0.45,
                     title=f"Share of {value_label}", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(height=420)
        show_chart(fig, f"exec_pie_{key_prefix}")
        explain("The whole circle is your total. Each slice shows how big that "
                f"{dim_label}'s share is — a big slice means heavy dependence on one name.")

    total = agg[value_col].sum()
    if total:
        leader = agg.iloc[0]
        share = pct(leader[value_col], total)
        takeaway(
            f"**{leader[dimension]}** is the biggest {dim_label}, contributing "
            f"**{leader[value_col]:,.0f}** ({share}%) of the {value_label} shown here."
            + (f" That is more than the rest put together — a real dependency risk." if share > 50 else "")
        )


def scenario_trend(dataframe, profiles, key_prefix):
    """How the numbers move over time, with period-on-period growth."""
    dates = by_role(profiles, 'date')
    measures = rank_measures(profiles)

    date_col = pick("📅 Which date column?", [p['name'] for p in dates],
                    f"auto_date_{key_prefix}", format_func=humanize)
    metric_options = [m['name'] for m in measures] + ["Record count"]
    metric = pick("📈 What do you want to track?", metric_options,
                  f"auto_trendmetric_{key_prefix}", format_func=metric_label)

    frame = dataframe[[date_col] + ([metric] if metric != "Record count" else [])].copy()
    frame[date_col] = parse_dates(frame[date_col])
    frame = frame.dropna(subset=[date_col])

    if frame.empty:
        st.info("No valid dates to plot.")
        return

    window = usable_date_window(frame[date_col])
    trimmed = 0
    if window:
        low, high = window
        before = len(frame)
        frame = frame[(frame[date_col] >= low) & (frame[date_col] <= high)]
        trimmed = before - len(frame)

    span_days = (frame[date_col].max() - frame[date_col].min()).days
    freq, freq_label = ('D', 'Daily') if span_days <= 90 else (('W', 'Weekly') if span_days <= 730 else ('MS', 'Monthly'))

    how = 'sum' if metric == "Record count" else agg_for(profiles, metric)
    grouper = pd.Grouper(key=date_col, freq=freq)
    if metric == "Record count":
        series = frame.groupby(grouper).size().reset_index(name='Value')
    else:
        series = frame.groupby(grouper)[metric].agg(how).reset_index().rename(columns={metric: 'Value'})

    series = series[series['Value'].notna()]

    label = metric_label(metric)
    if how == 'mean':
        label = f"Average {label}"
    chart_heading(f"📈 Chart — How has {label} changed over time?")

    fig = px.area(series, x=date_col, y='Value', markers=True,
                  title=f"{label} over time ({freq_label.lower()})",
                  color_discrete_sequence=['#2563eb'],
                  labels={'Value': label, date_col: humanize(date_col)})
    fig.update_layout(height=420, hovermode='x unified')
    show_chart(fig, f"trend_area_{key_prefix}")
    explain(
        f"Time runs left to right. The line going up means {label} is growing, "
        "going down means it is falling. Hover any point to see that period's exact number."
        + (f" {trimmed} record(s) carried a date far outside this range — most likely a typo or "
           f"a placeholder — and were left out so the chart is not squashed flat by them."
           if trimmed else "")
    )

    if len(series) >= 2:
        latest, previous = series['Value'].iloc[-1], series['Value'].iloc[-2]
        change = ((latest - previous) / previous * 100) if previous else 0
        peak = series.loc[series['Value'].idxmax()]

        col1, col2, col3 = st.columns(3)
        col1.metric("Latest period", f"{latest:,.0f}", f"{change:+.1f}% vs previous")
        col2.metric("Best period ever", f"{peak['Value']:,.0f}", help=str(peak[date_col].date()))
        col3.metric("Typical period", f"{series['Value'].mean():,.0f}")

        direction = "up" if change > 0 else ("down" if change < 0 else "flat")
        takeaway(
            f"The most recent period recorded **{latest:,.0f}** {label}, which is "
            f"**{abs(change):.1f}% {direction}** compared with the period before it. "
            f"The best period so far was **{peak[date_col].date()}** with {peak['Value']:,.0f}."
        )


def scenario_ranking(dataframe, profiles, key_prefix):
    """Who is on top, and how concentrated the total is (80/20 rule)."""
    categories = rank_categories(profiles)
    measures = rank_measures(profiles)

    dimension = pick("🏷️ Rank which group?", [c['name'] for c in categories],
                     f"auto_rankdim_{key_prefix}", format_func=humanize)
    metric_options = [m['name'] for m in measures] + ["Record count"]
    metric = pick("📊 Rank them by what?", metric_options,
                  f"auto_rankmetric_{key_prefix}", format_func=metric_label)

    if metric == "Record count":
        how = 'sum'
        agg = dataframe[dimension].value_counts().reset_index()
        agg.columns = [dimension, 'Value']
    else:
        how = agg_for(profiles, metric)
        agg = dataframe.groupby(dimension)[metric].agg(how).sort_values(ascending=False).reset_index()
        agg = agg.rename(columns={metric: 'Value'})

    agg = agg[agg['Value'].notna()].sort_values('Value', ascending=False)
    if agg.empty:
        st.info("Nothing to rank.")
        return

    agg['Cumulative %'] = 100 * agg['Value'].cumsum() / agg['Value'].sum()

    left, right = st.columns([3, 2])

    dim_label, value_label = humanize(dimension), metric_label(metric)
    if how == 'mean':
        value_label = f"Average {value_label}"

    with left:
        chart_heading(f"🏆 Chart 1 — Your top {dim_label}s by {value_label}")
        top = agg.head(15).sort_values('Value')
        fig = px.bar(top, x='Value', y=dimension, orientation='h', text_auto='.2s',
                     title=f"Top {len(top)} {dim_label}s by {value_label}", color='Value',
                     color_continuous_scale='Blues',
                     labels={'Value': value_label, dimension: dim_label})
        fig.update_layout(height=460, coloraxis_showscale=False)
        show_chart(fig, f"rank_bar_{key_prefix}")
        explain("The longest bar at the top is your best performer. "
                "Bars are sorted, so you read this list from top to bottom.")

    # 80/20 only means something when the values add up to a whole. Running a
    # cumulative share across averages produces a line that looks right and says
    # nothing, so that chart is simply not built for a rate.
    if how == 'mean':
        leader = agg.iloc[0]
        takeaway(
            f"**{leader[dimension]}** has the highest {value_label} at **{leader['Value']:,.2f}**, "
            f"against an overall average of {agg['Value'].mean():,.2f}. "
            "There is no 80/20 split to report here — averages do not add up to a total."
        )
        return

    with right:
        chart_heading("📉 Chart 2 — Do a few names carry the business?")
        pareto = agg.head(30).reset_index(drop=True)
        fig = px.line(pareto, x=pareto.index + 1, y='Cumulative %', markers=True,
                      title="Running total share (Pareto)", color_discrete_sequence=['#dc2626'])
        fig.add_hline(y=80, line_dash="dash", line_color="#94a3b8",
                      annotation_text="80% of the total", annotation_position="bottom right")
        fig.update_layout(height=460, xaxis_title=f"Number of {dim_label}s (best first)",
                          yaxis_title="% of total covered")
        show_chart(fig, f"rank_pareto_{key_prefix}")
        explain("Start at the left and add up your best performers one by one. "
                "Where the line crosses the dashed 80% mark tells you how few names "
                "make up most of the business.")

    needed = int((agg['Cumulative %'] < 80).sum()) + 1
    share = pct(needed, len(agg))
    takeaway(
        f"Just **{needed} out of {len(agg)}** {dim_label}s ({share}% of them) generate **80% of "
        f"all {value_label}**. "
        + ("That is heavy concentration — losing one of these would hurt badly, so protect them."
           if share <= 30 else
           "That is fairly evenly spread, so no single name is critical to the business.")
    )


def scenario_distribution(dataframe, profiles, key_prefix):
    """Shape of each measure, plus the outliers hiding in it."""
    measures = rank_measures(profiles)
    metric = pick("🔢 Which number do you want to examine?", [m['name'] for m in measures],
                  f"auto_dist_{key_prefix}", format_func=humanize)

    values = pd.to_numeric(dataframe[metric], errors='coerce').dropna()
    if values.empty:
        st.info("No numeric values in this column.")
        return

    left, right = st.columns([3, 2])

    label = humanize(metric)

    with left:
        chart_heading(f"📊 Chart 1 — What is a normal {label}?")
        fig = px.histogram(values, nbins=40, title=f"How {label} values are spread",
                           color_discrete_sequence=['#2563eb'])
        fig.update_layout(height=400, showlegend=False, xaxis_title=label,
                          yaxis_title="How many records")
        show_chart(fig, f"dist_hist_{key_prefix}")
        explain(f"Each bar counts how many records fall in that {label} range. The tallest "
                "bar is your most common value - that is what normal looks like.")

    with right:
        chart_heading(f"📦 Chart 2 — Any unusual {label} values?")
        fig = px.box(values, title=f"Typical range and odd values in {label}",
                     color_discrete_sequence=['#0ea5e9'])
        fig.update_layout(height=400, showlegend=False, yaxis_title=label)
        show_chart(fig, f"dist_box_{key_prefix}")
        explain("The box holds the middle half of your records. Dots sitting far away from "
                "the box are unusual values worth checking.")

    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = values[(values < low) | (values > high)]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Middle value", f"{values.median():,.2f}",
                help="Half the records are above this, half below")
    col2.metric("Average", f"{values.mean():,.2f}")
    col3.metric("Highest", f"{values.max():,.2f}")
    col4.metric("Unusual values", f"{len(outliers):,}",
                help=f"Outside the normal range {low:,.2f} to {high:,.2f}")

    skewed = abs(values.mean() - values.median()) > 0.3 * (values.std() or 1)
    takeaway(
        f"A typical {label} is around **{values.median():,.2f}**, and most records sit between "
        f"**{low:,.2f}** and **{high:,.2f}**."
        + (" The average is well above the middle value, so a few very large records are "
           "pulling it up - averages will mislead you here." if skewed else "")
    )

    if len(outliers):
        st.warning(
            f"⚠️ **{len(outliers):,} record(s)** ({pct(len(outliers), len(values))}%) fall far outside "
            f"that range for {label}. Check whether these are genuine big deals or typing mistakes - "
            "they distort every total on this dashboard."
        )


def scenario_relationships(dataframe, profiles, key_prefix):
    """Which measures move together - and how strongly."""
    measures = [m['name'] for m in rank_measures(profiles)]
    numeric = dataframe[measures].apply(pd.to_numeric, errors='coerce')
    correlation = numeric.corr(numeric_only=True)

    left, right = st.columns([2, 3])

    readable = correlation.rename(index=humanize, columns=humanize)

    with left:
        chart_heading("🔗 Chart 1 — Which numbers move together?")
        fig = px.imshow(readable, text_auto='.2f', aspect='auto',
                        color_continuous_scale='RdBu_r', zmin=-1, zmax=1,
                        title="Relationship strength between your numbers")
        fig.update_layout(height=430)
        show_chart(fig, f"corr_heatmap_{key_prefix}")
        explain("Find where a row and a column meet. A score near **+1** (red) means the two "
                "rise together, near **-1** (blue) means one falls as the other rises, and "
                "near **0** means they are unrelated.")

    pairs = []
    for i, first in enumerate(measures):
        for second in measures[i + 1:]:
            value = correlation.loc[first, second]
            if pd.notna(value):
                pairs.append((first, second, value))

    if not pairs:
        with right:
            st.info("Not enough overlapping numeric data to compare measures.")
        return

    pairs.sort(key=lambda item: abs(item[2]), reverse=True)
    first, second, strength = pairs[0]

    first_label, second_label = humanize(first), humanize(second)

    with right:
        chart_heading(f"🎯 Chart 2 — {first_label} vs {second_label}")
        colour_by = rank_categories(profiles)
        colour = colour_by[0]['name'] if colour_by else None
        labels = {first: first_label, second: second_label}
        if colour:
            labels[colour] = humanize(colour)
        fig = px.scatter(dataframe, x=first, y=second, color=colour, trendline=None,
                         title=f"{first_label} compared with {second_label}",
                         color_discrete_sequence=PALETTE, opacity=0.7, labels=labels)
        fig.update_layout(height=430)
        show_chart(fig, f"corr_scatter_{key_prefix}")
        explain("Every dot is one record. If the dots line up going upward the two numbers "
                "grow together; a shapeless cloud means they have little to do with each other.")

    direction = ("when one goes up the other goes up too" if strength > 0
                 else "when one goes up the other tends to go down")
    grade = "strong" if abs(strength) >= 0.7 else ("moderate" if abs(strength) >= 0.4 else "weak")
    takeaway(
        f"The closest link in your data is between **{first_label}** and **{second_label}** - "
        f"a {grade} relationship, meaning {direction}."
        + (" Strong enough to plan around." if abs(strength) >= 0.7
           else " Too weak to base decisions on." if abs(strength) < 0.4 else "")
    )


def scenario_crosstab(dataframe, profiles, key_prefix):
    """Two dimensions at once - where the volume actually sits."""
    categories = [c['name'] for c in rank_categories(profiles)]
    measures = rank_measures(profiles)

    if capture.active():
        rows = categories[0]
        cols = next((c for c in categories if c != rows), None)
        metric = ([m['name'] for m in measures] + ["Record count"])[0]
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            rows = pick("↕️ Down the side", categories,
                        f"auto_ctrow_{key_prefix}", format_func=humanize)
        with col2:
            remaining = [c for c in categories if c != rows]
            cols = pick("↔️ Across the top", remaining,
                        f"auto_ctcol_{key_prefix}", format_func=humanize)
        with col3:
            metric = pick("🔢 Show me", [m['name'] for m in measures] + ["Record count"],
                          f"auto_ctmetric_{key_prefix}", format_func=metric_label)

    how = 'sum' if metric == "Record count" else agg_for(profiles, metric)
    if metric == "Record count":
        matrix = pd.crosstab(dataframe[rows], dataframe[cols])
    else:
        matrix = pd.pivot_table(dataframe, index=rows, columns=cols, values=metric,
                                aggfunc=how, fill_value=0)

    # Rows and columns that hold nothing at all are dropped before anything is
    # drawn. A grid reading 0.00 in nine squares out of ten hides the very
    # pattern it exists to show, and an all-zero row is usually a value that
    # belongs to a different column entirely - a shifted cell in the source
    # sheet, not a real category.
    empty_rows = int((matrix.abs().sum(axis=1) == 0).sum())
    empty_cols = int((matrix.abs().sum(axis=0) == 0).sum())
    matrix = matrix.loc[matrix.abs().sum(axis=1) > 0, matrix.abs().sum(axis=0) > 0]

    if matrix.empty:
        st.info("Every combination of these two columns is empty, so there is no grid to draw.")
        return

    # Past a dozen each way the squares are too small to read on a page or in
    # the PDF, so only the busiest are kept.
    top_n = 12
    hidden = max(0, len(matrix.index) - top_n) + max(0, len(matrix.columns) - top_n)
    matrix = matrix.loc[matrix.sum(axis=1).sort_values(ascending=False).index[:top_n],
                        matrix.sum(axis=0).sort_values(ascending=False).index[:top_n]]

    row_label, col_label, value_label = humanize(rows), humanize(cols), metric_label(metric)
    if how == 'mean':
        value_label = f"Average {value_label}"
    chart_heading(f"🔥 Chart — Where does {value_label} pile up across {row_label} and {col_label}?")

    fig = px.imshow(matrix, text_auto='.3s', aspect='auto', color_continuous_scale='Blues',
                    title=f"{value_label} by {row_label} and {col_label}",
                    labels=dict(x=col_label, y=row_label, color=value_label))
    fig.update_layout(height=520)
    show_chart(fig, f"crosstab_heatmap_{key_prefix}")
    notes = []
    if empty_rows or empty_cols:
        parts = ([f"{empty_rows} {row_label}(s)"] if empty_rows else []) + \
                ([f"{empty_cols} {col_label}(s)"] if empty_cols else [])
        notes.append(f"{' and '.join(parts)} had no {value_label} at all and are not shown.")
    if hidden:
        notes.append(f"Only the busiest {top_n} each way are drawn.")

    explain(f"Every square is one {row_label} combined with one {col_label}. "
            "Darker squares hold more - the darkest square is your busiest combination, "
            "and empty pale areas are gaps you are not serving."
            + ("" if not notes else " " + " ".join(notes)))

    if matrix.size:
        flat = matrix.stack()
        peak_row, peak_col = flat.idxmax()
        takeaway(
            f"Your strongest combination is **{peak_row}** with **{peak_col}**, "
            f"reaching **{flat.max():,.0f}** {value_label}. "
            f"That is {pct(flat.max(), flat.sum())}% of everything shown in this grid."
        )


MISPLACED_MAX_HERE = 0.20    # a stray value must be rare in the column it turned up in
MISPLACED_MIN_RATIO = 3      # ...and this many times more common in its real home
SAME_KIND_OVERLAP = 0.5      # two columns sharing this much vocabulary are the same kind


def find_misplaced_values(dataframe, profiles, limit=4):
    """Values sitting in a column they do not belong to.

    A row that slipped a cell in the source spreadsheet leaves an order status
    in the Region column and a region in the Sales Rep column. Nothing errors -
    the reports simply draw a grid that is nine-tenths empty and rank performers
    who do not exist. The give-away is a value that is rare where it appears and
    common somewhere else.

    Returns [(column, home_column, [values]), ...], worst first.
    """
    names = [p['name'] for p in profiles if p['role'] in ('category', 'geo', 'flag')]
    if len(names) < 2:
        return []

    counts, totals = {}, {}
    for name in names:
        series = dataframe[name].dropna().astype(str).str.strip()
        series = series[series != '']
        if series.empty:
            continue
        counts[name] = series.value_counts()
        totals[name] = len(series)

    findings = []
    for here in counts:
        for home in counts:
            if here == home:
                continue
            shared = counts[here].index.intersection(counts[home].index)
            if not len(shared):
                continue

            # Billing City and Shipping City legitimately hold the same names.
            # Two columns of the same kind are not evidence of anything.
            if len(shared) > len(counts[here]) * SAME_KIND_OVERLAP:
                continue

            strays = [
                value for value in shared
                if counts[here][value] <= totals[here] * MISPLACED_MAX_HERE
                and counts[home][value] >= max(MISPLACED_MIN_RATIO,
                                               counts[here][value] * MISPLACED_MIN_RATIO)
            ]
            if strays:
                strays.sort(key=lambda v: counts[home][v], reverse=True)
                findings.append((here, home, strays))

    findings.sort(key=lambda item: len(item[2]), reverse=True)
    return findings[:limit]


def scenario_quality(dataframe, profiles, key_prefix):
    """Can these numbers be trusted? Missing data, duplicates, dead columns."""
    missing = pd.DataFrame({
        'Column': [humanize(p['name']) for p in profiles],
        'Missing %': [p['missing_pct'] for p in profiles],
        'Distinct': [p['n_unique'] for p in profiles],
    }).sort_values('Missing %', ascending=False)

    duplicates = int(dataframe.duplicated().sum())
    constants = [p['name'] for p in profiles if p['n_unique'] <= 1]
    empties = [p['name'] for p in profiles if p['missing_pct'] >= 100]
    complete = float((1 - dataframe.isna().sum().sum() / max(dataframe.size, 1)) * 100)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("How complete", f"{complete:.1f}%", help="Share of all cells that actually have a value")
    col2.metric("Repeated rows", f"{duplicates:,}")
    col3.metric("Useless columns", len(constants), help="Same value in every row")
    col4.metric("Blank columns", len(empties))

    chart_heading("🧪 Chart — Which columns have gaps in them?")
    fig = px.bar(missing.head(20), x='Missing %', y='Column', orientation='h',
                 title="Percentage of missing values, by column", color='Missing %',
                 color_continuous_scale='Reds', labels={'Column': 'Column'})
    fig.update_layout(height=460, coloraxis_showscale=False)
    show_chart(fig, f"quality_missing_{key_prefix}")
    explain("A longer red bar means more blank cells in that column. Anything past roughly "
            "20% is risky - charts built on it are only telling part of the story.")

    notes = []
    worst = missing.iloc[0]
    if worst['Missing %'] > 20:
        notes.append(f"**{worst['Column']}** is {worst['Missing %']}% empty - any chart built on it "
                     "is missing a big chunk of reality.")
    if duplicates:
        notes.append(f"**{duplicates:,}** row(s) appear more than once - your totals are counting "
                     "the same thing twice.")
    if constants:
        names = ', '.join(humanize(c) for c in constants[:5])
        notes.append(f"These columns hold the same value in every row and tell you nothing: {names}.")

    for column, home, strays in find_misplaced_values(dataframe, profiles):
        shown = ', '.join(f"**{value}**" for value in strays[:4])
        more = f" and {len(strays) - 4} more" if len(strays) > 4 else ""
        notes.append(
            f"**{humanize(column)}** contains {shown}{more} - values that belong in "
            f"**{humanize(home)}**. Rows like these have almost certainly slipped a cell in the "
            f"source sheet, which is what leaves empty bars and blank squares in the other reports."
        )

    for note in notes:
        warn(note)

    if notes:
        st.caption("👉 Fix these in the source sheet, then sync again - every number above improves.")
    else:
        takeaway("Your data is clean - no duplicate rows, no dead columns and very few gaps. "
                 "You can trust the numbers on the other tabs.")


def scenario_geography(dataframe, profiles, key_prefix):
    """Maps, driven by whichever geography column the data carries."""
    categories = dataframe.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    measures = rank_measures(profiles)
    metric = pick("🗺️ What should the map show?",
                  [m['name'] for m in measures] + ["Count (Frequency)"],
                  f"auto_geometric_{key_prefix}", format_func=metric_label)
    # Heading, then map, then the explanation - the same order as every other
    # scenario, so the captured blocks read correctly in the PDF too.
    chart_heading(f"🌍 Chart — Where does {metric_label(metric)} sit on the map?")
    geo_maps.render_geo_section(dataframe, categories, metric, f"auto_{key_prefix}")
    explain("Darker areas and bigger pins mean higher numbers. Hover any place to see its "
            "exact value, and scroll to zoom in.")


# --------------------------------------------------------------------------- #
# Scenario selection
# --------------------------------------------------------------------------- #

def build_scenarios(dataframe, profiles):
    """Pick only the scenarios this particular dataset can genuinely support."""
    measures = rank_measures(profiles)
    categories = rank_categories(profiles)
    dates = by_role(profiles, 'date')
    geos = by_role(profiles, 'geo')

    scenarios = [{
        'title': "📊 Business Overview",
        'why': "Your headline numbers and who is driving them. Start here.",
        'question': "How is the business doing overall, and who contributes most?",
        'render': scenario_executive,
    }]

    if dates:
        scenarios.append({
            'title': "📈 Growth Over Time",
            'why': f"Your sheet has real dates in '{humanize(dates[0]['name'])}', so we can track "
                   "whether things are improving or slipping.",
            'question': "Are we growing, flat, or falling - and when were our best periods?",
            'render': scenario_trend,
        })

    if categories:
        scenarios.append({
            'title': "🏆 Top Performers",
            'why': "Your data has groups worth comparing, so we ranked them and checked how much "
                   "of the business the top few actually carry.",
            'question': "Who are our best performers, and how dependent are we on them?",
            'render': scenario_ranking,
        })

    if measures:
        scenarios.append({
            'title': "📉 What Is Normal",
            'why': "You have numbers we can measure, so we worked out what a typical value looks "
                   "like and flagged anything strange.",
            'question': "What is a normal value here, and which records look wrong?",
            'render': scenario_distribution,
        })

    if len(measures) >= 2:
        scenarios.append({
            'title': "🔗 What Affects What",
            'why': f"You have {len(measures)} numbers, so we tested every pair to see which ones "
                   "move together.",
            'question': "When one number changes, which other numbers change with it?",
            'render': scenario_relationships,
        })

    if len(categories) >= 2:
        scenarios.append({
            'title': "🧮 Best Combinations",
            'why': "With two or more groups in your data, combining them reveals pockets that a "
                   "single chart hides.",
            'question': "Which combination of groups is performing best, and where are the gaps?",
            'render': scenario_crosstab,
        })

    if geos:
        scenarios.append({
            'title': "🌍 Location Map",
            'why': f"'{humanize(geos[0]['name'])}' contains real places, so your data can be "
                   "drawn on a map.",
            'question': "Which places bring the most business, and where are we absent?",
            'render': scenario_geography,
        })

    scenarios.append({
        'title': "🧪 Can You Trust This Data",
        'why': "Every number on the other tabs is only as good as the sheet underneath it.",
        'question': "Are there gaps, duplicates or dead columns that make these charts unreliable?",
        'render': scenario_quality,
    })

    return scenarios


def build_data_digest(dataframe, profiles, max_values=40):
    """A compact, factual description of this dataset for the AI to answer from.

    The chat used to be handed nothing but a list of column names, so it could
    not answer anything and fell back on explaining how to do it yourself in
    Excel. This gives it the actual distributions - distinct values and their
    counts for dimensions, real totals and ranges for measures - so answers come
    from the data instead of from general knowledge.

    Statistics only. Raw rows never leave the server.
    """
    lines = [
        f"DATASET: {len(dataframe):,} rows x {len(dataframe.columns)} columns.",
        "",
    ]

    for profile in profiles:
        name = profile["name"]
        readable = humanize(name)
        role = profile["role"]
        head = f"- {readable} (raw column '{name}') [{role}], {profile['n_unique']} distinct, {profile['missing_pct']}% missing"

        if role == "measure":
            lines.append(
                head + f", total={profile.get('total', 0):,.2f}"
                f", mean={profile.get('mean', 0):,.2f}"
                f", median={profile.get('median', 0):,.2f}"
                f", min={profile.get('minimum', 0):,.2f}"
                f", max={profile.get('maximum', 0):,.2f}"
            )
        elif role == "date":
            lines.append(head + f", from {profile.get('min')} to {profile.get('max')}")
        elif role in ("category", "geo", "flag"):
            counts = dataframe[name].dropna().astype(str).value_counts()
            shown = counts.head(max_values)
            listed = ", ".join(f"{value} ({count})" for value, count in shown.items())
            more = "" if len(counts) <= max_values else f", …and {len(counts) - max_values} more"
            lines.append(head + f"\n    values: {listed}{more}")
        else:
            lines.append(head)

    return "\n".join(lines)


DATA_ONLY_RULES = """
ANSWER ONLY FROM THE DATA SUMMARY ABOVE.

- Base every number and every claim on that summary. Do not use outside knowledge.
- If the summary does not contain what is needed, say exactly that in one line and
  name the column or figure that is missing. Do not guess.
- Never explain how the user could work it out themselves. Do not suggest Excel
  steps, pivot tables, SQL queries or Python code. Do not output code of any kind.
- Never ask the user to paste their data - you already have the summary.
- Give the answer first, in one or two sentences, then the supporting numbers.
- Use the readable column names, not the raw ones.
"""


def build_ai_briefing(dataframe, profiles, scenarios):
    """Compact, privacy-friendly profile text for the AI - stats only, no raw rows."""
    lines = [f"Dataset: {len(dataframe):,} rows x {len(dataframe.columns)} columns.", "", "COLUMNS:"]

    for profile in profiles:
        bits = [f"- {profile['name']} [{profile['role']}]",
                f"distinct={profile['n_unique']}", f"missing={profile['missing_pct']}%"]
        if profile['role'] == 'measure':
            bits.append(f"total={profile.get('total', 0):,.2f}")
            bits.append(f"mean={profile.get('mean', 0):,.2f}")
            bits.append(f"min={profile.get('minimum', 0):,.2f}")
            bits.append(f"max={profile.get('maximum', 0):,.2f}")
        elif profile['role'] == 'category':
            bits.append(f"most_common={profile.get('top_value')} ({profile.get('top_share')}%)")
        elif profile['role'] == 'date':
            bits.append(f"range={profile.get('min')} to {profile.get('max')}")
        lines.append(", ".join(bits))

    lines += ["", "DASHBOARDS BUILT: " + ", ".join(s['title'] for s in scenarios)]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def _slug(text):
    """Widget-key-safe version of a sheet name."""
    return re.sub(r'[^a-zA-Z0-9]+', '_', str(text)).strip('_').lower() or 'sheet'


def render_sheet_sections(sheets, key_prefix, ai_callback=None):
    """One self-contained section per sheet, plus an automatic comparison.

    Sheets are never merged for analysis. Different sheets have different
    columns, and concatenating them produces a table that is mostly blank -
    every total then looks broken. Each sheet is profiled on its own.
    """
    names = list(sheets.keys())

    if len(names) == 1:
        # Pass the name even with one sheet - it titles the PDF and names its file.
        render_auto_dashboard(sheets[names[0]], key_prefix, ai_callback,
                              sheet_name=names[0])
        return

    st.info(
        f"📚 **{len(names)} sheets loaded.** Each one gets its own section below, because "
        "sheets with different columns must be measured separately. The last section "
        "compares them."
    )

    labels = [f"📄 {name}" for name in names] + ["⚖️ Auto Compare"]

    # Streamlit renders every tab eagerly, so past a handful of sheets a picker
    # keeps the page fast instead of building dozens of charts at once.
    if len(names) <= 4:
        tabs = st.tabs(labels)
        for tab, name in zip(tabs, names):
            with tab:
                _render_one_sheet(name, sheets[name], key_prefix, ai_callback)
        with tabs[-1]:
            render_comparison(sheets, key_prefix)
        return

    choice = st.selectbox("Which sheet do you want to look at?", labels, key=f"sheetpick_{key_prefix}")
    if choice == "⚖️ Auto Compare":
        render_comparison(sheets, key_prefix)
    else:
        name = names[labels.index(choice)]
        _render_one_sheet(name, sheets[name], key_prefix, ai_callback)


def _render_one_sheet(name, dataframe, key_prefix, ai_callback):
    st.markdown(f"### 📄 Sheet: {name}")
    st.caption(f"{len(dataframe):,} rows × {len(dataframe.columns)} columns — analysed on its own.")
    render_auto_dashboard(dataframe, f"{key_prefix}_{_slug(name)}", ai_callback, sheet_name=name)


# --------------------------------------------------------------------------- #
# Auto comparison across sheets
# --------------------------------------------------------------------------- #

def _readable_column_map(frame):
    """{readable name: actual column} so sheets can be matched despite naming."""
    mapping = {}
    for column in frame.columns:
        mapping.setdefault(humanize(column).lower(), column)
    return mapping


def _role_of(profiles, column):
    for profile in profiles:
        if profile['name'] == column:
            return profile['role']
    return None


def render_comparison(sheets, key_prefix):
    """Compare sheets - on shared columns where they exist, on headlines otherwise."""
    st.markdown("### ⚖️ Auto Compare — how your sheets stack up")

    names = list(sheets.keys())
    profiles = {name: profile_dataframe(frame) for name, frame in sheets.items()}
    column_maps = {name: _readable_column_map(sheets[name]) for name in names}

    # ---- 1. Size ----------------------------------------------------------
    sizes = pd.DataFrame({
        'Sheet': names,
        'Rows': [len(sheets[name]) for name in names],
        'Columns': [len(sheets[name].columns) for name in names],
        'Numbers to measure': [len(rank_measures(profiles[name])) for name in names],
        'Groups to compare': [len(rank_categories(profiles[name])) for name in names],
    })

    chart_heading("📏 Chart 1 — How big is each sheet?")
    fig = px.bar(sizes, x='Sheet', y='Rows', color='Sheet', text_auto=True,
                 title="Records per sheet", color_discrete_sequence=PALETTE)
    fig.update_layout(height=380, showlegend=False)
    show_chart(fig, f"cmp_rows_{key_prefix}")
    explain("Each bar is one sheet — simply how much data it holds. A much smaller bar "
            "may mean that sheet is incomplete.")
    st.dataframe(sizes, use_container_width=True, hide_index=True)

    biggest = sizes.loc[sizes['Rows'].idxmax()]
    takeaway(f"**{biggest['Sheet']}** is your largest sheet with **{biggest['Rows']:,} records**, "
             f"out of {sizes['Rows'].sum():,} across all {len(names)} sheets.")

    # ---- 2. Headline number per sheet - works even with nothing in common --
    headline = []
    for name in names:
        measures = rank_measures(profiles[name])
        if measures:
            headline.append({
                'Sheet': name,
                'Headline number': humanize(measures[0]['name']),
                'Total': float(measures[0].get('total', 0)),
            })

    if headline:
        head_frame = pd.DataFrame(headline)
        chart_heading("💰 Chart 2 — The headline number in each sheet")
        fig = px.bar(head_frame, x='Sheet', y='Total', color='Sheet', text='Headline number',
                     title="Each sheet's main number", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition='outside')
        fig.update_layout(height=420, showlegend=False)
        show_chart(fig, f"cmp_headline_{key_prefix}")
        explain("Every sheet has one number that matters most — the label on each bar says "
                "which one. These may be different things, so compare the scale, not the meaning.")

        top = head_frame.loc[head_frame['Total'].idxmax()]
        takeaway(f"**{top['Sheet']}** carries the largest headline figure: "
                 f"**{top['Headline number']} = {top['Total']:,.0f}**.")

    # ---- 3. What the sheets share ----------------------------------------
    shared = set.intersection(*[set(column_maps[name].keys()) for name in names])

    chart_heading("🧩 What do these sheets have in common?")
    if shared:
        st.success(f"✅ **{len(shared)} column(s)** appear in every sheet (matched by their "
                   "readable name), so they can be compared directly.")
    else:
        st.warning("⚠️ These sheets have no column in common, so only their size and headline "
                   "numbers can be compared. That usually means they describe different things "
                   "— sales orders versus purchases, for example.")

    with st.expander("See which columns are shared and which are unique to one sheet"):
        rows = []
        for name in names:
            unique = sorted(set(column_maps[name].keys()) - shared)
            preview = ", ".join(key.title() for key in unique[:8])
            rows.append({
                'Sheet': name,
                'Shared columns': len(shared),
                'Only in this sheet': (preview + ("…" if len(unique) > 8 else "")) or "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        if shared:
            st.caption("Shared: " + ", ".join(sorted(key.title() for key in shared)))

    if not shared:
        return

    # ---- 4. Shared measures, side by side ---------------------------------
    shared_measures = [
        key for key in sorted(shared)
        if all(_role_of(profiles[name], column_maps[name][key]) == 'measure' for name in names)
    ]

    if shared_measures:
        picked = st.multiselect(
            "Which numbers should we compare?",
            shared_measures, default=shared_measures[:3],
            format_func=str.title, key=f"cmp_measures_{key_prefix}",
        )

        if picked:
            totals = pd.DataFrame([
                {'Sheet': name, 'Measure': key.title(),
                 'Total': float(pd.to_numeric(sheets[name][column_maps[name][key]],
                                              errors='coerce').sum())}
                for name in names for key in picked
            ])

            chart_heading("📊 Chart 3 — Same numbers, sheet by sheet")
            fig = px.bar(totals, x='Measure', y='Total', color='Sheet', barmode='group',
                         text_auto='.2s', title="Shared totals compared across sheets",
                         color_discrete_sequence=PALETTE)
            fig.update_layout(height=430)
            show_chart(fig, f"cmp_measures_chart_{key_prefix}")
            explain("Bars are grouped by measure and coloured by sheet. Comparing bars inside "
                    "one group tells you which sheet carries more of that number.")

            lead = totals.loc[totals['Total'].idxmax()]
            takeaway(f"The biggest shared figure is **{lead['Measure']}** in **{lead['Sheet']}**, "
                     f"totalling **{lead['Total']:,.0f}**.")

    # ---- 5. Shared breakdown ----------------------------------------------
    shared_dims = []
    for key in sorted(shared):
        ok = True
        for name in names:
            column = column_maps[name][key]
            profile = next((p for p in profiles[name] if p['name'] == column), None)
            if not profile or profile['role'] not in ('category', 'geo', 'flag') \
                    or not (2 <= profile['n_unique'] <= 30):
                ok = False
                break
        if ok:
            shared_dims.append(key)

    if not shared_dims:
        return

    chart_heading("🔍 Chart 4 — The same breakdown in every sheet")
    control1, control2 = st.columns(2)
    with control1:
        dim_key = st.selectbox("Break down by", shared_dims, format_func=str.title,
                               key=f"cmp_dim_{key_prefix}")
    with control2:
        metric_key = st.selectbox("Measure", shared_measures + ["Record count"],
                                  format_func=lambda k: "Number of Records" if k == "Record count" else k.title(),
                                  key=f"cmp_dimmetric_{key_prefix}")

    frames = []
    for name in names:
        frame = sheets[name]
        dim_col = column_maps[name][dim_key]
        labels = frame[dim_col].astype(str).str.strip()

        if metric_key == "Record count":
            grouped = labels.value_counts().reset_index()
            grouped.columns = ['Group', 'Value']
        else:
            values = pd.to_numeric(frame[column_maps[name][metric_key]], errors='coerce')
            grouped = pd.DataFrame({'Group': labels, 'Value': values})
            grouped = grouped.dropna(subset=['Value']).groupby('Group', as_index=False)['Value'].sum()

        grouped['Sheet'] = name
        frames.append(grouped)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined['Group'].str.lower() != 'nan']
    top_groups = combined.groupby('Group')['Value'].sum().nlargest(12).index
    combined = combined[combined['Group'].isin(top_groups)]

    if combined.empty:
        return

    metric_name = "Number of Records" if metric_key == "Record count" else metric_key.title()
    fig = px.bar(combined, x='Group', y='Value', color='Sheet', barmode='group',
                 title=f"{metric_name} by {dim_key.title()}, per sheet",
                 labels={'Group': dim_key.title(), 'Value': metric_name},
                 color_discrete_sequence=PALETTE)
    fig.update_layout(height=460, xaxis_tickangle=-40)
    show_chart(fig, f"cmp_dim_chart_{key_prefix}")
    explain(f"Each cluster is one {dim_key.title()}, with one bar per sheet. A missing or tiny "
            "bar shows where a sheet is behind the others.")

    pivot = combined.pivot_table(index='Group', columns='Sheet', values='Value', aggfunc='sum').fillna(0)
    if len(pivot.columns) >= 2 and len(pivot):
        spread = (pivot.max(axis=1) - pivot.min(axis=1)).sort_values(ascending=False)
        widest = spread.index[0]
        row = pivot.loc[widest]
        takeaway(
            f"The widest gap between sheets is at **{widest}** — **{row.idxmax()}** records "
            f"{row.max():,.0f} while **{row.idxmin()}** records only {row.min():,.0f}."
        )


def render_export_panel(dataframe, scenarios, key_prefix, sheet_name=None):
    """Export the reports to PDF - all of them, or just the one you are reading.

    Charts are rendered by a headless browser, which takes a few seconds each.
    The default is therefore a single report; exporting all of them shows a
    progress bar rather than appearing to hang.
    """
    # Imported here rather than at module scope: report_export imports this
    # module, and Kaleido is heavy enough not to load until it is needed.
    import report_export

    state_key = f"pdf_bytes_{key_prefix}"
    name_key = f"pdf_name_{key_prefix}"

    with st.expander("📄 Export to PDF", expanded=False):
        scope_col, button_col = st.columns([3, 1])

        with scope_col:
            options = ["All reports"] + [scenario["title"] for scenario in scenarios]
            scope = st.selectbox(
                "What should the PDF contain?", options, key=f"pdf_scope_{key_prefix}",
                help="One report is quick. All of them takes about a minute.",
            )
        with button_col:
            st.write("")
            generate = st.button("Generate PDF", type="primary", use_container_width=True,
                                 key=f"pdf_go_{key_prefix}")

        chosen = scenarios if scope == "All reports" else [
            s for s in scenarios if s["title"] == scope
        ]

        if scope == "All reports":
            st.caption(f"All {len(scenarios)} reports, every chart included. "
                       "Rendering the charts takes roughly a minute.")

        if generate:
            progress = st.progress(0.0, text="Starting…")

            def report_progress(done, total, label):
                progress.progress(done / max(total, 1), text=f"{label} ({done}/{total})")

            try:
                pdf_bytes = report_export.build_pdf(
                    dataframe, chosen, sheet_name=sheet_name,
                    title=sheet_name or "Data Report" if scope == "All reports" else scope,
                    on_progress=report_progress,
                )
                progress.empty()
                st.session_state[state_key] = pdf_bytes
                stub = (sheet_name or "report").replace(" ", "_").lower()
                st.session_state[name_key] = (
                    f"{stub}_all_reports.pdf" if scope == "All reports"
                    else f"{stub}_{_slug(scope)}.pdf"
                )
                st.success(f"Ready — {len(pdf_bytes) / 1024:,.0f} KB")
            except Exception as error:
                progress.empty()
                st.error(f"The PDF could not be built: {error}")

        if st.session_state.get(state_key):
            st.download_button(
                "⬇️ Download PDF",
                st.session_state[state_key],
                file_name=st.session_state.get(name_key, "report.pdf"),
                mime="application/pdf",
                use_container_width=True,
                key=f"pdf_dl_{key_prefix}",
            )


def render_auto_dashboard(dataframe, key_prefix, ai_callback=None, sheet_name=None):
    """Profile the data, explain it, then build every scenario it supports."""
    if dataframe is None or dataframe.empty:
        st.info("Load some data to run the auto analyst.")
        return

    profiles = profile_dataframe(dataframe)
    render_data_story(profiles, dataframe, key_prefix)

    scenarios = build_scenarios(dataframe, profiles)

    render_export_panel(dataframe, scenarios, key_prefix, sheet_name)

    st.write(f"### 📑 {len(scenarios)} ready-made reports from your sheet")
    st.caption("Open any tab below. Each report answers one business question, and every chart "
               "comes with a plain-English explanation of what it shows and what it means.")

    tabs = st.tabs([scenario['title'] for scenario in scenarios])
    for tab, scenario in zip(tabs, scenarios):
        with tab:
            question = scenario.get('question')
            if question:
                st.markdown(f"#### ❓ {question}")
            st.caption(f"🧠 Why this report was built: {scenario['why']}")
            try:
                scenario['render'](dataframe, profiles, key_prefix)
            except Exception as error:
                st.warning(f"This report could not be built for the current data ({error}).")

    if ai_callback:
        st.divider()
        st.write("### 🧠 AI Analyst Briefing")
        if st.button("✨ Ask the AI what to look at", key=f"auto_ai_{key_prefix}"):
            briefing = build_ai_briefing(dataframe, profiles, scenarios)
            with st.spinner("Reading the profile and forming an opinion..."):
                ai_callback(briefing)
