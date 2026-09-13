"""
src/budget_vs_actual.py
=======================
Comparison engine matching Actual P&L results against the SYNTHETIC Budget.
"""

import pandas as pd
from typing import Dict, Any

def generate_bva(pl_df: pd.DataFrame, budget_df: pd.DataFrame) -> pd.DataFrame:
    # pl_df comes from src.profit_loss, it has 'Line Item' and 'Amount'.
    # budget_df has 'grouping_label' and 'budget_amount'.
    
    # We want to map the actuals to the budget. The Line Item in pl_df often has "  " prepended.
    # We will aggregate budget_df by grouping_label first.
    budget_agg = budget_df.groupby("grouping_label")["budget_amount"].sum().reset_index()
    
    # We also need to get Total Revenue, COGS, Total Opex etc to match the P&L structure.
    total_budget_revenue = budget_df[budget_df["pl_category"] == "Revenue"]["budget_amount"].sum()
    total_budget_cogs = budget_df[budget_df["pl_category"] == "Cost of Sales"]["budget_amount"].sum()
    total_budget_opex = budget_df[budget_df["pl_category"] == "Operating Expenses"]["budget_amount"].sum()
    total_budget_finance = budget_df[budget_df["pl_category"] == "Finance Costs"]["budget_amount"].sum()
    
    budget_gp = total_budget_revenue - total_budget_cogs
    budget_ebit = budget_gp - total_budget_opex
    budget_pbt = budget_ebit - total_budget_finance
    
    # Build a lookup dictionary for budget amounts
    budget_lookup = {r["grouping_label"]: r["budget_amount"] for _, r in budget_agg.iterrows()}
    budget_lookup["Total Revenue"] = total_budget_revenue
    budget_lookup["Total Cost of Sales"] = total_budget_cogs
    budget_lookup["Gross Profit"] = budget_gp
    budget_lookup["Total Operating Expenses"] = total_budget_opex
    budget_lookup["Operating Profit (EBIT)"] = budget_ebit
    budget_lookup["Total Finance Costs"] = total_budget_finance
    budget_lookup["Profit Before Tax"] = budget_pbt
    budget_lookup["Net Profit / (Loss)"] = budget_pbt # assuming tax is 0 in budget too
    
    rows = []
    
    for _, r in pl_df.iterrows():
        line_item = r["Line Item"]
        actual = r["Amount"]
        
        if pd.isna(actual) or line_item == "Income Tax":
            rows.append({
                "Line Item": line_item,
                "Actual": actual,
                "Budget (SYNTHETIC)": None,
                "Variance": None,
                "Variance %": None,
                "Status": "",
                "Material": ""
            })
            continue
            
        clean_item = line_item.strip()
        budget_val = budget_lookup.get(clean_item, 0.0)
        
        # Calculate Variance
        # For Revenue and Profit lines, positive variance is Favorable
        # For Expenses and COGS, negative variance is Favorable
        is_expense = any(x in line_item for x in ["Cost", "Expense", "Depreciation", "Salaries", "Rent", "Utilities", "Insurance", "Advertising", "Repairs", "Miscellaneous", "Charges"])
        if "Total Revenue" in line_item or "Gross Profit" in line_item or "Operating Profit" in line_item or "Net Profit" in line_item:
            is_expense = False
            
        variance = actual - budget_val
        if is_expense:
            # We want (Actual - Budget). If Actual > Budget, it's over budget (Unfavorable).
            var_pct = (variance / budget_val) * 100 if budget_val else 0
            status = "Unfavorable" if variance > 0 else "Favorable"
        else:
            # Revenue/Profit: Actual > Budget is Favorable
            var_pct = (variance / budget_val) * 100 if budget_val else 0
            status = "Favorable" if variance > 0 else "Unfavorable"
            
        material = "⚠️ Material" if abs(var_pct) > 10.0 else ""
        
        rows.append({
            "Line Item": line_item,
            "Actual": float(actual) if pd.notnull(actual) else None,
            "Budget (SYNTHETIC)": float(budget_val),
            "Variance": float(variance),
            "Variance %": f"{var_pct:.1f}%",
            "Status": status,
            "Material": material
        })
        
    return pd.DataFrame(rows)
