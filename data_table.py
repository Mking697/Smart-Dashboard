"""The raw data, sheet by sheet - filterable, pivotable, and a fixed size.

Charts answer questions the app decided to ask. Sometimes you just need to look
at the rows: find one order, check what a filter actually matched, or roll the
numbers up your own way. That is what this is for.

The grid is deliberately a fixed box with its own scrollbars rather than a table
that grows down the page. A 400-row sheet rendered in full pushes every control
off screen, and the filters you need are the ones you can no longer reach.
"""

import numpy as np
import pandas as pd
import streamlit as st

import auto_analyst

# A column with more distinct values than this is a search box, not a picker.
MAX_PICKER_OPTIONS = 200

AGGREGATIONS = {
    "Sum": "sum",
    "Average": "mean",
    "Count": "count",
    "Highest": "max",
    "Lowest": "min",
}


def _column_kind(series):
    """How this column should be filtered."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    if pd.api.types.is_numeric_dtype(series):
        return "number"
    return "text"


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #

def _apply_search(frame, term):
    """Match the term against every column, as text."""
    if not term:
        return frame
    text = frame.astype(str).apply(lambda column: column.str.contains(term, case=False, na=False))
    return frame[text.any(axis=1)]


def _filter_controls(frame, key_prefix):
    """Render the filter widgets and return the filtered frame."""
    search = st.text_input(
        "Search all columns",
        placeholder="Type anything — an order number, a city, a name…",
        key=f"dt_search_{key_prefix}",
    )

    columns = list(frame.columns)
    chosen = st.multiselect(
        "Filter on specific columns",
        columns,
        format_func=auto_analyst.humanize,
        key=f"dt_cols_{key_prefix}",
        help="Pick a column to add a filter for it. Leave empty to see everything.",
    )

    filtered = _apply_search(frame, search)

    for column in chosen:
        kind = _column_kind(frame[column])
        label = auto_analyst.humanize(column)
        widget_key = f"dt_f_{key_prefix}_{column}"

        if kind == "number":
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if values.empty:
                continue
            low, high = float(values.min()), float(values.max())
            if low == high:
                continue
            picked = st.slider(label, low, high, (low, high), key=widget_key)
            column_values = pd.to_numeric(filtered[column], errors="coerce")
            filtered = filtered[column_values.between(*picked) | column_values.isna()]

        elif kind == "date":
            dates = auto_analyst.parse_dates(frame[column]).dropna()
            if dates.empty:
                continue
            start, end = dates.min().date(), dates.max().date()
            picked = st.date_input(label, (start, end), min_value=start, max_value=end, key=widget_key)
            if isinstance(picked, (tuple, list)) and len(picked) == 2:
                column_dates = auto_analyst.parse_dates(filtered[column])
                filtered = filtered[column_dates.dt.date.between(*picked) | column_dates.isna()]

        else:
            options = sorted(frame[column].dropna().astype(str).unique())
            if len(options) > MAX_PICKER_OPTIONS:
                st.caption(f"'{label}' has {len(options):,} distinct values — use the search box above instead.")
                continue
            picked = st.multiselect(label, options, key=widget_key)
            if picked:
                filtered = filtered[filtered[column].astype(str).isin(picked)]

    return filtered


# --------------------------------------------------------------------------- #
# Pivot
# --------------------------------------------------------------------------- #

def _pivot_controls(frame, key_prefix):
    """Build a pivot from the filtered rows, or explain why it cannot."""
    profiles = auto_analyst.profile_dataframe(frame)
    dimensions = [p["name"] for p in auto_analyst.rank_categories(profiles)]
    measures = [p["name"] for p in auto_analyst.rank_measures(profiles)]

    if not dimensions:
        st.info("A pivot needs at least one column to group by, and this sheet has none "
                "with a workable number of distinct values.")
        return None

    row_col, col_col, val_col, agg_col = st.columns([2, 2, 2, 1.4])

    with row_col:
        rows = st.multiselect("Rows", dimensions, default=dimensions[:1],
                              format_func=auto_analyst.humanize, key=f"pv_rows_{key_prefix}")
    with col_col:
        column_options = ["(none)"] + [d for d in dimensions if d not in rows]
        columns = st.selectbox("Columns", column_options,
                               format_func=lambda v: v if v == "(none)" else auto_analyst.humanize(v),
                               key=f"pv_cols_{key_prefix}")
    with val_col:
        value_options = measures + ["(count of rows)"]
        values = st.selectbox("Values", value_options,
                              format_func=lambda v: v if v.startswith("(") else auto_analyst.humanize(v),
                              key=f"pv_vals_{key_prefix}")
    with agg_col:
        how = st.selectbox("Summarise by", list(AGGREGATIONS),
                           disabled=values == "(count of rows)", key=f"pv_agg_{key_prefix}")

    if not rows:
        st.info("Pick at least one column for **Rows**.")
        return None

    working = frame.copy()

    if values == "(count of rows)":
        working["_count"] = 1
        value_column, aggregation = "_count", "sum"
    else:
        working[values] = pd.to_numeric(working[values], errors="coerce")
        value_column, aggregation = values, AGGREGATIONS[how]

    try:
        pivot = pd.pivot_table(
            working,
            index=rows,
            columns=None if columns == "(none)" else columns,
            values=value_column,
            aggfunc=aggregation,
            fill_value=0,
            margins=True,
            margins_name="Total",
        )
    except Exception as error:
        st.warning(f"That combination could not be pivoted ({error}). Try different columns.")
        return None

    pivot = pivot.rename_axis(index=[auto_analyst.humanize(r) for r in rows])
    if isinstance(pivot, pd.Series):
        pivot = pivot.to_frame(name="Total")
    if value_column == "_count":
        pivot.columns = [("Records" if c == "_count" else c) for c in pivot.columns]

    return pivot.reset_index()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def render_sheet_table(frame, key_prefix, sheet_name=None):
    """Filters, an optional pivot, and a fixed-size scrollable grid."""
    if frame is None or frame.empty:
        st.info("This sheet has no rows to show.")
        return

    total_rows = len(frame)

    with st.expander("🔍 Filters", expanded=False):
        filtered = _filter_controls(frame, key_prefix)

    # Layout controls sit above the grid, where they affect what you are looking at.
    pivot_col, height_col, cols_col = st.columns([1.3, 1.4, 2.3])

    with pivot_col:
        as_pivot = st.checkbox("🔀 Show as pivot table", key=f"dt_pivot_{key_prefix}",
                               help="Roll the rows up by any column, the way a spreadsheet pivot does")
    with height_col:
        height = st.slider("Table height", 240, 900, 430, step=30, key=f"dt_h_{key_prefix}",
                           help="The grid stays this tall and scrolls inside itself")
    with cols_col:
        if as_pivot:
            visible = None
        else:
            visible = st.multiselect(
                "Columns to show", list(filtered.columns), default=list(filtered.columns),
                format_func=auto_analyst.humanize, key=f"dt_show_{key_prefix}",
                help="Hide columns you don't need — the rest scroll sideways",
            )

    if as_pivot:
        table = _pivot_controls(filtered, key_prefix)
        if table is None:
            return
        caption = f"Pivot of {len(filtered):,} row(s)"
        file_stub = "pivot"
    else:
        table = filtered[visible] if visible else filtered
        caption = (f"Showing **{len(filtered):,}** of **{total_rows:,}** row(s)"
                   f" · {len(table.columns)} column(s)")
        file_stub = "rows"

    st.dataframe(table, height=height, use_container_width=True, hide_index=as_pivot)

    left, right = st.columns([3, 1])
    with left:
        st.caption(caption + ("" if as_pivot else " — scroll inside the grid for the rest"))
    with right:
        st.download_button(
            "⬇️ Download CSV",
            table.to_csv(index=not as_pivot).encode("utf-8"),
            file_name=f"{(sheet_name or 'data').replace(' ', '_').lower()}_{file_stub}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"dt_dl_{key_prefix}",
        )


def render(sheets, key_prefix):
    """Sheet-by-sheet data tables."""
    st.write("### 📋 Data Table")
    st.caption("The rows behind the reports — filter them, pivot them, or export what you see.")

    names = list(sheets.keys())

    if len(names) == 1:
        render_sheet_table(sheets[names[0]], f"{key_prefix}_0", names[0])
        return

    tabs = st.tabs([f"📄 {name}" for name in names])
    for tab, name in zip(tabs, names):
        with tab:
            render_sheet_table(sheets[name], f"{key_prefix}_{auto_analyst._slug(name)}", name)
