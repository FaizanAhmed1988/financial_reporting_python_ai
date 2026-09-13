"""
src/forecasting.py
==================
Basic Trend Extrapolation for Revenue, Expenses, and Cash.
Explicitly acknowledges the 3-month data limitation.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any

def generate_forecast(tb: pd.DataFrame, coa_classified: pd.DataFrame, gl: pd.DataFrame) -> Dict[str, Any]:
    """
    Limitation: Only 3 months of data available (Jan, Feb, Mar 2026).
    Methodology: Simple linear trend or moving average. We will group GL transactions by month.
    """
    df = gl.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.month
    
    # Let's map accounts to categories
    acct_mapping = coa_classified.set_index("account_code")[["pl_category", "bs_category"]].to_dict("index")
    
    def get_cat(code, cat_type):
        return acct_mapping.get(code, {}).get(cat_type, None)
        
    df["pl_category"] = df["account_code"].apply(lambda x: get_cat(x, "pl_category"))
    df["bs_category"] = df["account_code"].apply(lambda x: get_cat(x, "bs_category"))
    
    monthly_data = []
    
    for month in [1, 2, 3]:
        m_df = df[df["month"] == month]
        
        # Revenue is credit normal
        rev_df = m_df[m_df["pl_category"] == "Revenue"]
        revenue = (rev_df["credit"] - rev_df["debit"]).sum()
        
        # Expenses (COGS + Opex) debit normal
        exp_df = m_df[m_df["pl_category"].isin(["Cost of Sales", "Operating Expenses", "Finance Costs"])]
        expenses = (exp_df["debit"] - exp_df["credit"]).sum()
        
        # Cash (movement) debit normal
        cash_df = m_df[m_df["bs_category"] == "Cash & Cash Equivalents"]
        cash_movement = (cash_df["debit"] - cash_df["credit"]).sum()
        
        monthly_data.append({
            "Month": month,
            "Revenue": revenue,
            "Expenses": expenses,
            "Cash Movement": cash_movement
        })
        
    m_df_agg = pd.DataFrame(monthly_data)
    
    # Forecast Month 4 (April) using simple average of Month 1-3
    if len(m_df_agg) == 3:
        forecast_rev = m_df_agg["Revenue"].mean()
        forecast_exp = m_df_agg["Expenses"].mean()
        forecast_cash = m_df_agg["Cash Movement"].mean()
        
        # Backtesting: forecast Month 3 using Month 1 & 2
        f3_rev = m_df_agg.loc[0:1, "Revenue"].mean()
        actual_m3_rev = m_df_agg.loc[2, "Revenue"]
        mae_rev = abs(f3_rev - actual_m3_rev)
    else:
        forecast_rev, forecast_exp, forecast_cash, mae_rev = 0, 0, 0, 0
        
    forecast_results = pd.DataFrame([{
        "Metric": "Revenue",
        "Month 1 (Actual)": m_df_agg.loc[0, "Revenue"] if len(m_df_agg) > 0 else 0,
        "Month 2 (Actual)": m_df_agg.loc[1, "Revenue"] if len(m_df_agg) > 1 else 0,
        "Month 3 (Actual)": m_df_agg.loc[2, "Revenue"] if len(m_df_agg) > 2 else 0,
        "Month 4 (Forecast)": forecast_rev,
        "MAE (Month 3 Backtest)": mae_rev
    }, {
        "Metric": "Expenses",
        "Month 1 (Actual)": m_df_agg.loc[0, "Expenses"] if len(m_df_agg) > 0 else 0,
        "Month 2 (Actual)": m_df_agg.loc[1, "Expenses"] if len(m_df_agg) > 1 else 0,
        "Month 3 (Actual)": m_df_agg.loc[2, "Expenses"] if len(m_df_agg) > 2 else 0,
        "Month 4 (Forecast)": forecast_exp,
        "MAE (Month 3 Backtest)": abs(m_df_agg.loc[0:1, "Expenses"].mean() - m_df_agg.loc[2, "Expenses"]) if len(m_df_agg)==3 else 0
    }])
    
    return {
        "limitation_warning": "Only 3 months of data available — this forecast is illustrative of the METHODOLOGY only, not a reliable prediction. A production system would need at least 12-24 months of history for meaningful forecasting.",
        "forecast_df": forecast_results
    }
