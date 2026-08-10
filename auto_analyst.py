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

import geo_maps

# Column names that usually signal a real business measure worth totalling.
MEASURE_HINTS = (
    'amount', 'revenue', 'sales', 'price', 'cost', 'profit', 'margin', 'qty',
    'quantity', 'total', 'value', 'score', 'rating', 'salary', 'budget',
    'spend', 'income', 'balance', 'units', 'volume', 'weight', 'duration',
)

IDENTIFIER_HINTS = ('id', 'code', 'uuid', 'guid', 'ref', 'number', 'no', 'key', 'sr', 'srno')

DATE_HINTS = ('date', 'time', 'day', 'month', 'year', 'created', 'updated', 'timestamp', 'dob')

PROFILE_SAMPLE_ROWS = 50_000
PALETTE = px.colors.qualitative.Bold


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


def explain(text):
    """One plain-English line under a chart telling the user how to read it."""
    st.caption(f"📖 **How to read this:** {text}")


def takeaway(text):
    """The finding the chart actually shows, stated in words."""
    st.success(f"💡 **What it means:** {text}")


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


def rank_measures(profiles):
    """Most business-relevant measures first: named ones, then the most varied."""
    measures = by_role(profiles, 'measure')
    return sorted(measures, key=lambda p: (p.get('named_measure', False), p.get('std', 0)), reverse=True)


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


