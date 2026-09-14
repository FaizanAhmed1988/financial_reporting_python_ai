"""
src/coa_mapper.py
=================
UP2 — Chart of Accounts mapping for uploaded files.

Takes a column-mapped upload (produced by UP1's file_upload.py) and compares its
account codes against the platform's existing classified Chart of Accounts
(`data/processed/coa_classified.csv`, or the in-memory equivalent the dashboard
already computes). Every account in the upload lands in exactly one bucket:

    Matched   — code exists in the reference COA and is already classified.
    New       — code is absent from the reference COA, but the user has
                previously confirmed a category for it (remembered mapping).
    Unmapped  — code is absent from the reference COA with no confirmed
                category, or the row carries no account code at all.
                These are surfaced as "Mapping Required".
    Duplicate — code appears more than once where uniqueness is expected
                (COA / TB). Tracked as a flag alongside the bucket above,
                since a duplicate is also either Matched, New or Unmapped.

ARCHITECTURE COMPLIANCE
-----------------------
- NO streamlit import. This module is pure logic so it can be unit-tested
  headlessly; all rendering lives in `src/file_upload.py`.
- NO hardcoded account codes. The reference COA drives every decision.
- NO auto-assignment. An account the reference COA does not know is NEVER
  given a category by the system — it is returned as "Mapping Required" for a
  human to resolve. Remembered mappings are replayed only because a user
  confirmed them previously; they are labelled with their provenance.
- NO second classification system. The 7 manual categories translate into the
  engine's own canonical fields via CATEGORY_TO_ENGINE, so UP3 can hand
  confirmed accounts to account_classifier.py's schema without a parallel
  vocabulary.

PERSISTENCE
-----------
User-confirmed mappings are stored in `data/processed/user_coa_mappings.json`:

    {
      "version": 1,
      "updated_at": "2026-09-14T12:00:00+00:00",
      "sources": {
        "general_ledger::gl_q1.xlsx": {
          "file_name": "gl_q1.xlsx",
          "slot": "general_ledger",
          "accounts": {
            "7300": {"category": "Expense", "account_name": "Marketing",
                     "confirmed_at": "..."}
          }
        }
      },
      "global": {
        "7300": {"category": "Expense", "account_name": "Marketing",
                 "confirmed_at": "...", "source_key": "general_ledger::gl_q1.xlsx"}
      }
    }

`sources` gives exact recall for repeat uploads of the same file/slot.
`global` is a cross-source fallback so a code confirmed once is offered again
elsewhere — still flagged for confirmation, never silently applied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

# ============================================================
# 1. PATHS & VOCABULARY
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_COA_PATH = PROJECT_ROOT / "data" / "processed" / "coa_classified.csv"
USER_MAPPINGS_PATH = PROJECT_ROOT / "data" / "processed" / "user_coa_mappings.json"

STORE_VERSION = 1

#: Shown in the category dropdown for anything the system will not guess.
MAPPING_REQUIRED = "— Mapping Required —"

#: The 7 manual categories a user may assign to an unknown account.
MANUAL_CATEGORIES: List[str] = [
    "Asset",
    "Liability",
    "Equity",
    "Revenue",
    "COGS",
    "Expense",
    "Other",
]

#: Full dropdown option list (index 0 is the "not yet decided" sentinel).
CATEGORY_OPTIONS: List[str] = [MAPPING_REQUIRED] + MANUAL_CATEGORIES

#: Translation into account_classifier.py's canonical output fields.
#: Consumed by UP3 — keeps the manual vocabulary and the engine vocabulary in
#: one place instead of letting a second classification scheme grow.
CATEGORY_TO_ENGINE: Dict[str, Dict[str, Optional[str]]] = {
    "Asset":     {"financial_statement": "Balance Sheet",
                  "bs_category": "Assets",      "pl_category": None},
    "Liability": {"financial_statement": "Balance Sheet",
                  "bs_category": "Liabilities", "pl_category": None},
    "Equity":    {"financial_statement": "Balance Sheet",
                  "bs_category": "Equity",      "pl_category": None},
    "Revenue":   {"financial_statement": "Income Statement",
                  "bs_category": None,          "pl_category": "Revenue"},
    "COGS":      {"financial_statement": "Income Statement",
                  "bs_category": None,          "pl_category": "Cost of Sales"},
    "Expense":   {"financial_statement": "Income Statement",
                  "bs_category": None,          "pl_category": "Operating Expenses"},
    # "Other" deliberately maps to nothing — it records that a human looked at
    # the account and declined to place it. UP3 must not post it to a statement.
    "Other":     {"financial_statement": None,
                  "bs_category": None,          "pl_category": None},
}

# Bucket labels
STATUS_MATCHED = "Matched"
STATUS_NEW = "New"
STATUS_UNMAPPED = "Unmapped"

#: Slots where one account code must appear at most once. A General Ledger
#: repeats codes by design (one row per transaction), so duplicates there are
#: not a finding.
SLOTS_EXPECTING_UNIQUE_ACCOUNTS: Set[str] = {
    "chart_of_accounts",
    "trial_balance",
    "opening_trial_balance",
}

#: Placeholder shown for rows that carry no account code at all.
MISSING_CODE_LABEL = "— missing —"


# ============================================================
# 2. NORMALISATION HELPERS
# ============================================================

def normalise_code(value: Any) -> str:
    """
    Normalise an account code to a comparable string.

    Excel round-trips frequently turn the code 1000 into the string "1000.0";
    without this, every account would be reported as New. Returns "" for
    blank / NaN so callers can treat it as a missing code.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).strip()
    if text.lower() in ("", "nan", "none", "<na>"):
        return ""

    # "1000.0" -> "1000", but leave genuine decimal-bearing codes like "10.25"
    if text.endswith(".0") and text[:-2].replace("-", "").isdigit():
        text = text[:-2]
    return text


