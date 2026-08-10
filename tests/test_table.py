"""Data table: filters, pivot, sizing, export."""
import os
import sys

# Run from anywhere: the project root is one level up from tests/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

st_stub.install()

import pandas as pd  # noqa: E402

import data_table  # noqa: E402
import sample_data  # noqa: E402

df = sample_data.build_sample_workbook()["Sales 2025-26"]

print("=" * 74)
print("PART 1 — SEARCH MATCHES ACROSS EVERY COLUMN")
print("=" * 74)
print(f"  all rows          : {len(df)}")
for term in ["Mumbai", "Laptop", "ORD-25010", "zzzznope"]:
    hit = data_table._apply_search(df, term)
    print(f"  search {term!r:12} -> {len(hit):4} row(s)")
assert len(data_table._apply_search(df, "Mumbai")) > 0
assert len(data_table._apply_search(df, "zzzznope")) == 0
assert len(data_table._apply_search(df, "")) == len(df), "empty search must not filter"

print("\n" + "=" * 74)
print("PART 2 — COLUMN KINDS DRIVE THE RIGHT WIDGET")
print("=" * 74)
for column in ["Order Date", "Total Amount", "City", "Quantity", "Order ID"]:
    print(f"  {column:14} -> {data_table._column_kind(df[column])}")
assert data_table._column_kind(df["Order Date"]) == "date"
assert data_table._column_kind(df["Total Amount"]) == "number"
assert data_table._column_kind(df["City"]) == "text"

print("\n" + "=" * 74)
print("PART 3 — PIVOT BUILDS AND TOTALS CORRECTLY")
print("=" * 74)


def pivot_with(rows, columns, values, how):
    """Drive _pivot_controls by pinning the widget answers."""
    answers = {"rows": rows, "cols": columns, "vals": values, "agg": how}
    st_stub.stub.multiselect = lambda label, options, default=None, **k: (
        answers["rows"] if label == "Rows" else (default if default is not None else list(options))
    )

    def _select(label, options, index=0, **k):
        if label == "Columns":
            return answers["cols"]
        if label == "Values":
            return answers["vals"]
        if label == "Summarise by":
            return answers["agg"]
        return list(options)[index]

    st_stub.stub.selectbox = _select
    return data_table._pivot_controls(df, "t")


pivot = pivot_with(["Region"], "(none)", "Total Amount", "Sum")
print(pivot.to_string(index=False))

grand = pivot[pivot["Region"] == "Total"]["Total Amount"].iloc[0]
actual = df["Total Amount"].sum()
print(f"\n  pivot grand total : {grand:,.2f}")
print(f"  dataframe sum     : {actual:,.2f}")
assert abs(grand - actual) < 1, "pivot total must match the data"

print("\n  --- two dimensions, Region x Category (Sum of Quantity) ---")
pivot2 = pivot_with(["Region"], "Category", "Quantity", "Sum")
print(pivot2.to_string(index=False))
assert "Total" in pivot2.columns or "Total" in pivot2["Region"].values

print("\n  --- count of rows ---")
pivot3 = pivot_with(["Channel"], "(none)", "(count of rows)", "Sum")
print(pivot3.to_string(index=False))
total_row = pivot3[pivot3["Channel"] == "Total"]
counted = total_row.iloc[0, 1]
print(f"\n  counted rows: {counted}  (dataframe has {len(df)})")
assert counted == len(df)

print("\n  --- average instead of sum ---")
pivot4 = pivot_with(["Category"], "(none)", "Unit Price", "Average")
print(pivot4.to_string(index=False))

print("\n" + "=" * 74)
print("PART 4 — FULL RENDER, BOTH MODES")
print("=" * 74)
st_stub.install()  # restore plain stub behaviour

for pivot_on in (False, True):
    st_stub.reset()
    st_stub.stub.checkbox = lambda label, **k: pivot_on
    st_stub.stub.slider = lambda label, lo, hi, default=None, **k: (default if default is not None else lo)
    data_table.render_sheet_table(df, f"t_{pivot_on}", "Sales")
    errors = [m for k, m in st_stub.messages if k == "ERROR"]
    tables = len(st_stub.tables)
    print(f"  pivot={str(pivot_on):5} -> grids rendered: {tables} | errors: {len(errors)}")
    for e in errors:
        print("    !", e)
    assert not errors
    assert tables == 1, f"expected exactly one grid, got {tables}"

print("\n" + "=" * 74)
print("PART 5 — MULTI-SHEET ENTRY POINT")
print("=" * 74)
st_stub.reset()
st_stub.stub.checkbox = lambda label, **k: False
sheets = {"Sales": df, "Returns": df.head(40)}
data_table.render(sheets, "multi")
print(f"  grids rendered for {len(sheets)} sheets: {len(st_stub.tables)}")
assert len(st_stub.tables) == 2

print("\nALL DATA TABLE CHECKS PASSED")
