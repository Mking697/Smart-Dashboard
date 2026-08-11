"""The judgement calls: what gets totalled, what gets trimmed, what gets flagged.

Each part here exists because a real export got it wrong. A per-unit price was
headlined as a total, one stray 1900 date flattened a year of trading into a
single spike, a cross-tab came out nine-tenths empty, and the map never reached
the PDF at all.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

st_stub.install()

import pandas as pd  # noqa: E402

import auto_analyst  # noqa: E402
import capture  # noqa: E402
import sample_data  # noqa: E402

df = sample_data.build_sample_workbook()["Sales 2025-26"]
profiles = auto_analyst.profile_dataframe(df)

print("=" * 74)
print("PART 1 — A RATE IS NEVER TOTALLED")
print("=" * 74)

cases = {
    "Unit Price": True, "Q_UnitPrice": True, "price per box": True,
    "Growth Rate": True, "Rating": True, "avg_ticket": True, "Tax Percent": True,
    "Total Amount": False, "Corporate Sales": False, "Quantity": False,
    "Tax Amount": False, "Discount": False, "Revenue": False,
}
for name, expected in cases.items():
    actual = auto_analyst.is_rate(name)
    flag = "OK" if actual == expected else "WRONG"
    print(f"  [{flag}] {name:<18} rate={actual}")
    assert actual == expected, f"{name}: expected rate={expected}"

print("\n  'Corporate' must not trip the 'rate' hint - word boundaries matter.")

rated = pd.DataFrame({
    "Unit Price": [10.0, 20.0, 30.0, 40.0],
    "Total Amount": [100.0, 200.0, 300.0, 400.0],
    "Sales Rep": ["A", "A", "B", "B"],
})
rp = auto_analyst.profile_dataframe(rated)
print(f"\n  agg for Unit Price   : {auto_analyst.agg_for(rp, 'Unit Price')}")
print(f"  agg for Total Amount : {auto_analyst.agg_for(rp, 'Total Amount')}")
assert auto_analyst.agg_for(rp, "Unit Price") == "mean"
assert auto_analyst.agg_for(rp, "Total Amount") == "sum"

ranked = [m["name"] for m in auto_analyst.rank_measures(rp)]
print(f"  measures ranked      : {ranked}")
assert ranked[0] == "Total Amount", "a rate must never headline a report"

with auto_analyst.capturing() as blocks:
    auto_analyst._kpi_row(rated, rp)
labels = [payload[0] for kind, payload in blocks if kind == "kpi"]
print(f"  KPI labels           : {labels}")
assert "Average Unit Price" in labels, "a per-unit price must be averaged, not summed"
assert not any(label.startswith("Total Unit") for label in labels), "'Total Unit Price' is meaningless"

print("\n" + "=" * 74)
print("PART 2 — ONE STRAY DATE DOES NOT FLATTEN A CHART")
print("=" * 74)

clean = pd.Series(pd.date_range("2024-01-01", periods=200, freq="D"))
print(f"  200 clean days              : {auto_analyst.usable_date_window(clean)}")
assert auto_analyst.usable_date_window(clean) is None, "clean dates must be left alone"

decades = pd.Series(pd.date_range("1990-01-01", periods=400, freq="ME"))
print(f"  a genuine 33-year span      : {auto_analyst.usable_date_window(decades)}")
assert auto_analyst.usable_date_window(decades) is None, "real long history must survive"

junk = pd.concat([clean, pd.Series(pd.to_datetime(["1900-01-01", "1900-05-02"]))],
                 ignore_index=True)
window = auto_analyst.usable_date_window(junk)
kept = junk[(junk >= window[0]) & (junk <= window[1])]
print(f"  200 days + two 1900 dates   : kept {len(kept)} of {len(junk)}")
print(f"    newest kept {kept.max().date()}, newest real {clean.max().date()}")
assert len(junk) - len(kept) == 2, "only the two placeholders should go"
assert kept.max() == clean.max(), "the most recent real date drives the headline - never drop it"
assert kept.min() == clean.min(), "the earliest real date must survive too"

small = pd.Series(pd.to_datetime(["1900-01-01"] + ["2024-01-0%d" % d for d in range(1, 9)]))
print(f"  too few rows to judge       : {auto_analyst.usable_date_window(small)}")
assert auto_analyst.usable_date_window(small) is None, "under 20 rows, do not guess"

print("\n" + "=" * 74)
print("PART 3 — VALUES SITTING IN THE WRONG COLUMN ARE FOUND")
print("=" * 74)

# A handful of rows slipped a cell in the source sheet, so an order status and a
# rep name ended up in Region, and a region name ended up in Sales Rep.
messy = pd.DataFrame({
    "Sales Rep": (["Amit"] * 30 + ["Sara"] * 25 + ["Arun"] * 20 + ["Raj"] * 15
                  + ["John"] * 10 + ["Ravi"] * 8 + ["North", "Card"]),
    "Region": (["North"] * 44 + ["South"] * 25 + ["East"] * 15 + ["West"] * 12
               + ["Central"] * 8 + ["Delivered", "Processing", "Pending", "Shipped",
                                    "Amit", "Ravi"]),
    "Order Status": (["Delivered"] * 42 + ["Shipped"] * 30 + ["Pending"] * 20
                     + ["Processing"] * 18),
})
mp = auto_analyst.profile_dataframe(messy)
found = auto_analyst.find_misplaced_values(messy, mp)
for column, home, strays in found:
    print(f"  {column:<12} holds {strays} -> belongs in {home}")

flagged = {(column, home) for column, home, _ in found}
assert ("Region", "Order Status") in flagged, "order statuses in Region went unnoticed"
assert ("Sales Rep", "Region") in flagged, "a region in Sales Rep went unnoticed"

print("\n  and clean data is not accused of anything:")
tidy = pd.DataFrame({
    "Billing City": ["Mumbai", "Delhi", "Pune", "Chennai", "Kolkata", "Jaipur"] * 10,
    "Shipping City": ["Jaipur", "Kolkata", "Chennai", "Pune", "Delhi", "Mumbai"] * 10,
    "Payment Mode": ["Card", "UPI", "Cash"] * 20,
})
tp = auto_analyst.profile_dataframe(tidy)
print(f"    Billing City vs Shipping City: {auto_analyst.find_misplaced_values(tidy, tp)}")
assert not auto_analyst.find_misplaced_values(tidy, tp), \
    "two columns of the same kind share values legitimately"

print("\n" + "=" * 74)
print("PART 4 — EVERY REPORT CAPTURES ITS CHARTS, INCLUDING THE MAP")
print("=" * 74)

for scenario in auto_analyst.build_scenarios(df, profiles):
    st_stub.reset()
    with auto_analyst.capturing() as blocks:
        scenario["render"](df, profiles, "cap")
    charts = sum(1 for kind, _ in blocks if kind == "chart")
    print(f"  {scenario['title']:<28} {charts} chart(s) captured, "
          f"{len(st_stub.charts)} drawn")
    assert charts >= 1, f"{scenario['title']} captured no chart - it exports as a blank page"
    assert not st_stub.charts, f"{scenario['title']} drew to the page while capturing"

print("\n  the buffer is released and no widget leaked:")
print(f"    capture.active() = {capture.active()}")
assert not capture.active()

print("\n" + "=" * 74)
print("PART 5 — AN EXPORT DRAWS NO WIDGETS")
print("=" * 74)
# Widgets rendered during a capture would appear on the page while the PDF is
# being built, and the export would depend on whatever the user last picked.
st_stub.reset()
with auto_analyst.capturing():
    for scenario in auto_analyst.build_scenarios(df, profiles):
        scenario["render"](df, profiles, "widgetcheck")
leaked = getattr(st_stub, "widgets", None)
if leaked is None:
    print("  st_stub does not record widgets - checking the geo controls directly")
    with auto_analyst.capturing():
        import geo_maps
        zoom, projection, blink = geo_maps.map_controls("x", allow_blink=True)
    print(f"    map_controls returned defaults: {zoom!r}, {projection!r}, blink={blink}")
    assert blink is False, "a still image cannot pulse"
else:
    print(f"  widgets created during capture: {len(leaked)}")
    assert not leaked, "an export must not draw widgets"

print("\nALL ANALYSIS CHECKS PASSED")
