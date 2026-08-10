"""Map rendering engine for the AI Smart Dashboard.

Given any location column, this module works out what it actually is - countries,
Indian states, Indian districts/cities, US states, or raw coordinates - and draws
the right map for it.

India gets first-class treatment: boundaries come from the bundled district
GeoJSON, so **Jammu & Kashmir and Ladakh are always shown as part of India**,
unlike Plotly's default world outline.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import geo_assets as geo

US_STATE_CODES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO',
    'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA',
    'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'PR',
}

US_STATE_NAMES = {
    'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR',
    'california': 'CA', 'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE',
    'district of columbia': 'DC', 'florida': 'FL', 'georgia': 'GA',
    'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN',
    'iowa': 'IA', 'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA',
    'maine': 'ME', 'maryland': 'MD', 'massachusetts': 'MA', 'michigan': 'MI',
    'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO', 'montana': 'MT',
    'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
    'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC',
    'north dakota': 'ND', 'ohio': 'OH', 'oklahoma': 'OK', 'oregon': 'OR',
    'pennsylvania': 'PA', 'puerto rico': 'PR', 'rhode island': 'RI',
    'south carolina': 'SC', 'south dakota': 'SD', 'tennessee': 'TN',
    'texas': 'TX', 'utah': 'UT', 'vermont': 'VT', 'virginia': 'VA',
    'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI',
    'wyoming': 'WY',
}

COUNTRY_HINTS = ('country', 'nation', 'desh')
STATE_HINTS = ('state', 'province', 'region', 'rajya')
CITY_HINTS = ('city', 'district', 'town', 'zone', 'branch', 'location', 'place')

# Blink effect. Plotly cannot auto-play an animation without a click, so the
# pulse is done in CSS - `path.point` only matches scatter markers, which on this
# page means the map pins and nothing else.
PULSE_CSS = """
<style>
@keyframes sd-pin-pulse {
  0%   { opacity: 1;    }
  50%  { opacity: 0.25; }
  100% { opacity: 1;    }
}
[data-testid="stPlotlyChart"] path.point {
  animation: sd-pin-pulse 1.6s ease-in-out infinite;
}
</style>
"""


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

# Real sheets mix pin codes, SKUs and stray notes into location columns, so a
# hinted column only needs a minority of its labels to resolve before we map it.
HINTED_THRESHOLD = 0.3
UNHINTED_THRESHOLD = 0.6


def _candidate_labels(labels):
    """Distinct text labels worth testing - numbers and blanks are never places."""
    values = pd.Series(labels).dropna().astype(str).str.strip()
    values = values[(values != '') & (values.str.lower() != 'nan')]
    values = values[~values.str.fullmatch(r'[\d\.\-\s]+')]  # pin codes, phone numbers
    return pd.Series(values.unique())


def _ratio(labels, matcher):
    """Share of labels a matcher can resolve."""
    if len(labels) == 0:
        return 0.0
    return sum(1 for value in labels if matcher(value)) / len(labels)


def detect_map_mode(labels, column_name):
    """Work out which basemap can render this location column.

    Returns one of 'country', 'india-states', 'india-districts', 'usa-states',
    or None when nothing built-in can place these values.
    """
    values = _candidate_labels(labels)
    if values.empty:
        return None

    name = str(column_name).lower()
    upper = values.str.upper()

    is_country = _ratio(values, geo.normalize_country)
    is_indian_state = _ratio(values, geo.match_state)
    is_us_state = (upper.isin(US_STATE_CODES).mean()
                   if (upper.str.len() == 2).mean() > 0.8
                   else values.str.lower().map(US_STATE_NAMES).notna().mean())
    is_indian_city = _ratio(values, geo.match_district)

    # The column name is the strongest signal - trust it before guessing.
    if any(hint in name for hint in COUNTRY_HINTS) and is_country >= HINTED_THRESHOLD:
        return 'country'

    if any(hint in name for hint in STATE_HINTS):
        # Indian state codes and US state codes overlap, so pick the better fit.
        if is_indian_state >= HINTED_THRESHOLD and is_indian_state >= is_us_state:
            return 'india-states'
        if is_us_state >= HINTED_THRESHOLD:
            return 'usa-states'

    if any(hint in name for hint in CITY_HINTS) and is_indian_city >= HINTED_THRESHOLD:
        return 'india-districts'

    # No usable hint in the name: go with whatever matches best.
    scores = {
        'india-states': is_indian_state,
        'usa-states': is_us_state,
        'country': is_country,
        'india-districts': is_indian_city,
    }
    best = max(scores, key=scores.get)
    return best if scores[best] >= UNHINTED_THRESHOLD else None


def to_map_codes(labels, mode):
    """Turn raw labels into the codes/names the chosen basemap expects."""
    values = pd.Series(labels).astype(str).str.strip()

    if mode == 'country':
        return values.map(geo.normalize_country)
    if mode == 'india-states':
        return values.map(geo.match_state)
    if mode == 'india-districts':
        return values.map(geo.match_district)
    if mode == 'usa-states':
        upper = values.str.upper()
        by_name = values.str.lower().map(US_STATE_NAMES)
        return upper.where(upper.isin(US_STATE_CODES), by_name)

    return values


def find_latlon_columns(dataframe):
    """Detect a usable numeric Latitude/Longitude pair, or (None, None)."""
    lat_col = lon_col = None

    for col in dataframe.columns:
        key = str(col).strip().lower().replace('_', '').replace('-', '').replace(' ', '')
        if lat_col is None and key in ('lat', 'latitude', 'lattitude'):
            lat_col = col
        if lon_col is None and key in ('lon', 'lng', 'long', 'longitude'):
            lon_col = col

    if lat_col is None or lon_col is None:
        return None, None

    lats = pd.to_numeric(dataframe[lat_col], errors='coerce')
    lons = pd.to_numeric(dataframe[lon_col], errors='coerce')

    if (lats.between(-90, 90) & lons.between(-180, 180)).sum() == 0:
        return None, None

    return lat_col, lon_col


# --------------------------------------------------------------------------- #
# Shared plumbing
# --------------------------------------------------------------------------- #

def aggregate_by_place(dataframe, place_col, y_axis):
    """Roll the data up to one row per location, using the dashboard's metric."""
    columns = [place_col] + ([y_axis] if y_axis != "Count (Frequency)" else [])
    frame = dataframe[list(dict.fromkeys(columns))].copy()
    frame[place_col] = frame[place_col].astype(str).str.strip()
    frame = frame[(frame[place_col] != '') & (frame[place_col].str.lower() != 'nan')]

    if frame.empty:
        return None, None

    if y_axis == "Count (Frequency)":
        return frame.groupby(place_col).size().reset_index(name='Value'), "Records"

    # Never trust the dtype: a stray note in a numeric column would otherwise
    # crash the sum, or make Plotly colour the map as if it were a category.
    frame[y_axis] = pd.to_numeric(frame[y_axis], errors='coerce')
    frame = frame[frame[y_axis].notna()]
    if frame.empty:
        return None, None

    agg = frame.groupby(place_col)[y_axis].sum().reset_index().rename(columns={y_axis: 'Value'})
    return agg, f"Sum of {y_axis}"


