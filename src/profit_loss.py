"""
src/profit_loss.py
==================
Generates the Profit & Loss Statement (Income Statement).
Driven entirely by the classified COA.
"""

import pandas as pd
from typing import Dict, Any, Tuple

def generate_profit_loss(coa_classified: pd.DataFrame, tb: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    # Merge COA with TB
    merged = coa_classified.merge(tb, on="account_code", how="inner")
    
    # Calculate net closing balance (P&L accounts are usually credit normal for revenue, debit normal for expenses)
    # To display positively, we'll negate revenue and keep expenses positive
    merged["cb_net"] = merged["closing_debit"] - merged["closing_credit"]
    
    # Filter only Income Statement accounts
    pl_accounts = merged[merged["financial_statement"] == "Income Statement"].copy()
    
    metrics: Dict[str, Any] = {}
    
    # 1. Revenue
    revenue_df = pl_accounts[pl_accounts["pl_category"] == "Revenue"]
    total_revenue = -revenue_df["cb_net"].sum() # Credit normal
    
    # 2. Cost of Sales
    cogs_df = pl_accounts[pl_accounts["pl_category"] == "Cost of Sales"]
    total_cogs = cogs_df["cb_net"].sum() # Debit normal
    
    # 3. Gross Profit
    gross_profit = total_revenue - total_cogs
    gross_margin = (gross_profit / total_revenue) * 100 if total_revenue else 0.0
    
    # 4. Operating Expenses
    opex_df = pl_accounts[pl_accounts["pl_category"] == "Operating Expenses"]
    grouped_opex = opex_df.groupby("grouping_label")["cb_net"].sum().reset_index()
    total_opex = opex_df["cb_net"].sum()
    
    # 5. EBITDA (Gross Profit - Opex excluding Depreciation & Amortisation)
    # Let's find Depreciation
    depr_opex = opex_df[opex_df["pl_sub_category"] == "Depreciation & Amortisation"]["cb_net"].sum()
    ebitda = gross_profit - (total_opex - depr_opex)
    ebitda_margin = (ebitda / total_revenue) * 100 if total_revenue else 0.0
    
    # 6. Operating Profit (EBIT)
    ebit = gross_profit - total_opex
    ebit_margin = (ebit / total_revenue) * 100 if total_revenue else 0.0
    
    # 7. Finance Costs
    finance_df = pl_accounts[pl_accounts["pl_category"] == "Finance Costs"]
    total_finance = finance_df["cb_net"].sum()
    
    # 8. Profit Before Tax
    pbt = ebit - total_finance
    
    # 9. Income Tax (Assumed 0)
    income_tax = 0.0
    
    # 10. Net Profit
    net_profit = pbt - income_tax
    net_profit_margin = (net_profit / total_revenue) * 100 if total_revenue else 0.0
    
    metrics = {
        "Total Revenue": float(total_revenue),
        "Total COGS": float(total_cogs),
        "Gross Profit": float(gross_profit),
        "Gross Margin %": float(gross_margin),
        "Total Opex": float(total_opex),
        "EBITDA": float(ebitda),
        "EBITDA Margin %": float(ebitda_margin),
        "Operating Profit (EBIT)": float(ebit),
        "EBIT Margin %": float(ebit_margin),
        "Total Finance Costs": float(total_finance),
        "Profit Before Tax": float(pbt),
        "Income Tax": float(income_tax),
        "Net Profit": float(net_profit),
        "Net Profit Margin %": float(net_profit_margin)
    }
    
    # Build formatted P&L DataFrame for display
    rows = []
    rows.append({"Line Item": "Revenue", "Amount": None})
    for _, r in revenue_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Line Item": f"  {r['grouping_label']}", "Amount": -r["cb_net"]})
    rows.append({"Line Item": "Total Revenue", "Amount": total_revenue})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Cost of Sales", "Amount": None})
    for _, r in cogs_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Line Item": f"  {r['grouping_label']}", "Amount": r["cb_net"]})
    rows.append({"Line Item": "Total Cost of Sales", "Amount": total_cogs})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Gross Profit", "Amount": gross_profit})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Operating Expenses", "Amount": None})
    for _, r in grouped_opex.iterrows():
        rows.append({"Line Item": f"  {r['grouping_label']}", "Amount": r["cb_net"]})
    rows.append({"Line Item": "Total Operating Expenses", "Amount": total_opex})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Operating Profit (EBIT)", "Amount": ebit})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Finance Costs", "Amount": None})
    for _, r in finance_df.groupby("grouping_label")["cb_net"].sum().reset_index().iterrows():
        rows.append({"Line Item": f"  {r['grouping_label']}", "Amount": r["cb_net"]})
    rows.append({"Line Item": "Total Finance Costs", "Amount": total_finance})
    
    rows.append({"Line Item": "", "Amount": None})
    rows.append({"Line Item": "Profit Before Tax", "Amount": pbt})
    rows.append({"Line Item": "Income Tax", "Amount": income_tax})
    rows.append({"Line Item": "Net Profit / (Loss)", "Amount": net_profit})
    
    pl_statement = pd.DataFrame(rows)
    return pl_statement, metrics

if __name__ == "__main__":
    from src.data_loader import load_workbook
    from src.account_classifier import AccountClassifier
    from pathlib import Path
    
    wb = load_workbook(Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx"), header_row=3)
    coa_c = AccountClassifier().classify(wb.coa)
    pl_df, metrics = generate_profit_loss(coa_c, wb.tb)
    print("Profit & Loss Statement (Q1 2026)")
    print(pl_df.to_string(index=False))
