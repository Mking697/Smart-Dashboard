"""Automated analyst - reads the data, decides what is worth showing, builds it.

The idea: instead of the user picking axes, we profile every column, work out the
role it plays (measure, dimension, date, geography, identifier, flag), and then
assemble the scenarios a human analyst would actually build for that shape of
data - trends, rankings, Pareto, distributions, correlations, cross-tabs,
geography and data quality.

Every scenario carries a "why" line, so the dashboard also explains itself.
"""

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
        named_id = any(h == lower or lower.endswith('_' + h) or lower.startswith(h + '_')
                       for h in IDENTIFIER_HINTS)
        # A continuous measure is nearly all-unique by nature, so "mostly unique"
        # alone is not enough - a row id is a whole number and never a named measure.
        whole_numbers = pd.api.types.is_integer_dtype(series) or (non_null % 1 == 0).all()
        serial_like = whole_numbers and info['unique_ratio'] > 0.99 and info['n_unique'] > 20

        if not named_measure and ((named_id and info['unique_ratio'] > 0.9) or serial_like):
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
            'Column': profile['name'],
            'Detected as': label,
            'Why it matters': meaning,
            'Distinct': profile['n_unique'],
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
        slot.metric(f"Σ {measure['name']}", f"{total:,.0f}", help=f"Average {measure.get('mean', 0):,.2f}")

    if categories:
        primary = categories[0]
        tiles[-1].metric(f"🏷️ {primary['name']}", f"{primary['n_unique']:,}",
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

    if measures:
        measure = measures[0]['name']
        agg = dataframe.groupby(dimension, dropna=True)[measure].sum().sort_values(ascending=False).head(12).reset_index()
        title = f"{measure} by {dimension}"
        value_col = measure
    else:
        agg = dataframe[dimension].value_counts().head(12).reset_index()
        agg.columns = [dimension, 'Records']
        title = f"Records by {dimension}"
        value_col = 'Records'

    with left:
        fig = px.bar(agg, x=dimension, y=value_col, color=dimension, text_auto='.2s',
                     title=title, color_discrete_sequence=PALETTE)
        fig.update_layout(showlegend=False, xaxis_tickangle=-40, height=420)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.pie(agg, names=dimension, values=value_col, hole=0.45,
                     title=f"Share of {value_col}", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)


def scenario_trend(dataframe, profiles, key_prefix):
    """How the numbers move over time, with period-on-period growth."""
    dates = by_role(profiles, 'date')
    measures = rank_measures(profiles)

    date_col = st.selectbox("Timeline", [p['name'] for p in dates], key=f"auto_date_{key_prefix}")
    metric_options = ["Record count"] + [m['name'] for m in measures]
    metric = st.selectbox("Measure", metric_options, key=f"auto_trendmetric_{key_prefix}")

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

    fig = px.area(series, x=date_col, y='Value', markers=True,
                  title=f"{freq_label} trend of {metric}", color_discrete_sequence=['#2563eb'])
    fig.update_layout(height=420, hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True)

    if len(series) >= 2:
        latest, previous = series['Value'].iloc[-1], series['Value'].iloc[-2]
        change = ((latest - previous) / previous * 100) if previous else 0
        peak = series.loc[series['Value'].idxmax()]

        col1, col2, col3 = st.columns(3)
        col1.metric(f"Latest {freq_label.lower()} period", f"{latest:,.0f}", f"{change:+.1f}%")
        col2.metric("Peak period", f"{peak['Value']:,.0f}", help=str(peak[date_col].date()))
        col3.metric("Period average", f"{series['Value'].mean():,.0f}")


def scenario_ranking(dataframe, profiles, key_prefix):
    """Who is on top, and how concentrated the total is (80/20 rule)."""
    categories = rank_categories(profiles)
    measures = rank_measures(profiles)

    dimension = st.selectbox("Rank by", [c['name'] for c in categories], key=f"auto_rankdim_{key_prefix}")
    metric_options = ["Record count"] + [m['name'] for m in measures]
    metric = st.selectbox("Measure", metric_options, key=f"auto_rankmetric_{key_prefix}")

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

    with left:
        top = agg.head(15).sort_values('Value')
        fig = px.bar(top, x='Value', y=dimension, orientation='h', text_auto='.2s',
                     title=f"Top {len(top)} by {metric}", color='Value',
                     color_continuous_scale='Blues')
        fig.update_layout(height=460, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        pareto = agg.head(30).reset_index(drop=True)
        fig = px.line(pareto, x=pareto.index + 1, y='Cumulative %', markers=True,
                      title="Concentration (Pareto)", color_discrete_sequence=['#dc2626'])
        fig.add_hline(y=80, line_dash="dash", line_color="#94a3b8")
        fig.update_layout(height=460, xaxis_title=f"Number of {dimension} values")
        st.plotly_chart(fig, use_container_width=True)

    needed = int((agg['Cumulative %'] < 80).sum()) + 1
    share = round(100 * needed / len(agg), 1)
    st.success(
        f"💡 **{needed} of {len(agg)}** {dimension} values ({share}%) make up 80% of {metric}. "
        + ("Highly concentrated — a few names carry the business."
           if share <= 30 else "Fairly evenly spread across the base.")
    )


def scenario_distribution(dataframe, profiles, key_prefix):
    """Shape of each measure, plus the outliers hiding in it."""
    measures = rank_measures(profiles)
    metric = st.selectbox("Measure", [m['name'] for m in measures], key=f"auto_dist_{key_prefix}")

    values = pd.to_numeric(dataframe[metric], errors='coerce').dropna()
    if values.empty:
        st.info("No numeric values in this column.")
        return

    left, right = st.columns([3, 2])

    with left:
        fig = px.histogram(values, nbins=40, title=f"Distribution of {metric}",
                           color_discrete_sequence=['#2563eb'])
        fig.update_layout(height=400, showlegend=False, xaxis_title=metric)
        st.plotly_chart(fig, use_container_width=True)

    with right:
        fig = px.box(values, title=f"Spread & outliers: {metric}",
                     color_discrete_sequence=['#0ea5e9'])
        fig.update_layout(height=400, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    q1, q3 = values.quantile(0.25), values.quantile(0.75)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = values[(values < low) | (values > high)]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Median", f"{values.median():,.2f}")
    col2.metric("Average", f"{values.mean():,.2f}")
    col3.metric("Std deviation", f"{values.std():,.2f}")
    col4.metric("Outliers", f"{len(outliers):,}", help=f"Outside {low:,.2f} – {high:,.2f}")

    if len(outliers):
        st.warning(
            f"⚠️ {len(outliers):,} record(s) ({100 * len(outliers) / len(values):.1f}%) sit far outside the "
            f"normal range of {metric}. Worth checking whether these are genuine extremes or data-entry errors."
        )


def scenario_relationships(dataframe, profiles, key_prefix):
    """Which measures move together - and how strongly."""
    measures = [m['name'] for m in rank_measures(profiles)]
    numeric = dataframe[measures].apply(pd.to_numeric, errors='coerce')
    correlation = numeric.corr(numeric_only=True)

    left, right = st.columns([2, 3])

    with left:
        fig = px.imshow(correlation, text_auto='.2f', aspect='auto',
                        color_continuous_scale='RdBu_r', zmin=-1, zmax=1,
                        title="Correlation matrix")
        fig.update_layout(height=430)
        st.plotly_chart(fig, use_container_width=True)

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

    with right:
        colour_by = rank_categories(profiles)
        colour = colour_by[0]['name'] if colour_by else None
        fig = px.scatter(dataframe, x=first, y=second, color=colour, trendline=None,
                         title=f"{first} vs {second} (r = {strength:.2f})",
                         color_discrete_sequence=PALETTE, opacity=0.7)
        fig.update_layout(height=430)
        st.plotly_chart(fig, use_container_width=True)

    direction = "rise together" if strength > 0 else "move in opposite directions"
    grade = "strong" if abs(strength) >= 0.7 else ("moderate" if abs(strength) >= 0.4 else "weak")
    st.info(f"🔗 Strongest link: **{first}** and **{second}** — a {grade} relationship (r = {strength:.2f}); they {direction}.")


def scenario_crosstab(dataframe, profiles, key_prefix):
    """Two dimensions at once - where the volume actually sits."""
    categories = [c['name'] for c in rank_categories(profiles)]
    measures = rank_measures(profiles)

    col1, col2, col3 = st.columns(3)
    with col1:
        rows = st.selectbox("Rows", categories, key=f"auto_ctrow_{key_prefix}")
    with col2:
        remaining = [c for c in categories if c != rows]
        cols = st.selectbox("Columns", remaining, key=f"auto_ctcol_{key_prefix}")
    with col3:
        metric = st.selectbox("Cell value", ["Record count"] + [m['name'] for m in measures],
                              key=f"auto_ctmetric_{key_prefix}")

    if metric == "Record count":
        matrix = pd.crosstab(dataframe[rows], dataframe[cols])
    else:
        matrix = pd.pivot_table(dataframe, index=rows, columns=cols, values=metric,
                                aggfunc='sum', fill_value=0)

    matrix = matrix.loc[matrix.sum(axis=1).sort_values(ascending=False).index[:20],
                        matrix.sum(axis=0).sort_values(ascending=False).index[:20]]

    fig = px.imshow(matrix, text_auto='.3s', aspect='auto', color_continuous_scale='Blues',
                    title=f"{metric}: {rows} × {cols}")
    fig.update_layout(height=520)
    st.plotly_chart(fig, use_container_width=True)

    if matrix.size:
        flat = matrix.stack()
        peak_row, peak_col = flat.idxmax()
        st.success(f"🎯 Hotspot: **{peak_row} × {peak_col}** with {flat.max():,.0f}.")


def scenario_quality(dataframe, profiles, key_prefix):
    """Can these numbers be trusted? Missing data, duplicates, dead columns."""
    missing = pd.DataFrame({
        'Column': [p['name'] for p in profiles],
        'Missing %': [p['missing_pct'] for p in profiles],
        'Distinct': [p['n_unique'] for p in profiles],
    }).sort_values('Missing %', ascending=False)

    duplicates = int(dataframe.duplicated().sum())
    constants = [p['name'] for p in profiles if p['n_unique'] <= 1]
    empties = [p['name'] for p in profiles if p['missing_pct'] >= 100]
    complete = float((1 - dataframe.isna().sum().sum() / max(dataframe.size, 1)) * 100)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Completeness", f"{complete:.1f}%")
    col2.metric("Duplicate rows", f"{duplicates:,}")
    col3.metric("Constant columns", len(constants))
    col4.metric("Empty columns", len(empties))

    fig = px.bar(missing.head(20), x='Missing %', y='Column', orientation='h',
                 title="Missing data by column", color='Missing %',
                 color_continuous_scale='Reds')
    fig.update_layout(height=460, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    notes = []
    worst = missing.iloc[0]
    if worst['Missing %'] > 20:
        notes.append(f"**{worst['Column']}** is {worst['Missing %']}% empty — treat any chart built on it with care.")
    if duplicates:
        notes.append(f"**{duplicates:,}** fully duplicated row(s) — totals may be inflated.")
    if constants:
        notes.append(f"Constant column(s) with a single value: {', '.join(constants[:5])} — they add no information.")

    for note in notes:
        st.warning("⚠️ " + note)
    if not notes:
        st.success("✅ No structural data quality problems detected.")


def scenario_geography(dataframe, profiles, key_prefix):
    """Maps, driven by whichever geography column the data carries."""
    categories = dataframe.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    measures = rank_measures(profiles)
    metric = st.selectbox("Map metric", ["Count (Frequency)"] + [m['name'] for m in measures],
                          key=f"auto_geometric_{key_prefix}")
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
        'title': "📊 Executive Summary",
        'why': "The headline numbers, and the one breakdown that explains most of them.",
        'render': scenario_executive,
    }]

    if dates:
        scenarios.append({
            'title': "📈 Trends",
            'why': f"'{dates[0]['name']}' is a real timeline, so movement over time and growth can be measured.",
            'render': scenario_trend,
        })

    if categories:
        scenarios.append({
            'title': "🏆 Rankings & 80/20",
            'why': "Dimensions with a workable number of buckets — worth ranking and testing for concentration.",
            'render': scenario_ranking,
        })

    if measures:
        scenarios.append({
            'title': "📉 Distribution & Outliers",
            'why': "Numeric measures found — their spread reveals typical values and suspicious extremes.",
            'render': scenario_distribution,
        })

    if len(measures) >= 2:
        scenarios.append({
            'title': "🔗 Relationships",
            'why': f"{len(measures)} measures present, so they can be tested for correlation.",
            'render': scenario_relationships,
        })

    if len(categories) >= 2:
        scenarios.append({
            'title': "🧮 Cross-Tab Heatmap",
            'why': "Two or more dimensions — combining them shows where volume concentrates.",
            'render': scenario_crosstab,
        })

    if geos:
        scenarios.append({
            'title': "🌍 Geography",
            'why': f"'{geos[0]['name']}' resolves to real places, so it can be mapped.",
            'render': scenario_geography,
        })

    scenarios.append({
        'title': "🧪 Data Quality",
        'why': "Every number above is only as good as the data underneath it.",
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
    st.write(f"### 🤖 {len(scenarios)} dashboards built automatically from this data")

    tabs = st.tabs([scenario['title'] for scenario in scenarios])
    for tab, scenario in zip(tabs, scenarios):
        with tab:
            st.caption(f"🧠 Why this view: {scenario['why']}")
            try:
                scenario['render'](dataframe, profiles, key_prefix)
            except Exception as error:
                st.warning(f"This view could not be built for the current data ({error}).")

    if ai_callback:
        st.divider()
        st.write("### 🧠 AI Analyst Briefing")
        if st.button("✨ Ask the AI what to look at", key=f"auto_ai_{key_prefix}"):
            briefing = build_ai_briefing(dataframe, profiles, scenarios)
            with st.spinner("Reading the profile and forming an opinion..."):
                ai_callback(briefing)
