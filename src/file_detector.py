"""
src/file_detector.py
====================
Detects the accounting file type (General Ledger, Trial Balance, Chart of Accounts)
from a DataFrame's columns by leveraging the existing ConfigurableColumnMapper.

Design principle: extends — not replaces — data_loader.py's mapper infrastructure.
"""

from __future__ import annotations
from typing import Dict, List, Tuple
import pandas as pd

# Column fingerprints: which canonical columns are diagnostic for each type
FILE_TYPE_SIGNATURES: Dict[str, Dict] = {
    "General Ledger": {
        "required":    ["account_code", "debit", "credit"],
        "supporting":  ["txn_no", "date", "voucher_no", "narration", "account_name"],
        "description": "Transaction-level journal entries with Debit/Credit amounts.",
    },
    "Trial Balance": {
        "required":    ["account_code", "closing_debit", "closing_credit"],
        "supporting":  ["account_name", "opening_debit", "opening_credit",
                        "period_debit", "period_credit"],
        "description": "Account-level summary with opening and closing debit/credit balances.",
    },
    "Chart of Accounts": {
        "required":    ["account_code", "account_name", "account_type"],
        "supporting":  ["normal_balance"],
        "description": "Master list of account codes, names, types, and normal balances.",
    },
    "Opening Trial Balance": {
        "required":    ["account_code", "opening_debit", "opening_credit"],
        "supporting":  ["account_name", "period_debit", "period_credit"],
        "description": "Opening period balances only.",
    },
    "Other / Unknown": {
        "required":    [],
        "supporting":  [],
        "description": "File does not match any known accounting structure.",
    },
}


def detect_file_type(
    df: pd.DataFrame,
    mapper,  # ConfigurableColumnMapper instance
    user_hint: str = "Auto Detect",
) -> Tuple[str, float, Dict[str, str]]:
    """
    Detect the accounting role of a DataFrame.

    Parameters
    ----------
    df          : The raw (unmapped) DataFrame.
    mapper      : A ConfigurableColumnMapper instance from data_loader.py.
    user_hint   : Optional user-selected hint ("Auto Detect", "General Ledger", etc.).

    Returns
    -------
    (detected_type, confidence_score, rename_map)
      detected_type    : str — one of the FILE_TYPE_SIGNATURES keys
      confidence_score : float 0.0–1.0
      rename_map       : {source_col: canonical_col} for all matched columns
    """
    # Use the existing mapper to identify matched columns
    rename_map = mapper.build_rename_map(list(df.columns))
    matched_canonical = set(rename_map.values())

    if user_hint != "Auto Detect" and user_hint in FILE_TYPE_SIGNATURES:
        # User forced a type — still calculate confidence score
        sig = FILE_TYPE_SIGNATURES[user_hint]
        score = _score(sig, matched_canonical)
        return user_hint, score, rename_map

    # Auto detect: score every type and pick the best
    scores: List[Tuple[str, float]] = []
    for ftype, sig in FILE_TYPE_SIGNATURES.items():
        if ftype == "Other / Unknown":
            continue
        score = _score(sig, matched_canonical)
        scores.append((ftype, score))

    if not scores:
        return "Other / Unknown", 0.0, rename_map

    best_type, best_score = max(scores, key=lambda x: x[1])

    if best_score < 0.3:
        return "Other / Unknown", best_score, rename_map

    return best_type, best_score, rename_map


def _score(signature: Dict, matched_canonical: set) -> float:
    """
    Compute a confidence score between 0.0 and 1.0 for a given file type signature.
    Required columns are weighted 3x vs supporting columns.
    """
    required   = signature["required"]
    supporting = signature["supporting"]

    if not required and not supporting:
        return 0.0

    req_hits  = sum(1 for c in required   if c in matched_canonical)
    sup_hits  = sum(1 for c in supporting if c in matched_canonical)

    max_score = len(required) * 3 + len(supporting)
    raw_score = req_hits * 3 + sup_hits

    if max_score == 0:
        return 0.0

    return round(min(raw_score / max_score, 1.0), 4)


def get_file_quality_status(df: pd.DataFrame, rename_map: Dict[str, str]) -> str:
    """
    Returns a simple data quality label based on null-rate and column match rate.
    """
    if df.empty:
        return "⚠️ Empty file"

    null_rate = df.isnull().mean().mean()
    match_rate = len(rename_map) / max(len(df.columns), 1)

    if null_rate > 0.5:
        return "⚠️ High null rate — data may need cleaning"
    elif match_rate < 0.2:
        return "⚠️ Low column recognition — manual mapping required"
    elif match_rate >= 0.7 and null_rate < 0.1:
        return "✅ Clean — high column recognition"
    else:
        return "⚠️ Partial match — review mapping below"
