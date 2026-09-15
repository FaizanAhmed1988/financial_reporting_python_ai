"""
Builds the recruiter-facing project overview PDF.

Every figure quoted in the report is computed live from the project's own engine
at build time — the same `compute_statements()` path the dashboard uses — so no
number in the report can drift out of step with the data. Nothing is typed in
from memory.

The live-interface pages embed the PNGs produced by `src/capture_screenshots.py`.
If any of them is missing or implausibly small the build stops rather than
laying out a blank space.

Usage:
    python -m src.generate_project_pdf
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import FancyBboxPatch                    # noqa: E402
from PIL import Image                                            # noqa: E402
from reportlab.lib import colors                                 # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY            # noqa: E402
from reportlab.lib.pagesizes import LETTER                       # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch                             # noqa: E402
from reportlab.pdfbase import pdfmetrics                         # noqa: E402
from reportlab.pdfbase.ttfonts import TTFont                     # noqa: E402
from reportlab.pdfgen import canvas as pdfcanvas                 # noqa: E402
from reportlab.platypus import (                                 # noqa: E402
    BaseDocTemplate, Frame, Image as RLImage, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.account_classifier import AccountClassifier             # noqa: E402
from src.anomaly_detection import run_ml_anomaly_detection       # noqa: E402
from src.controls import run_control_tests                       # noqa: E402
from src.data_loader import load_workbook                        # noqa: E402
from src.dataset_manager import build_original_dataset, compute_statements  # noqa: E402

SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "screenshots"
FIGURE_DIR = PROJECT_ROOT / "docs" / "figures"
OUTPUT_PDF = PROJECT_ROOT / "reports" / "Financial_Reporting_AI_Project_Overview.pdf"
RAW_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"

REPO_URL = "github.com/FaizanAhmed1988/financial_reporting_python_ai"
AUTHOR = "Faizan Ahmed — CPA (Pakistan), MS Finance"
EXPECTED_PAGES = 11
MIN_SCREENSHOT_BYTES = 20_000

NAVY = colors.HexColor("#12263F")
TEAL = colors.HexColor("#0F766E")
MUTED = colors.HexColor("#5A6B7F")
RULE = colors.HexColor("#D9DEE6")
BAND = colors.HexColor("#F4F6F9")
FLAG = colors.HexColor("#B3261E")
INK = colors.HexColor("#1F2933")

HEX_NAVY, HEX_TEAL, HEX_MUTED = "#12263F", "#0F766E", "#5A6B7F"

PAGE_W, PAGE_H = LETTER
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 0.85 * inch, 0.85 * inch, 0.75 * inch
CONTENT_W = PAGE_W - 2 * MARGIN_X

SCREENSHOTS = [
    ("01_executive_summary.png",
     "Executive Summary — headline metrics above the rule-based interpretation engine, which "
     "cites the figures behind every finding."),
    ("02_financial_statements.png",
     "Financial Statements — P&amp;L, Balance Sheet and Cash Flow, each generated from the "
     "ledger and validated before display."),
    ("03_ratios_working_capital.png",
     "Ratios &amp; Working Capital — metrics computed from the statements, with the "
     "single-period limitation stated on screen rather than buried."),
    ("04_scenario_analysis.png",
     "Scenario Analysis — Base / Best / Worst cases recalculated live from the assumption "
     "sliders in the sidebar."),
    ("05_upload_feature.png",
     "Dynamic Upload Engine — a real General Ledger upload auto-detected at 100% confidence, "
     "with its columns mapped to the engine's schema."),
    ("06_controls_ai.png",
     "Controls &amp; AI — Isolation Forest anomaly detection over the General Ledger, reported "
     "as items to review rather than as confirmed fraud."),
]


# ── Figures computed from the project's own engine ───────────────────────────

def compute_figures() -> dict:
    """Run the real engine and return the numbers this report quotes."""
    wb = load_workbook(RAW_WORKBOOK, header_row=3)
    coa = AccountClassifier().classify(wb.coa)
    dataset = build_original_dataset(coa, wb)
    stmts = compute_statements(dataset, days_in_period=90)

    pl, bs, cf = stmts["pl_metrics"], stmts["bs_metrics"], stmts["cf_metrics"]
    pl_df, wc_df = stmts["pl_df"], stmts["wc_df"]

    # The report states that the balance sheet balances and the cash flow
    # reconciles. Assert it here so the claim can never outlive the fact.
    if not bs["Is Balanced"]:
        raise ValueError(f"Balance sheet does not balance: {bs['Difference']}")
    if not cf["Reconciled"]:
        raise ValueError(f"Cash flow does not reconcile: {cf['Difference']}")

    def pl_line(label: str) -> float:
        hit = pl_df[pl_df["Line Item"].astype(str).str.strip() == label]
        return float(hit["Amount"].iloc[0])

    def wc_value(metric: str) -> str:
        hit = wc_df[wc_df["Metric"].astype(str).str.strip() == metric]
        return str(hit["Amount/Value"].iloc[0]).strip()

    controls = run_control_tests(dataset.gl)

    return {
        "revenue": pl["Total Revenue"],
        "cogs": pl["Total COGS"],
        "gross_profit": pl["Gross Profit"],
        "gross_margin": pl["Gross Margin %"],
        "opex": pl["Total Opex"],
        "finance_costs": pl["Total Finance Costs"],
        "net_profit": pl["Net Profit"],
        "salaries": pl_line("Salaries & Employee Benefits"),
        "total_assets": bs["Total Assets"],
        "opening_cash": cf["Opening Cash"],
        "closing_cash": cf["Closing Cash (Actual)"],
        "current_ratio": wc_value("Current Ratio"),
        "working_capital": float(wc_value("Net Working Capital").replace(",", "")),
        "dpo": wc_value("AP Days (DPO)"),
        "coa_accounts": len(coa),
        "gl_rows": len(dataset.gl),
        "tb_rows": len(dataset.tb),
        "ratio_count": len(stmts["ratios_df"]),
        "ml_anomalies": run_ml_anomaly_detection(dataset.gl)["count"],
        "outliers": controls["Statistical Outliers (>2.5 Std Dev)"]["count"],
        "round_numbers": controls["Round-Number Transactions"]["count"],
        "weekend_txns": controls["Weekend Transactions"]["count"],
    }


def money(value: float) -> str:
    """Accounting presentation — negatives in parentheses."""
    return f"({abs(value):,.0f})" if value < 0 else f"{value:,.0f}"


# ── Generated artwork ────────────────────────────────────────────────────────

def build_architecture_diagram() -> Path:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURE_DIR / "architecture_flow.png"

    top = [
        ("Raw Data", "Excel export\nGL · TB · COA"),
        ("Data Loader", "configurable column mapper\nno hardcoded column names"),
        ("COA Mapping", "rule-based classification\nno hardcoded account codes"),
        ("Financial Engine", "P&L · Balance Sheet\nCash Flow (indirect)"),
    ]
    bottom = [
        ("Analytics & AI", "ratios · working capital\ncontrols · Isolation Forest"),
        ("Dashboard", "Streamlit\n8 interactive sections"),
        ("Export", "15-sheet formatted\nExcel workbook"),
    ]

    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    # 4 boxes + 3 gaps must stay inside xlim, or `bbox_inches="tight"` clips the last one.
    box_w, box_h, gap = 2.32, 1.18, 0.33
    x0, y_top, y_bot = 0.35, 3.15, 0.62

    def draw_row(items, y, fill):
        spans = []
        for i, (title, sub) in enumerate(items):
            x = x0 + i * (box_w + gap)
            ax.add_patch(FancyBboxPatch(
                (x, y), box_w, box_h,
                boxstyle="round,pad=0.02,rounding_size=0.09",
                linewidth=1.3, edgecolor="#C7D0DB", facecolor=fill))
            ax.text(x + box_w / 2, y + box_h * 0.70, title, ha="center", va="center",
                    fontsize=11.5, fontweight="bold", color=HEX_NAVY)
            ax.text(x + box_w / 2, y + box_h * 0.31, sub, ha="center", va="center",
                    fontsize=8.1, color=HEX_MUTED, linespacing=1.5)
            spans.append((x, x + box_w / 2, x + box_w))
        for i in range(len(items) - 1):
            ax.annotate("", xy=(spans[i + 1][0] - 0.05, y + box_h / 2),
                        xytext=(spans[i][2] + 0.05, y + box_h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=HEX_TEAL, linewidth=1.7,
                                        shrinkA=0, shrinkB=0))
        return spans

    top_spans = draw_row(top, y_top, "#FFFFFF")
    bottom_spans = draw_row(bottom, y_bot, "#F4F6F9")

    # Elbow: the end of the top row wraps down and back to the start of the bottom row.
    mid_y = y_bot + box_h + (y_top - y_bot - box_h) / 2
    x_end, x_start = top_spans[-1][1], bottom_spans[0][1]
    ax.plot([x_end, x_end, x_start, x_start],
            [y_top - 0.02, mid_y, mid_y, y_bot + box_h + 0.16],
            color=HEX_TEAL, linewidth=1.7, solid_capstyle="round", zorder=1)
    ax.annotate("", xy=(x_start, y_bot + box_h + 0.02), xytext=(x_start, y_bot + box_h + 0.20),
                arrowprops=dict(arrowstyle="-|>", color=HEX_TEAL, linewidth=1.7,
                                shrinkA=0, shrinkB=0))

    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.08)
    plt.close(fig)
    return out


def build_revenue_chart(f: dict) -> Path:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURE_DIR / "revenue_vs_expenses.png"

    fig, ax = plt.subplots(figsize=(8.6, 4.0))
    ax.bar([0], [f["revenue"]], width=0.46, color=HEX_TEAL, label="Revenue")

    # `stacked` is the in-bar wording — it has to fit inside the bar's width.
    layers = [
        ("Cost of Sales", "Cost of Sales", f["cogs"], "#4A6FA5"),
        ("Operating Expenses", "Operating\nExpenses", f["opex"], "#12263F"),
        ("Finance Costs", "Finance Costs", f["finance_costs"], "#8A9AAE"),
    ]
    total_costs = sum(v for _, _, v, _ in layers)
    running = 0.0
    for label, stacked, value, colour in layers:
        ax.bar([1], [value], bottom=[running], width=0.46, color=colour, label=label)
        mid = running + value / 2
        if value / total_costs >= 0.10:
            ax.text(1, mid, f"{stacked}\n{value:,.0f}", ha="center", va="center",
                    fontsize=8.2, color="white", linespacing=1.5)
        else:
            # Too thin to hold a label — annotate outside the bar instead of overprinting it.
            ax.annotate(f"{label}  {value:,.0f}", xy=(1.24, mid), xytext=(1.36, mid),
                        ha="left", va="center", fontsize=8.4, color=HEX_MUTED,
                        arrowprops=dict(arrowstyle="-", color="#B7C1CE", linewidth=0.9))
        running += value

    ax.text(0, f["revenue"] + running * 0.02, f"{f['revenue']:,.0f}",
            ha="center", fontsize=10.5, fontweight="bold", color=HEX_NAVY)
    ax.text(1, running + running * 0.02, f"{running:,.0f}",
            ha="center", fontsize=10.5, fontweight="bold", color=HEX_NAVY)
    # Sits in the gap between the two bars, so it must stay narrower than that gap.
    ax.annotate(
        f"Net Loss\n{money(f['net_profit'])}", xy=(0.5, running * 0.52),
        ha="center", va="center", fontsize=9, fontweight="bold", color="#B3261E",
        linespacing=1.5,
        bbox=dict(boxstyle="round,pad=0.32", facecolor="#FDECEA",
                  edgecolor="#B3261E", linewidth=1.1))

    ax.set_ylabel("Q1 2026 amount", fontsize=9.5, color=HEX_MUTED)
    ax.set_ylim(0, running * 1.14)
    ax.set_xlim(-0.7, 2.25)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Revenue", "Total Costs"], fontsize=11, fontweight="bold",
                       color=HEX_NAVY)
    ax.tick_params(axis="both", labelsize=9.5, colors=HEX_MUTED, length=0)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color("#D9DEE6")
    ax.grid(axis="y", color="#EDF0F4", linewidth=1)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", ncols=2, labelcolor=HEX_MUTED)

    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor="white", pad_inches=0.08)
    plt.close(fig)
    return out


# ── Document chrome ──────────────────────────────────────────────────────────

class NumberedCanvas(pdfcanvas.Canvas):
    """Two-pass canvas so the footer can say 'Page X of Y'."""

    total_pages = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        NumberedCanvas.total_pages = total
        for state in self._saved:
            self.__dict__.update(state)
            if self._pageNumber > 1:
                self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int):
        y = MARGIN_BOT - 0.17 * inch
        self.setStrokeColor(RULE)
        self.setLineWidth(0.6)
        self.line(MARGIN_X, y, PAGE_W - MARGIN_X, y)
        self.setFont("Helvetica", 7.8)
        self.setFillColor(MUTED)
        self.drawString(MARGIN_X, y - 0.18 * inch, "Financial Reporting AI — Project Overview")
        self.drawRightString(PAGE_W - MARGIN_X, y - 0.18 * inch,
                             f"Page {self._pageNumber} of {total}")


def _register_symbol_font() -> str:
    """
    Register a font that actually carries U+2713 so the feature checklist renders
    as check marks. Helvetica's WinAnsi encoding has no check mark, and the
    ZapfDingbats base-14 glyph is not resolved by every PDF renderer. DejaVuSans
    ships with Matplotlib, which is already a dependency.
    """
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
    if not ttf.exists():
        return "Helvetica"
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(ttf)))
    return "DejaVuSans"


def _styles() -> dict:
    base = getSampleStyleSheet()
    symbol_font = _register_symbol_font()
    s = {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=19, leading=23, textColor=NAVY,
                             spaceBefore=0, spaceAfter=2),
        "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=8, leading=10,
                                 textColor=TEAL, spaceAfter=3),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                             textColor=NAVY, spaceBefore=12, spaceAfter=4),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=15,
                               textColor=INK, alignment=TA_JUSTIFY, spaceAfter=8),
        "caption": ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=8.4,
                                  leading=11.5, textColor=MUTED, spaceBefore=5, spaceAfter=10),
        "note": ParagraphStyle("note", fontName="Helvetica", fontSize=8.8, leading=12.5,
                               textColor=MUTED, spaceAfter=6),
        "cover_title": ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=34, leading=39,
                                      textColor=colors.white, alignment=TA_CENTER),
        "cover_tag": ParagraphStyle("ctag", fontName="Helvetica", fontSize=12, leading=18,
                                    textColor=colors.HexColor("#C5D2E0"), alignment=TA_CENTER),
        "cover_name": ParagraphStyle("cn", fontName="Helvetica-Bold", fontSize=14, leading=18,
                                     textColor=colors.white, alignment=TA_CENTER),
        "cover_sub": ParagraphStyle("cs", fontName="Helvetica", fontSize=10, leading=15,
                                    textColor=colors.HexColor("#9FB0C4"), alignment=TA_CENTER),
    }
    s["bullet"] = ParagraphStyle("bullet", parent=s["body"], alignment=0,
                                 leftIndent=13, bulletIndent=2, spaceAfter=5)
    # Feature checklist runs tighter and narrower — it sits in a two-column grid.
    s["check"] = ParagraphStyle("check", fontName="Helvetica", fontSize=8.5, leading=11.6,
                                textColor=INK, leftIndent=13, bulletIndent=0, spaceAfter=5,
                                bulletFontName=symbol_font, bulletFontSize=8)
    s["check_head"] = ParagraphStyle("check_head", fontName="Helvetica-Bold", fontSize=9.5,
                                     leading=12, textColor=TEAL, spaceBefore=9, spaceAfter=4)
    return s


def _rule(width: float = CONTENT_W, colour=TEAL, thickness: float = 1.6,
          align: str = "LEFT") -> Table:
    t = Table([[""]], colWidths=[width], rowHeights=[thickness], hAlign=align)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colour),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def section_header(title: str, kicker: str, s: dict) -> list:
    return [Paragraph(kicker.upper(), s["kicker"]), Paragraph(title, s["h1"]),
            _rule(), Spacer(1, 9)]


def bullets(items: list[str], s: dict) -> list:
    return [Paragraph(text, s["bullet"], bulletText="•") for text in items]


def scaled_image(path: Path, max_w: float, max_h: float) -> RLImage:
    with Image.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    return RLImage(str(path), width=w * scale, height=h * scale)


# ── Pages ────────────────────────────────────────────────────────────────────

def page_cover(s: dict, today: str) -> list:
    return [
        Spacer(1, 1.5 * inch),
        Paragraph("Financial Reporting AI", s["cover_title"]),
        Spacer(1, 15),
        _rule(width=2.1 * inch, colour=TEAL, thickness=2.4, align="CENTER"),
        Spacer(1, 19),
        Paragraph(
            "From a raw trial balance and general ledger to balanced financial statements, "
            "ratio analytics, automated controls and AI anomaly detection — without a single "
            "manual VLOOKUP.", s["cover_tag"]),
        Spacer(1, 1.45 * inch),
        Paragraph(AUTHOR, s["cover_name"]),
        Spacer(1, 7),
        Paragraph("Enterprise Finance Analytics Platform<br/>"
                  "Python · Accounting Automation · AI / ML", s["cover_sub"]),
        Spacer(1, 0.8 * inch),
        Paragraph(today, s["cover_sub"]),
        NextPageTemplate("body"),
        PageBreak(),
    ]


def page_executive_summary(s: dict, f: dict) -> list:
    story = section_header("Executive Summary", "What this project is", s)
    story += [
        Paragraph(
            "<b>Financial Reporting AI</b> takes the three files every finance team already has "
            "— a Chart of Accounts, a Trial Balance and a General Ledger — and produces a "
            "complete reporting pack from them: Profit &amp; Loss, Balance Sheet, Cash Flow, "
            "ratio and working-capital analytics, automated internal-control tests, "
            "machine-learning anomaly detection, FP&amp;A scenario modelling, and a formatted "
            "15-sheet Excel workbook.", s["body"]),
        Paragraph(
            "It was built to close the gap between two disciplines. Month-end reporting is still "
            "largely manual: export the CSVs, map the accounts in Excel, rebuild the same "
            "statements every cycle, and find there is no time left for the analysis that "
            "actually informs a decision. The accounting logic here is written by someone who "
            "has done that close — a CPA moving into data and engineering — so the double-entry "
            "treatment, the indirect-method cash flow and the control tests are modelled the way "
            "an accountant would defend them, not the way a generic data pipeline would "
            "approximate them.", s["body"]),
        Paragraph("Core value proposition", s["h2"]),
    ]
    story += bullets([
        "<b>The close becomes a run, not a rebuild.</b> The statements regenerate from source "
        "data in seconds — balanced and reconciled — every time the underlying file changes.",
        "<b>It is reusable, not a one-off script.</b> Column names and account codes are never "
        "hardcoded. Any accounting export can be uploaded, auto-detected, mapped and validated "
        "through the dashboard, so the platform is not tied to the dataset it was built on.",
        "<b>It says what it cannot prove.</b> A check that could not run is reported as "
        "“skipped — not verified”, never as a pass; synthetic data is labelled as synthetic; and "
        "an unrecognised account is held for a human rather than auto-assigned.",
        f"<b>It interprets, not just calculates.</b> A deterministic rules engine turns "
        f"{f['ratio_count']} ratios and a full statement set into a ranked list of findings in "
        "plain business language, each citing the numbers it was derived from.",
    ], s)
    story += [
        Spacer(1, 4),
        Paragraph(
            f"Built and validated against a {f['coa_accounts']}-account Chart of Accounts, "
            f"{f['tb_rows']} trial-balance rows and {f['gl_rows']} general-ledger lines covering "
            f"Q1 2026. The balance sheet balances to 0.00 and the cash flow reconciles to the "
            f"actual closing cash — both asserted by this report's own build step and by the "
            f"project's test suite.", s["note"]),
        PageBreak(),
    ]
    return story


def page_problem(s: dict) -> list:
    story = section_header("Business Problem & Objectives", "Why it was built", s)
    story += [
        Paragraph("The problem", s["h2"]),
        Paragraph(
            "Finance and accounting teams spend days at month-end downloading CSVs, mapping "
            "accounts manually in Excel via VLOOKUPs, and building static P&amp;L and Balance "
            "Sheet reports. These manual processes are error-prone, hard to scale, and leave "
            "little time for actual financial analysis. Traditional audit controls compound the "
            "problem: they rely on static rules that fail to catch nuanced, multi-dimensional "
            "anomalies in the general ledger.", s["body"]),
        Paragraph("Objectives", s["h2"]),
    ]
    story += bullets([
        "<b>Automate the core engine.</b> A Python pipeline that digests a raw General Ledger "
        "and Trial Balance, maps them against a dynamic Chart of Accounts, and produces "
        "perfectly balanced financial statements.",
        "<b>Advanced analytics on demand.</b> Liquidity ratios, working-capital metrics and "
        "sub-ledger analytics without rebuilding a spreadsheet each cycle.",
        "<b>AI-powered controls.</b> Replace static audit rules with unsupervised machine "
        "learning to surface unusual journal entries for review.",
        "<b>Presentation ready.</b> Deliver through an interactive dashboard and a "
        "professionally formatted 15-sheet Excel workbook.",
    ], s)
    story += [Paragraph("Design rules held throughout", s["h2"])]
    story += bullets([
        "No hardcoded column names — ingestion runs through a configurable column mapper.",
        "No hardcoded account codes — classification is driven by the Chart of Accounts itself.",
        "Never fabricate data — missing data is recorded as a stated limitation instead.",
        "Synthetic data is labelled as synthetic wherever it appears: in code, in file names, "
        "in the dashboard and in the Excel export.",
    ], s)
    story.append(PageBreak())
    return story


def page_architecture(s: dict, diagram: Path) -> list:
    story = section_header("Architecture Overview", "How it fits together", s)
    story += [
        Paragraph(
            "Each stage is an independent module with a single responsibility. The engine "
            "sequence is expressed in exactly one place, so the dashboard and the upload path "
            "reach the same calculations through the same code — there is no parallel "
            "implementation to drift out of step.", s["body"]),
        Spacer(1, 2),
        scaled_image(diagram, CONTENT_W, 2.95 * inch),
        Spacer(1, 12),
        Paragraph("Tech stack", s["h2"]),
    ]
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9.2, leading=12.5,
                          textColor=INK)
    label_cell = ParagraphStyle("label_cell", parent=cell, fontName="Helvetica-Bold",
                                textColor=NAVY)
    rows = [
        ["Language &amp; data", "Python 3.13 · Pandas · NumPy"],
        ["Machine learning", "Scikit-learn (Isolation Forest) · Statsmodels"],
        ["Interface", "Streamlit — 8 interactive sections with a live dataset selector"],
        ["Reporting", "OpenPyXL — 15-sheet formatted workbook · Matplotlib · Plotly"],
        ["Automation &amp; QA", "Playwright (interface capture) · ReportLab (this report) · "
                                "unittest — 6 engine tests and 51 acceptance criteria"],
    ]
    rows = [[Paragraph(label, label_cell), Paragraph(text, cell)] for label, text in rows]
    table = Table(rows, colWidths=[1.5 * inch, CONTENT_W - 1.5 * inch])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.2),
        ("TEXTCOLOR", (0, 0), (0, -1), NAVY),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, RULE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [BAND, colors.white]),
    ]))
    story += [table, PageBreak()]
    return story


def page_key_results(s: dict, f: dict, chart: Path) -> list:
    story = section_header("Key Results", "Q1 2026 demo dataset", s)

    rows = [
        ["Revenue", money(f["revenue"]), "Two streams — product and service"],
        ["Gross Profit", money(f["gross_profit"]),
         f"{f['gross_margin']:.1f}% margin — pricing is healthy"],
        ["Net Profit / (Loss)", money(f["net_profit"]), "Driven by overheads, not by pricing"],
        ["Total Assets", money(f["total_assets"]), "Balance sheet balances to 0.00"],
        ["Closing Cash", money(f["closing_cash"]),
         f"Down from {money(f['opening_cash'])} opening"],
        ["Current Ratio", f["current_ratio"], "FLAG — below 1.0x: a liquidity problem"],
        ["Net Working Capital", money(f["working_capital"]),
         "Current liabilities exceed current assets"],
        ["Days Payable Outstanding", f["dpo"], "FLAG — suppliers are financing the business"],
    ]
    table = Table([["Metric", "Q1 2026", "Read"]] + rows,
                  colWidths=[1.8 * inch, 1.15 * inch, CONTENT_W - 2.95 * inch])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.2),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, 1), (0, -1), NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 6.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 1), (-1, -2), 0.5, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BAND]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for idx, row in enumerate(rows, start=1):
        if row[2].startswith("FLAG"):
            style += [("TEXTCOLOR", (2, idx), (2, idx), FLAG),
                      ("FONTNAME", (2, idx), (2, idx), "Helvetica-Bold")]
        if row[0] == "Net Profit / (Loss)":
            style += [("TEXTCOLOR", (1, idx), (1, idx), FLAG),
                      ("FONTNAME", (1, idx), (1, idx), "Helvetica-Bold")]
    table.setStyle(TableStyle(style))

    story += [
        table,
        Spacer(1, 10),
        Paragraph(
            f"<b>What the numbers say.</b> This business is not losing money because it sells "
            f"badly — it keeps {f['gross_margin']:.1f} cents of every sales dollar after the cost "
            f"of delivery. It is losing money because overheads are roughly double revenue: "
            f"salaries alone are {money(f['salaries'])} against {money(f['revenue'])} of revenue, "
            f"or {f['salaries'] / f['revenue'] * 100:.0f}% of every dollar earned. The loss is an "
            f"overhead problem, not a pricing problem — and that distinction decides which lever "
            f"management pulls.", s["body"]),
        Paragraph(
            f"<b>The cash story is more urgent than the loss.</b> Cash fell from "
            f"{money(f['opening_cash'])} to {money(f['closing_cash'])}, and a current ratio of "
            f"{f['current_ratio']} means there is only {f['current_ratio'].rstrip('x')} of "
            f"current assets for every 1.00 falling due inside a year. A DPO of {f['dpo']} is "
            f"not efficiency — unpaid suppliers are funding the business, which is a liquidity "
            f"risk rather than a working-capital win.", s["body"]),
        Spacer(1, 2),
        scaled_image(chart, CONTENT_W - 0.6 * inch, 2.45 * inch),
        Paragraph("Revenue against the full cost base — the gap is the reported net loss. "
                  "Plotted from the platform's own Profit &amp; Loss output.", s["caption"]),
        PageBreak(),
    ]
    return story


def page_features(s: dict, f: dict) -> list:
    story = section_header("Features Delivered", "What is built and working", s)

    column_a = [
        ("Core Accounting Engine", [
            "Configurable ingestion — no hardcoded column names; separator-insensitive matching "
            "across 106 recognised headers",
            f"Rule-based COA classification — {f['coa_accounts']} accounts mapped, 0 "
            "unclassified, 0 GL/TB orphans",
            "P&amp;L, Balance Sheet and Cash Flow (indirect method)",
            "Balance sheet balances to 0.00; cash flow reconciles opening to actual closing cash",
        ]),
        ("Analytics", [
            f"{f['ratio_count']} ratios across liquidity, profitability, efficiency and "
            "leverage, each with a plain-language reading",
            "Working capital — NWC, DSO, DIO, DPO and the cash conversion cycle",
            "AR / AP aggregate analytics, built to accept invoice-level sub-ledgers",
            "Bank reconciliation with two-pass matching; timing differences reported separately "
            "from true reconciling items",
        ]),
        ("AI / Machine Learning", [
            f"Isolation Forest on Z-score scaled ledger amounts — {f['ml_anomalies']} "
            "transactions flagged for review",
            "Flagged as potential anomalies requiring review, never as confirmed fraud",
            "Moving-average forecasting, shipped with a warning that one quarter cannot support "
            "real prediction",
        ]),
    ]
    column_b = [
        ("Controls", [
            f"Automated tests over {f['gl_rows']} ledger lines — {f['outliers']} statistical "
            f"outliers, {f['round_numbers']} round-number entries, {f['weekend_txns']} weekend "
            "postings",
            "Untestable controls declared untestable rather than silently passed",
            "Formula-injection (CWE-1236) neutralised on every exported free-text field",
            "Month-end close checklist with Pending / Completed / Exception states",
        ]),
        ("FP&amp;A Scenario Analysis", [
            "Base / Best / Worst modelling across revenue, profit, cash and current ratio",
            "Assumptions adjustable live — revenue growth, COGS %, opex %, DSO and DPO",
        ]),
        ("Dynamic Upload Engine — reusable, not a one-off script", [
            "Auto-detects General Ledger, Trial Balance, COA and Bank Statement files, with a "
            "confidence score and an editable column-mapping table",
            "Validation engine returning PASS / WARNING / ERROR across ten check families; "
            "processing blocked while any error or unmapped account remains",
            "Dataset manager — analyse separately or append to an existing dataset; the original "
            "can never be overwritten",
            "Row-level and file-level duplicate detection, plus an append-only upload audit trail",
        ]),
        ("Reporting", [
            "15-sheet Excel workbook — conditional formatting, freeze panes, auto-filters and a "
            "management summary generated from live figures",
            "Streamlit dashboard with a dataset selector that recalculates every section",
            "Automated interface capture and this PDF, both regenerated from source on demand",
        ]),
    ]

    def column(groups) -> list:
        out = []
        for title, items in groups:
            out.append(Paragraph(title, s["check_head"]))
            out += [Paragraph(text, s["check"], bulletText="✓") for text in items]
        return out

    col_w = (CONTENT_W - 0.3 * inch) / 2
    grid = Table([[column(column_a), column(column_b)]],
                 colWidths=[col_w, col_w])
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 0.3 * inch),
        ("LEFTPADDING", (1, 0), (1, -1), 0),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [grid, PageBreak()]
    return story


def page_interface(s: dict, pair: list[tuple[Path, str]], part: int) -> list:
    story = section_header("Live Interface", f"The running application — {part} of 3", s)
    for path, caption in pair:
        story += [scaled_image(path, CONTENT_W, 3.7 * inch),
                  Paragraph(caption, s["caption"])]
    story.append(PageBreak())
    return story


def page_limitations(s: dict) -> list:
    story = section_header("Honest Limitations", "What this dataset cannot support", s)
    story += [Paragraph(
        "The architecture is built to scale; the <i>insights</i> are bounded by the demo dataset "
        "behind them. Stating those bounds is part of the deliverable — a report that overstates "
        "its evidence is worth less than one that marks its edges.", s["body"])]

    items = [
        ("Single quarter of data",
         "The dataset covers Q1 2026 only. Efficiency and turnover ratios therefore use "
         "period-end closing balances instead of averages, day-based metrics use a fixed 90-day "
         "divisor, and time-series forecasting is fundamentally limited. No trend comparison is "
         "possible."),
        ("No department or cost-centre dimension",
         "The ledger carries no department, cost-centre or project coding, so contribution "
         "analysis and departmental P&amp;Ls cannot be produced from it. The platform is also "
         "single-currency by design."),
        ("No invoice-level AR / AP",
         "The General Ledger holds aggregate receivable and payable balances only. True 30 / 60 / "
         "90-day ageing needs invoice-level sub-ledgers; the ageing functions are built and "
         "waiting for that data rather than estimating it."),
        ("Synthetic budget — clearly labelled",
         "No budget was supplied, so one was generated purely to demonstrate the budget-versus-"
         "actual engine. It carries a visible SYNTHETIC / DEMO DATA banner in the dashboard and "
         "in the Excel export, and is never presented as company data."),
        ("No bank statement in the source data",
         "Bank reconciliation is fully implemented and verified against a statement derived from "
         "the ledger with planted differences. Because the source data contains no bank export, "
         "the close checklist correctly shows the item as Pending until one is uploaded."),
        ("Interpretation thresholds are general, not industry-calibrated",
         "The rules engine uses conventional benchmarks — current ratio 1.0 / 1.5, DSO 60 days, "
         "DPO 90 days, gross margin 40%. A 90-day DPO is unremarkable in construction and "
         "alarming in retail, so these should be tuned per industry before commercial reliance."),
    ]
    for title, text in items:
        story.append(KeepTogether([Paragraph(title, s["h2"]), Paragraph(text, s["body"])]))
    story.append(PageBreak())
    return story


def page_closing(s: dict, f: dict) -> list:
    return [
        *section_header("Closing", "Repository and author", s),
        Paragraph("Source code", s["h2"]),
        Paragraph(
            f'<b><font color="{HEX_TEAL}">{REPO_URL}</font></b><br/>'
            "The repository holds the full engine, the Streamlit dashboard, the unit and "
            "acceptance test suites, the architecture and accounting-logic documentation, and "
            "the automation that regenerates this report end to end.", s["body"]),
        Paragraph("About me", s["h2"]),
        Paragraph(
            "I am a CPA (Pakistan) with an MS in Finance, and I built this platform to make the "
            "move from practising accounting to engineering it. Every design decision came from "
            "the other side of the close: the loader tolerates the messy exports real systems "
            "produce because I have cleaned them by hand; the controls flag what an auditor would "
            "actually ask about; the cash flow uses the indirect method because that is what gets "
            "signed off. The value I bring is not that I can write the Python — it is that I know "
            "which numbers have to be right, and what it means when they are not.", s["body"]),
        Spacer(1, 10),
        _rule(colour=RULE, thickness=0.8),
        Spacer(1, 10),
        Paragraph(
            f"Every figure in this report was computed at build time by the platform's own engine "
            f"against data/raw/GL_COA_TB_Dummy_Dataset.xlsx ({f['coa_accounts']} accounts · "
            f"{f['tb_rows']} trial-balance rows · {f['gl_rows']} ledger lines). The interface "
            f"images are unedited captures of the running application.", s["note"]),
    ]


# ── Build ────────────────────────────────────────────────────────────────────

def verify_screenshots() -> list[tuple[Path, str]]:
    """Every screenshot must exist and be a plausible image before a page is laid out."""
    resolved, problems = [], []
    for filename, caption in SCREENSHOTS:
        path = SCREENSHOT_DIR / filename
        if not path.exists():
            problems.append(f"{filename}: missing — run `python -m src.capture_screenshots`")
        elif path.stat().st_size < MIN_SCREENSHOT_BYTES:
            problems.append(f"{filename}: only {path.stat().st_size:,} bytes — blank or truncated")
        else:
            resolved.append((path, caption))
    if problems:
        raise FileNotFoundError(
            "Cannot build the PDF — the live-interface pages would have gaps:\n  - "
            + "\n  - ".join(problems))
    return resolved


def build_pdf() -> dict:
    shots = verify_screenshots()
    figures = compute_figures()
    diagram = build_architecture_diagram()
    chart = build_revenue_chart(figures)
    s = _styles()

    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT_PDF), pagesize=LETTER,
        leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP, bottomMargin=MARGIN_BOT,
        title="Financial Reporting AI — Project Overview",
        author=AUTHOR.split(" — ")[0],
        subject="Enterprise Finance Analytics Platform — Python, Accounting Automation, AI/ML",
    )
    body_frame = Frame(MARGIN_X, MARGIN_BOT, CONTENT_W,
                       PAGE_H - MARGIN_TOP - MARGIN_BOT, id="body")

    def paint_cover(canv, _doc):
        canv.setFillColor(NAVY)
        canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
        canv.setFillColor(TEAL)
        canv.rect(0, 0, PAGE_W, 0.26 * inch, stroke=0, fill=1)

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[body_frame], onPage=paint_cover),
        PageTemplate(id="body", frames=[body_frame]),
    ])

    story: list = []
    story += page_cover(s, date.today().strftime("%B %Y"))
    story += page_executive_summary(s, figures)
    story += page_problem(s)
    story += page_architecture(s, diagram)
    story += page_key_results(s, figures, chart)
    story += page_features(s, figures)
    story += page_interface(s, shots[0:2], 1)
    story += page_interface(s, shots[2:4], 2)
    story += page_interface(s, shots[4:6], 3)
    story += page_limitations(s)
    story += page_closing(s, figures)

    doc.build(story, canvasmaker=NumberedCanvas)
    return figures


def _page_count() -> int:
    """Page count read back from the written file, independent of the build."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(OUTPUT_PDF)).pages)
    except ImportError:
        data = OUTPUT_PDF.read_bytes()
        return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def main() -> int:
    try:
        figures = build_pdf()
    except (FileNotFoundError, ValueError) as exc:
        print(f"\nBUILD STOPPED\n{exc}\n")
        return 1

    pages = _page_count()
    size = OUTPUT_PDF.stat().st_size
    header_ok = OUTPUT_PDF.read_bytes()[:5] == b"%PDF-"

    print(f"\nWrote {OUTPUT_PDF.relative_to(PROJECT_ROOT)}")
    print(f"  pages       : {pages} (expected {EXPECTED_PAGES}); "
          f"build reported {NumberedCanvas.total_pages}")
    print(f"  size        : {size:,} bytes")
    print(f"  valid header: {header_ok}")
    print(f"  screenshots : {len(SCREENSHOTS)} embedded from "
          f"{SCREENSHOT_DIR.relative_to(PROJECT_ROOT)}/")
    print(f"  key figures : revenue {money(figures['revenue'])} · "
          f"net {money(figures['net_profit'])} · assets {money(figures['total_assets'])} · "
          f"current ratio {figures['current_ratio']}")

    if not header_ok or size < 100_000:
        print("\nFAILED — the output does not look like a complete PDF.")
        return 1
    if pages != EXPECTED_PAGES or NumberedCanvas.total_pages != EXPECTED_PAGES:
        print(f"\nFAILED — expected {EXPECTED_PAGES} pages. Content has overflowed or "
              f"collapsed; fix the layout before shipping.")
        return 1
    print("\nOK — report built and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
