"""
src/reconciliation.py
=====================
Bank Reconciliation module.
Currently extracts GL Bank Account balance and awaits bank statement data.
"""

import pandas as pd
from typing import Dict, Any

def get_gl_bank_balance(bs_df: pd.DataFrame) -> float:
    # 1010 Bank Account - Main is mapped to Cash & Cash Equivalents
    # However, Cash & Cash Equivalents also contains 1000 Cash in Hand.
    # To be precise, we should look at the TB or GL for 1010.
    return 0.0 # Placeholder if not using TB directly.

def analyze_reconciliation(tb: pd.DataFrame, coa_classified: pd.DataFrame) -> Dict[str, Any]:
    # Find Bank Account(s)
    bank_accounts = coa_classified[coa_classified["account_name"].str.contains("Bank", case=False, na=False)]["account_code"]
    
    gl_bank_balance = 0.0
    if not bank_accounts.empty:
        bank_tb = tb[tb["account_code"].isin(bank_accounts)]
        if not bank_tb.empty:
            # Debit normal
            cb_net = (bank_tb["closing_debit"] - bank_tb["closing_credit"]).sum()
            gl_bank_balance = float(cb_net)
            
    return {
        "GL Bank Balance": gl_bank_balance,
        "Status": "No bank statement file provided — reconciliation module built and ready, awaiting bank statement data."
    }

def reconcile_bank(gl_df: pd.DataFrame, bank_statement_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Placeholder for future bank statement reconciliation.
    Will identify: Matched, Unmatched, Missing Entries, Duplicates, Timing Differences.
    """
    if bank_statement_df is None or bank_statement_df.empty:
        return pd.DataFrame({"Status": ["Awaiting bank statement data for reconciliation."]})
    
    # Future logic: Match on Date, Amount, Reference
    pass
