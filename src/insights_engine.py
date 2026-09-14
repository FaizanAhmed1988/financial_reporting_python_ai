"""
src/insights_engine.py
======================
UP5 — Rule-based financial interpretation and insights.

Turns the computed statements into plain-language findings an accountant would
actually write, each one citing the figures it is derived from.

WHY RULE-BASED
--------------
Every insight is a deterministic function of numbers already computed by the
engine. That means it is reproducible, testable, explainable line by line, and
it never invents a figure — which matters more here than fluency, because the
platform's governing principle is that nothing is fabricated. No external
service is called and no financial data leaves the machine.

HONESTY RULES BUILT IN
----------------------
1. A rule whose inputs are missing or non-computable does not fire. Silence is
   correct; a guess is not.
2. Insights that depend on the closing *position* (liquidity, solvency, working
   capital) are SUPPRESSED for a dataset whose balance sheet only reflects
   period movement — e.g. a General Ledger uploaded with no opening balances.
   Telling a user their current ratio is 0.3x when the opening cash is missing
   would be worse than telling them nothing, so the engine says why instead.
3. Every insight carries the evidence it used, so any number on screen can be
   traced back to the statement it came from.

ARCHITECTURE COMPLIANCE
-----------------------
- NO streamlit import — pure logic, headlessly testable.
- Recomputes nothing: it reads the metrics the existing engine produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

# ============================================================
# 1. VOCABULARY
# ============================================================

CRITICAL = "CRITICAL"
WARNING = "WARNING"
WATCH = "WATCH"
POSITIVE = "POSITIVE"
INFO = "INFO"

SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, WATCH: 2, POSITIVE: 3, INFO: 4}
SEVERITY_ICON = {
    CRITICAL: "🔴", WARNING: "🟠", WATCH: "🟡", POSITIVE: "🟢", INFO: "🔵",
}

CAT_LIQUIDITY = "Liquidity"
CAT_PROFITABILITY = "Profitability"
CAT_WORKING_CAPITAL = "Working Capital"
CAT_CASH = "Cash"
CAT_DATA = "Data Quality"

#: Phrases in a dataset limitation that mean the balance sheet shows movement,
#: not position — position-dependent insights must not fire.
_POSITION_UNRELIABLE_MARKERS = ("no opening balances", "opening balances that are absent")


# ============================================================
# 2. INSIGHT
# ============================================================

@dataclass
class Insight:
    severity: str
    category: str
    headline: str
    explanation: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommendation: Optional[str] = None

    @property
    def icon(self) -> str:
        return SEVERITY_ICON.get(self.severity, "•")

    def to_row(self) -> Dict[str, Any]:
        return {
            "Severity": self.severity,
            "Area": self.category,
            "Finding": self.headline,
            "Basis": "; ".join(f"{k}: {v}" for k, v in self.evidence.items()),
        }


# ============================================================
# 3. VALUE EXTRACTION
# ============================================================

def _num(value: Any) -> Optional[float]:
    """Parse a formatted metric ('3,662,400', '0.62x', '-1212 days', '68.5%')."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None if pd.isna(value) else float(value)
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[,\s]", "", text)
    cleaned = re.sub(r"(x|days|day|%)$", "", cleaned, flags=re.IGNORECASE)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _wc(wc_df: pd.DataFrame, metric: str) -> Optional[float]:
    """Look up a metric in the working-capital table by name."""
    if wc_df is None or wc_df.empty or "Metric" not in wc_df.columns:
        return None
    hit = wc_df[wc_df["Metric"].astype(str).str.strip() == metric]
    if hit.empty:
        return None
    return _num(hit.iloc[0]["Amount/Value"])


def _line(df: pd.DataFrame, label: str) -> Optional[float]:
    """Look up a statement line item by exact name."""
    if df is None or df.empty or "Line Item" not in df.columns:
        return None
    hit = df[df["Line Item"].astype(str).str.strip() == label]
    if hit.empty:
        return None
    return _num(hit.iloc[0]["Amount"])


def _money(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:,.0f}"


def _largest_opex(pl_df: pd.DataFrame) -> Optional[tuple]:
    """Biggest single operating-expense line, as (label, amount)."""
    if pl_df is None or pl_df.empty:
        return None
    rows = pl_df.dropna(subset=["Amount"]).copy()
    rows["Line Item"] = rows["Line Item"].astype(str).str.strip()
    skip_prefixes = ("Total", "Gross", "Net", "Revenue", "Cost of Sales",
                     "Operating Expenses", "EBITDA", "EBIT", "Profit")
    rows = rows[~rows["Line Item"].str.startswith(skip_prefixes)]
    rows = rows[rows["Amount"] > 0]
    if rows.empty:
        return None
    top = rows.sort_values("Amount", ascending=False).iloc[0]
    return str(top["Line Item"]), float(top["Amount"])