def make_source_key(file_name: str, slot: str) -> str:
    """
    Stable identifier for "the same source" — a given file uploaded into a
    given slot. Case- and whitespace-insensitive so re-uploading `GL_Q1.xlsx`
    still recalls mappings saved under `gl_q1.xlsx`.
    """
    return f"{(slot or 'unknown').strip().lower()}::{(file_name or 'unnamed').strip().lower()}"


# ============================================================
# 3. REFERENCE COA
# ============================================================

def load_reference_coa(
    in_memory: Optional[pd.DataFrame] = None,
    path: Optional[Path] = None,
) -> Tuple[pd.DataFrame, bool, str]:
    """
    Resolve the reference Chart of Accounts.

    Resolution order:
      1. `in_memory` — the classified COA the dashboard already holds.
      2. `data/processed/coa_classified.csv` on disk.
      3. Nothing — returns an empty frame with available=False.

    Returns
    -------
    (reference_df, available, message)
        `available` is False when no reference COA could be found, in which
        case callers must degrade honestly rather than treating every account
        in the upload as new.
    """
    if in_memory is not None and not in_memory.empty:
        return in_memory.copy(), True, "Reference COA: in-memory classified COA from the live engine."

    csv_path = Path(path) if path is not None else REFERENCE_COA_PATH
    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, dtype=str)
            return df, True, f"Reference COA: `{csv_path.name}` ({len(df)} accounts)."
        except Exception as exc:  # pragma: no cover - defensive
            return (pd.DataFrame(), False,
                    f"Reference COA could not be read from `{csv_path.name}`: {exc}")

    return (
        pd.DataFrame(),
        False,
        "Reference COA unavailable — neither a live classified COA nor "
        f"`{csv_path}` was found. Account comparison is degraded: accounts "
        "cannot be confirmed as Matched, so all are reported as requiring review.",
    )