def map_controls(key_prefix, allow_blink=False):
    """Zoom / projection (and optionally blink) switches shared by every map."""
    columns = st.columns(3 if allow_blink else 2)

    with columns[0]:
        zoom = st.segmented_control(
            "Zoom", ["🎯 Auto Fit", "🌍 Whole World"],
            default="🎯 Auto Fit", key=f"geozoom_{key_prefix}",
        ) or "🎯 Auto Fit"
    with columns[1]:
        shape = st.segmented_control(
            "Projection", ["🗺️ Flat Map", "🔮 3D Globe"],
            default="🗺️ Flat Map", key=f"geoproj_{key_prefix}",
        ) or "🗺️ Flat Map"

    blink = False
    if allow_blink:
        with columns[2]:
            blink = st.toggle("✨ Blink pins", value=True, key=f"geoblink_{key_prefix}")

    projection = 'orthographic' if shape == "🔮 3D Globe" else 'natural earth'
    return zoom, projection, blink


def style_and_render(fig, zoom, metric_label, key, height=580):
    """Apply the shared basemap look, then render with scroll-zoom enabled."""
    if zoom == "🎯 Auto Fit":
        fig.update_geos(fitbounds="locations")
    else:
        fig.update_geos(scope='world')

    fig.update_geos(
        showcountries=True, countrycolor='#c9d3dd',
        showcoastlines=True, coastlinecolor='#b7c3ce',
        showland=True, landcolor='#f2f5f8',
        showocean=True, oceancolor='#eaf2fb',
        showlakes=False, showframe=False,
    )
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=60, b=0),
        coloraxis_colorbar=dict(title=metric_label),
    )
    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True}, key=key)


