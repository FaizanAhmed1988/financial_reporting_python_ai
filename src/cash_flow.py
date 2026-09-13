"""
src/cash_flow.py
================
Generates the Cash Flow Statement (Indirect Method).
Driven by the classified COA, Opening TB, and Closing TB.
"""

import pandas as pd
from typing import Dict, Any, Tuple

def generate_cash_flow(coa_classified: pd.DataFrame, tb: pd.DataFrame, net_profit: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    merged = coa_classified.merge(tb, on="account_code", how="inner")
    
    # Calculate movements (Closing - Opening)
    # Assets: Debit is positive, Credit is negative
    # Liabilities/Equity: Credit is negative, Debit is positive in net, but standard convention
    # Let's just calculate (Closing Net - Opening Net) where Net = Debit - Credit
    merged["ob_net"] = merged["opening_debit"] - merged["opening_credit"]
    merged["cb_net"] = merged["closing_debit"] - merged["closing_credit"]
    merged["movement"] = merged["cb_net"] - merged["ob_net"]
    
    # 1. Operating Activities
    # Net Profit
    
    # Add back non-cash items (Depreciation)
    depr_accts = merged[merged["grouping_label"] == "Depreciation & Amortisation"]
    # Depreciation expense is debit normal, so movement is positive. Add it back.
    depreciation_added_back = depr_accts["movement"].sum()
    
    # Working Capital adjustments
    # Assets increase -> Cash outflow (negative)
    # Liabilities increase -> Cash inflow (positive)
    
    # Let's get Current Assets excluding Cash
    current_assets = merged[(merged["bs_sub_category"] == "Current Assets") & (merged["grouping_label"] != "Cash & Cash Equivalents")]
    # Assets are debit normal. A positive movement means asset increased -> Cash outflow.
    # So adjustment = -movement
    wc_assets_adjustment = -current_assets["movement"].sum()
    
    # Let's get Current Liabilities (assuming no short term debt like overdrafts in Current Liabilities for now, or if they are, they'd be Financing. "Loan Payable" is Non-Current, so it's fine).
    current_liab = merged[merged["bs_sub_category"] == "Current Liabilities"]
    # Liabilities are credit normal, so net is negative. A decrease in net (e.g. -100 to -200) means liability increased -> Cash inflow.
    # Wait: movement = cb_net - ob_net. If liability increases, cb_net is more negative. Movement is negative.
    # Cash inflow should be positive. So adjustment = -movement.
    wc_liab_adjustment = -current_liab["movement"].sum()
    
    net_cash_operating = net_profit + depreciation_added_back + wc_assets_adjustment + wc_liab_adjustment
    
    # 2. Investing Activities
    # PPE additions (cost)
    ppe_cost = merged[merged["grouping_label"].str.contains("Property, Plant & Equipment", na=False) & (merged["is_contra"] == False)]
    # Increase in asset -> Cash outflow -> -movement
    investing_cash_flow = -ppe_cost["movement"].sum()
    
    # 3. Financing Activities
    loans = merged[merged["bs_sub_category"] == "Non-Current Liabilities"]
    # Increase in liability -> cb_net more negative -> movement negative -> Cash inflow -> -movement
    loan_movement = -loans["movement"].sum()
    
    equity_movement = merged[(merged["bs_category"] == "Equity") & (merged["bs_sub_category"] != "Retained Earnings")]["movement"].sum()
    financing_cash_flow = loan_movement - equity_movement # Equity is also credit normal, so -movement
    
    net_increase_in_cash = net_cash_operating + investing_cash_flow + financing_cash_flow
    
    # Verify with Cash accounts
    cash_accounts = merged[merged["grouping_label"] == "Cash & Cash Equivalents"]
    opening_cash = cash_accounts["ob_net"].sum()
    closing_cash = cash_accounts["cb_net"].sum()
    
    actual_increase = closing_cash - opening_cash
    cf_diff = round(net_increase_in_cash - actual_increase, 2)
    reconciled = abs(cf_diff) < 1.0
    
    metrics = {
        "Net Cash from Operating": float(net_cash_operating),
        "Net Cash from Investing": float(investing_cash_flow),
        "Net Cash from Financing": float(financing_cash_flow),
        "Net Increase in Cash": float(net_increase_in_cash),
        "Opening Cash": float(opening_cash),
        "Closing Cash (Calculated)": float(opening_cash + net_increase_in_cash),
        "Closing Cash (Actual)": float(closing_cash),
        "Difference": float(cf_diff),
        "Reconciled": reconciled
    }
    
    # Build formatted CF DataFrame for display
    rows = []
    rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": "Net Profit / (Loss)", "Amount": net_profit})
    rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": "Adjustments for:", "Amount": None})
    rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": "  Depreciation & Amortisation", "Amount": depreciation_added_back})
    rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": "Changes in Working Capital:", "Amount": None})
    for _, r in current_assets.iterrows():
        name = r.get('account_name_x', r.get('account_name', r['grouping_label']))
        rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": f"  (Increase)/Decrease in {name}", "Amount": -r["movement"]})
    for _, r in current_liab.iterrows():
        name = r.get('account_name_x', r.get('account_name', r['grouping_label']))
        rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": f"  Increase/(Decrease) in {name}", "Amount": -r["movement"]})
    rows.append({"Category": "Cash Flows from Operating Activities", "Line Item": "Net Cash from Operating Activities", "Amount": net_cash_operating})
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    
    rows.append({"Category": "Cash Flows from Investing Activities", "Line Item": "Purchase of Property, Plant & Equipment", "Amount": investing_cash_flow})
    rows.append({"Category": "Cash Flows from Investing Activities", "Line Item": "Net Cash from Investing Activities", "Amount": investing_cash_flow})
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    
    rows.append({"Category": "Cash Flows from Financing Activities", "Line Item": "Proceeds from / (Repayment of) Borrowings", "Amount": loan_movement})
    rows.append({"Category": "Cash Flows from Financing Activities", "Line Item": "Net Cash from Financing Activities", "Amount": financing_cash_flow})
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    
    rows.append({"Category": "Summary", "Line Item": "Net Increase / (Decrease) in Cash", "Amount": net_increase_in_cash})
    rows.append({"Category": "Summary", "Line Item": "Cash & Cash Equivalents, Beginning of Period", "Amount": opening_cash})
    rows.append({"Category": "Summary", "Line Item": "Cash & Cash Equivalents, End of Period", "Amount": opening_cash + net_increase_in_cash})
    
    cf_statement = pd.DataFrame(rows)
    return cf_statement, metrics

if __name__ == "__main__":
    from src.data_loader import load_workbook
    from src.account_classifier import AccountClassifier
    from src.profit_loss import generate_profit_loss
    from pathlib import Path
    
    wb = load_workbook(Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx"), header_row=3)
    coa_c = AccountClassifier().classify(wb.coa)
    _, pl_metrics = generate_profit_loss(coa_c, wb.tb)
    net_profit = pl_metrics["Net Profit"]
    
    cf_df, cf_metrics = generate_cash_flow(coa_c, wb.tb, net_profit)
    print("Cash Flow Statement (Q1 2026)")
    print(cf_df.to_string(index=False))
    print(f"\nReconciled: {cf_metrics['Reconciled']} (Diff: {cf_metrics['Difference']})")
