"""
src/balance_sheet.py
====================
Generates the Balance Sheet.
Driven by the classified COA and Trial Balance.
"""

import pandas as pd
from typing import Dict, Any, Tuple

def generate_balance_sheet(coa_classified: pd.DataFrame, tb: pd.DataFrame, net_profit: float) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    merged = coa_classified.merge(tb, on="account_code", how="inner")
    
    # Net balance for BS accounts: Debit - Credit
    # Assets are positive, Liab/Equity are negative in cb_net, so we negate them for display
    merged["cb_net"] = merged["closing_debit"] - merged["closing_credit"]
    
    bs_accounts = merged[merged["financial_statement"] == "Balance Sheet"].copy()
    
    # 1. Assets
    assets_df = bs_accounts[bs_accounts["bs_category"] == "Assets"]
    current_assets_df = assets_df[assets_df["bs_sub_category"] == "Current Assets"]
    non_current_assets_df = assets_df[assets_df["bs_sub_category"] == "Non-Current Assets"]
    
    total_current_assets = current_assets_df["cb_net"].sum()
    total_non_current_assets = non_current_assets_df["cb_net"].sum()
    total_assets = total_current_assets + total_non_current_assets
    
    # 2. Liabilities (credit normal -> negate for display)
    liab_df = bs_accounts[bs_accounts["bs_category"] == "Liabilities"]
    current_liab_df = liab_df[liab_df["bs_sub_category"] == "Current Liabilities"]
    non_current_liab_df = liab_df[liab_df["bs_sub_category"] == "Non-Current Liabilities"]
    
    total_current_liab = -current_liab_df["cb_net"].sum()
    total_non_current_liab = -non_current_liab_df["cb_net"].sum()
    total_liabilities = total_current_liab + total_non_current_liab
    
    # 3. Equity (credit normal -> negate for display)
    equity_df = bs_accounts[bs_accounts["bs_category"] == "Equity"]
    total_equity_before_np = -equity_df["cb_net"].sum()
    total_equity = total_equity_before_np + net_profit
    
    # Validations
    bs_diff = round(total_assets - (total_liabilities + total_equity), 2)
    is_balanced = abs(bs_diff) < 1.0
    
    metrics = {
        "Total Assets": float(total_assets),
        "Total Liabilities": float(total_liabilities),
        "Total Equity": float(total_equity),
        "Difference": float(bs_diff),
        "Is Balanced": is_balanced
    }
    
    # Build formatted BS DataFrame for display
    rows = []
    
    # ASSETS
    rows.append({"Category": "ASSETS", "Line Item": "", "Amount": None})
    rows.append({"Category": "", "Line Item": "Current Assets", "Amount": None})
    for _, r in current_assets_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Category": "", "Line Item": f"  {r['grouping_label']}", "Amount": r["cb_net"]})
    rows.append({"Category": "", "Line Item": "Total Current Assets", "Amount": total_current_assets})
    
    rows.append({"Category": "", "Line Item": "Non-Current Assets", "Amount": None})
    for _, r in non_current_assets_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Category": "", "Line Item": f"  {r['grouping_label']}", "Amount": r["cb_net"]})
    rows.append({"Category": "", "Line Item": "Total Non-Current Assets", "Amount": total_non_current_assets})
    rows.append({"Category": "", "Line Item": "TOTAL ASSETS", "Amount": total_assets})
    
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    
    # LIABILITIES
    rows.append({"Category": "LIABILITIES", "Line Item": "", "Amount": None})
    rows.append({"Category": "", "Line Item": "Current Liabilities", "Amount": None})
    for _, r in current_liab_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Category": "", "Line Item": f"  {r['grouping_label']}", "Amount": -r["cb_net"]})
    rows.append({"Category": "", "Line Item": "Total Current Liabilities", "Amount": total_current_liab})
    
    rows.append({"Category": "", "Line Item": "Non-Current Liabilities", "Amount": None})
    for _, r in non_current_liab_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Category": "", "Line Item": f"  {r['grouping_label']}", "Amount": -r["cb_net"]})
    rows.append({"Category": "", "Line Item": "Total Non-Current Liabilities", "Amount": total_non_current_liab})
    rows.append({"Category": "", "Line Item": "TOTAL LIABILITIES", "Amount": total_liabilities})
    
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    
    # EQUITY
    rows.append({"Category": "EQUITY", "Line Item": "", "Amount": None})
    for _, r in equity_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Category": "", "Line Item": f"  {r['grouping_label']}", "Amount": -r["cb_net"]})
    rows.append({"Category": "", "Line Item": "  Current Year Profit / (Loss)", "Amount": net_profit})
    rows.append({"Category": "", "Line Item": "TOTAL EQUITY", "Amount": total_equity})
    
    rows.append({"Category": "", "Line Item": "", "Amount": None})
    rows.append({"Category": "", "Line Item": "TOTAL LIABILITIES AND EQUITY", "Amount": total_liabilities + total_equity})
    
    bs_statement = pd.DataFrame(rows)
    return bs_statement, metrics

if __name__ == "__main__":
    from src.data_loader import load_workbook
    from src.account_classifier import AccountClassifier
    from src.profit_loss import generate_profit_loss
    from pathlib import Path
    
    wb = load_workbook(Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx"), header_row=3)
    coa_c = AccountClassifier().classify(wb.coa)
    _, pl_metrics = generate_profit_loss(coa_c, wb.tb)
    net_profit = pl_metrics["Net Profit"]
    
    bs_df, bs_metrics = generate_balance_sheet(coa_c, wb.tb, net_profit)
    print("Balance Sheet (As at 31-Mar-2026)")
    print(bs_df.to_string(index=False))
    print(f"\nBalanced: {bs_metrics['Is Balanced']} (Diff: {bs_metrics['Difference']})")
