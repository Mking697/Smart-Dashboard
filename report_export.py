"""Turn the reports on screen into a PDF.

The document is built from the same code that draws the page: each scenario is
run inside `auto_analyst.capturing()`, which collects its headings, charts, KPIs
and plain-English lines instead of rendering them. There is no second copy of the
report logic to drift out of step with the first.

Charts become PNGs through Kaleido, which starts a headless browser. That costs
roughly four seconds per chart on a laptop and more on a small server, so the
caller is given a progress callback and the UI defaults to exporting one report
rather than all of them.
"""

import datetime as dt
import io

from fpdf import FPDF

import auto_analyst
import theme

class ChartRenderError(RuntimeError):
    """Kaleido could not produce an image - the message says how to fix it."""


PAGE_WIDTH = 210          # A4 portrait, millimetres
MARGIN = 14
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

CHART_PX = (1100, 620)    # rendered size before scaling into the page
CHART_SCALE = 2

INK = (30, 58, 138)
BODY = (44, 62, 93)
MUTED = (100, 116, 139)
RULE = (219, 234, 254)
TEAL = (14, 148, 136)


def _rgb(hex_colour):
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))


class ReportPDF(FPDF):
    """A4 with a running header and a page number in the footer."""

    def __init__(self, title, subtitle):
        super().__init__(orientation="P", unit="mm", format="A4")
        # The header runs on every page, so anything the core fonts cannot encode
        # has to be stripped here - otherwise a single em dash in the title
        # aborts the export on page two.
        self.report_title = _ascii(title)
        self.report_subtitle = _ascii(subtitle)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(MARGIN, MARGIN, MARGIN)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*INK)
        self.cell(0, 6, self.report_title, align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "Autolyst", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*RULE)
        self.line(MARGIN, 20, PAGE_WIDTH - MARGIN, 20)
        self.ln(6)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


def _ascii(text):
    """fpdf2's core fonts are Latin-1 only - drop what they cannot encode.

    The reports are full of emoji and en dashes, and a single unencodable
    character otherwise aborts the whole export.
    """
    replacements = {"—": "-", "–": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "…": "..."}
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text.encode("latin-1", "ignore").decode("latin-1").strip()


def _strip_markdown(text):
    return _ascii(text.replace("**", ""))


