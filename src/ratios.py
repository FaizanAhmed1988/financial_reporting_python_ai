"""
src/ratios.py
=============
Calculates financial ratios for Liquidity, Profitability, Efficiency, and Leverage.
Designed for a single period (Q1 2026).
"""

import pandas as pd
from typing import Dict, Any, Tuple

def calculate_ratios(pl_metrics: Dict[str, Any], bs_metrics: Dict[str, Any], bs_df: pd.DataFrame, days_in_period: int = 90) -> pd.DataFrame:
    # Extract needed values from metrics
    revenue = pl_metrics.get("Total Revenue", 0)
    cogs = pl_metrics.get("Total COGS", 0)
    gross_profit = pl_metrics.get("Gross Profit", 0)
    ebitda = pl_metrics.get("EBITDA", 0)
    ebit = pl_metrics.get("Operating Profit (EBIT)", 0)
    net_profit = pl_metrics.get("Net Profit", 0)
    interest_expense = pl_metrics.get("Total Finance Costs", 0)
    
    total_assets = bs_metrics.get("Total Assets", 0)
    total_equity = bs_metrics.get("Total Equity", 0)
    total_liabilities = bs_metrics.get("Total Liabilities", 0)
    
    # Extract specific line items from the BS dataframe
    # We need Current Assets, Current Liab, Cash, Inventory, AR, AP
    
    def get_bs_value(line_item_name: str) -> float:
        # line items in bs_df have leading spaces, e.g. "  Cash & Cash Equivalents"
        row = bs_df[bs_df["Line Item"].str.strip() == line_item_name]
        if not row.empty:
            return float(row.iloc[0]["Amount"])
        return 0.0

    current_assets = get_bs_value("Total Current Assets")
    current_liabilities = get_bs_value("Total Current Liabilities")
    cash = get_bs_value("Cash & Cash Equivalents")
    inventory = get_bs_value("Inventories")
    ar = get_bs_value("Trade Receivables")
    ap = get_bs_value("Trade Payables")
    
    # --- LIQUIDITY ---
    current_ratio = current_assets / current_liabilities if current_liabilities else 0
    quick_ratio = (current_assets - inventory) / current_liabilities if current_liabilities else 0
    cash_ratio = cash / current_liabilities if current_liabilities else 0
    
    # --- PROFITABILITY ---
    gross_margin = gross_profit / revenue if revenue else 0
    ebit_margin = ebit / revenue if revenue else 0
    ebitda_margin = ebitda / revenue if revenue else 0
    net_profit_margin = net_profit / revenue if revenue else 0
    roa = net_profit / total_assets if total_assets else 0
    roe = net_profit / total_equity if total_equity else 0
    
    # --- EFFICIENCY (Single Period) ---
    asset_turnover = revenue / total_assets if total_assets else 0
    inventory_turnover = cogs / inventory if inventory else 0
    
    dso = (ar / revenue) * days_in_period if revenue else 0
    dpo = (ap / cogs) * days_in_period if cogs else 0
    dio = (inventory / cogs) * days_in_period if cogs else 0
    ccc = dio + dso - dpo
    
    # --- LEVERAGE ---
    debt_ratio = total_liabilities / total_assets if total_assets else 0
    debt_to_equity = total_liabilities / total_equity if total_equity else 0
    interest_coverage = ebit / interest_expense if interest_expense else 0
    
    rows = [
        {"Category": "Liquidity", "Ratio": "Current Ratio", "Formula": "Current Assets / Current Liab", "Value": current_ratio, "Interpretation": f"{current_ratio:.2f}x - ability to cover short term obligations"},
        {"Category": "Liquidity", "Ratio": "Quick Ratio", "Formula": "(Current Assets - Inventory) / Current Liab", "Value": quick_ratio, "Interpretation": f"{quick_ratio:.2f}x - liquid assets against short term liabilities"},
        {"Category": "Liquidity", "Ratio": "Cash Ratio", "Formula": "Cash / Current Liab", "Value": cash_ratio, "Interpretation": f"{cash_ratio:.2f}x - strict liquidity ignoring receivables"},
        
        {"Category": "Profitability", "Ratio": "Gross Profit Margin", "Formula": "Gross Profit / Revenue", "Value": f"{gross_margin*100:.1f}%", "Interpretation": f"{gross_margin*100:.1f}% - core mark-up profitability"},
        {"Category": "Profitability", "Ratio": "EBIT Margin", "Formula": "EBIT / Revenue", "Value": f"{ebit_margin*100:.1f}%", "Interpretation": f"{ebit_margin*100:.1f}% - operating efficiency"},
        {"Category": "Profitability", "Ratio": "EBITDA Margin", "Formula": "EBITDA / Revenue", "Value": f"{ebitda_margin*100:.1f}%", "Interpretation": f"{ebitda_margin*100:.1f}% - cash operating profitability"},
        {"Category": "Profitability", "Ratio": "Net Profit Margin", "Formula": "Net Profit / Revenue", "Value": f"{net_profit_margin*100:.1f}%", "Interpretation": f"{net_profit_margin*100:.1f}% - bottom line profitability (NOTE: loss)"},
        {"Category": "Profitability", "Ratio": "ROA (Period-End)", "Formula": "Net Profit / Total Assets", "Value": f"{roa*100:.1f}%", "Interpretation": f"{roa*100:.1f}% - asset efficiency"},
        {"Category": "Profitability", "Ratio": "ROE (Period-End)", "Formula": "Net Profit / Total Equity", "Value": f"{roe*100:.1f}%", "Interpretation": f"{roe*100:.1f}% - return to shareholders"},
        
        {"Category": "Efficiency", "Ratio": "Asset Turnover", "Formula": "Revenue / Total Assets", "Value": f"{asset_turnover:.2f}x", "Interpretation": f"{asset_turnover:.2f}x - revenue generated per dollar of assets"},
        {"Category": "Efficiency", "Ratio": "Inventory Turnover", "Formula": "COGS / Inventory", "Value": f"{inventory_turnover:.2f}x", "Interpretation": f"{inventory_turnover:.2f}x - times inventory sold in period"},
        {"Category": "Efficiency", "Ratio": "Days Sales Outstanding (DSO)", "Formula": "(AR / Revenue) * 90", "Value": f"{dso:.0f} days", "Interpretation": f"{dso:.0f} days to collect cash from customers"},
        {"Category": "Efficiency", "Ratio": "Days Payable Outstanding (DPO)", "Formula": "(AP / COGS) * 90", "Value": f"{dpo:.0f} days", "Interpretation": f"{dpo:.0f} days to pay suppliers (very high!)"},
        {"Category": "Efficiency", "Ratio": "Cash Conversion Cycle (CCC)", "Formula": "DIO + DSO - DPO", "Value": f"{ccc:.0f} days", "Interpretation": f"{ccc:.0f} days cash is tied up in ops (negative is cash flow positive)"},
        
        {"Category": "Leverage", "Ratio": "Debt Ratio", "Formula": "Total Liabilities / Total Assets", "Value": f"{debt_ratio*100:.1f}%", "Interpretation": f"{debt_ratio*100:.1f}% of assets financed by debt"},
        {"Category": "Leverage", "Ratio": "Debt-to-Equity", "Formula": "Total Liabilities / Total Equity", "Value": f"{debt_to_equity:.2f}x", "Interpretation": f"{debt_to_equity:.2f}x - reliance on external vs internal funding"},
        {"Category": "Leverage", "Ratio": "Interest Coverage", "Formula": "EBIT / Interest Expense", "Value": f"{interest_coverage:.2f}x", "Interpretation": f"{interest_coverage:.2f}x - ability to pay interest (negative means operating loss)"}
    ]
    
    return pd.DataFrame(rows)

