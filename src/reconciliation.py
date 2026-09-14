"""
src/reconciliation.py
=====================
Bank Reconciliation — public surface.

The real matching engine lives in `bank_reconciliation.py`. This module keeps
the signatures the dashboard and month-end close already call, and now delegates
to that engine instead of returning placeholders.

WHAT CHANGED
------------
1. `reconcile_bank()` previously ended in a bare `pass`, so supplying a bank
   statement returned None. It now performs a real reconciliation.
2. Bank accounts were selected with `account_name.contains("Bank")`, which also
   matched "Loan Payable - Bank" (a liability) and "Bank Charges" (an expense).
   That reported a bank balance of (131,400) against a true figure of 596,100 —
   an error of 727,500. Selection is now driven by the COA classification.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from src.bank_reconciliation import (
    ReconciliationResult,
    find_bank_accounts,
    run_bank_reconciliation,
)

NO_STATEMENT_MARKER = "No bank statement file provided"


def get_gl_bank_balance(tb: pd.DataFrame, coa_classified: pd.DataFrame) -> float:
    """Closing balance of the identified bank account(s) from the trial balance."""
    banks = find_bank_accounts(coa_classified)
    if banks.empty or tb is None or tb.empty:
        return 0.0
    codes = set(banks["account_code"].astype(str).str.strip())
    rows = tb[tb["account_code"].astype(str).str.strip().isin(codes)]
    if rows.empty:
        return 0.0
    return float((rows["closing_debit"] - rows["closing_credit"]).sum())


def analyze_reconciliation(
    tb: pd.DataFrame,
    coa_classified: pd.DataFrame,
    gl: Optional[pd.DataFrame] = None,
    statement: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Summary for the dashboard and the month-end close checklist.

    `gl` and `statement` are optional so existing two-argument callers keep
    working; supplying both produces a full reconciliation.
    """
    banks = find_bank_accounts(coa_classified)
    gl_bank_balance = get_gl_bank_balance(tb, coa_classified)

    result: Optional[ReconciliationResult] = None
    if gl is not None and statement is not None and not statement.empty:
        result = run_bank_reconciliation(gl, coa_classified, tb, statement)

    if result is not None and result.available:
        status = (
            f"Reconciled against uploaded bank statement — "
            f"{result.counts['Matched']} matched, "
            f"{result.counts['Timing Differences']} timing difference(s), "
            f"{result.counts['In Books Only']} in books only, "
            f"{result.counts['On Statement Only']} on statement only."
        )
        if not result.is_reconciled:
            status += (
                f" UNEXPLAINED DIFFERENCE of "
                f"{result.statement_table().iloc[-1]['Amount']:,.2f} remains."
            )
    else:
        status = (
            f"{NO_STATEMENT_MARKER}. Cash-book side is ready "
            f"({', '.join(banks['account_code'].astype(str)) or 'no bank account identified'}). "
            "Upload a bank statement CSV/XLSX to complete the reconciliation."
        )

    return {
        "GL Bank Balance": gl_bank_balance,
        "Bank Accounts": list(banks["account_code"].astype(str)) if not banks.empty else [],
        "Status": status,
        "Result": result,
    }


def reconcile_bank(
    gl_df: pd.DataFrame,
    bank_statement_df: pd.DataFrame = None,
    coa_classified: pd.DataFrame = None,
    tb: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Reconcile the cash book against a bank statement.

    Returns the classic reconciliation statement (balance per books, reconciling
    items, balance per bank). Previously a stub that returned None whenever a
    statement was actually supplied.
    """
    if bank_statement_df is None or bank_statement_df.empty:
        return pd.DataFrame({"Status": ["Awaiting bank statement data for reconciliation."]})
    if coa_classified is None or coa_classified.empty:
        return pd.DataFrame({"Status": ["A classified Chart of Accounts is required to identify the bank account."]})

    result = run_bank_reconciliation(gl_df, coa_classified, tb, bank_statement_df)
    if not result.available:
        return pd.DataFrame({"Status": [result.message]})
    return result.statement_table()