def _leaderboard(agg, label_col, metric_label, top_n=5):
    top = agg.sort_values('Value', ascending=False).head(top_n)
    leaders = " · ".join(f"**{row[label_col]}** ({row['Value']:,.0f})" for _, row in top.iterrows())
    st.caption(f"🏆 Top by {metric_label}: {leaders}")


# --------------------------------------------------------------------------- #
# Choropleth maps
# --------------------------------------------------------------------------- #

def render_region_map(dataframe, place_col, y_axis, mode, key_prefix):
    """Filled-region map: countries, Indian states/districts, or US states."""
    agg, metric_label = aggregate_by_place(dataframe, place_col, y_axis)
    if agg is None:
        st.info(f"No usable location values found in '{place_col}'.")
        return

    agg['Map_Code'] = to_map_codes(agg[place_col], mode)
    unmatched = sorted(agg.loc[agg['Map_Code'].isna(), place_col].unique())
    agg = agg.dropna(subset=['Map_Code'])

    if agg.empty:
        st.warning(f"⚠️ None of the values in '{place_col}' matched a place on the map.")
        return

    # Different spellings of the same place (India / IND / IN) collapse here, so
    # one region is never counted two or three times.
    merged = agg.groupby('Map_Code', as_index=False)['Value'].sum()
    merged['Value'] = pd.to_numeric(merged['Value'], errors='coerce').fillna(0)

    if mode == 'country':
        merged['Label'] = merged['Map_Code'].map(geo.country_display_name)
    else:
        merged['Label'] = merged['Map_Code']

    zoom, projection, _ = map_controls(key_prefix)

    if mode == 'country':
        fig = _country_figure(merged, metric_label, projection)
    elif mode == 'india-states':
        fig = _geojson_figure(merged, geo.load_state_geojson(), 'properties.st_nm',
                              metric_label, projection, f"India by {place_col}")
    elif mode == 'india-districts':
        fig = _geojson_figure(merged, geo.load_district_geojson(), 'properties.district',
                              metric_label, projection, f"District view: {place_col}")
    else:
        fig = px.choropleth(
            merged, locations='Map_Code', locationmode='USA-states', color='Value',
            hover_name='Label', color_continuous_scale='Blues', projection=projection,
            labels={'Value': metric_label}, title=f"🌍 {metric_label} by {place_col}",
        )

    if fig is None:
        st.warning("Boundary data for this map is unavailable.")
        return

    style_and_render(fig, zoom, metric_label, key=f"regionmap_{key_prefix}")
    _leaderboard(merged, 'Label', metric_label)

    if len(agg) != len(merged):
        st.caption(f"🔗 Merged {len(agg) - len(merged)} duplicate spelling(s) into a single region each.")
    if unmatched:
        shown = ", ".join(str(v) for v in unmatched[:6])
        more = f" (+{len(unmatched) - 6} more)" if len(unmatched) > 6 else ""
        st.caption(f"⚠️ Not on the map and skipped: {shown}{more}")


def _country_figure(merged, metric_label, projection):
    """World country map, with India repainted to include J&K and Ladakh."""
    fig = px.choropleth(
        merged, locations='Map_Code', locationmode='ISO-3', color='Value',
        hover_name='Label', color_continuous_scale='Blues', projection=projection,
        labels={'Value': metric_label}, title=f"🌍 {metric_label} by Country",
    )

    outline = geo.load_india_outline()
    india = merged[merged['Map_Code'] == 'IND']

    if outline is not None and not india.empty:
        value = float(india['Value'].iloc[0])
        fig.add_trace(go.Choropleth(
            geojson=outline,
            featureidkey='properties.iso3',
            locations=['IND'],
            z=[value],
            coloraxis='coloraxis',
            marker_line_width=0.4,
            marker_line_color='#ffffff',
            name='India',
            hovertemplate=f"<b>India</b><br>{metric_label}: {value:,.0f}<extra></extra>",
        ))

    return fig


def _geojson_figure(merged, geojson, feature_key, metric_label, projection, title):
    """Choropleth driven by our bundled India boundaries."""
    if geojson is None:
        return None

    return px.choropleth(
        merged,
        geojson=geojson,
        featureidkey=feature_key,
        locations='Map_Code',
        color='Value',
        hover_name='Label',
        color_continuous_scale='Blues',
        projection=projection,
        labels={'Value': metric_label},
        title=f"🌍 {metric_label} — {title}",
    )


