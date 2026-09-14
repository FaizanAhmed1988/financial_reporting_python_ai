"""
src/bank_reconciliation.py
==========================
Real bank reconciliation — matches the cash book against a bank statement.

Replaces the placeholder in `reconciliation.py`, whose `reconcile_bank()` ended
in `pass` and therefore returned None whenever a statement was actually supplied.

THE SIGN CONVENTION THAT CAUSES MOST BANK-REC BUGS
--------------------------------------------------
A bank statement is written from the BANK's point of view, so its columns are
the mirror of the cash book's:

    money leaving the account   -> statement "Withdrawal"/"Debit"  -> book CREDIT
    money entering the account  -> statement "Deposit"/"Credit"    -> book DEBIT

Both sides are therefore normalised to one signed `amount`, positive for money
in and negative for money out, before anything is compared. Statements arrive in
three shapes and all three are handled:
  * separate withdrawal / deposit columns
  * separate debit / credit columns (bank perspective)
  * a single signed amount column

MATCHING
--------
Two passes, strongest first, each entry consumed at most once:
  1. Exact   — same signed amount and same date.
  2. Timing  — same signed amount, date within `date_tolerance_days`. These are
               genuine reconciling items (cheques in clearing, deposits in
               transit), reported separately rather than merged into "matched".

What is left over is the substance of a reconciliation:
  * in books, not on statement  -> unpresented cheques / deposits in transit
  * on statement, not in books  -> bank charges, interest, direct debits the
                                   business has not posted yet

NOTHING IS INVENTED. If no statement is supplied the module says so and returns
an empty result; it never manufactures the other side of a reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

TOLERANCE = 0.01
DEFAULT_DATE_TOLERANCE_DAYS = 5

#: Grouping label the classifier assigns to cash accounts.
CASH_GROUPING = "Cash & Cash Equivalents"


# ============================================================
# 1. ACCOUNT SELECTION
# ============================================================

def find_bank_accounts(coa_classified: pd.DataFrame) -> pd.DataFrame:
    """
    Bank accounts, identified from the COA classification rather than a name
    substring.

    A blind `account_name.contains("Bank")` also catches "Loan Payable - Bank"
    (a liability) and "Bank Charges" (an expense). Summing those into a cash
    balance produced a reported bank balance of (131,400) when the real figure
    was 596,100. The grouping label is the authoritative signal; the name is
    only used to narrow within cash accounts when several exist.
    """
    if coa_classified is None or coa_classified.empty:
        return pd.DataFrame()

    cash = coa_classified[
        coa_classified.get("grouping_label", pd.Series(dtype=str))
        .astype(str).str.strip().str.lower() == CASH_GROUPING.lower()
    ].copy()
    if cash.empty:
        return cash

    named = cash[cash["account_name"].astype(str).str.contains("bank", case=False, na=False)]
    # Fall back to all cash accounts when none is explicitly called a bank.
    return named if not named.empty else cash


# ============================================================
# 2. NORMALISATION
# ============================================================

def _to_num(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str).str.strip()
        .str.replace(r"[,$€£\s]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def normalise_book_entries(gl: pd.DataFrame, bank_codes) -> pd.DataFrame:
    """
    Cash-book side: the bank account's own GL lines, as signed amounts.
    A book DEBIT increases cash, so it is positive.
    """
    if gl is None or gl.empty:
        return pd.DataFrame(columns=["date", "amount", "reference", "description", "source"])

    codes = {str(c).strip() for c in bank_codes}
    rows = gl[gl["account_code"].astype(str).str.strip().isin(codes)].copy()
    if rows.empty:
        return pd.DataFrame(columns=["date", "amount", "reference", "description", "source"])

    out = pd.DataFrame({
        "date": pd.to_datetime(rows.get("date"), errors="coerce"),
        "amount": _to_num(rows.get("debit", 0)) - _to_num(rows.get("credit", 0)),
        "reference": rows.get("voucher_no", pd.Series("", index=rows.index)).astype(str),
        "description": rows.get("narration", pd.Series("", index=rows.index)).astype(str),
    })
    out["source"] = "Cash Book"
    return out.reset_index(drop=True)


def normalise_statement(statement: pd.DataFrame) -> Tuple[pd.DataFrame, str]:
    """
    Bank side, converted to the BOOK's sign convention (positive = money in).

    Returns (frame, shape) where shape names which column layout was detected,
    so the UI can state how the file was interpreted.
    """
    empty = pd.DataFrame(columns=["date", "amount", "reference", "description", "source"])
    if statement is None or statement.empty:
        return empty, "none"

    df = statement.copy()
    cols = set(df.columns)

    if {"bank_debit", "bank_credit"} & cols:
        # Statement perspective: debit = money OUT of the account.
        money_out = _to_num(df["bank_debit"]) if "bank_debit" in cols else 0.0
        money_in = _to_num(df["bank_credit"]) if "bank_credit" in cols else 0.0
        amount = money_in - money_out
        shape = "withdrawal/deposit columns"
    elif {"debit", "credit"} & cols:
        money_out = _to_num(df["debit"]) if "debit" in cols else 0.0
        money_in = _to_num(df["credit"]) if "credit" in cols else 0.0
        amount = money_in - money_out
        shape = "debit/credit columns (bank perspective)"
    elif "bank_amount" in cols:
        amount = _to_num(df["bank_amount"])
        shape = "single signed amount column"
    else:
        return empty, "unrecognised"

    out = pd.DataFrame({
        "date": pd.to_datetime(df.get("date"), errors="coerce"),
        "amount": amount,
        "reference": df.get("voucher_no", pd.Series("", index=df.index)).astype(str),
        "description": df.get("narration", pd.Series("", index=df.index)).astype(str),
    })
    out["source"] = "Bank Statement"
    return out.reset_index(drop=True), shape


# ============================================================
# 3. RESULT
# ============================================================

@dataclass
class ReconciliationResult:
    matched: pd.DataFrame = field(default_factory=pd.DataFrame)
    timing_differences: pd.DataFrame = field(default_factory=pd.DataFrame)
    in_books_only: pd.DataFrame = field(default_factory=pd.DataFrame)
    on_statement_only: pd.DataFrame = field(default_factory=pd.DataFrame)
    book_balance: float = 0.0
    statement_balance: float = 0.0
    statement_shape: str = "none"
    available: bool = False
    message: str = ""

    @property
    def counts(self) -> Dict[str, int]:
        return {
            "Matched": len(self.matched),
            "Timing Differences": len(self.timing_differences),
            "In Books Only": len(self.in_books_only),
            "On Statement Only": len(self.on_statement_only),
        }

    @property
    def difference(self) -> float:
        return round(self.book_balance - self.statement_balance, 2)

    @property
    def is_reconciled(self) -> bool:
        """
        True when every unmatched item accounts for the gap exactly — which is
        what a reconciliation proves. A zero difference with items outstanding
        is a coincidence, not a reconciliation.
        """
        if not self.available:
            return False
        unexplained = self.difference - (
            self.in_books_only["amount"].sum() if not self.in_books_only.empty else 0.0
        ) + (
            self.on_statement_only["amount"].sum() if not self.on_statement_only.empty else 0.0
        )
        return abs(unexplained) <= TOLERANCE

    def statement_table(self) -> pd.DataFrame:
        """The classic bank reconciliation statement."""
        if not self.available:
            return pd.DataFrame()
        rows = [{"Line": "Balance per cash book", "Amount": round(self.book_balance, 2)}]
        if not self.in_books_only.empty:
            rows.append({
                "Line": f"Less: recorded in books, not yet on statement ({len(self.in_books_only)} item(s))",
                "Amount": round(-self.in_books_only["amount"].sum(), 2),
            })
        if not self.on_statement_only.empty:
            rows.append({
                "Line": f"Add: on statement, not yet recorded in books ({len(self.on_statement_only)} item(s))",
                "Amount": round(self.on_statement_only["amount"].sum(), 2),
            })
        derived = (
            self.book_balance
            - (self.in_books_only["amount"].sum() if not self.in_books_only.empty else 0.0)
            + (self.on_statement_only["amount"].sum() if not self.on_statement_only.empty else 0.0)
        )
        rows.append({"Line": "= Derived balance per bank statement", "Amount": round(derived, 2)})
        rows.append({"Line": "Actual balance per bank statement", "Amount": round(self.statement_balance, 2)})
        rows.append({"Line": "Unexplained difference", "Amount": round(derived - self.statement_balance, 2)})
        return pd.DataFrame(rows)


# ============================================================
# 4. MATCHING
# ============================================================

def reconcile(
    book: pd.DataFrame,
    statement: pd.DataFrame,
    statement_shape: str = "",
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    opening_book_balance: float = 0.0,
    statement_closing_balance: Optional[float] = None,
) -> ReconciliationResult:
    """
    Match the cash book against the bank statement.

    `book` and `statement` must already be normalised to signed amounts
    (positive = money into the account).
    """
    if statement is None or statement.empty:
        return ReconciliationResult(
            available=False,
            message="No bank statement supplied — nothing to reconcile against.",
        )

    book = book.reset_index(drop=True).copy()
    stmt = statement.reset_index(drop=True).copy()
    book["_used"] = False
    stmt["_used"] = False

    matched_rows: List[Dict[str, Any]] = []
    timing_rows: List[Dict[str, Any]] = []

    # Index statement lines by rounded amount for cheap candidate lookup.
    by_amount: Dict[float, List[int]] = {}
    for idx, amt in stmt["amount"].round(2).items():
        by_amount.setdefault(float(amt), []).append(idx)

    def _pair(b_idx, s_idx, kind, day_gap):
        b, s = book.loc[b_idx], stmt.loc[s_idx]
        return {
            "Book Date": b["date"], "Statement Date": s["date"],
            "Amount": round(float(b["amount"]), 2),
            "Book Reference": b["reference"], "Book Description": b["description"],
            "Statement Description": s["description"],
            "Match": kind, "Day Gap": day_gap,
        }

    for pass_name, max_gap in (("Exact", 0), ("Timing", date_tolerance_days)):
        for b_idx in book.index[~book["_used"]]:
            amt = round(float(book.at[b_idx, "amount"]), 2)
            b_date = book.at[b_idx, "date"]
            for s_idx in by_amount.get(amt, []):
                if stmt.at[s_idx, "_used"]:
                    continue
                s_date = stmt.at[s_idx, "date"]
                if pd.isna(b_date) or pd.isna(s_date):
                    gap = 0 if pass_name == "Exact" else None
                    if gap is None:
                        continue
                else:
                    gap = abs((b_date - s_date).days)
                if gap > max_gap:
                    continue
                book.at[b_idx, "_used"] = True
                stmt.at[s_idx, "_used"] = True
                (matched_rows if pass_name == "Exact" else timing_rows).append(
                    _pair(b_idx, s_idx, pass_name, gap)
                )
                break

    cols = ["date", "amount", "reference", "description"]
    in_books_only = book[~book["_used"]][cols].copy()
    on_statement_only = stmt[~stmt["_used"]][cols].copy()

    book_balance = opening_book_balance + book["amount"].sum()
    if statement_closing_balance is None:
        statement_closing_balance = opening_book_balance + stmt["amount"].sum()

    return ReconciliationResult(
        matched=pd.DataFrame(matched_rows),
        timing_differences=pd.DataFrame(timing_rows),
        in_books_only=in_books_only.reset_index(drop=True),
        on_statement_only=on_statement_only.reset_index(drop=True),
        book_balance=float(book_balance),
        statement_balance=float(statement_closing_balance),
        statement_shape=statement_shape,
        available=True,
        message="",
    )


# ============================================================
# 5. TOP-LEVEL
# ============================================================

def run_bank_reconciliation(
    gl: pd.DataFrame,
    coa_classified: pd.DataFrame,
    tb: Optional[pd.DataFrame] = None,
    statement: Optional[pd.DataFrame] = None,
    date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    statement_closing_balance: Optional[float] = None,
) -> ReconciliationResult:
    """
    Convenience entry point: select bank accounts, build both sides, reconcile.

    Opening balance comes from the trial balance when supplied, so the cash-book
    balance is the true closing position rather than the period's movement.
    """
    banks = find_bank_accounts(coa_classified)
    if banks.empty:
        return ReconciliationResult(
            available=False,
            message="No bank account could be identified in the Chart of Accounts.",
        )
    codes = list(banks["account_code"].astype(str).str.strip())

    opening = 0.0
    if tb is not None and not tb.empty:
        rows = tb[tb["account_code"].astype(str).str.strip().isin(codes)]
        if not rows.empty:
            opening = float((rows["opening_debit"] - rows["opening_credit"]).sum())

    book = normalise_book_entries(gl, codes)
    stmt, shape = normalise_statement(statement)

    if stmt.empty:
        return ReconciliationResult(
            book_balance=opening + (book["amount"].sum() if not book.empty else 0.0),
            available=False,
            statement_shape=shape,
            message=(
                "No bank statement has been uploaded. The cash-book side is ready "
                "({} transaction(s) on account(s) {}). Upload a bank statement via "
                "Upload Financial Data to complete the reconciliation."
            ).format(len(book), ", ".join(codes)),
        )

    return reconcile(
        book, stmt, statement_shape=shape,
        date_tolerance_days=date_tolerance_days,
        opening_book_balance=opening,
        statement_closing_balance=statement_closing_balance,
    )