def render_data_story(profiles, dataframe):
    """The 'here is what your data can show' panel."""
    st.write("### 🧭 What this data can show you")

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
    tiles[0].metric("📊 Records", f"{len(dataframe):,}")

    for slot, measure in zip(tiles[1:], measures):
        total = measure.get('total', 0)
        slot.metric(f"Total {humanize(measure['name'])}", f"{total:,.0f}",
                    help=f"Average per record: {measure.get('mean', 0):,.2f}")

    if categories:
        primary = categories[0]
        tiles[-1].metric(f"Different {humanize(primary['name'])}s", f"{primary['n_unique']:,}",
                         help=f"Most common: {primary.get('top_value', '-')}")


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

    if measures:
        measure = measures[0]['name']
        agg = dataframe.groupby(dimension, dropna=True)[measure].sum().sort_values(ascending=False).head(12).reset_index()
        value_col = measure
        value_label = humanize(measure)
    else:
        agg = dataframe[dimension].value_counts().head(12).reset_index()
        agg.columns = [dimension, 'Records']
        value_col = 'Records'
        value_label = "Number of Records"

    with left:
        st.markdown(f"##### 📊 Chart 1 — Which {dim_label} brings the most {value_label}?")
        fig = px.bar(agg, x=dimension, y=value_col, color=dimension, text_auto='.2s',
                     title=f"{value_label} by {dim_label}", color_discrete_sequence=PALETTE,
                     labels={dimension: dim_label, value_col: value_label})
        fig.update_layout(showlegend=False, xaxis_tickangle=-40, height=420)
        st.plotly_chart(fig, use_container_width=True, key=f"exec_bar_{key_prefix}")
        explain(f"Each bar is one {dim_label}. Taller bar = more {value_label}. "
                "The tallest bar on the left is your biggest contributor.")

    with right:
        st.markdown(f"##### 🥧 Chart 2 — How is {value_label} split across {dim_label}?")
        fig = px.pie(agg, names=dimension, values=value_col, hole=0.45,
                     title=f"Share of {value_label}", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True, key=f"exec_pie_{key_prefix}")
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

    date_col = st.selectbox("📅 Which date column?", [p['name'] for p in dates],
                            format_func=humanize, key=f"auto_date_{key_prefix}")
    metric_options = [m['name'] for m in measures] + ["Record count"]
    metric = st.selectbox("📈 What do you want to track?", metric_options,
                          format_func=metric_label, key=f"auto_trendmetric_{key_prefix}")

    frame = dataframe[[date_col] + ([metric] if metric != "Record count" else [])].copy()
    frame[date_col] = parse_dates(frame[date_col])
    frame = frame.dropna(subset=[date_col])

    if frame.empty:
        st.info("No valid dates to plot.")
        return

    span_days = (frame[date_col].max() - frame[date_col].min()).days
    freq, freq_label = ('D', 'Daily') if span_days <= 90 else (('W', 'Weekly') if span_days <= 730 else ('MS', 'Monthly'))

    grouper = pd.Grouper(key=date_col, freq=freq)
    if metric == "Record count":
        series = frame.groupby(grouper).size().reset_index(name='Value')
    else:
        series = frame.groupby(grouper)[metric].sum().reset_index().rename(columns={metric: 'Value'})

    series = series[series['Value'].notna()]

    label = metric_label(metric)
    st.markdown(f"##### 📈 Chart — How has {label} changed over time?")

    fig = px.area(series, x=date_col, y='Value', markers=True,
                  title=f"{label} over time ({freq_label.lower()})",
                  color_discrete_sequence=['#2563eb'],
                  labels={'Value': label, date_col: humanize(date_col)})
    fig.update_layout(height=420, hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True, key=f"trend_area_{key_prefix}")
    explain(f"Time runs left to right. The line going up means {label} is growing, "
            "going down means it is falling. Hover any point to see that period's exact number.")

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

    dimension = st.selectbox("🏷️ Rank which group?", [c['name'] for c in categories],
                             format_func=humanize, key=f"auto_rankdim_{key_prefix}")
    metric_options = [m['name'] for m in measures] + ["Record count"]
    metric = st.selectbox("📊 Rank them by what?", metric_options,
                          format_func=metric_label, key=f"auto_rankmetric_{key_prefix}")

    if metric == "Record count":
        agg = dataframe[dimension].value_counts().reset_index()
        agg.columns = [dimension, 'Value']
    else:
        agg = dataframe.groupby(dimension)[metric].sum().sort_values(ascending=False).reset_index()
        agg = agg.rename(columns={metric: 'Value'})

    agg = agg[agg['Value'].notna()].sort_values('Value', ascending=False)
    if agg.empty:
        st.info("Nothing to rank.")
        return

    agg['Cumulative %'] = 100 * agg['Value'].cumsum() / agg['Value'].sum()

    left, right = st.columns([3, 2])

    dim_label, value_label = humanize(dimension), metric_label(metric)

    with left:
        st.markdown(f"##### 🏆 Chart 1 — Your top {dim_label}s by {value_label}")
        top = agg.head(15).sort_values('Value')
        fig = px.bar(top, x='Value', y=dimension, orientation='h', text_auto='.2s',
                     title=f"Top {len(top)} {dim_label}s by {value_label}", color='Value',
                     color_continuous_scale='Blues',
                     labels={'Value': value_label, dimension: dim_label})
        fig.update_layout(height=460, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True, key=f"rank_bar_{key_prefix}")
        explain("The longest bar at the top is your best performer. "
                "Bars are sorted, so you read this list from top to bottom.")

    with right:
        st.markdown("##### 📉 Chart 2 — Do a few names carry the business?")
        pareto = agg.head(30).reset_index(drop=True)
        fig = px.line(pareto, x=pareto.index + 1, y='Cumulative %', markers=True,
                      title="Running total share (Pareto)", color_discrete_sequence=['#dc2626'])
        fig.add_hline(y=80, line_dash="dash", line_color="#94a3b8",
                      annotation_text="80% of the total", annotation_position="bottom right")
        fig.update_layout(height=460, xaxis_title=f"Number of {dim_label}s (best first)",
                          yaxis_title="% of total covered")
        st.plotly_chart(fig, use_container_width=True, key=f"rank_pareto_{key_prefix}")
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
    metric = st.selectbox("🔢 Which number do you want to examine?", [m['name'] for m in measures],
                          format_func=humanize, key=f"auto_dist_{key_prefix}")

    values = pd.to_numeric(dataframe[metric], errors='coerce').dropna()
    if values.empty:
        st.info("No numeric values in this column.")
        return

    left, right = st.columns([3, 2])

    label = humanize(metric)

    with left:
        st.markdown(f"##### 📊 Chart 1 — What is a normal {label}?")
        fig = px.histogram(values, nbins=40, title=f"How {label} values are spread",
                           color_discrete_sequence=['#2563eb'])
        fig.update_layout(height=400, showlegend=False, xaxis_title=label,
                          yaxis_title="How many records")
        st.plotly_chart(fig, use_container_width=True, key=f"dist_hist_{key_prefix}")
        explain(f"Each bar counts how many records fall in that {label} range. The tallest "
                "bar is your most common value - that is what normal looks like.")

    with right:
        st.markdown(f"##### 📦 Chart 2 — Any unusual {label} values?")
        fig = px.box(values, title=f"Typical range and odd values in {label}",
                     color_discrete_sequence=['#0ea5e9'])
        fig.update_layout(height=400, showlegend=False, yaxis_title=label)
        st.plotly_chart(fig, use_container_width=True, key=f"dist_box_{key_prefix}")
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
        st.markdown("##### 🔗 Chart 1 — Which numbers move together?")
        fig = px.imshow(readable, text_auto='.2f', aspect='auto',
                        color_continuous_scale='RdBu_r', zmin=-1, zmax=1,
                        title="Relationship strength between your numbers")
        fig.update_layout(height=430)
        st.plotly_chart(fig, use_container_width=True, key=f"corr_heatmap_{key_prefix}")
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
        st.markdown(f"##### 🎯 Chart 2 — {first_label} vs {second_label}")
        colour_by = rank_categories(profiles)
        colour = colour_by[0]['name'] if colour_by else None
        labels = {first: first_label, second: second_label}
        if colour:
            labels[colour] = humanize(colour)
        fig = px.scatter(dataframe, x=first, y=second, color=colour, trendline=None,
                         title=f"{first_label} compared with {second_label}",
                         color_discrete_sequence=PALETTE, opacity=0.7, labels=labels)
        fig.update_layout(height=430)
        st.plotly_chart(fig, use_container_width=True, key=f"corr_scatter_{key_prefix}")
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

    col1, col2, col3 = st.columns(3)
    with col1:
        rows = st.selectbox("↕️ Down the side", categories, format_func=humanize,
                            key=f"auto_ctrow_{key_prefix}")
    with col2:
        remaining = [c for c in categories if c != rows]
        cols = st.selectbox("↔️ Across the top", remaining, format_func=humanize,
                            key=f"auto_ctcol_{key_prefix}")
    with col3:
        metric = st.selectbox("🔢 Show me", [m['name'] for m in measures] + ["Record count"],
                              format_func=metric_label, key=f"auto_ctmetric_{key_prefix}")

    if metric == "Record count":
        matrix = pd.crosstab(dataframe[rows], dataframe[cols])
    else:
        matrix = pd.pivot_table(dataframe, index=rows, columns=cols, values=metric,
                                aggfunc='sum', fill_value=0)

    matrix = matrix.loc[matrix.sum(axis=1).sort_values(ascending=False).index[:20],
                        matrix.sum(axis=0).sort_values(ascending=False).index[:20]]

    row_label, col_label, value_label = humanize(rows), humanize(cols), metric_label(metric)
    st.markdown(f"##### 🔥 Chart — Where does {value_label} pile up across {row_label} and {col_label}?")

    fig = px.imshow(matrix, text_auto='.3s', aspect='auto', color_continuous_scale='Blues',
                    title=f"{value_label} by {row_label} and {col_label}",
                    labels=dict(x=col_label, y=row_label, color=value_label))
    fig.update_layout(height=520)
    st.plotly_chart(fig, use_container_width=True, key=f"crosstab_heatmap_{key_prefix}")
    explain(f"Every square is one {row_label} combined with one {col_label}. "
            "Darker squares hold more - the darkest square is your busiest combination, "
            "and empty pale areas are gaps you are not serving.")

    if matrix.size:
        flat = matrix.stack()
        peak_row, peak_col = flat.idxmax()
        takeaway(
            f"Your strongest combination is **{peak_row}** with **{peak_col}**, "
            f"reaching **{flat.max():,.0f}** {value_label}. "
            f"That is {pct(flat.max(), flat.sum())}% of everything shown in this grid."
        )


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

    st.markdown("##### 🧪 Chart — Which columns have gaps in them?")
    fig = px.bar(missing.head(20), x='Missing %', y='Column', orientation='h',
                 title="Percentage of missing values, by column", color='Missing %',
                 color_continuous_scale='Reds', labels={'Column': 'Column'})
    fig.update_layout(height=460, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True, key=f"quality_missing_{key_prefix}")
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

    for note in notes:
        st.warning("⚠️ " + note)

    if notes:
        st.caption("👉 Fix these in the source sheet, then sync again - every number above improves.")
    else:
        takeaway("Your data is clean - no duplicate rows, no dead columns and very few gaps. "
                 "You can trust the numbers on the other tabs.")


def scenario_geography(dataframe, profiles, key_prefix):
    """Maps, driven by whichever geography column the data carries."""
    categories = dataframe.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    measures = rank_measures(profiles)
    metric = st.selectbox("🗺️ What should the map show?",
                          [m['name'] for m in measures] + ["Count (Frequency)"],
                          format_func=metric_label, key=f"auto_geometric_{key_prefix}")
    explain("Darker areas and bigger pins mean higher numbers. Hover any place to see its "
            "exact value, and scroll to zoom in.")
    geo_maps.render_geo_section(dataframe, categories, metric, f"auto_{key_prefix}")


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

def render_auto_dashboard(dataframe, key_prefix, ai_callback=None):
    """Profile the data, explain it, then build every scenario it supports."""
    if dataframe is None or dataframe.empty:
        st.info("Load some data to run the auto analyst.")
        return

    profiles = profile_dataframe(dataframe)
    render_data_story(profiles, dataframe)

    scenarios = build_scenarios(dataframe, profiles)

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
