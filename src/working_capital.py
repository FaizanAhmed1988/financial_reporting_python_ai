"""
src/working_capital.py
======================
Deep dive into working capital metrics and operating cycle.
"""

import pandas as pd
from typing import Dict, Any

def analyze_working_capital(pl_metrics: Dict[str, Any], bs_df: pd.DataFrame, days_in_period: int = 90) -> pd.DataFrame:
    
    def get_bs_value(line_item_name: str) -> float:
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
    
    revenue = pl_metrics.get("Total Revenue", 0)
    cogs = pl_metrics.get("Total COGS", 0)
    
    nwc = current_assets - current_liabilities
    current_ratio = current_assets / current_liabilities if current_liabilities else 0
    quick_ratio = (current_assets - inventory) / current_liabilities if current_liabilities else 0
    
    dso = (ar / revenue) * days_in_period if revenue else 0
    dpo = (ap / cogs) * days_in_period if cogs else 0
    dio = (inventory / cogs) * days_in_period if cogs else 0
    ccc = dio + dso - dpo
    
    rows = [
        {"Metric": "Total Current Assets", "Amount/Value": f"{current_assets:,.0f}"},
        {"Metric": "Total Current Liabilities", "Amount/Value": f"{current_liabilities:,.0f}"},
        {"Metric": "Net Working Capital", "Amount/Value": f"{nwc:,.0f}"},
        {"Metric": "Current Ratio", "Amount/Value": f"{current_ratio:.2f}x"},
        {"Metric": "Quick Ratio", "Amount/Value": f"{quick_ratio:.2f}x"},
        {"Metric": "", "Amount/Value": ""},
        {"Metric": "AR Days (DSO)", "Amount/Value": f"{dso:.0f} days"},
        {"Metric": "Inventory Days (DIO)", "Amount/Value": f"{dio:.0f} days"},
        {"Metric": "AP Days (DPO)", "Amount/Value": f"{dpo:.0f} days"},
        {"Metric": "Cash Conversion Cycle (CCC)", "Amount/Value": f"{ccc:.0f} days"}
    ]
    
    return pd.DataFrame(rows)

