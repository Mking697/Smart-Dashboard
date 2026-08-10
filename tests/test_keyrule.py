"""Key-column rule: what each setting keeps and drops."""
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

import data_cleaner  # noqa: E402

spec = importlib.util.spec_from_file_location("appmod", os.path.join(ROOT, "app.py"))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

print("=" * 74)
print("PART 1 — BLANK KEY vs KEY-ONLY ROWS")
print("=" * 74)

sheet = pd.DataFrame({
    "OrderID": ["ORD1", "ORD2", None, "ORD4", "ORD5", None],
    "Customer": ["Amit", "Sara", "Ghost", None, "Raj", None],
    "City": ["Mumbai", "Delhi", "Pune", None, "Jaipur", None],
    "Amount": [100.0, 200.0, 300.0, None, 500.0, None],
})
print(sheet.to_string())
print()
print("  Row 2 -> blank OrderID but real data behind it")
print("  Row 3 -> has OrderID, nothing else (the ORD020 case in your sheet)")
print("  Row 5 -> completely blank")
print()

cases = [
    ("both rules ON  (default)", True, True),
    ("only key rule  (your rule)", True, False),
    ("only sparse rule", False, True),
    ("both OFF", False, False),
]
for label, key, sparse in cases:
    clean, report = data_cleaner.clean_dataframe(sheet.copy(), require_key_column=key, drop_sparse_rows=sparse)
    kept = clean["OrderID"].fillna("(blank)").tolist()
    print(f"  {label:28} kept {len(clean)} rows -> {kept}")
    print(f"  {'':28} blank-key removed={report['key_blank_rows']} sparse removed={report['sparse_rows']} blank removed={report['blank_rows']}")

both = data_cleaner.clean_dataframe(sheet.copy(), True, True)[0]
key_only = data_cleaner.clean_dataframe(sheet.copy(), True, False)[0]
assert len(both) == 3, both
assert len(key_only) == 4, key_only
assert "ORD4" in key_only["OrderID"].tolist(), "key-only rule should keep the key-with-no-data row"
assert "ORD4" not in both["OrderID"].tolist(), "both rules should drop the key-with-no-data row"

print("\n" + "=" * 74)
print("PART 2 — MOSTLY-EMPTY FIRST COLUMN MUST NOT DELETE THE SHEET")
print("=" * 74)
notes_first = pd.DataFrame({
    "Notes": [None, None, "check this", None, None],
    "Product": ["A", "B", "C", "D", "E"],
    "Sales": [10, 20, 30, 40, 50],
})
clean, report = data_cleaner.clean_dataframe(notes_first)
print(f"  first column {report['key_column']!r} filled 20% -> rule skipped: {report['key_column_skipped']}")
print(f"  rows kept: {len(clean)} of {len(notes_first)}")
assert report['key_column_skipped'] is True
assert len(clean) == 5, "a notes column must never be treated as a key"

print("\n" + "=" * 74)
print("PART 3 — REAL WORKBOOK, EACH SETTING")
print("=" * 74)
xl = pd.ExcelFile(WORKBOOK)
for name in xl.sheet_names:
    fixed = appmod.auto_fix_headers(xl.parse(name))
    line = f"  {name:16}raw={len(fixed):4}"
    for label, key, sparse in cases:
        clean, _ = data_cleaner.clean_dataframe(fixed.copy(), require_key_column=key, drop_sparse_rows=sparse)
        line += f" | {label.split('(')[0].strip()}={len(clean):4}"
    print(line)

print("\n" + "=" * 74)
print("PART 4 — 1000-ROW SHEET STILL COLLAPSES TO ITS 100 REAL ROWS")
print("=" * 74)
real = pd.DataFrame({
    "InvoiceNo": [f"INV{i:04d}" for i in range(100)],
    "Party": ["A", "B"] * 50,
    "Amount": range(100),
})
padding = pd.DataFrame({c: [None] * 900 for c in real.columns})
big = pd.concat([real, padding], ignore_index=True)
clean, report = data_cleaner.clean_dataframe(big)
print(f"  {report['rows_before']} rows -> {report['rows_after']} rows "
      f"(blank={report['blank_rows']}, blank key={report['key_blank_rows']})")
assert report['rows_after'] == 100

print("\nALL KEY-RULE CHECKS PASSED")
