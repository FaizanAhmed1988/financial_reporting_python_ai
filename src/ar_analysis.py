"""
src/ar_analysis.py
==================
Accounts Receivable Analytics module.
Currently restricted to GL aggregate data pending invoice-level subledger.
"""

import pandas as pd
from typing import Dict, Any

def analyze_ar(bs_df: pd.DataFrame, tb: pd.DataFrame, coa_classified: pd.DataFrame, days_in_period: int = 90) -> Dict[str, Any]:
    # 1. Get AR Balance
    ar_row = bs_df[bs_df["Line Item"].str.strip() == "Trade Receivables"]
    ar_balance = float(ar_row.iloc[0]["Amount"]) if not ar_row.empty else 0.0
    
    # 2. Get AR Movement (Closing Net - Opening Net)
    # Trade Receivables is usually account 1100, let's find it via grouping label
    ar_accounts = coa_classified[coa_classified["grouping_label"] == "Trade Receivables"]["account_code"]
    
    ar_movement = 0.0
    if not ar_accounts.empty:
        ar_tb = tb[tb["account_code"].isin(ar_accounts)]
        if not ar_tb.empty:
            ob_net = (ar_tb["opening_debit"] - ar_tb["opening_credit"]).sum()
            cb_net = (ar_tb["closing_debit"] - ar_tb["closing_credit"]).sum()
            ar_movement = float(cb_net - ob_net)
            
    return {
        "Total AR Balance": ar_balance,
        "AR Movement (Period)": ar_movement,
        "Limitation": "Customer-level ageing (Current, 1-30, 31-60, etc.) requires invoice-level data which is not present in this dataset. Architecture below is ready to accept that data if/when it becomes available."
    }

def ageing_report(invoices_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Placeholder for future sub-ledger integration.
    """
    if invoices_df is None or invoices_df.empty:
        return pd.DataFrame({"Message": ["Awaiting invoice-level data for ageing report."]})
    
    # Future logic: group invoices by days past due
    pass
