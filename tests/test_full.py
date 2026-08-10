"""Integration test: geo_maps + auto_analyst against Indian-shaped data."""
import os
import sys

# Run from anywhere: the project root is one level up from tests/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

st_stub.install()

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import auto_analyst  # noqa: E402
import geo_maps  # noqa: E402

rng = np.random.default_rng(7)
n = 300

cities = ["Mumbai", "Bangalore", "Delhi", "Pune", "Srinagar", "Leh", "Jaipur", "Kochi", "Gurgaon", "Kolkata"]
states = ["Maharashtra", "Karnataka", "Delhi", "Maharashtra", "Jammu and Kashmir",
          "Ladakh", "Rajasthan", "Kerala", "Haryana", "West Bengal"]
city_to_state = dict(zip(cities, states))

picked = rng.choice(cities, n)
df = pd.DataFrame({
    "Order_ID": [f"ORD{i:05d}" for i in range(n)],
    "I_Country": rng.choice(["India", "IND", "IN"], n),          # same country, 3 spellings
    "State": [city_to_state[c] for c in picked],
    "City": picked,
    "Category": rng.choice(["Electronics", "Apparel", "Grocery", "Furniture"], n),
    "Order_Date": pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 400, n), unit="D"),
    "Revenue": rng.gamma(3, 4000, n).round(2),
    "Quantity": rng.integers(1, 12, n),
})
df.loc[df.sample(18, random_state=3).index, "Revenue"] = np.nan

print("=" * 70)
print("PART 1 — GEO DETECTION")
print("=" * 70)
for col in ["I_Country", "State", "City", "Category", "Order_ID"]:
    print(f"  {col:12} -> {geo_maps.detect_map_mode(df[col], col)}")

assert geo_maps.detect_map_mode(df["I_Country"], "I_Country") == "country"
assert geo_maps.detect_map_mode(df["State"], "State") == "india-states"
assert geo_maps.detect_map_mode(df["City"], "City") == "india-districts"

print("\n" + "=" * 70)
print("PART 2 — COUNTRY MAP: India/IND/IN must merge into ONE region")
print("=" * 70)
st_stub.reset()
geo_maps.render_region_map(df, "I_Country", "Count (Frequency)", "country", "t_country")

choro = [c for c in st_stub.charts if c.data[0].type == "choropleth"]
assert choro, "no country map rendered"
fig = choro[0]
base = fig.data[0]
print(f"  regions on map : {list(base.locations)}  (was India/IND/IN = 3 separate)")
print(f"  value          : {list(base.z)}  (expected {len(df)} = all rows)")
assert list(base.locations) == ["IND"], f"expected one merged region, got {list(base.locations)}"
assert int(base.z[0]) == len(df)

print(f"  traces         : {len(fig.data)} (base + India J&K overlay)")
assert len(fig.data) == 2, "India overlay trace missing — J&K would not be drawn"
overlay = fig.data[1]
assert overlay.geojson is not None and overlay.locations[0] == "IND"
states_in_overlay = len(overlay.geojson["features"][0]["geometry"]["coordinates"])
print(f"  overlay polygons: {states_in_overlay} (drawn from bundled India boundary)")
for kind, msg in st_stub.messages:
    print(f"  {kind}: {msg}")

print("\n" + "=" * 70)
print("PART 3 — INDIA STATE MAP (J&K + Ladakh present)")
print("=" * 70)
st_stub.reset()
geo_maps.render_region_map(df, "State", "Revenue", "india-states", "t_state")
choro = [c for c in st_stub.charts if c.data[0].type == "choropleth"]
assert choro, "no state map rendered"
locs = list(choro[0].data[0].locations)
print("  states plotted:", locs)
assert "Jammu and Kashmir" in locs and "Ladakh" in locs
geojson_states = {f["properties"]["st_nm"] for f in choro[0].data[0].geojson["features"]}
print("  J&K in boundary file  :", "Jammu and Kashmir" in geojson_states)
print("  Ladakh in boundary file:", "Ladakh" in geojson_states)

print("\n" + "=" * 70)
print("PART 4 — BLINKING PIN MAP (city names, no lat/long columns)")
print("=" * 70)
st_stub.reset()
geo_maps.render_pin_map(df, "City", "Revenue", "t_pin")
pins = [c for c in st_stub.charts if c.data[0].type == "scattergeo"]
assert pins, "no pin map rendered"
fig = pins[0]
print(f"  traces: {len(fig.data)} (halo + pins + labels)")
marker_trace = fig.data[1]
print(f"  pins plotted: {len(marker_trace.lat)}")
print(f"  hovertemplate: {marker_trace.hovertemplate}")
print(f"  sample coords: {[(round(a, 2), round(b, 2)) for a, b in list(zip(marker_trace.lat, marker_trace.lon))[:4]]}")
assert len(marker_trace.lat) >= 8
for kind, msg in st_stub.messages:
    print(f"  {kind}: {msg}")

print("\n" + "=" * 70)
print("PART 5 — AUTO ANALYST PROFILING")
print("=" * 70)
profiles = auto_analyst.profile_dataframe(df)
for p in profiles:
    print(f"  {p['name']:12} role={p['role']:11} distinct={p['n_unique']:<5} missing={p['missing_pct']}%")

roles = {p["name"]: p["role"] for p in profiles}
assert roles["Order_ID"] == "identifier"
assert roles["Order_Date"] == "date"
assert roles["Revenue"] == "measure"
assert roles["Quantity"] == "measure"
assert roles["Category"] == "category"
assert roles["State"] == "geo"

print("\n" + "=" * 70)
print("PART 6 — SCENARIOS BUILT AUTOMATICALLY")
print("=" * 70)
scenarios = auto_analyst.build_scenarios(df, profiles)
for s in scenarios:
    print(f"  {s['title']:28} — {s['why'][:70]}")

titles = [s["title"] for s in scenarios]
for expected in ["📊 Business Overview", "📈 Growth Over Time", "🏆 Top Performers",
                 "📉 What Is Normal", "🔗 What Affects What",
                 "🧮 Best Combinations", "🌍 Location Map", "🧪 Can You Trust This Data"]:
    assert expected in titles, f"missing scenario: {expected}"

print("\n" + "=" * 70)
print("PART 7 — EVERY SCENARIO RENDERS WITHOUT ERROR")
print("=" * 70)
for s in scenarios:
    st_stub.reset()
    s["render"](df, profiles, "t_auto")
    kinds = [c.data[0].type for c in st_stub.charts]
    errors = [m for k, m in st_stub.messages if k in ("ERROR", "WARN")]
    print(f"  {s['title']:28} charts={kinds}")
    for e in errors:
        print(f"      note: {e[:110]}")

print("\n" + "=" * 70)
print("PART 8 — FULL AUTO DASHBOARD + AI BRIEFING TEXT")
print("=" * 70)
st_stub.reset()
auto_analyst.render_auto_dashboard(df, "t_full")
print(f"  charts rendered: {len(st_stub.charts)}")
print(f"  profile table rows: {len(st_stub.tables[0]) if st_stub.tables else 0}")
failures = [m for k, m in st_stub.messages if k == "WARN" and "could not be built" in m]
assert not failures, f"scenario failures: {failures}"

briefing = auto_analyst.build_ai_briefing(df, profiles, scenarios)
print("\n  --- AI briefing payload (first 12 lines) ---")
for line in briefing.split("\n")[:12]:
    print("   ", line)

print("\nALL INTEGRATION CHECKS PASSED")
