"""
src/data_loader.py
==================
Enterprise-grade configurable data loader for the Financial Reporting AI platform.

ARCHITECTURE PRINCIPLE
----------------------
Column names, sheet names, and account codes are NEVER hardcoded in business logic.
Instead, a ConfigurableColumnMapper translates any incoming column names (from any
file format / ERP export) to a fixed set of internal canonical field names.

The loader can be reconfigured at runtime to accept new file layouts without any
code changes -- just update the mapping config dict or pass a custom one.

CANONICAL INTERNAL FIELD NAMES
-------------------------------
  account_code   | account_name  | account_type  | normal_balance
  txn_no         | date          | voucher_no     | narration
  debit          | credit
  opening_debit  | opening_credit
  period_debit   | period_credit
  closing_debit  | closing_credit

SUPPORTED SHEET ROLES
---------------------
  coa   -> Chart of Accounts
  otb   -> Opening Trial Balance
  gl    -> General Ledger
  tb    -> Closing / Full Trial Balance
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)


# ============================================================
# 1. DEFAULT COLUMN MAPPING  (extend / override as needed)
# ============================================================

# Maps canonical internal name -> list of acceptable source column names
# Matching is case-insensitive and strips surrounding whitespace.
DEFAULT_COLUMN_ALIASES: Dict[str, List[str]] = {
    # --- Universal ---
    "account_code":    ["Account Code", "Acct No", "Account No", "Account Number",
                        "GL Code", "Code", "Acc Code", "Acct Code"],
    "account_name":    ["Account Name", "Account Description", "Description",
                        "Name", "Acc Name", "Acct Name"],
    "account_type":    ["Account Type", "Type", "Category", "Account Category",
                        "Classification", "Acct Type"],
    "normal_balance":  ["Normal Balance", "Dr/Cr", "Balance Type"],

    # --- GL-specific ---
    "txn_no":          ["Txn No", "Transaction No", "Txn ID", "Transaction ID",
                        "Entry No", "Journal No"],
    "date":            ["Date", "Transaction Date", "Txn Date", "Posting Date",
                        "GL Date", "Value Date"],
    "voucher_no":      ["Voucher No", "Voucher", "Ref", "Reference",
                        "Journal Ref", "Doc No", "Document No"],
    "narration":       ["Narration", "Description", "Particulars", "Memo",
                        "Details", "Remarks"],
    "debit":           ["Debit", "Dr", "Debit Amount", "Dr Amount", "Debit $"],
    "credit":          ["Credit", "Cr", "Credit Amount", "Cr Amount", "Credit $"],

    # --- TB-specific (Opening) ---
    "opening_debit":   ["Opening Debit", "Op Debit", "OB Debit", "Opening Dr"],
    "opening_credit":  ["Opening Credit", "Op Credit", "OB Credit", "Opening Cr"],

    # --- TB-specific (Period Movement) ---
    "period_debit":    ["Period Debit", "Movement Debit", "Activity Debit",
                        "Mvt Dr", "Period Dr"],
    "period_credit":   ["Period Credit", "Movement Credit", "Activity Credit",
                        "Mvt Cr", "Period Cr"],

    # --- TB-specific (Closing) ---
    "closing_debit":   ["Closing Debit", "Cl Debit", "CB Debit", "Closing Dr",
                        "Debit Balance"],
    "closing_credit":  ["Closing Credit", "Cl Credit", "CB Credit", "Closing Cr",
                        "Credit Balance"],
}

# Maps canonical sheet role -> list of acceptable sheet name fragments (case-insensitive)
DEFAULT_SHEET_ALIASES: Dict[str, List[str]] = {
    "coa": ["chart of accounts", "chart_of_accounts", "coa", "accounts list"],
    "otb": ["opening balances", "opening trial balance", "opening tb", "ob tb",
            "ob-tb", "opening_balances"],
    "gl":  ["general ledger", "general_ledger", "gl", "journal", "ledger"],
    "tb":  ["trial balance", "trial_balance", "closing balance", "tb"],
}


# ============================================================
# 2. CONFIGURABLE COLUMN MAPPER
# ============================================================

class ConfigurableColumnMapper:
    """
    Translates arbitrary source column names to canonical internal field names.
    Matching is case-insensitive and whitespace-normalised.

    Usage
    -----
    mapper = ConfigurableColumnMapper(custom_aliases={"debit": ["Dr Amount"]})
    df = mapper.rename_columns(df)
    missing = mapper.audit_missing_fields(df, required=["account_code", "debit", "credit"])
    """

    def __init__(self, custom_aliases: Optional[Dict[str, List[str]]] = None):
        # Merge custom aliases on top of defaults (custom wins)
        self.aliases: Dict[str, List[str]] = {**DEFAULT_COLUMN_ALIASES}
        if custom_aliases:
            for canon, variants in custom_aliases.items():
                self.aliases[canon] = variants + self.aliases.get(canon, [])

        # Build reverse map: normalised_source -> canonical
        self._reverse: Dict[str, str] = {}
        for canon, variants in self.aliases.items():
            for v in variants:
                self._reverse[v.lower().strip()] = canon

    def find_canonical(self, source_col: str) -> Optional[str]:
        """Return the canonical field name for a source column, or None."""
        return self._reverse.get(source_col.lower().strip())

    def build_rename_map(self, df_columns: List[str]) -> Dict[str, str]:
        """Return {source_col: canonical_col} for all matched columns."""
        rename = {}
        for col in df_columns:
            canon = self.find_canonical(col)
            if canon:
                rename[col] = canon
        return rename

    def rename_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of df with source columns renamed to canonical names."""
        rename_map = self.build_rename_map(list(df.columns))
        return df.rename(columns=rename_map)

    def audit_missing_fields(
        self, df: pd.DataFrame, required: List[str]
    ) -> List[str]:
        """Return list of required canonical fields absent from df."""
        return [f for f in required if f not in df.columns]

    def detected_fields(self, df_columns: List[str]) -> Dict[str, Optional[str]]:
        """Return {canonical: detected_source_col or None} for all known fields."""
        rmap = self.build_rename_map(df_columns)
        rev_rmap = {v: k for k, v in rmap.items()}
        return {canon: rev_rmap.get(canon) for canon in self.aliases}


