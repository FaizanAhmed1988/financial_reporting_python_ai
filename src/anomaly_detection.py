"""
src/anomaly_detection.py
========================
AI Anomaly Detection module using Isolation Forest.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from typing import Dict, Any

def run_ml_anomaly_detection(gl: pd.DataFrame) -> Dict[str, Any]:
    """
    Business Problem: Identifying statistically unusual transactions in the GL that 
    may require audit review (e.g., potential fraud, keying errors).
    
    Model: Scikit-learn's Isolation Forest (Unsupervised).
    Why: We lack labeled fraud data. Isolation Forest works well for isolating 
    anomalies in high-dimensional or scaled continuous data without needing training labels.
    
    Feature Engineering:
    - Transaction amount (absolute sum of debit/credit).
    - To prevent flagging normal large transactions in high-volume accounts (like Cash), 
      we scale the amounts per account using Z-score standardization.
    """
    df = gl.copy()
    df["amount"] = df["debit"] + df["credit"]
    
    # Feature Engineering: Scale amounts within each account
    # We only scale accounts with at least 3 transactions to avoid division by zero or over-fitting
    scaled_amounts = []
    
    for acct, group in df.groupby("account_code"):
        if len(group) >= 3:
            mean = group["amount"].mean()
            std = group["amount"].std()
            if std > 0:
                scaled = (group["amount"] - mean) / std
            else:
                scaled = np.zeros(len(group))
        else:
            scaled = np.zeros(len(group)) # Ignore for anomaly detection if too small
            
        scaled_amounts.extend(scaled.tolist())
        
    # We must preserve order. groupby might have changed order. Let's do it safely:
    df["scaled_amount"] = 0.0
    for acct, group in df.groupby("account_code"):
        if len(group) >= 3:
            std = group["amount"].std()
            mean = group["amount"].mean()
            if std > 0:
                df.loc[group.index, "scaled_amount"] = (group["amount"] - mean) / std

    # Filter to items we can actually model
    model_df = df[df["scaled_amount"] != 0.0].copy()
    
    if model_df.empty:
        return {
            "model_explanation": "Isolation Forest (Unsupervised)",
            "findings": pd.DataFrame(),
            "count": 0,
            "message": "Not enough data points with variance to run ML detection."
        }
    
    # Reshape for sklearn
    X = model_df[["scaled_amount"]].values
    
    # Train/Predict
    # contamination=0.02 means we expect roughly 2% of the data to be anomalous
    clf = IsolationForest(contamination=0.02, random_state=42)
    model_df["anomaly_score"] = clf.fit_predict(X)
    
    # -1 indicates anomaly
    anomalies = model_df[model_df["anomaly_score"] == -1].copy()
    
    # Business interpretation
    anomalies["Business Interpretation"] = "Potential Anomaly - Statistically isolated transaction amount relative to account history"
    
    return {
        "model_explanation": "Isolation Forest (Unsupervised). Features: Per-account Z-score scaled transaction amounts. Training: Fit directly on GL (no train/test split). Evaluation: Cross-referenced manually with statistical outliers.",
        "findings": anomalies[["txn_no", "date", "account_code", "amount", "narration", "Business Interpretation"]],
        "count": len(anomalies),
        "message": "AI model execution complete."
    }