def _clean_label(value: Any) -> Optional[str]:
    """
    Return a trimmed string, or None for NaN / blank / null-ish values.

    Necessary because a missing cell arrives as float('nan'), which is TRUTHY —
    so `row.get("bs_category") or row.get("pl_category")` would stop at the NaN
    and silently drop every Income Statement classification.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return None if text.lower() in ("", "nan", "none", "<na>") else text


def _reference_lookup(reference_coa: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """Build {normalised_code: {account_name, category, grouping_label}}."""
    if reference_coa is None or reference_coa.empty or "account_code" not in reference_coa.columns:
        return {}

    lookup: Dict[str, Dict[str, Any]] = {}
    for _, row in reference_coa.iterrows():
        code = normalise_code(row.get("account_code"))
        if not code or code in lookup:
            continue
        # Prefer the engine's own classification labels when present. Balance
        # Sheet accounts carry bs_category; Income Statement ones pl_category.
        category = _clean_label(row.get("bs_category")) or _clean_label(row.get("pl_category"))
        lookup[code] = {
            "account_name": _clean_label(row.get("account_name")),
            "category": category,
            "grouping_label": _clean_label(row.get("grouping_label")),
        }
    return lookup


# ============================================================
# 4. PERSISTENT USER MAPPINGS
# ============================================================

def _empty_store() -> Dict[str, Any]:
    return {"version": STORE_VERSION, "updated_at": None, "sources": {}, "global": {}}


def load_user_mappings(path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load the persisted user-confirmed mappings. Returns an empty store when the
    file is absent or unreadable — a corrupt store must never block an upload.
    """
    store_path = Path(path) if path is not None else USER_MAPPINGS_PATH
    if not store_path.exists():
        return _empty_store()
    try:
        with open(store_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()
    data.setdefault("version", STORE_VERSION)
    data.setdefault("sources", {})
    data.setdefault("global", {})
    data.setdefault("updated_at", None)
    return data


def save_user_mappings(store: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Persist the store, creating `data/processed/` if it does not exist."""
    store_path = Path(path) if path is not None else USER_MAPPINGS_PATH
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = dict(store)
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=2, ensure_ascii=False)
    return store_path


def get_remembered(
    store: Dict[str, Any],
    source_key: str,
    code: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Look up a previously confirmed category for an account code.

    Returns (category, scope) where scope is "source" (same file + slot) or
    "global" (confirmed against a different source), or (None, None).
    """
    code = normalise_code(code)
    if not code:
        return None, None

    source_entry = (store.get("sources") or {}).get(source_key) or {}
    hit = (source_entry.get("accounts") or {}).get(code)
    if hit and hit.get("category") in MANUAL_CATEGORIES:
        return hit["category"], "source"

    hit = (store.get("global") or {}).get(code)
    if hit and hit.get("category") in MANUAL_CATEGORIES:
        return hit["category"], "global"

    return None, None


def confirm_mappings(
    store: Dict[str, Any],
    source_key: str,
    slot: str,
    file_name: str,
    decisions: Dict[str, str],
    account_names: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Record user-confirmed category decisions into the store (in memory).

    `decisions` is {account_code: category}. Entries whose category is not one
    of MANUAL_CATEGORIES (i.e. still "Mapping Required") are ignored, so an
    unresolved account is never persisted as a decision.

    Returns (updated_store, number_of_accounts_written).
    """
    account_names = account_names or {}
    store = json.loads(json.dumps(store))  # deep copy; store is plain JSON data
    store.setdefault("sources", {})
    store.setdefault("global", {})

    entry = store["sources"].setdefault(
        source_key, {"file_name": file_name, "slot": slot, "accounts": {}}
    )
    entry["file_name"] = file_name
    entry["slot"] = slot
    entry.setdefault("accounts", {})

    stamp = datetime.now(timezone.utc).isoformat()
    written = 0
    for raw_code, category in (decisions or {}).items():
        code = normalise_code(raw_code)
        if not code or category not in MANUAL_CATEGORIES:
            continue
        record = {
            "category": category,
            "account_name": account_names.get(code),
            "confirmed_at": stamp,
        }
        entry["accounts"][code] = record
        store["global"][code] = {**record, "source_key": source_key}
        written += 1

    return store, written


def known_account_codes(
    reference_coa: pd.DataFrame,
    store: Optional[Dict[str, Any]] = None,
    source_key: Optional[str] = None,
) -> Set[str]:
    """
    Every account code the platform can currently place: the reference COA plus
    any user-confirmed mappings. Used by validation_engine to decide whether an
    account code in an upload is resolvable.
    """
    codes = set(_reference_lookup(reference_coa).keys())
    if store:
        if source_key:
            entry = (store.get("sources") or {}).get(source_key) or {}
            codes |= {normalise_code(c) for c in (entry.get("accounts") or {})}
        codes |= {normalise_code(c) for c in (store.get("global") or {})}
    codes.discard("")
    return codes


# ============================================================
# 5. COMPARISON
# ============================================================

@dataclass
class CoaComparison:
    """Result of comparing an uploaded dataset against the reference COA."""
    table: pd.DataFrame
    summary: Dict[str, int] = field(default_factory=dict)
    expects_unique: bool = False
    reference_available: bool = True
    reference_message: str = ""
    missing_code_rows: int = 0

    @property
    def requires_mapping(self) -> pd.DataFrame:
        """Accounts the user still has to categorise (excludes missing-code row)."""
        if self.table.empty:
            return self.table
        mask = (
            (self.table["Status"] == STATUS_UNMAPPED)
            & (self.table["Account Code"] != MISSING_CODE_LABEL)
        )
        return self.table[mask]

    @property
    def is_fully_mapped(self) -> bool:
        return self.requires_mapping.empty


def build_coa_comparison(
    df_mapped: pd.DataFrame,
    slot: str,
    reference_coa: Optional[pd.DataFrame] = None,
    store: Optional[Dict[str, Any]] = None,
    source_key: str = "",
    reference_available: bool = True,
    reference_message: str = "",
) -> CoaComparison:
    """
    Compare the account codes in a mapped upload against the reference COA.

    Parameters
    ----------
    df_mapped   : upload with canonical column names (from UP1's override step).
    slot        : session slot, e.g. "general_ledger" / "trial_balance".
    reference_coa : classified COA to compare against (see load_reference_coa).
    store       : persisted user mappings (see load_user_mappings).
    source_key  : identifier from make_source_key(), for remembered lookups.

    Returns
    -------
    CoaComparison — one row per distinct account code, plus (when present) a
    single summary row for rows carrying no account code at all.
    """
    reference_coa = reference_coa if reference_coa is not None else pd.DataFrame()
    store = store or _empty_store()
    lookup = _reference_lookup(reference_coa)
    expects_unique = slot in SLOTS_EXPECTING_UNIQUE_ACCOUNTS

    empty_summary = {
        STATUS_MATCHED: 0, STATUS_NEW: 0, STATUS_UNMAPPED: 0,
        "Duplicate": 0, "Total Accounts": 0, "Rows Without Account Code": 0,
    }

    if df_mapped is None or df_mapped.empty or "account_code" not in df_mapped.columns:
        return CoaComparison(
            table=pd.DataFrame(columns=[
                "Account Code", "Account Name", "Status", "Duplicate",
                "Occurrences", "Reference Category", "Assigned Category", "Mapping Source",
            ]),
            summary=empty_summary,
            expects_unique=expects_unique,
            reference_available=reference_available,
            reference_message=reference_message or (
                "No `account_code` column is mapped — COA comparison cannot run. "
                "Map an Account Code column above first."
                if df_mapped is not None and not df_mapped.empty else ""
            ),
        )

    codes = df_mapped["account_code"].map(normalise_code)
    missing_code_rows = int((codes == "").sum())

    names_by_code: Dict[str, str] = {}
    if "account_name" in df_mapped.columns:
        for code, name in zip(codes, df_mapped["account_name"]):
            if code and code not in names_by_code:
                text = "" if name is None else str(name).strip()
                if text and text.lower() not in ("nan", "none", "<na>"):
                    names_by_code[code] = text

    occurrences = codes[codes != ""].value_counts()

    rows: List[Dict[str, Any]] = []
    for code in occurrences.index:
        count = int(occurrences[code])
        ref = lookup.get(code)
        remembered_category, remembered_scope = get_remembered(store, source_key, code)

        if ref is not None:
            status = STATUS_MATCHED
            assigned = ref.get("category") or "—"
            mapping_source = "Reference COA"
        elif remembered_category:
            status = STATUS_NEW
            assigned = remembered_category
            mapping_source = (
                "Remembered — this source" if remembered_scope == "source"
                else "Remembered — another source (confirm)"
            )
        else:
            # Never guessed. A human decides.
            status = STATUS_UNMAPPED
            assigned = MAPPING_REQUIRED
            mapping_source = "Mapping Required"

        rows.append({
            "Account Code":       code,
            "Account Name":       names_by_code.get(code) or (ref or {}).get("account_name") or "—",
            "Status":             status,
            "Duplicate":          "Yes" if (expects_unique and count > 1) else "No",
            "Occurrences":        count,
            "Reference Category": (ref or {}).get("category") or "—",
            "Assigned Category":  assigned,
            "Mapping Source":     mapping_source,
        })

    if missing_code_rows:
        rows.append({
            "Account Code":       MISSING_CODE_LABEL,
            "Account Name":       "—",
            "Status":             STATUS_UNMAPPED,
            "Duplicate":          "No",
            "Occurrences":        missing_code_rows,
            "Reference Category": "—",
            "Assigned Category":  "—",
            "Mapping Source":     "Row has no account code — cannot be mapped",
        })

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(
            ["Status", "Account Code"],
            key=lambda s: s.map(
                {STATUS_UNMAPPED: 0, STATUS_NEW: 1, STATUS_MATCHED: 2}
            ) if s.name == "Status" else s,
        ).reset_index(drop=True)

    summary = {
        STATUS_MATCHED: int((table["Status"] == STATUS_MATCHED).sum()) if not table.empty else 0,
        STATUS_NEW: int((table["Status"] == STATUS_NEW).sum()) if not table.empty else 0,
        STATUS_UNMAPPED: int((table["Status"] == STATUS_UNMAPPED).sum()) if not table.empty else 0,
        "Duplicate": int((table["Duplicate"] == "Yes").sum()) if not table.empty else 0,
        "Total Accounts": int(len(occurrences)),
        "Rows Without Account Code": missing_code_rows,
    }

    return CoaComparison(
        table=table,
        summary=summary,
        expects_unique=expects_unique,
        reference_available=reference_available,
        reference_message=reference_message,
        missing_code_rows=missing_code_rows,
    )