def _cover(pdf, title, subtitle, rows, columns, sheet_name):
    pdf.add_page()
    pdf.set_fill_color(*_rgb(theme.PRIMARY))
    pdf.rect(0, 0, PAGE_WIDTH, 52, style="F")

    pdf.set_y(18)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 12, "Autolyst", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _ascii(subtitle), new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(70)
    pdf.set_font("Helvetica", "B", 19)
    pdf.set_text_color(*INK)
    pdf.multi_cell(CONTENT_WIDTH, 9, _ascii(title))
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*BODY)
    facts = [
        ("Sheet", sheet_name or "-"),
        ("Rows analysed", f"{rows:,}"),
        ("Columns", str(columns)),
        ("Generated", dt.datetime.now().strftime("%d %b %Y, %H:%M")),
    ]
    for label, value in facts:
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*MUTED)
        pdf.cell(40, 7, label)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*BODY)
        pdf.cell(0, 7, _ascii(value), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_draw_color(*RULE)
    pdf.line(MARGIN, pdf.get_y(), PAGE_WIDTH - MARGIN, pdf.get_y())


def _kpi_strip(pdf, kpis):
    """The headline numbers, laid out across the page."""
    if not kpis:
        return

    per_row = min(len(kpis), 4)
    box_width = CONTENT_WIDTH / per_row

    for index in range(0, len(kpis), per_row):
        chunk = kpis[index:index + per_row]
        top = pdf.get_y()

        for position, (label, value) in enumerate(chunk):
            left = MARGIN + position * box_width
            pdf.set_xy(left, top)
            pdf.set_draw_color(*RULE)
            pdf.set_fill_color(248, 250, 252)
            pdf.rect(left + 1, top, box_width - 2, 18, style="DF")

            pdf.set_xy(left + 4, top + 2)
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(*MUTED)
            pdf.cell(box_width - 8, 4, _ascii(label)[:28].upper())

            pdf.set_xy(left + 4, top + 7)
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(*INK)
            pdf.cell(box_width - 8, 8, _ascii(value))

        pdf.set_y(top + 22)


def _write_block(pdf, kind, payload):
    if kind == "heading":
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*INK)
        pdf.multi_cell(CONTENT_WIDTH, 6, _strip_markdown(payload))
        pdf.ln(1)

    elif kind == "chart":
        try:
            png = payload.to_image(format="png", width=CHART_PX[0], height=CHART_PX[1],
                                   scale=CHART_SCALE)
        except Exception as error:
            # Kaleido drives a browser rather than shipping one. A server with no
            # Chrome fails here with something unreadable, so say what to do.
            raise ChartRenderError(
                "Charts could not be rendered to images. Kaleido needs a Chrome "
                "browser, which this machine does not have yet.\n\n"
                "On the server, run once:\n"
                "    ~/Smart-Dashboard/deploy/install-pdf.sh\n\n"
                f"Underlying error: {error}"
            ) from error
        height = CONTENT_WIDTH * CHART_PX[1] / CHART_PX[0]
        if pdf.get_y() + height > pdf.h - 22:
            pdf.add_page()
        pdf.image(io.BytesIO(png), x=MARGIN, w=CONTENT_WIDTH)
        pdf.ln(3)

    elif kind == "explain":
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(CONTENT_WIDTH, 4.6, "How to read this: " + _strip_markdown(payload))
        pdf.ln(2)

    elif kind == "takeaway":
        text = "What it means: " + _strip_markdown(payload)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(*TEAL)
        pdf.multi_cell(CONTENT_WIDTH, 5, text)
        pdf.ln(3)


def build_pdf(dataframe, scenarios, sheet_name=None, title=None, on_progress=None):
    """Render the given scenarios into PDF bytes.

    `on_progress(done, total, label)` is called as each report is captured, so a
    slow export can show its progress instead of appearing to hang.
    """
    profiles = auto_analyst.profile_dataframe(dataframe)

    pdf = ReportPDF(
        title=title or "Data Report",
        subtitle="Automated report - every chart explained in plain English",
    )
    _cover(pdf, title or "Data Report",
           "Automated report - every chart explained in plain English",
           len(dataframe), len(dataframe.columns), sheet_name)

    total = len(scenarios)

    for index, scenario in enumerate(scenarios, start=1):
        if on_progress:
            on_progress(index - 1, total, scenario["title"])

        with auto_analyst.capturing() as blocks:
            try:
                scenario["render"](dataframe, profiles, f"pdf_{index}")
            except Exception as error:                      # a report that cannot
                blocks.append(("explain", f"This report could not be built: {error}"))

        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(*INK)
        pdf.multi_cell(CONTENT_WIDTH, 8, _strip_markdown(scenario["title"]))

        question = scenario.get("question")
        if question:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*BODY)
            pdf.multi_cell(CONTENT_WIDTH, 5.5, _strip_markdown(question))

        pdf.set_font("Helvetica", "I", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(CONTENT_WIDTH, 4.5, "Why this report: " + _strip_markdown(scenario["why"]))
        pdf.ln(3)

        kpis = [payload for kind, payload in blocks if kind == "kpi"]
        _kpi_strip(pdf, kpis)

        for kind, payload in blocks:
            if kind != "kpi":
                _write_block(pdf, kind, payload)

    if on_progress:
        on_progress(total, total, "Writing the document")

    return bytes(pdf.output())


def chart_count(dataframe, scenarios):
    """How many charts an export would contain - used to warn about the wait."""
    profiles = auto_analyst.profile_dataframe(dataframe)
    count = 0
    for index, scenario in enumerate(scenarios):
        with auto_analyst.capturing() as blocks:
            try:
                scenario["render"](dataframe, profiles, f"count_{index}")
            except Exception:
                pass
        count += sum(1 for kind, _ in blocks if kind == "chart")
    return count
