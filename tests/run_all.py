"""Run every suite and print one line per result.

    venv/Scripts/python.exe tests/run_all.py

Each suite is a plain script that stubs Streamlit, executes the real code paths,
and asserts on what comes out - the Plotly figures, the cleaned frames, the
column roles, the pivot totals. There is no test framework to install.

Suites that need a messy real-world workbook skip themselves when one is not
present. Point SAMPLE_WORKBOOK at an .xlsx to run those too.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    ("test_full",    "Geo detection, J&K overlay, auto scenarios"),
    ("test_real",    "The whole pipeline on a messy real workbook"),
    ("test_cleaner", "Row rules, placeholders, sparse-data guard"),
    ("test_sheets",  "Per-sheet sections and Auto Compare"),
    ("test_keyrule", "Key column vs nearly-empty row rules"),
    ("test_auth",    "Signup, OTP, login, lockout, abuse guards"),
    ("test_table",   "Filters, pivot correctness, export"),
    ("test_html",    "Markup renders as HTML, buttons stay readable"),
    ("test_pdf",     "PDF export: capture mode, one report vs all"),
    ("test_analysis", "Rates vs totals, date windows, misplaced values"),
]


def main():
    results = []

    for name, description in SUITES:
        completed = subprocess.run(
            [sys.executable, os.path.join(HERE, f"{name}.py")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        tail = [line for line in (completed.stdout or "").splitlines() if line.strip()]
        last = tail[-1] if tail else "(no output)"

        if completed.returncode != 0:
            status = "FAIL"
        elif "SKIPPED" in (completed.stdout or ""):
            status = "SKIP"
        else:
            status = "PASS"

        results.append((status, name, description, last, completed))
        print(f"  [{status}] {name:14} {description}")
        if status == "FAIL":
            print("        " + last)

    print()
    passed = sum(1 for r in results if r[0] == "PASS")
    skipped = sum(1 for r in results if r[0] == "SKIP")
    failed = sum(1 for r in results if r[0] == "FAIL")
    print(f"  {passed} passed, {skipped} skipped, {failed} failed")

    if failed:
        print("\n--- output from the first failure ---")
        first = next(r for r in results if r[0] == "FAIL")
        print(first[4].stdout[-3000:])
        print(first[4].stderr[-3000:])

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