def position_is_reliable(limitations: Optional[List[str]]) -> bool:
    """False when the dataset's balance sheet reflects movement, not position."""
    blob = " ".join(limitations or []).lower()
    return not any(marker in blob for marker in _POSITION_UNRELIABLE_MARKERS)


# ============================================================
# 4. RULES
# ============================================================

def _liquidity_insights(wc_df, bs_metrics) -> List[Insight]:
    out: List[Insight] = []
    cr = _wc(wc_df, "Current Ratio")
    qr = _wc(wc_df, "Quick Ratio")
    nwc = _wc(wc_df, "Net Working Capital")
    ca = _wc(wc_df, "Total Current Assets")
    cl = _wc(wc_df, "Total Current Liabilities")

    if cr is not None:
        if cr < 1.0:
            out.append(Insight(
                CRITICAL, CAT_LIQUIDITY,
                f"Current ratio of {cr:.2f}x is below 1.0 — short-term obligations exceed short-term assets",
                f"Current assets of {_money(ca)} do not cover current liabilities of "
                f"{_money(cl)}, leaving a shortfall of {_money(nwc)}. The entity cannot "
                "settle its obligations over the next twelve months from current assets alone.",
                {"Current Ratio": f"{cr:.2f}x", "Current Assets": _money(ca),
                 "Current Liabilities": _money(cl)},
                "Confirm the maturity profile of current liabilities and secure a "
                "committed facility or shareholder support before the next payment run.",
            ))
        elif cr < 1.5:
            out.append(Insight(
                WATCH, CAT_LIQUIDITY,
                f"Current ratio of {cr:.2f}x leaves a thin buffer",
                f"Current assets of {_money(ca)} cover current liabilities of {_money(cl)}, "
                "but with little headroom for a delayed receipt or an unexpected cost.",
                {"Current Ratio": f"{cr:.2f}x"},
            ))
        else:
            out.append(Insight(
                POSITIVE, CAT_LIQUIDITY,
                f"Current ratio of {cr:.2f}x indicates adequate short-term cover",
                f"Current assets of {_money(ca)} cover current liabilities of {_money(cl)}.",
                {"Current Ratio": f"{cr:.2f}x"},
            ))

    if qr is not None and cr is not None and qr < 0.5 <= cr + 1:
        gap = (cr - qr) if cr is not None else None
        out.append(Insight(
            WARNING, CAT_LIQUIDITY,
            f"Quick ratio of {qr:.2f}x shows liquidity depends heavily on inventory",
            f"Excluding inventory, liquid assets cover only {qr:.2f}x of current "
            "liabilities"
            + (f", against a current ratio of {cr:.2f}x — a gap of {gap:.2f}x carried by stock."
               if gap is not None else ".")
            + " Inventory must convert to cash on schedule for obligations to be met.",
            {"Quick Ratio": f"{qr:.2f}x", "Current Ratio": f"{cr:.2f}x"},
            "Review inventory ageing and identify slow-moving stock that will not "
            "convert within the payment window.",
        ))
    return out


def _profitability_insights(pl_metrics, pl_df) -> List[Insight]:
    out: List[Insight] = []
    rev = pl_metrics.get("Total Revenue")
    net = pl_metrics.get("Net Profit")
    gp = pl_metrics.get("Gross Profit")
    gm = pl_metrics.get("Gross Margin %")
    opex = pl_metrics.get("Total Opex")

    if net is not None and net < 0:
        top = _largest_opex(pl_df)
        driver = ""
        if top:
            label, amount = top
            share = (amount / rev * 100) if rev else None
            driver = (f" The single largest cost is {label} at {_money(amount)}"
                      + (f", equal to {share:.0f}% of revenue." if share is not None else "."))
        out.append(Insight(
            CRITICAL, CAT_PROFITABILITY,
            f"Net loss of {_money(abs(net))} for the period",
            f"Revenue of {_money(rev)} did not cover total costs." + driver,
            {"Revenue": _money(rev), "Net Profit": _money(net),
             "Largest cost": f"{top[0]} {_money(top[1])}" if top else "n/a"},
            "Address the largest cost line first — it moves the result more than "
            "any revenue action available in the short term.",
        ))

    # The most useful derived signal: healthy margin, unprofitable business.
    if gm is not None and gm > 40 and net is not None and net < 0 and gp is not None:
        out.append(Insight(
            WARNING, CAT_PROFITABILITY,
            f"Gross margin of {gm:.1f}% is healthy — the loss is an overhead problem, not a pricing one",
            f"Each sale contributes well: gross profit is {_money(gp)} on revenue of "
            f"{_money(rev)}. The loss arises below that line, where operating "
            f"expenses of {_money(opex)} exceed gross profit by "
            f"{_money((opex or 0) - gp)}. Raising prices or volume alone will not "
            "close a gap of that size.",
            {"Gross Margin": f"{gm:.1f}%", "Gross Profit": _money(gp),
             "Operating Expenses": _money(opex)},
            "Focus on the overhead base rather than pricing; the unit economics "
            "are already working.",
        ))
    elif gm is not None and gm > 40:
        out.append(Insight(
            POSITIVE, CAT_PROFITABILITY,
            f"Gross margin of {gm:.1f}% indicates solid unit economics",
            f"Gross profit of {_money(gp)} on revenue of {_money(rev)}.",
            {"Gross Margin": f"{gm:.1f}%"},
        ))

    if opex is not None and rev and opex > rev:
        out.append(Insight(
            CRITICAL, CAT_PROFITABILITY,
            f"Operating expenses of {_money(opex)} exceed total revenue of {_money(rev)}",
            f"The overhead base is {opex / rev:.1f}x revenue. No achievable gross "
            "margin makes the business profitable at this cost level.",
            {"Operating Expenses": _money(opex), "Revenue": _money(rev),
             "Opex / Revenue": f"{opex / rev:.1f}x"},
            "A structural cost reduction is required, not incremental savings.",
        ))
    return out


