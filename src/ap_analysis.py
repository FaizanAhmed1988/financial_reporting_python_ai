"""
src/ap_analysis.py
==================
Accounts Payable Analytics module.
Currently restricted to GL aggregate data pending vendor-level subledger.
"""

import pandas as pd
from typing import Dict, Any

def analyze_ap(bs_df: pd.DataFrame, tb: pd.DataFrame, coa_classified: pd.DataFrame, days_in_period: int = 90) -> Dict[str, Any]:
    # 1. Get AP Balance
    ap_row = bs_df[bs_df["Line Item"].str.strip() == "Trade Payables"]
    ap_balance = float(ap_row.iloc[0]["Amount"]) if not ap_row.empty else 0.0
    # Note: balance sheet might store it as positive or negative depending on display logic
    # In our balance sheet, liabilities are rendered as positive for display under LIABILITIES.
    # We will just take the absolute value or the displayed value.
    ap_balance = abs(ap_balance)
    
    # 2. Get AP Movement
    ap_accounts = coa_classified[coa_classified["grouping_label"] == "Trade Payables"]["account_code"]
    
    ap_movement = 0.0
    if not ap_accounts.empty:
        ap_tb = tb[tb["account_code"].isin(ap_accounts)]
        if not ap_tb.empty:
            # Credit normal, so net = Cr - Dr
            ob_net = (ap_tb["opening_credit"] - ap_tb["opening_debit"]).sum()
            cb_net = (ap_tb["closing_credit"] - ap_tb["closing_debit"]).sum()
            ap_movement = float(cb_net - ob_net)
            
    return {
        "Total AP Balance": ap_balance,
        "AP Movement (Period)": ap_movement,
        "Limitation": "Vendor-level ageing (Current, 1-30, 31-60, etc.) requires invoice-level data which is not present in this dataset. Architecture below is ready to accept that data if/when it becomes available."
    }

def vendor_ageing_report(invoices_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Placeholder for future sub-ledger integration.
    """
    if invoices_df is None or invoices_df.empty:
        return pd.DataFrame({"Message": ["Awaiting vendor invoice-level data for ageing report."]})
    
    # Future logic: group invoices by days past due
    pass