# ============================================================
# 3. SHEET ROLE DETECTOR
# ============================================================

class SheetRoleDetector:
    """
    Detects which accounting role a sheet plays based on its name.
    Roles: 'coa' | 'otb' | 'gl' | 'tb' | 'unknown'
    """

    def __init__(self, custom_aliases: Optional[Dict[str, List[str]]] = None):
        self.aliases: Dict[str, List[str]] = {**DEFAULT_SHEET_ALIASES}
        if custom_aliases:
            self.aliases.update(custom_aliases)

    def detect(self, sheet_name: str) -> str:
        nm = sheet_name.lower().strip()
        # Check most specific first (otb before tb)
        for role in ["coa", "otb", "gl", "tb"]:
            for fragment in self.aliases.get(role, []):
                if fragment in nm:
                    return role
        return "unknown"

    def detect_all(self, sheet_names: List[str]) -> Dict[str, str]:
        return {name: self.detect(name) for name in sheet_names}


# ============================================================
# 4. WORKBOOK LOADER
# ============================================================

@dataclass
class LoadedWorkbook:
    """Container for all loaded and normalised DataFrames from one workbook."""
    path: Path
    raw_sheets:       Dict[str, pd.DataFrame] = field(default_factory=dict)
    sheet_roles:      Dict[str, str]          = field(default_factory=dict)
    coa:  Optional[pd.DataFrame] = None   # Chart of Accounts
    otb:  Optional[pd.DataFrame] = None   # Opening Trial Balance
    gl:   Optional[pd.DataFrame] = None   # General Ledger
    tb:   Optional[pd.DataFrame] = None   # Closing / Full Trial Balance
    load_warnings:    List[str]  = field(default_factory=list)
    header_row_index: int        = 3       # 0-indexed Excel row containing headers


