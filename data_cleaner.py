"""Turn an unmanaged sheet into a table worth charting.

Real spreadsheets arrive with blank rows between sections, an "END" marker at the
bottom, 900 empty rows below the last record, stray spaces (" Noida"), and
placeholder text like "N/A" or "-" standing in for nothing at all.

Every chart in this app is only as honest as the rows underneath it, so the data
is cleaned first and the user is told exactly what was removed - nothing happens
silently.
"""

import pandas as pd

# Text that means "no value" even though the cell is not technically empty.
BLANK_TOKENS = {
    '', '-', '--', '---', 'n/a', 'na', 'n.a.', 'null', 'none', 'nan', 'nil',
    '#n/a', '#value!', '#ref!', '#div/0!', '#name?', '?', '.', 'tbd', 'unknown',
}

# Footer/marker rows people leave at the bottom of a sheet.
FOOTER_TOKENS = {
    'end', 'the end', 'total', 'totals', 'grand total', 'sub total', 'subtotal',
    'sum', 'x', 'xx', 'xxx', 'eof',
}

# A row must have at least this share of its columns filled to count as a record.
MIN_ROW_FILL = 0.25

# Keep the sparse-row filter from eating a genuinely sparse dataset.
MAX_SPARSE_REMOVAL = 0.5

# The first column only counts as a key if it is mostly filled in.
MIN_KEY_FILL = 0.5

# A column this numeric is treated as a number column; junk values become blanks.
NUMERIC_COERCE_THRESHOLD = 0.8


def coerce_numeric_columns(dataframe, threshold=NUMERIC_COERCE_THRESHOLD):
    """Make mostly-numeric columns actually numeric.

    One stray date or note in a sales column is enough to leave the whole column
    as text, which silently drops it from every chart. If most of the values are
    numbers, keep the numbers and null out the rest.
    """
    for column in dataframe.columns:
        if pd.api.types.is_numeric_dtype(dataframe[column]) or pd.api.types.is_datetime64_any_dtype(dataframe[column]):
            continue

        non_null = dataframe[column].dropna()
        if non_null.empty:
            continue

        coerced = pd.to_numeric(dataframe[column], errors='coerce')
        if coerced.notna().sum() / len(non_null) >= threshold:
            dataframe[column] = coerced

    return dataframe


def _tidy_text_cells(dataframe):
    """Trim stray spaces and turn placeholder text into real blanks."""
    trimmed = blanked = 0

    for column in dataframe.columns:
        series = dataframe[column]
        if not (series.dtype == object or isinstance(series.dtype, pd.StringDtype)):
            continue

        is_text = series.map(lambda value: isinstance(value, str))
        if not is_text.any():
            continue

        stripped = series.where(~is_text, series.where(~is_text, series.astype(str)).str.strip())
        trimmed += int((is_text & (stripped != series)).sum())

        looks_blank = is_text & stripped.where(~is_text, stripped.astype(str)).str.lower().isin(BLANK_TOKENS)
        blanked += int(looks_blank.sum())

        dataframe[column] = stripped.mask(looks_blank, None)

    return dataframe, trimmed, blanked


def _is_footer_row(row):
    """A lone 'END' / 'Grand Total' sitting under the real data."""
    values = row.dropna()
    if len(values) != 1:
        return False
    return str(values.iloc[0]).strip().lower() in FOOTER_TOKENS


