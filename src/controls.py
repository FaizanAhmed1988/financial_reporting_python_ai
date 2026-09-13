"""
src/controls.py
===============
Financial Control Analytics module.
Runs automated control tests on the General Ledger to identify potential anomalies.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List

def run_control_tests(gl: pd.DataFrame) -> Dict[str, Any]:
    # We expect gl to have: Txn No, Date, Voucher No, Account Code, Account Name, Debit, Credit, Narration
    findings: Dict[str, Any] = {}
    
    # Pre-process: calculate absolute amount for standard deviation
    df = gl.copy()
    df["amount"] = df["debit"] + df["credit"]
    
    # 1. Duplicate transactions/journal entries
    # Exact match on Date, Account Code, Amount, and Narration
    duplicates = df[df.duplicated(subset=["date", "account_code", "amount", "narration"], keep=False)]
    findings["Duplicate Transactions"] = {
        "count": len(duplicates),
        "data": duplicates[["txn_no", "date", "account_code", "amount", "narration"]],
        "label": "Potential Anomaly - Duplicate Posting" if len(duplicates) > 0 else "Clean"
    }
    
    # 2. Unusual/large transactions (Statistical Outliers > 2.5 std dev)
    outliers_list = []
    for acct, group in df.groupby("account_code"):
        if len(group) >= 3:  # Need sufficient data points
            mean = group["amount"].mean()
            std = group["amount"].std()
            if std > 0:
                outliers = group[group["amount"] > (mean + 2.5 * std)]
                if not outliers.empty:
                    outliers_list.append(outliers)
    
    if outliers_list:
        outliers_df = pd.concat(outliers_list)
    else:
        outliers_df = pd.DataFrame()
        
    findings["Statistical Outliers (>2.5 Std Dev)"] = {
        "count": len(outliers_df),
        "data": outliers_df[["txn_no", "date", "account_code", "amount", "narration"]] if not outliers_df.empty else None,
        "label": "Requires Review - Unusually Large Transaction" if len(outliers_df) > 0 else "Clean"
    }
    
    # 3. Round-number transactions (ending in 000.00)
    # Be careful not to flag small numbers like 1000 or 2000 if they are common, but let's flag >= 10,000 ending in 000
    round_numbers = df[(df["amount"] >= 10000) & (df["amount"] % 1000 == 0)]
    findings["Round-Number Transactions"] = {
        "count": len(round_numbers),
        "data": round_numbers[["txn_no", "date", "account_code", "amount", "narration"]],
        "label": "Requires Review - Potential Estimate/Manual Entry" if len(round_numbers) > 0 else "Clean"
    }
    
    # 4. Weekend transactions
    # Ensure Date is datetime
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    weekends = df[df["date"].dt.dayofweek.isin([5, 6])] # 5=Sat, 6=Sun
    findings["Weekend Transactions"] = {
        "count": len(weekends),
        "data": weekends[["txn_no", "date", "account_code", "amount", "narration"]],
        "label": "Potential Anomaly - Weekend Posting" if len(weekends) > 0 else "Clean"
    }
    
    # 5. Backdated transactions
    findings["Backdated Transactions"] = {
        "count": 0,
        "data": None,
        "label": "Cannot be tested with current data (GL lacks Post Date vs Transaction Date)"
    }
    
    # 6. Manual journal indicators
    findings["Manual Journal Indicators"] = {
        "count": 0,
        "data": None,
        "label": "Cannot be tested with current data (GL lacks Journal Source/Type field)"
    }
    
    # 7. Unusual account combinations in the same voucher
    # E.g. Expense account debited with an unrelated account.
    # Let's find vouchers that hit both Expense (5xxx, 6xxx) and Equity (3xxx) directly.
    unusual_vouchers = []
    for voucher, group in df.groupby("voucher_no"):
        codes = group["account_code"].astype(str).tolist()
        has_expense = any(c.startswith("5") or c.startswith("6") for c in codes)
        has_equity = any(c.startswith("3") for c in codes)
        if has_expense and has_equity:
            unusual_vouchers.append(voucher)
            
    unusual = df[df["voucher_no"].isin(unusual_vouchers)]
    findings["Unusual Account Combinations"] = {
        "count": len(unusual_vouchers),
        "data": unusual[["voucher_no", "date", "account_code", "amount", "narration"]] if not unusual.empty else None,
        "label": "Requires Review - Expense paired with Equity" if unusual_vouchers else "Clean"
    }
    
    return findings
