"""Per-sheet sections + Auto Compare, against the real 3-sheet workbook."""
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

import importlib.util  # noqa: E402

import pandas as pd  # noqa: E402

import auto_analyst  # noqa: E402
import data_cleaner  # noqa: E402

spec = importlib.util.spec_from_file_location("appmod", os.path.join(ROOT, "app.py"))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

xl = pd.ExcelFile(WORKBOOK)
sheets = {}
for name in xl.sheet_names:
    frame = appmod.auto_fix_headers(xl.parse(name))
    frame, _ = data_cleaner.clean_dataframe(frame)
    sheets[name] = frame

print("=" * 74)
print("PART 1 — THE BUG: MERGING SHEETS DESTROYS THE DATA")
print("=" * 74)
merged = appmod.build_master_df(sheets)
merged_profiles = auto_analyst.profile_dataframe(merged)
merged_missing = merged.isna().sum().sum() / merged.size * 100
print(f"  merged into one table : {len(merged)} rows x {len(merged.columns)} columns")
print(f"  missing cells         : {merged_missing:.1f}%")
print("  per sheet instead:")
for name, frame in sheets.items():
    missing = frame.isna().sum().sum() / frame.size * 100
    print(f"    {name:16} {len(frame):4} rows x {len(frame.columns):3} columns | {missing:.1f}% missing")

assert len(merged.columns) > max(len(f.columns) for f in sheets.values()), "merge should inflate columns"
assert merged_missing > 50, "the merged table should be mostly blank - that was the bug"
print("  ✅ confirmed: merging inflates columns and blanks out most cells")

print("\n" + "=" * 74)
print("PART 2 — EACH SHEET NOW ANALYSED ON ITS OWN")
print("=" * 74)
for name, frame in sheets.items():
    profiles = auto_analyst.profile_dataframe(frame)
    scenarios = auto_analyst.build_scenarios(frame, profiles)
    measures = auto_analyst.rank_measures(profiles)
    st_stub.reset()
    auto_analyst.render_auto_dashboard(frame, f"t_{auto_analyst._slug(name)}")
    failures = [m for k, m in st_stub.messages if k == "WARN" and "could not be built" in m]
    print(f"\n  [{name}]")
    print(f"     reports : {len(scenarios)} -> {[s['title'] for s in scenarios]}")
    print(f"     measures: {[auto_analyst.humanize(m['name']) for m in measures[:4]]}")
    print(f"     charts  : {len(st_stub.charts)} | build failures: {len(failures)}")
    for f in failures:
        print("       !", f)
    assert not failures
    assert len(st_stub.charts) >= 8, "sheet section rendered too few charts"

print("\n" + "=" * 74)
print("PART 3 — AUTO COMPARE SECTION")
print("=" * 74)
st_stub.reset()
auto_analyst.render_comparison(sheets, "t_cmp")
charts = [c.data[0].type for c in st_stub.charts]
print(f"  charts: {charts}")
assert len(charts) >= 2, f"comparison should draw at least 2 charts, got {charts}"

for kind, msg in st_stub.messages:
    if kind in ("OK", "WARN", "INFO"):
        print(f"  {kind}: {msg[:150]}")

print("\n  comparison tables:")
for table in st_stub.tables:
    print("   ", list(table.columns))
    print("   ", table.head(4).to_string().replace("\n", "\n    "))

print("\n" + "=" * 74)
print("PART 4 — FULL MULTI-SHEET ENTRY POINT")
print("=" * 74)
st_stub.reset()
auto_analyst.render_sheet_sections(sheets, "t_all")
failures = [m for k, m in st_stub.messages if k == "WARN" and "could not be built" in m]
print(f"  total charts across all sections: {len(st_stub.charts)}")
print(f"  build failures: {len(failures)}")
assert not failures

print("\n" + "=" * 74)
print("PART 5 — SINGLE SHEET STILL BEHAVES AS BEFORE")
print("=" * 74)
one = {"sales_data": sheets["sales_data"]}
st_stub.reset()
auto_analyst.render_sheet_sections(one, "t_one")
info = [m for k, m in st_stub.messages if k == "INFO" and "sheets loaded" in m]
print(f"  charts: {len(st_stub.charts)} | multi-sheet notice shown: {bool(info)}")
assert not info, "single sheet should not show the multi-sheet notice"
assert len(st_stub.charts) >= 8

print("\nALL MULTI-SHEET CHECKS PASSED")