class WorkbookLoader:
    """
    Loads an Excel workbook, auto-detects sheet roles and header rows,
    and maps all columns to canonical names.

    Parameters
    ----------
    column_aliases  : extend / override column name mappings
    sheet_aliases   : extend / override sheet role detection
    header_row      : 0-indexed row number of the header row (default 3 = Excel row 4)
                      Set to None to auto-detect.
    """

    HEADER_PROBE_MAX_ROWS = 8   # scan up to this many rows to find the header

    def __init__(
        self,
        column_aliases: Optional[Dict[str, List[str]]] = None,
        sheet_aliases:  Optional[Dict[str, List[str]]] = None,
        header_row:     Optional[int] = None,
    ):
        self.mapper   = ConfigurableColumnMapper(custom_aliases=column_aliases)
        self.detector = SheetRoleDetector(custom_aliases=sheet_aliases)
        self._forced_header_row = header_row

    # ----------------------------------------------------------
    def load(self, path: Path | str) -> LoadedWorkbook:
        path = Path(path)
        wb = LoadedWorkbook(path=path)

        raw_all = pd.read_excel(path, sheet_name=None, header=None, dtype=str)
        wb.sheet_roles = self.detector.detect_all(list(raw_all.keys()))

        for sheet_name, raw_df in raw_all.items():
            role = wb.sheet_roles[sheet_name]
            hrow = (
                self._forced_header_row
                if self._forced_header_row is not None
                else self._detect_header_row(raw_df, sheet_name)
            )

            # Re-read with proper header
            df = pd.read_excel(path, sheet_name=sheet_name, header=hrow, dtype=str)

            # Normalise: strip whitespace, drop all-null rows
            for col in df.select_dtypes(include=["object", "string"]).columns:
                df[col] = df[col].astype(str).str.strip().replace("nan", pd.NA)
            df = df.dropna(how="all").reset_index(drop=True)

            wb.raw_sheets[sheet_name] = df

            # Rename to canonical columns
            df_canon = self.mapper.rename_columns(df)
            wb.header_row_index = hrow

            if role == "coa":
                wb.coa = self._coerce_coa(df_canon, sheet_name, wb)
            elif role == "otb":
                wb.otb = self._coerce_tb(df_canon, sheet_name, wb,
                                          numeric_cols=["opening_debit", "opening_credit"])
            elif role == "gl":
                wb.gl  = self._coerce_gl(df_canon, sheet_name, wb)
            elif role == "tb":
                wb.tb  = self._coerce_tb(
                    df_canon, sheet_name, wb,
                    numeric_cols=["opening_debit", "opening_credit",
                                  "period_debit",  "period_credit",
                                  "closing_debit", "closing_credit"]
                )
            else:
                wb.load_warnings.append(
                    f"Sheet '{sheet_name}' role='{role}' — not mapped to a standard table."
                )

        return wb

    # ----------------------------------------------------------
    def _detect_header_row(self, raw_df: pd.DataFrame, sheet_name: str) -> int:
        """
        Scan the first N rows to find the one that most resembles a header
        (i.e. has the most non-null string cells that match known column aliases).
        """
        known = set(self.mapper._reverse.keys())
        best_row, best_score = 0, -1
        for i in range(min(self.HEADER_PROBE_MAX_ROWS, len(raw_df))):
            row_vals = [str(v).lower().strip() for v in raw_df.iloc[i] if pd.notna(v)]
            score = sum(1 for v in row_vals if v in known)
            if score > best_score:
                best_score, best_row = score, i
        return best_row

    # ----------------------------------------------------------
    @staticmethod
    def _coerce_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        return df

    def _coerce_coa(self, df: pd.DataFrame, sheet: str, wb: LoadedWorkbook) -> pd.DataFrame:
        missing = self.mapper.audit_missing_fields(df, ["account_code", "account_name", "account_type"])
        if missing:
            wb.load_warnings.append(f"[{sheet}/COA] Missing canonical fields: {missing}")
        # Drop totals / blank account rows
        if "account_code" in df.columns:
            df = df[df["account_code"].notna()].copy()
        return df

    def _coerce_tb(self, df: pd.DataFrame, sheet: str,
                   wb: LoadedWorkbook, numeric_cols: List[str]) -> pd.DataFrame:
        df = self._coerce_numeric(df, numeric_cols)
        # Drop footer / totals rows (no account code)
        if "account_code" in df.columns:
            df = df[df["account_code"].notna()].copy()
        return df

    def _coerce_gl(self, df: pd.DataFrame, sheet: str, wb: LoadedWorkbook) -> pd.DataFrame:
        df = self._coerce_numeric(df, ["debit", "credit"])
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        # Drop rows with no account code AND no debit/credit (summary / footer rows)
        if "account_code" in df.columns:
            df = df[df["account_code"].notna()].copy()
        return df


# ============================================================
# 5. CONVENIENCE FUNCTION
# ============================================================

def load_workbook(
    path: Path | str,
    column_aliases: Optional[Dict[str, List[str]]] = None,
    sheet_aliases:  Optional[Dict[str, List[str]]] = None,
    header_row:     Optional[int] = None,
) -> LoadedWorkbook:
    """
    Top-level convenience function. Returns a LoadedWorkbook with
    .coa, .otb, .gl, .tb DataFrames using canonical column names.

    Parameters
    ----------
    path            : path to the .xlsx file
    column_aliases  : {canonical_name: [list_of_source_names]} overrides
    sheet_aliases   : {role: [list_of_name_fragments]} overrides
    header_row      : force a specific 0-indexed header row (default: auto-detect)
    """
    loader = WorkbookLoader(
        column_aliases=column_aliases,
        sheet_aliases=sheet_aliases,
        header_row=header_row,
    )
    return loader.load(path)


# ============================================================
# 6. SELF-TEST (run directly to verify loader works)
# ============================================================

if __name__ == "__main__":
    WB = Path(__file__).parent.parent / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"
    wb = load_workbook(WB, header_row=3)

    print("Loaded workbook:", wb.path.name)
    print("Sheet roles:", wb.sheet_roles)
    print("Warnings:", wb.load_warnings or "None")
    print("")

    for label, df in [("COA", wb.coa), ("OTB", wb.otb), ("GL", wb.gl), ("TB", wb.tb)]:
        if df is not None:
            print(f"  [{label}]  {len(df)} rows x {len(df.columns)} cols  |  columns: {list(df.columns)}")
        else:
            print(f"  [{label}]  NOT LOADED")
