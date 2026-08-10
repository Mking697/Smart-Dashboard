"""Run the whole pipeline against the user's real (messy) workbook."""
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

import pandas as pd  # noqa: E402

import auto_analyst  # noqa: E402
import geo_maps  # noqa: E402

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("appmod", os.path.join(ROOT, "app.py"))
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)

import data_cleaner
raw = pd.ExcelFile(WORKBOOK).parse("sales_data")
df = appmod.auto_fix_headers(raw)
df, _clean_report = data_cleaner.clean_dataframe(df)

# Column names differ between versions of the workbook (A_OrderID vs OrderID),
# so resolve them by their readable name instead of hard-coding.
_LOOKUP = {auto_analyst.humanize(c).replace(" ", "").lower(): c for c in df.columns}


def col(readable):
    key = readable.replace(" ", "").lower()
    assert key in _LOOKUP, f"no column matching {readable!r} in {list(df.columns)}"
    return _LOOKUP[key]


CITY, STATE, COUNTRY = col("City"), col("State"), col("Country")
REGION, AMOUNT = col("Region"), col("Total Amount")


print("=" * 74)
print("PART 1 — HUMANIZED COLUMN NAMES")
print("=" * 74)
for col in list(df.columns)[:14]:
    print(f"  {str(col):18} ->  {auto_analyst.humanize(col)}")

assert auto_analyst.humanize("Q_TaxAmount") == "Tax Amount"
assert auto_analyst.humanize("W_SalesRep") == "Sales Rep"
assert auto_analyst.humanize("A_OrderID") == "Order ID"

print("\n" + "=" * 74)
print("PART 2 — GEO DETECTION ON THE MESSY REAL COLUMNS")
print("=" * 74)
for name in [CITY, STATE, COUNTRY, REGION]:
    mode = geo_maps.detect_map_mode(df[name], name)
    print(f"  {str(name):12} -> {mode}")

assert geo_maps.detect_map_mode(df[COUNTRY], COUNTRY) == "country", "country still not detected"
assert geo_maps.detect_map_mode(df[STATE], STATE) == "india-states", "state codes still not detected"
assert geo_maps.detect_map_mode(df[CITY], CITY) == "india-districts", "city codes still not detected"

print("\n  state code resolution:")
for v in ["DL", "MH", "KA", "TN", "WB", "UK", "OR", "TS", "Maharashtra", "Pune"]:
    print(f"    {v:14} -> {geo_maps.geo.match_state(v)}")

print("\n  airport/city code resolution:")
for v in ["BOM", "HYD", "BLR", "CCU", "LKO", "Bangalore", "Noida", " Camp"]:
    print(f"    {v:14} -> {geo_maps.geo.match_district(v)}")

print("\n" + "=" * 74)
print("PART 3 — COUNTRY MAP MERGES India/IND/IN/INDIA/Ind")
print("=" * 74)
st_stub.reset()
geo_maps.render_region_map(df, COUNTRY, "Count (Frequency)", "country", "real_country")
choro = [c for c in st_stub.charts if c.data[0].type == "choropleth"]
assert choro, "no country map"
base = choro[0].data[0]
print(f"  regions: {list(base.locations)}   values: {[int(v) for v in base.z]}")
assert set(base.locations) <= {"IND", "USA"}, base.locations
print(f"  traces: {len(choro[0].data)} (India J&K overlay included)")
for kind, msg in st_stub.messages:
    print(f"  {kind}: {msg[:130]}")

print("\n" + "=" * 74)
print("PART 4 — INDIA STATE MAP FROM 2-LETTER CODES")
print("=" * 74)
st_stub.reset()
geo_maps.render_region_map(df, STATE, AMOUNT, "india-states", "real_state")
choro = [c for c in st_stub.charts if c.data[0].type == "choropleth"]
assert choro, "no state map"
print("  states plotted:", sorted(choro[0].data[0].locations))
for kind, msg in st_stub.messages:
    print(f"  {kind}: {msg[:130]}")

print("\n" + "=" * 74)
print("PART 5 — PIN MAP FROM AIRPORT CODES + CITY NAMES")
print("=" * 74)
st_stub.reset()
geo_maps.render_pin_map(df, CITY, AMOUNT, "real_pin")
pins = [c for c in st_stub.charts if c.data[0].type == "scattergeo"]
assert pins, "no pin map"
print(f"  pins plotted: {len(pins[0].data[1].lat)}")
for kind, msg in st_stub.messages:
    print(f"  {kind}: {msg[:130]}")

print("\n" + "=" * 74)
print("PART 6 — COLUMN ROLES ON REAL DATA")
print("=" * 74)
profiles = auto_analyst.profile_dataframe(df)
for p in profiles:
    print(f"  {auto_analyst.humanize(p['name']):20} {p['role']:11} distinct={p['n_unique']:<5} missing={p['missing_pct']}%")

roles = {p["name"]: p["role"] for p in profiles}
assert roles[COUNTRY] == "geo", roles[COUNTRY]
assert roles[STATE] == "geo", roles[STATE]
assert roles[CITY] == "geo", roles[CITY]
assert roles[AMOUNT] == "measure", roles[AMOUNT]

print("\n" + "=" * 74)
print("PART 7 — REPORTS BUILT + EVERY ONE RENDERS")
print("=" * 74)
scenarios = auto_analyst.build_scenarios(df, profiles)
for s in scenarios:
    st_stub.reset()
    s["render"](df, profiles, "real")
    charts = [c.data[0].type for c in st_stub.charts]
    problems = [m for k, m in st_stub.messages if k in ("ERROR",)]
    print(f"\n  {s['title']}")
    print(f"     Q: {s.get('question')}")
    print(f"     charts: {charts}")
    for kind, msg in st_stub.messages:
        if kind in ("OK", "CAPTION") and ("What it means" in msg or "How to read" in msg):
            print(f"     {msg[:150]}")
    assert not problems, problems

print("\n" + "=" * 74)
print("PART 8 — FULL DASHBOARD, NO DUPLICATE CHART KEYS")
print("=" * 74)
st_stub.reset()
auto_analyst.render_auto_dashboard(df, "real_full")
print(f"  charts rendered: {len(st_stub.charts)}")
failures = [m for k, m in st_stub.messages if k == "WARN" and "could not be built" in m]
assert not failures, failures

import re  # noqa: E402

src = open(os.path.join(ROOT, "auto_analyst.py"), encoding="utf-8").read()
src += open(os.path.join(ROOT, "geo_maps.py"), encoding="utf-8").read()
src += open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
unkeyed = [m for m in re.findall(r"st\.plotly_chart\([^)]*\)", src) if "key=" not in m]
print(f"  plotly_chart calls without a key: {len(unkeyed)}")
assert not unkeyed, unkeyed

print("\nALL REAL-DATA CHECKS PASSED")