def clean_dataframe(dataframe, require_key_column=True, drop_sparse_rows=True):
    """Clean an unmanaged sheet. Returns (clean dataframe, report dict).

    Only rows that actually carry data survive: a sheet with 1,000 rows and 100
    real records is charted as 100 records.

    Two independent rules decide what a real record is:

    * ``require_key_column`` - the first column is the key (Order ID, Invoice No,
      Transaction ID). A row with a blank key is not a record. Skipped
      automatically when the first column is itself mostly blank, since it is
      then a note column rather than a key.
    * ``drop_sparse_rows`` - a row that fills less than a quarter of its columns
      is a leftover, not a record. This is what catches a row holding an order
      number and nothing else: a key with no data behind it still counts for
      nothing, and would otherwise inflate every total by one.
    """
    report = {
        'rows_before': len(dataframe),
        'columns_before': len(dataframe.columns),
        'blank_rows': 0,
        'sparse_rows': 0,
        'footer_rows': 0,
        'key_blank_rows': 0,
        'key_only_rows': 0,
        'key_column': None,
        'key_column_skipped': False,
        'empty_columns': 0,
        'trimmed_cells': 0,
        'placeholder_cells': 0,
        'duplicate_rows': 0,
        'rows_after': len(dataframe),
        'columns_after': len(dataframe.columns),
    }

    if dataframe is None or dataframe.empty:
        return dataframe, report

    frame = dataframe.copy()

    # 1. Tidy the text before deciding what counts as empty.
    frame, report['trimmed_cells'], report['placeholder_cells'] = _tidy_text_cells(frame)

    # 2. Columns with nothing in them at all.
    empty_columns = [column for column in frame.columns if frame[column].isna().all()]
    if empty_columns:
        frame = frame.drop(columns=empty_columns)
        report['empty_columns'] = len(empty_columns)
        report['empty_column_names'] = empty_columns

    if frame.empty or not len(frame.columns):
        report.update(rows_after=len(frame), columns_after=len(frame.columns))
        return frame, report

    # 3. Completely blank rows - the 900 empty rows under the real data.
    blank_mask = frame.isna().all(axis=1)
    report['blank_rows'] = int(blank_mask.sum())
    frame = frame[~blank_mask]

    # 4. Footer markers such as a lone "END".
    if len(frame):
        footer_mask = frame.apply(_is_footer_row, axis=1)
        report['footer_rows'] = int(footer_mask.sum())
        frame = frame[~footer_mask]

    # 5. The key column: no key, no record.
    if require_key_column and len(frame):
        key_column = frame.columns[0]
        filled_ratio = frame[key_column].notna().mean()

        if filled_ratio >= MIN_KEY_FILL:
            report['key_column'] = key_column
            key_blank = frame[key_column].isna()
            report['key_blank_rows'] = int(key_blank.sum())
            frame = frame[~key_blank]
        else:
            # A first column that is itself mostly empty is a note column, not a
            # key - using it would delete most of the sheet.
            report['key_column'] = key_column
            report['key_column_skipped'] = True

    # 6. Rows too sparse to be a record (section separators, stray notes,
    #    and keys with nothing behind them).
    if drop_sparse_rows and len(frame):
        filled = frame.notna().sum(axis=1)

        # A row holding its key and nothing else is not a record - an order
        # number with no customer, date or amount would still add one to every
        # count. Checked exactly rather than by percentage, so it works the same
        # on a 4-column sheet and a 40-column one.
        if report.get('key_column') and not report.get('key_column_skipped'):
            key_only = (filled == 1) & frame[report['key_column']].notna()

            # Same back-off as the sparse filter: if most rows look like this,
            # the sheet really is just a list of keys - keep it rather than
            # deleting everything.
            if 0 < key_only.sum() <= MAX_SPARSE_REMOVAL * len(frame):
                report['key_only_rows'] = int(key_only.sum())
                frame = frame[~key_only]
                filled = filled[~key_only]

    if drop_sparse_rows and len(frame):
        fill_ratio = frame.notna().sum(axis=1) / len(frame.columns)
        sparse_mask = fill_ratio < MIN_ROW_FILL

        # If most rows look sparse, the data really is sparse - keep it all.
        if 0 < sparse_mask.sum() <= MAX_SPARSE_REMOVAL * len(frame):
            report['sparse_rows'] = int(sparse_mask.sum())
            frame = frame[~sparse_mask]

    # 6. Report duplicates, but never delete them silently.
    if len(frame):
        report['duplicate_rows'] = int(frame.duplicated().sum())

    frame = frame.reset_index(drop=True)
    frame = coerce_numeric_columns(frame)

    report['rows_after'] = len(frame)
    report['columns_after'] = len(frame.columns)
    report['rows_removed'] = report['rows_before'] - report['rows_after']

    return frame, report


def report_lines(report):
    """Human-readable bullets describing what the cleaner did."""
    lines = []

    if report.get('blank_rows'):
        lines.append(f"Removed **{report['blank_rows']:,} completely blank row(s)** — empty rows are never charted.")
    if report.get('key_blank_rows'):
        lines.append(f"Removed **{report['key_blank_rows']:,} row(s) with no **{report.get('key_column')}**"
                     " — that is the key column, so a blank there means it is not a record.")
    if report.get('key_column_skipped'):
        lines.append(f"Skipped the key-column rule: **{report.get('key_column')}** is itself mostly "
                     "empty, so it is a notes column rather than a key.")
    if report.get('key_only_rows'):
        lines.append(f"Removed **{report['key_only_rows']:,} row(s) that had only a "
                     f"**{report.get('key_column')}** and nothing else — a key with no data behind it "
                     "would add a phantom record to every total.")
    if report.get('sparse_rows'):
        lines.append(f"Removed **{report['sparse_rows']:,} nearly-empty row(s)** — too few values "
                     "to measure anything.")
    if report.get('footer_rows'):
        lines.append(f"Removed **{report['footer_rows']:,} footer row(s)** such as a lone “END” or “Total” marker.")
    if report.get('empty_columns'):
        names = ", ".join(str(name) for name in report.get('empty_column_names', [])[:5])
        lines.append(f"Dropped **{report['empty_columns']} empty column(s)**{f' ({names})' if names else ''}.")
    if report.get('trimmed_cells'):
        lines.append(f"Trimmed stray spaces in **{report['trimmed_cells']:,} cell(s)** — “ Noida” and “Noida” now count as one place.")
    if report.get('placeholder_cells'):
        lines.append(f"Treated **{report['placeholder_cells']:,} placeholder value(s)** like “N/A”, “-” or “NULL” as blank.")
    if report.get('duplicate_rows'):
        lines.append(f"⚠️ Found **{report['duplicate_rows']:,} duplicate row(s)** — left in place, but they will inflate your totals.")

    return lines
