"""Test the data cleaner: blank rows, footers, placeholders, real workbook."""
import os
import sys

# Run from anywhere: the project root is one level up from tests/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

WORKBOOK = os.environ.get("SAMPLE_WORKBOOK", r"C:/Users/Admin/Desktop/Company Data1.xlsx")
if not os.path.exists(WORKBOOK):
    print(f"SKIPPED - needs a messy workbook at {WORKBOOK}")
    print("Set SAMPLE_WORKBOOK to point at one, or run the other suites.")
    raise SystemExit(0)

st_stub.install()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import data_cleaner  # noqa: E402

print("=" * 74)
print("PART 1 — 1000-ROW SHEET WITH ONLY 100 REAL RECORDS")
print("=" * 74)

real = pd.DataFrame({
    "Customer": [f"Cust {i}" for i in range(100)],
    "City": ["Mumbai", " Noida", "Delhi", "Pune"] * 25,
    "Amount": np.arange(100) * 100.0,
    "Status": ["Paid", "Pending"] * 50,
})
padding = pd.DataFrame({c: [None] * 900 for c in real.columns})
footer = pd.DataFrame([{"Customer": "END", "City": None, "Amount": None, "Status": None}])
note = pd.DataFrame([{"Customer": None, "City": None, "Amount": None, "Status": "N/A"}])
messy = pd.concat([real, note, footer, padding], ignore_index=True)

print(f"  sheet as loaded: {len(messy)} rows")
clean, report = data_cleaner.clean_dataframe(messy)
print(f"  after cleaning : {len(clean)} rows")
for line in data_cleaner.report_lines(report):
    print("   -", line.replace("**", ""))

assert len(clean) == 100, f"expected 100 usable rows, got {len(clean)}"
assert report['blank_rows'] >= 900
assert report['footer_rows'] == 1
assert clean['City'].isin(['Mumbai', 'Noida', 'Delhi', 'Pune']).all(), "spaces not trimmed"
print("  ✅ only rows with data survived, ' Noida' trimmed to 'Noida'")

print("\n" + "=" * 74)
print("PART 2 — PLACEHOLDERS BECOME REAL BLANKS")
print("=" * 74)
ph = pd.DataFrame({
    "Name": ["Amit", "Sara", "Raj", "John"],
    "Region": ["North", "N/A", "-", "South"],
    "Sales": [100, 200, 300, 400],
    "Notes": ["ok", "NULL", "#N/A", "fine"],
})
clean_ph, rep_ph = data_cleaner.clean_dataframe(ph)
print("  Region column after cleaning:", clean_ph['Region'].tolist())
print("  Notes  column after cleaning:", clean_ph['Notes'].tolist())
print(f"  placeholder cells blanked: {rep_ph['placeholder_cells']}")
assert clean_ph['Region'].isna().sum() == 2
assert rep_ph['placeholder_cells'] == 4
assert len(clean_ph) == 4, "no real rows should be lost"

print("\n" + "=" * 74)
print("PART 3 — GENUINELY SPARSE DATA MUST NOT BE WIPED OUT")
print("=" * 74)
sparse = pd.DataFrame({
    "A": [1, None, None, None, 5],
    "B": [None, None, None, None, None],
    "C": [None, 2, None, None, None],
    "D": [None, None, 3, None, None],
})
# With the key rule on, a row without a value in the first column is not a record.
clean_key, rep_key = data_cleaner.clean_dataframe(sparse.copy())
print(f"  key rule ON : {len(sparse)} -> {len(clean_key)} rows "
      f"(blank key removed: {rep_key['key_blank_rows']}, empty col dropped: {rep_key['empty_columns']})")
assert len(clean_key) == 2, clean_key

# With it off, the percentage-based sparse filter must not delete real rows.
clean_sp, rep_sp = data_cleaner.clean_dataframe(sparse.copy(), require_key_column=False)
print(f"  key rule OFF: {len(sparse)} -> {len(clean_sp)} rows (sparse removed: {rep_sp['sparse_rows']})")
assert len(clean_sp) == 4, "sparse-but-real rows were deleted"
print("  ✅ key rule removes keyless rows; sparse filter alone keeps real data")

print("\n" + "=" * 74)
print("PART 4 — REAL WORKBOOK (Company Data1.xlsx)")
print("=" * 74)
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("appmod", os.path.join(ROOT, "app.py"))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

xl = pd.ExcelFile(WORKBOOK)
for sheet in xl.sheet_names:
    raw = xl.parse(sheet)
    fixed = appmod.auto_fix_headers(raw.copy())
    clean, report = data_cleaner.clean_dataframe(fixed)
    print(f"\n  [{sheet}] {report['rows_before']} rows -> {report['rows_after']} usable "
          f"| {report['columns_before']} cols -> {report['columns_after']}")
    for line in data_cleaner.report_lines(report):
        print("     -", line.replace("**", ""))

print("\n" + "=" * 74)
print("PART 5 — CLEANED DATA STILL BUILDS EVERY REPORT")
print("=" * 74)
import auto_analyst  # noqa: E402

raw = xl.parse("sales_data")
df = appmod.auto_fix_headers(raw.copy())
df, _ = data_cleaner.clean_dataframe(df)
profiles = auto_analyst.profile_dataframe(df)
scenarios = auto_analyst.build_scenarios(df, profiles)

st_stub.reset()
auto_analyst.render_auto_dashboard(df, "clean_test")
failures = [m for k, m in st_stub.messages if k == "WARN" and "could not be built" in m]
print(f"  reports built: {len(scenarios)} | charts rendered: {len(st_stub.charts)} | failures: {len(failures)}")
for f in failures:
    print("   !", f)
assert not failures

kpis = [m for k, m in st_stub.messages if "What it means" in m]
for m in kpis[:3]:
    print("   ", m[:140])

print("\nALL CLEANER CHECKS PASSED")
