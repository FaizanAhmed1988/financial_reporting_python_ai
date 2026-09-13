"""
src/scenario_analysis.py
========================
Scenario Analysis Engine.
Calculates Base, Best, and Worst case scenarios based on adjustable assumptions.
"""

import pandas as pd
from typing import Dict, Any

def run_scenarios(pl_metrics: Dict[str, Any], bs_metrics: Dict[str, Any], 
                  bs_df: pd.DataFrame, days_in_period: int = 90,
                  assumptions: Dict[str, Dict[str, float]] = None) -> pd.DataFrame:
    
    # Default illustrative assumptions if none provided
    if assumptions is None:
        assumptions = {
            "Base Case": {"rev_growth": 0.0, "cogs_pct": 0.315, "opex_pct": 1.25, "dso": 68, "dpo": 1826},
            "Best Case": {"rev_growth": 0.10, "cogs_pct": 0.30, "opex_pct": 1.10, "dso": 45, "dpo": 90},
            "Worst Case": {"rev_growth": -0.10, "cogs_pct": 0.35, "opex_pct": 1.40, "dso": 90, "dpo": 30}
        }
        
    actual_rev = pl_metrics.get("Total Revenue", 0)
    actual_cogs = pl_metrics.get("Total COGS", 0)
    
    def get_bs_value(line_item_name: str) -> float:
        row = bs_df[bs_df["Line Item"].str.strip() == line_item_name]
        if not row.empty:
            return float(row.iloc[0]["Amount"])
        return 0.0

    actual_ca = get_bs_value("Total Current Assets")
    actual_cl = get_bs_value("Total Current Liabilities")
    actual_ar = get_bs_value("Trade Receivables")
    actual_ap = get_bs_value("Trade Payables")
    actual_cash = get_bs_value("Cash & Cash Equivalents")
    
    # Base Current Ratio calculation parts
    # CR = CA / CL. If we change AR and AP, we change CA and CL.
    # Cash flow impact = (Old AR - New AR) + (New AP - Old AP)
    # This ignores other working capital movements for simplicity of the scenario demo.
    
    scenario_results = []
    
    for case_name, params in assumptions.items():
        # P&L Impacts
        rev = actual_rev * (1 + params["rev_growth"])
        cogs = rev * params["cogs_pct"]
        gp = rev - cogs
        opex = rev * params["opex_pct"]
        ebit = gp - opex
        finance = pl_metrics.get("Total Finance Costs", 0) # assume fixed
        net_profit = ebit - finance
        
        # Working Capital Impacts
        # New AR = (DSO / days) * Revenue
        new_ar = (params["dso"] / days_in_period) * rev
        # New AP = (DPO / days) * COGS
        new_ap = (params["dpo"] / days_in_period) * cogs
        
        # Cash impact = (Decrease in AR) + (Increase in AP) + Net Profit (assuming cash profit = net profit for this simplified model)
        # To be precise on WC: cash flow from ops impact = Delta AR + Delta AP + Delta Net Profit
        delta_ar = actual_ar - new_ar
        delta_ap = new_ap - actual_ap
        delta_np = net_profit - pl_metrics.get("Net Profit", 0)
        
        # Simplified simulated cash
        sim_cash = actual_cash + delta_ar + delta_ap + delta_np
        
        new_ca = actual_ca - actual_ar + new_ar + (sim_cash - actual_cash)
        new_cl = actual_cl - actual_ap + new_ap
        
        current_ratio = new_ca / new_cl if new_cl else 0
        
        scenario_results.append({
            "Scenario": case_name,
            "Revenue": rev,
            "Gross Profit": gp,
            "Operating Profit": ebit,
            "Net Profit": net_profit,
            "Simulated Cash": sim_cash,
            "Current Ratio": f"{current_ratio:.2f}x"
        })
        
    return pd.DataFrame(scenario_results)
