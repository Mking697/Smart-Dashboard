"""PDF export: capture mode, one report vs all, and a readable document."""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

st_stub.install()

import auto_analyst  # noqa: E402
import report_export  # noqa: E402
import sample_data  # noqa: E402

df = sample_data.build_sample_workbook()["Sales 2025-26"]
profiles = auto_analyst.profile_dataframe(df)
scenarios = auto_analyst.build_scenarios(df, profiles)

print("=" * 74)
print("PART 1 — CAPTURE COLLECTS INSTEAD OF RENDERING")
print("=" * 74)

st_stub.reset()
with auto_analyst.capturing() as blocks:
    scenarios[0]["render"](df, profiles, "cap")

kinds = {}
for kind, _ in blocks:
    kinds[kind] = kinds.get(kind, 0) + 1

print(f"  captured blocks : {kinds}")
print(f"  drawn to screen : {len(st_stub.charts)} charts")
assert st_stub.charts == [], "capture must not draw to the page"
assert kinds.get("chart", 0) >= 2, "the overview should capture both charts"
assert kinds.get("kpi", 0) >= 2, "KPI tiles should be captured"
assert kinds.get("takeaway", 0) >= 1, "the plain-English finding should be captured"

print("\n  the buffer is released afterwards:", auto_analyst._sink() is None)
assert auto_analyst._sink() is None

print("\n  and normal rendering still works after capturing:")
st_stub.reset()
scenarios[0]["render"](df, profiles, "normal")
print(f"    charts drawn: {len(st_stub.charts)}")
assert len(st_stub.charts) >= 2, "rendering broke after a capture"

print("\n" + "=" * 74)
print("PART 2 — ONE REPORT ONLY")
print("=" * 74)
one = [s for s in scenarios if s["title"] == "📊 Business Overview"]
t0 = time.time()
pdf_one = report_export.build_pdf(df, one, sheet_name="Sales 2025-26",
                                  title="Business Overview")
print(f"  {len(pdf_one):,} bytes in {time.time() - t0:.1f}s")
assert pdf_one.startswith(b"%PDF"), "not a PDF"
assert len(pdf_one) > 40_000, "suspiciously small - are the charts in it?"

print("\n" + "=" * 74)
print("PART 3 — ALL REPORTS")
print("=" * 74)
progress = []
t0 = time.time()
pdf_all = report_export.build_pdf(
    df, scenarios, sheet_name="Sales 2025-26", title="Full Report",
    on_progress=lambda done, total, label: progress.append((done, total, label)),
)
elapsed = time.time() - t0
print(f"  {len(pdf_all):,} bytes in {elapsed:.1f}s for {len(scenarios)} reports")
print(f"  progress callbacks: {len(progress)}")
for done, total, label in progress[:4]:
    print(f"    {done}/{total}  {label}")

assert pdf_all.startswith(b"%PDF")
assert len(pdf_all) > len(pdf_one), "the full report should be larger than one report"
assert len(progress) == len(scenarios) + 1, "progress should report every report plus the write"

print("\n" + "=" * 74)
print("PART 4 — THE DOCUMENT IS READABLE")
print("=" * 74)
out = os.path.join(os.environ.get("TEMP", "."), "autolyst_test_report.pdf")
with open(out, "wb") as handle:
    handle.write(pdf_all)
print(f"  written to {out}")

try:
    from pypdf import PdfReader
    reader = PdfReader(out)
    print(f"  pages: {len(reader.pages)}")
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    for needle in ["Autolyst", "Business Overview", "What it means", "Rows analysed"]:
        found = needle in text
        print(f"  [{'OK' if found else 'MISSING'}] {needle!r} appears in the text")
        assert found, f"{needle} missing from the PDF text"
    assert len(reader.pages) >= len(scenarios), "expected at least one page per report"
except ImportError:
    print("  pypdf not installed - skipping the text check")

print("\n" + "=" * 74)
print("PART 5 — NON-LATIN CHARACTERS DO NOT ABORT THE EXPORT")
print("=" * 74)
tricky = "Report — with an em dash, ellipsis… and emoji 📊🌍"
print(f"  in : {tricky}")
print(f"  out: {report_export._ascii(tricky)}")
assert report_export._ascii(tricky), "text should survive, stripped"

pdf_emoji = report_export.build_pdf(df, one, sheet_name="Sales — 2025", title=tricky)
print(f"  PDF still built: {len(pdf_emoji):,} bytes")
assert pdf_emoji.startswith(b"%PDF")

print("\n" + "=" * 74)
print("PART 6 — NOTHING IS WRITTEN OFF THE EDGE OF THE PAGE")
print("=" * 74)
# fpdf2 leaves the cursor at the right-hand edge of a multi_cell by default, so
# a run of them walks off the page: the second block was clipped to a few
# characters and the third vanished entirely. This shipped once.
probe = report_export.ReportPDF(title="Probe", subtitle="probe")
probe.add_page()
report_export._report_header(probe, {
    "title": "📊 Business Overview",
    "question": "How is the business doing overall, and who contributes most?",
    "why": "Every dataset has a headline number and a biggest contributor.",
})
print(f"  cursor x after the header: {probe.get_x():.1f}mm "
      f"(left margin is {report_export.MARGIN}mm)")
assert probe.get_x() == report_export.MARGIN, "the cursor drifted off the left margin"

for kind, payload in [("heading", "Chart 1 - a heading"),
                      ("explain", "An explanation line."),
                      ("takeaway", "A finding.")]:
    report_export._write_block(probe, kind, payload)
    assert probe.get_x() == report_export.MARGIN, f"{kind} left the cursor adrift"
print("  every block returns to the left margin")

try:
    from pypdf import PdfReader

    reader = PdfReader(out)
    page_two = reader.pages[1].extract_text() or ""
    for needle in ["Why this report", "contributes most"]:
        found = needle in page_two
        print(f"  [{'OK' if found else 'CLIPPED'}] {needle!r} survives on the report page")
        assert found, f"{needle!r} was clipped off the page"

    width = float(reader.pages[1].mediabox.width)          # points
    right_edge = width - report_export.MARGIN * 72 / 25.4
    furthest = 0.0

    def watch(text, cm, tm, font, size):
        global furthest
        if text.strip():
            furthest = max(furthest, tm[4])       # where the glyphs start, in points

    reader.pages[1].extract_text(visitor_text=watch)
    print(f"  furthest text starts at {furthest:.0f}pt, right margin is {right_edge:.0f}pt")
    assert furthest < right_edge, "text starts beyond the right margin - it is being clipped"
except ImportError:
    print("  pypdf not installed - skipping the clipping check")

print("\nALL PDF EXPORT CHECKS PASSED")
