"""
src/column_mapper.py
====================
Interactive column-mapping helpers for the Upload Feature.
Extends ConfigurableColumnMapper from data_loader.py for a Streamlit UI context.
Does NOT create a second, independent mapping system.
"""

from __future__ import annotations
from typing import Dict, List, Optional
import pandas as pd

from src.data_loader import DEFAULT_COLUMN_ALIASES


# Canonical fields that are required per detected file type
REQUIRED_FIELDS_BY_TYPE: Dict[str, List[str]] = {
    "General Ledger":        ["account_code", "debit", "credit"],
    "Trial Balance":         ["account_code", "closing_debit", "closing_credit"],
    "Chart of Accounts":     ["account_code", "account_name", "account_type"],
    "Opening Trial Balance": ["account_code", "opening_debit", "opening_credit"],
    "Bank Statement":        ["date", "bank_balance"],
    "Other / Unknown":       [],
}

ALL_CANONICAL_OPTIONS = ["— unmapped —"] + sorted(DEFAULT_COLUMN_ALIASES.keys())


def get_required_canonical_columns(file_type: str) -> List[str]:
    """Return the list of required canonical column names for a given file type."""
    return REQUIRED_FIELDS_BY_TYPE.get(file_type, [])


def generate_mapping_dataframe(
    df: pd.DataFrame,
    rename_map: Dict[str, str],   # {source_col: canonical_col} from file_detector
    file_type: str,
) -> pd.DataFrame:
    """
    Build a mapping table DataFrame ready for display in st.data_editor.

    Returns a DataFrame with columns:
      Source Column  | Auto-Detected Mapping | Required | Status
    """
    required = set(get_required_canonical_columns(file_type))
    already_mapped_canonical = set(rename_map.values())

    rows = []
    for source_col in df.columns:
        auto_mapped = rename_map.get(source_col, "— unmapped —")
        is_required = auto_mapped in required
        if auto_mapped == "— unmapped —":
            status = "⚠️ Unmapped"
        elif is_required:
            status = "✅ Required — matched"
        else:
            status = "✅ Matched"

        rows.append({
            "Source Column":         str(source_col),
            "Auto-Detected Mapping": auto_mapped,
            "Override Mapping":      auto_mapped,   # Editable column in data_editor
            "Required":              "Yes" if is_required else "No",
            "Status":                status,
        })

    # Add a note for required fields that are completely unmatched
    unmatched_required = required - already_mapped_canonical
    for canon in sorted(unmatched_required):
        rows.append({
            "Source Column":         "— not found —",
            "Auto-Detected Mapping": "— unmapped —",
            "Override Mapping":      canon,
            "Required":              "Yes",
            "Status":                "❌ Required — NOT FOUND in file",
        })

    return pd.DataFrame(rows)


def apply_user_overrides(
    df: pd.DataFrame,
    mapping_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply user-edited overrides from the mapping_df back onto df to produce
    a renamed DataFrame with canonical column names.
    Stored in session_state for use in Phase 3 processing.
    """
    override_map: Dict[str, str] = {}
    for _, row in mapping_df.iterrows():
        source = row["Source Column"]
        override = row["Override Mapping"]
        if (
            source != "— not found —"
            and override
            and override != "— unmapped —"
        ):
            override_map[source] = override

    renamed = df.rename(columns=override_map)
    return renamed, override_map