# --------------------------------------------------------------------------- #
# Pin map
# --------------------------------------------------------------------------- #

def render_pin_map(dataframe, place_col, y_axis, key_prefix, lat_col=None, lon_col=None):
    """Point-level map with blinking pins, hover values and scroll zoom.

    Coordinates come from Latitude/Longitude columns when the data has them, and
    otherwise from the bundled India boundaries - so city names alone are enough.
    """
    if lat_col and lon_col:
        frame = dataframe.copy()
        frame['_lat'] = pd.to_numeric(frame[lat_col], errors='coerce')
        frame['_lon'] = pd.to_numeric(frame[lon_col], errors='coerce')
        frame = frame.dropna(subset=['_lat', '_lon'])
        frame = frame[frame['_lat'].between(-90, 90) & frame['_lon'].between(-180, 180)]

        if frame.empty:
            st.info("No valid Latitude/Longitude pairs found.")
            return

        label_col = place_col if place_col else None
        if label_col:
            frame[label_col] = frame[label_col].astype(str)
            group_keys = [label_col, '_lat', '_lon']
        else:
            frame['Point'] = frame['_lat'].round(4).astype(str) + ", " + frame['_lon'].round(4).astype(str)
            label_col = 'Point'
            group_keys = [label_col, '_lat', '_lon']

        if y_axis == "Count (Frequency)":
            points = frame.groupby(group_keys).size().reset_index(name='Value')
            metric_label = "Records"
        else:
            points = frame[frame[y_axis].notna()].groupby(group_keys)[y_axis].sum().reset_index()
            points = points.rename(columns={y_axis: 'Value'})
            metric_label = f"Sum of {y_axis}"
        source_note = f"'{lat_col}' / '{lon_col}' columns"

    else:
        agg, metric_label = aggregate_by_place(dataframe, place_col, y_axis)
        if agg is None:
            st.info(f"No usable location values found in '{place_col}'.")
            return

        coords = agg[place_col].map(geo.geocode_place)
        agg['_lat'] = coords.map(lambda point: point[0] if point else None)
        agg['_lon'] = coords.map(lambda point: point[1] if point else None)

        missing = sorted(agg.loc[agg['_lat'].isna(), place_col].unique())
        points = agg.dropna(subset=['_lat', '_lon']).rename(columns={place_col: 'Label'})
        label_col = 'Label'
        source_note = "the bundled India boundaries"

        if points.empty:
            st.warning(
                f"⚠️ Couldn't place any value from '{place_col}' on the map. "
                "Built-in coordinates cover Indian cities/districts — for other places, "
                "add **Latitude** and **Longitude** columns."
            )
            return

        if missing:
            shown = ", ".join(str(v) for v in missing[:6])
            more = f" (+{len(missing) - 6} more)" if len(missing) > 6 else ""
            st.caption(f"📍 No coordinates found for: {shown}{more}")

    if points.empty:
        st.info("Nothing left to plot after cleaning the coordinates.")
        return

    zoom, projection, blink = map_controls(key_prefix, allow_blink=True)

    if blink:
        st.markdown(PULSE_CSS, unsafe_allow_html=True)

    points = points.sort_values('Value', ascending=False)
    largest = float(points['Value'].abs().max()) or 1.0
    points['_size'] = 10 + 26 * (points['Value'].abs() / largest)

    fig = go.Figure()

    # Soft halo underneath so each pin reads as a glowing hotspot.
    fig.add_trace(go.Scattergeo(
        lat=points['_lat'], lon=points['_lon'],
        mode='markers',
        marker=dict(size=points['_size'] * 2.1, color='#2563eb', opacity=0.16),
        hoverinfo='skip', showlegend=False,
    ))

    fig.add_trace(go.Scattergeo(
        lat=points['_lat'], lon=points['_lon'],
        mode='markers',
        marker=dict(
            size=points['_size'],
            color=points['Value'],
            coloraxis='coloraxis',
            line=dict(width=1, color='white'),
        ),
        customdata=points[[label_col, 'Value']],
        hovertemplate="<b>%{customdata[0]}</b><br>" + metric_label + ": %{customdata[1]:,.0f}<extra></extra>",
        showlegend=False,
    ))

    # Labels for the biggest locations so values are readable without hovering.
    leaders = points.head(10)
    fig.add_trace(go.Scattergeo(
        lat=leaders['_lat'], lon=leaders['_lon'],
        mode='text',
        text=[f"{row[label_col]}<br>{row['Value']:,.0f}" for _, row in leaders.iterrows()],
        textposition='top center',
        textfont=dict(size=10, color='#0f2b46'),
        hoverinfo='skip', showlegend=False,
    ))

    fig.update_layout(
        title=f"📍 {metric_label} by location — hover a pin for its value",
        coloraxis=dict(colorscale='Blues', cmin=float(points['Value'].min()), cmax=float(points['Value'].max())),
    )

    style_and_render(fig, zoom, metric_label, key=f"pinmap_{key_prefix}")

    st.caption(
        f"📌 {len(points):,} location(s) plotted from {source_note}. "
        "Scroll to zoom, drag to pan, hover any pin for its exact value."
    )
    _leaderboard(points, label_col, metric_label)