def _working_capital_insights(wc_df) -> List[Insight]:
    out: List[Insight] = []
    dso, dio, dpo = _wc(wc_df, "AR Days (DSO)"), _wc(wc_df, "Inventory Days (DIO)"), _wc(wc_df, "AP Days (DPO)")
    ccc = _wc(wc_df, "Cash Conversion Cycle (CCC)")

    if dpo is not None and dpo > 90:
        out.append(Insight(
            CRITICAL if dpo > 365 else WARNING, CAT_WORKING_CAPITAL,
            f"Days payable outstanding of {dpo:,.0f} days indicates suppliers are not being paid",
            f"At {dpo:,.0f} days, payables are being held far beyond any normal credit "
            "term. This is usually a symptom of cash shortage rather than negotiated "
            "terms, and it inflates apparent liquidity because the unpaid balance sits "
            "in current liabilities.",
            {"DPO": f"{dpo:,.0f} days"},
            "Agree a written payment plan with major suppliers before terms are "
            "withdrawn or supply is interrupted.",
        ))
    if dso is not None and dso > 60:
        out.append(Insight(
            WARNING, CAT_WORKING_CAPITAL,
            f"Days sales outstanding of {dso:,.0f} days — cash is tied up in receivables",
            f"Customers are taking {dso:,.0f} days to pay on average.",
            {"DSO": f"{dso:,.0f} days"},
            "Age the receivables ledger and chase the oldest balances first.",
        ))
    if dio is not None and dio > 120:
        out.append(Insight(
            WARNING, CAT_WORKING_CAPITAL,
            f"Inventory days of {dio:,.0f} — stock is turning slowly",
            f"Inventory is held for {dio:,.0f} days on average before it is sold.",
            {"DIO": f"{dio:,.0f} days"},
            "Identify obsolete or overstocked lines and review the provision.",
        ))
    # A negative CCC normally signals efficiency. Driven by unpaid suppliers it
    # signals the opposite, and reporting it as a strength would mislead.
    if ccc is not None and ccc < 0 and dpo is not None and dpo > 90:
        out.append(Insight(
            WARNING, CAT_WORKING_CAPITAL,
            f"Negative cash conversion cycle of {ccc:,.0f} days is not a sign of efficiency here",
            f"A negative cycle usually means suppliers fund operations by agreement. "
            f"In this case it is produced by DPO of {dpo:,.0f} days — unpaid balances, "
            "not negotiated terms. Read it as a liability, not an achievement.",
            {"CCC": f"{ccc:,.0f} days", "DPO": f"{dpo:,.0f} days"},
        ))
    return out


def _cash_insights(cf_metrics, pl_metrics) -> List[Insight]:
    out: List[Insight] = []
    opening = cf_metrics.get("Opening Cash")
    closing = cf_metrics.get("Closing Cash (Calculated)")
    operating = cf_metrics.get("Net Cash from Operating")
    investing = cf_metrics.get("Net Cash from Investing")
    net_change = cf_metrics.get("Net Increase in Cash")
    net_profit = pl_metrics.get("Net Profit")

    if opening is not None and closing is not None and net_change is not None and net_change < 0:
        burn = abs(net_change)
        pct = (burn / opening * 100) if opening else None
        runway = (closing / burn) if burn else None
        out.append(Insight(
            CRITICAL if (runway is not None and runway < 1) else WARNING, CAT_CASH,
            f"Cash fell by {_money(burn)} over the period"
            + (f" — {pct:.0f}% of the opening balance" if pct is not None else ""),
            f"Cash moved from {_money(opening)} to {_money(closing)}."
            + (f" At the same rate of outflow the remaining balance covers about "
               f"{runway:.1f} further period(s)." if runway is not None else ""),
            {"Opening Cash": _money(opening), "Closing Cash": _money(closing),
             "Net Change": _money(net_change)},
            "Build a short-term cash forecast before committing to further outflows.",
        ))

    if operating is not None and net_profit is not None and operating > 0 and net_profit < 0:
        out.append(Insight(
            INFO, CAT_CASH,
            f"Operating cash flow is positive ({_money(operating)}) despite a net loss",
            "The loss is not all cash: non-cash charges such as depreciation, and "
            "movements in working capital, offset it. The reported loss overstates "
            "the immediate cash impact for this period.",
            {"Operating Cash Flow": _money(operating), "Net Profit": _money(net_profit)},
        ))

    if investing is not None and operating is not None and investing < 0 and abs(investing) > abs(operating):
        out.append(Insight(
            WARNING, CAT_CASH,
            f"Investing outflow of {_money(abs(investing))} exceeds operating cash generated",
            f"Operations produced {_money(operating)} while investing consumed "
            f"{_money(abs(investing))}. Capital spending is being funded from reserves "
            "or borrowing rather than from trading.",
            {"Operating": _money(operating), "Investing": _money(investing)},
            "Confirm committed capital expenditure is still affordable at the "
            "current cash position.",
        ))
    return out


# ============================================================
# 5. ENTRY POINT
# ============================================================

def generate_insights(
    statements: Dict[str, Any],
    limitations: Optional[List[str]] = None,
    validation_warnings: int = 0,
    dataset_name: str = "",
) -> List[Insight]:
    """
    Produce ranked insights from the output of dataset_manager.compute_statements().

    `limitations` are the active dataset's own caveats; when they say the balance
    sheet reflects movement rather than position, every position-dependent rule
    is suppressed and replaced with a single explanation of why.
    """
    limitations = limitations or []
    pl_metrics = statements.get("pl_metrics", {}) or {}
    bs_metrics = statements.get("bs_metrics", {}) or {}
    cf_metrics = statements.get("cf_metrics", {}) or {}
    pl_df = statements.get("pl_df")
    wc_df = statements.get("wc_df")

    insights: List[Insight] = []
    reliable = position_is_reliable(limitations)

    # Income Statement rules are valid either way — P&L accounts genuinely open
    # at zero each period, so a movement-only dataset still yields a true P&L.
    insights += _profitability_insights(pl_metrics, pl_df)

    if reliable:
        insights += _liquidity_insights(wc_df, bs_metrics)
        insights += _working_capital_insights(wc_df)
        insights += _cash_insights(cf_metrics, pl_metrics)
    else:
        insights.append(Insight(
            INFO, CAT_DATA,
            "Liquidity, working-capital and cash insights are withheld for this dataset",
            "This dataset was built from ledger movements without opening balances, "
            "so its balance sheet shows the period's movement rather than the closing "
            "position. Ratios derived from it would be wrong, so no interpretation of "
            "them is offered. Profitability findings above remain valid, because "
            "Income Statement accounts genuinely start each period at zero.",
            {"Dataset": dataset_name or "uploaded dataset"},
            "Upload a Trial Balance, or use \"Add to Existing Dataset\", to bring "
            "opening balances in.",
        ))

    if bs_metrics.get("Difference") not in (None, 0, 0.0):
        insights.append(Insight(
            CRITICAL, CAT_DATA,
            f"Balance sheet does not balance — difference of {_money(bs_metrics.get('Difference'))}",
            "Assets do not equal liabilities plus equity. Every figure derived from "
            "this dataset should be treated as unreliable until the difference is found.",
            {"Difference": _money(bs_metrics.get("Difference"))},
            "Trace the imbalance before using these statements.",
        ))

    for note in limitations:
        insights.append(Insight(
            INFO, CAT_DATA, "Dataset limitation", note, {}, None,
        ))

    if validation_warnings:
        insights.append(Insight(
            WATCH, CAT_DATA,
            f"{validation_warnings} validation warning(s) were accepted when this dataset was created",
            "The upload was processed with outstanding warnings. Review them in the "
            "Upload History before relying on these figures.",
            {"Warnings": validation_warnings},
        ))

    insights.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.category))
    return insights


def insights_to_dataframe(insights: List[Insight]) -> pd.DataFrame:
    if not insights:
        return pd.DataFrame(columns=["Severity", "Area", "Finding", "Basis"])
    return pd.DataFrame([i.to_row() for i in insights])


def severity_counts(insights: List[Insight]) -> Dict[str, int]:
    counts = {s: 0 for s in SEVERITY_ORDER}
    for i in insights:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    return counts