# --------------------------------------------------------------------------- #
# Section entry point
# --------------------------------------------------------------------------- #

def render_geo_section(dataframe, cat_cols, y_axis, key_prefix):
    """Full geographical block: picks the views this data can actually support."""
    loc_keywords = COUNTRY_HINTS + STATE_HINTS + CITY_HINTS + ('pin', 'zip', 'pincode')
    loc_cols = [
        col for col in cat_cols
        if any(k in str(col).lower() for k in loc_keywords)
        and 'email' not in str(col).lower() and 'address' not in str(col).lower()
    ]

    lat_col, lon_col = find_latlon_columns(dataframe)

    if not loc_cols and not (lat_col and lon_col):
        return

    st.write("### 🌍 Geographical Intelligence")

    # Broadest level first: Country > State > City.
    hierarchy = []
    for keyword in ('country', 'state', 'province', 'region', 'district', 'city', 'zone', 'zip', 'pin'):
        for col in loc_cols:
            if keyword in str(col).lower() and col not in hierarchy:
                hierarchy.append(col)
    for col in loc_cols:
        if col not in hierarchy:
            hierarchy.append(col)

    modes = {col: detect_map_mode(dataframe[col], col) for col in hierarchy}
    mappable = [col for col in hierarchy if modes[col]]
    pinnable = [col for col in hierarchy if modes[col] in ('india-districts', 'india-states')]

    views = []
    if mappable:
        views.append("🗺️ Region Map")
    if (lat_col and lon_col) or pinnable:
        views.append("📍 Pin Map (Blinking)")
    if hierarchy:
        views.append("🧩 Treemap Drill-Down")

    if not views:
        return

    view = st.segmented_control(
        "Map Style", views, default=views[0], key=f"geoview_{key_prefix}",
    ) or views[0]

    if view == "🗺️ Region Map":
        picked = st.selectbox("Location column to plot:", mappable, key=f"geocol_{key_prefix}")
        render_region_map(dataframe, picked, y_axis, modes[picked], key_prefix)

    elif view == "📍 Pin Map (Blinking)":
        if lat_col and lon_col:
            label_options = hierarchy or [None]
            picked = st.selectbox("Label the pins with:", label_options, key=f"geopin_{key_prefix}")
            render_pin_map(dataframe, picked, y_axis, key_prefix, lat_col, lon_col)
        else:
            picked = st.selectbox("City / district column:", pinnable, key=f"geopin_{key_prefix}")
            render_pin_map(dataframe, picked, y_axis, key_prefix)

    else:
        st.info("💡 Click on any region/block to zoom in and see the drill-down details.")
        render_treemap(dataframe, hierarchy[:4], key_prefix)


def render_treemap(dataframe, path_cols, key_prefix):
    """The original hierarchical drill-down, kept intact."""
    df_map = dataframe.copy()
    df_map[path_cols] = df_map[path_cols].fillna('Unknown')

    for column in path_cols:
        df_map[column] = df_map[column].astype(str)
        df_map.loc[df_map[column].str.strip() == '', column] = 'Unknown'

    try:
        fig = px.treemap(df_map, path=path_cols,
                         title=f"Geographical Drill-Down: {' ➡️ '.join(path_cols)}")
        st.plotly_chart(fig, use_container_width=True, key=f"treemap_{key_prefix}")
    except Exception:
        st.warning("Map generation skipped due to unsupported data structure in location columns.")
