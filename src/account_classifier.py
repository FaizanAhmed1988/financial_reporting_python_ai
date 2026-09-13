"""
src/account_classifier.py
==========================
Phase 2 — Chart of Accounts Mapping & Classification

ARCHITECTURE PRINCIPLE
----------------------
No account codes, account names, or classification rules are hardcoded in
business logic. The classification is driven entirely by a configurable
CLASSIFICATION_MAP — a list of rules applied in order. The first matching
rule wins. Rules can match on:
  - code_range  : (low, high) inclusive integer range of account codes
  - code_prefix : string prefix of account code
  - account_type: value of the `account_type` canonical field
  - account_name: substring match (case-insensitive)

OUTPUT CANONICAL FIELDS (added to COA DataFrame)
-------------------------------------------------
  financial_statement   : "Balance Sheet" | "Income Statement"
  bs_category           : "Assets" | "Liabilities" | "Equity" | None
  bs_sub_category       : "Current Assets" | "Non-Current Assets" | etc.
  is_section            : "Income Statement" | "Balance Sheet" | None
  pl_category           : "Revenue" | "Cost of Sales" | "Operating Expenses" |
                          "Finance Costs" | None
  pl_sub_category       : e.g. "Sales Revenue" | "COGS" | "Staff Costs" | etc.
  sort_order            : integer for deterministic financial-statement ordering
  is_contra             : True if account offsets another (e.g. Accum. Dep.)
  grouping_label        : Short human-readable group label for reports

USAGE
-----
  from src.account_classifier import AccountClassifier, classify_workbook
  from src.data_loader import load_workbook

  wb      = load_workbook("data/raw/...")
  coa_map = AccountClassifier().classify(wb.coa)
  # coa_map now has all classification columns above
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

# ============================================================
# 1.  DEFAULT CLASSIFICATION RULES
# ============================================================
# Each rule is a dict with:
#   match_type       : "code_range" | "code_prefix" | "account_type" | "account_name"
#   match_value      : value to match (tuple for range, str for others)
#   financial_statement
#   bs_category      (Balance Sheet accounts)
#   bs_sub_category
#   pl_category      (Income Statement accounts)
#   pl_sub_category
#   grouping_label
#   sort_order
#   is_contra        (optional, default False)
#
# Rules are evaluated in ORDER — first match wins.
# To adapt for a new COA structure, pass custom_rules to AccountClassifier.

DEFAULT_CLASSIFICATION_RULES: List[Dict[str, Any]] = [

    # ── BALANCE SHEET ─────────────────────────────────────────────────────

    # --- Current Assets ---
    {
        "match_type": "code_range", "match_value": (1000, 1099),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Cash & Cash Equivalents",
        "sort_order": 100,
    },
    {
        "match_type": "code_range", "match_value": (1100, 1199),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Trade Receivables",
        "sort_order": 110,
    },
    {
        "match_type": "code_range", "match_value": (1200, 1249),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Inventories",
        "sort_order": 120,
    },
    {
        "match_type": "code_range", "match_value": (1250, 1399),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Prepayments & Other Current Assets",
        "sort_order": 130,
    },

    # --- Non-Current Assets (PPE) ---
    {
        "match_type": "code_range", "match_value": (1400, 1499),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Non-Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Intangible Assets",
        "sort_order": 200,
    },
    # Accumulated Depreciation — Contra-Asset rule MUST come BEFORE the PPE
    # code-range rule (1500-1549) so that account_type match takes priority.
    {
        "match_type": "account_type", "match_value": "Contra-Asset",
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Non-Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Accumulated Depreciation",
        "sort_order": 215,
        "is_contra": True,
    },
    {
        "match_type": "code_range", "match_value": (1500, 1549),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Non-Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Property, Plant & Equipment — Cost",
        "sort_order": 210,
        "is_contra": False,
    },
    {
        "match_type": "code_range", "match_value": (1550, 1999),
        "financial_statement": "Balance Sheet",
        "bs_category": "Assets", "bs_sub_category": "Non-Current Assets",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Other Non-Current Assets",
        "sort_order": 220,
    },

    # --- Current Liabilities ---
    {
        "match_type": "code_range", "match_value": (2000, 2099),
        "financial_statement": "Balance Sheet",
        "bs_category": "Liabilities", "bs_sub_category": "Current Liabilities",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Trade Payables",
        "sort_order": 300,
    },
    {
        "match_type": "code_range", "match_value": (2100, 2199),
        "financial_statement": "Balance Sheet",
        "bs_category": "Liabilities", "bs_sub_category": "Current Liabilities",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Accrued Liabilities",
        "sort_order": 310,
    },
    {
        "match_type": "code_range", "match_value": (2200, 2299),
        "financial_statement": "Balance Sheet",
        "bs_category": "Liabilities", "bs_sub_category": "Non-Current Liabilities",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Interest-Bearing Loans & Borrowings",
        "sort_order": 400,
    },
    {
        "match_type": "code_range", "match_value": (2300, 2399),
        "financial_statement": "Balance Sheet",
        "bs_category": "Liabilities", "bs_sub_category": "Current Liabilities",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Tax Payables",
        "sort_order": 320,
    },
    {
        "match_type": "code_range", "match_value": (2400, 2999),
        "financial_statement": "Balance Sheet",
        "bs_category": "Liabilities", "bs_sub_category": "Current Liabilities",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Other Current Liabilities",
        "sort_order": 330,
    },

    # --- Equity ---
    {
        "match_type": "code_range", "match_value": (3000, 3099),
        "financial_statement": "Balance Sheet",
        "bs_category": "Equity", "bs_sub_category": "Paid-In Capital",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Share Capital",
        "sort_order": 500,
    },
    {
        "match_type": "code_range", "match_value": (3100, 3199),
        "financial_statement": "Balance Sheet",
        "bs_category": "Equity", "bs_sub_category": "Retained Earnings",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Retained Earnings",
        "sort_order": 510,
    },
    {
        "match_type": "code_range", "match_value": (3200, 3999),
        "financial_statement": "Balance Sheet",
        "bs_category": "Equity", "bs_sub_category": "Other Reserves",
        "pl_category": None, "pl_sub_category": None,
        "grouping_label": "Other Reserves",
        "sort_order": 520,
    },

    # ── INCOME STATEMENT ──────────────────────────────────────────────────

    # --- Revenue ---
    {
        "match_type": "code_range", "match_value": (4000, 4099),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Revenue", "pl_sub_category": "Sales Revenue",
        "grouping_label": "Sales Revenue",
        "sort_order": 600,
    },
    {
        "match_type": "code_range", "match_value": (4100, 4199),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Revenue", "pl_sub_category": "Service Revenue",
        "grouping_label": "Service Revenue",
        "sort_order": 610,
    },
    {
        "match_type": "code_range", "match_value": (4200, 4999),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Revenue", "pl_sub_category": "Other Income",
        "grouping_label": "Other Income",
        "sort_order": 620,
    },

    # --- Cost of Sales ---
    {
        "match_type": "code_range", "match_value": (5000, 5099),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Cost of Sales", "pl_sub_category": "Cost of Goods Sold",
        "grouping_label": "Cost of Goods Sold",
        "sort_order": 700,
    },

    # --- Operating Expenses (Staff) ---
    {
        "match_type": "code_range", "match_value": (5100, 5199),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Staff Costs",
        "grouping_label": "Salaries & Employee Benefits",
        "sort_order": 800,
    },

    # --- Operating Expenses (Occupancy) ---
    {
        "match_type": "code_range", "match_value": (5200, 5299),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Occupancy Costs",
        "grouping_label": "Rent & Occupancy",
        "sort_order": 810,
    },

    # --- Operating Expenses (Utilities) ---
    {
        "match_type": "code_range", "match_value": (5300, 5399),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Utilities",
        "grouping_label": "Utilities",
        "sort_order": 820,
    },

    # --- Operating Expenses (Depreciation) ---
    {
        "match_type": "code_range", "match_value": (5400, 5499),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Depreciation & Amortisation",
        "grouping_label": "Depreciation & Amortisation",
        "sort_order": 830,
    },

    # --- Operating Expenses (Admin) ---
    {
        "match_type": "code_range", "match_value": (5500, 5599),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Administration",
        "grouping_label": "Office & Administration",
        "sort_order": 840,
    },
    {
        "match_type": "code_range", "match_value": (5600, 5699),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Administration",
        "grouping_label": "Insurance",
        "sort_order": 850,
    },

    # --- Finance Costs ---
    {
        "match_type": "code_range", "match_value": (5700, 5799),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Finance Costs", "pl_sub_category": "Interest Expense",
        "grouping_label": "Interest Expense",
        "sort_order": 900,
    },
    {
        "match_type": "code_range", "match_value": (5800, 5899),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Finance Costs", "pl_sub_category": "Bank Charges",
        "grouping_label": "Bank Charges",
        "sort_order": 910,
    },

    # --- Selling & Marketing ---
    {
        "match_type": "code_range", "match_value": (5900, 5999),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Selling & Marketing",
        "grouping_label": "Advertising & Marketing",
        "sort_order": 860,
    },

    # --- Other Operating Expenses (6xxx) ---
    {
        "match_type": "code_range", "match_value": (6000, 6099),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Repairs & Maintenance",
        "grouping_label": "Repairs & Maintenance",
        "sort_order": 870,
    },
    {
        "match_type": "code_range", "match_value": (6100, 6999),
        "financial_statement": "Income Statement",
        "bs_category": None, "bs_sub_category": None,
        "pl_category": "Operating Expenses", "pl_sub_category": "Other Expenses",
        "grouping_label": "Miscellaneous Expenses",
        "sort_order": 880,
    },
]


# ============================================================
# 2.  ACCOUNT CLASSIFIER
# ============================================================

class AccountClassifier:
    """
    Enriches a COA DataFrame with financial-statement classification fields.

    All rules are data-driven — no account codes hardcoded in logic.
    To adapt for a different COA structure, pass custom_rules (replaces defaults)
    or extra_rules (prepended — evaluated first, take priority).

    Parameters
    ----------
    custom_rules : fully replaces DEFAULT_CLASSIFICATION_RULES
    extra_rules  : prepended in front of default rules (custom overrides first)
    """

    CLASSIFICATION_FIELDS = [
        "financial_statement",
        "bs_category",
        "bs_sub_category",
        "pl_category",
        "pl_sub_category",
        "grouping_label",
        "sort_order",
        "is_contra",
    ]

    def __init__(
        self,
        custom_rules: Optional[List[Dict[str, Any]]] = None,
        extra_rules:  Optional[List[Dict[str, Any]]] = None,
    ):
        if custom_rules is not None:
            self.rules = custom_rules
        else:
            self.rules = (extra_rules or []) + DEFAULT_CLASSIFICATION_RULES

    # ----------------------------------------------------------
    def classify(self, coa: pd.DataFrame) -> pd.DataFrame:
        """
        Returns an enriched copy of the COA DataFrame with classification fields.
        Also validates integrity (GL/TB orphans, unclassified accounts).
        """
        df = coa.copy()
        df["account_code_int"] = pd.to_numeric(df["account_code"], errors="coerce")

        # Build classification results as plain lists to avoid Pandas dtype conflicts
        results: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            match = self._match_row(row)
            if match:
                results.append({fld: match.get(fld) for fld in self.CLASSIFICATION_FIELDS})
            else:
                results.append({fld: (False if fld == "is_contra" else None) for fld in self.CLASSIFICATION_FIELDS})

        class_df = pd.DataFrame(results, index=df.index)

        # Assign non-boolean columns as object dtype to accept None safely
        for fld in self.CLASSIFICATION_FIELDS:
            if fld == "is_contra":
                df[fld] = class_df[fld].fillna(False).astype(bool)
            elif fld == "sort_order":
                df[fld] = pd.to_numeric(class_df[fld], errors="coerce").fillna(9999).astype(int)
            else:
                df[fld] = class_df[fld].astype(object)

        df = df.sort_values("sort_order").reset_index(drop=True)
        df = df.drop(columns=["account_code_int"], errors="ignore")
        return df

    # ----------------------------------------------------------
    def _match_row(self, row: pd.Series) -> Optional[Dict[str, Any]]:
        """Find first matching rule for this COA row."""
        code_int = pd.to_numeric(row.get("account_code", None), errors="coerce")
        acct_type = str(row.get("account_type", "")).strip()
        acct_name = str(row.get("account_name", "")).strip().lower()

        for rule in self.rules:
            mt = rule["match_type"]
            mv = rule["match_value"]

            if mt == "code_range":
                lo, hi = mv
                if pd.notna(code_int) and lo <= code_int <= hi:
                    return rule
            elif mt == "code_prefix":
                if str(row.get("account_code", "")).startswith(str(mv)):
                    return rule
            elif mt == "account_type":
                if acct_type.lower() == str(mv).lower():
                    return rule
            elif mt == "account_name":
                if str(mv).lower() in acct_name:
                    return rule

        return None  # unclassified

    # ----------------------------------------------------------
    def validate(
        self,
        coa_classified: pd.DataFrame,
        gl: Optional[pd.DataFrame] = None,
        tb: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Validates:
        1. All COA accounts are classified (no unclassified)
        2. All GL account codes exist in COA
        3. All TB account codes exist in COA
        4. BS Equation: Assets = Liabilities + Equity (on closing balances if tb provided)

        Returns a validation report dict.
        """
        report: Dict[str, Any] = {}
        coa_codes = set(coa_classified["account_code"].dropna().unique())

        # --- Unclassified accounts ---
        unclassified = coa_classified[coa_classified["financial_statement"].isna()]
        report["unclassified_accounts"] = {
            "count": len(unclassified),
            "accounts": unclassified[["account_code", "account_name", "account_type"]].to_dict(orient="records"),
        }

        # --- GL orphans ---
        if gl is not None and "account_code" in gl.columns:
            gl_codes = set(gl["account_code"].dropna().unique())
            orphans  = gl_codes - coa_codes
            report["gl_orphan_codes"] = {
                "count": len(orphans),
                "codes": sorted(orphans),
            }
        else:
            report["gl_orphan_codes"] = {"count": 0, "codes": [], "note": "GL not provided"}

        # --- TB orphans ---
        if tb is not None and "account_code" in tb.columns:
            tb_codes = set(tb["account_code"].dropna().unique())
            orphans  = tb_codes - coa_codes
            report["tb_orphan_codes"] = {
                "count": len(orphans),
                "codes": sorted(orphans),
            }
        else:
            report["tb_orphan_codes"] = {"count": 0, "codes": [], "note": "TB not provided"}

        # --- BS Equation check (if TB provided) ---
        # NOTE: The TB contains open P&L accounts (Revenue/Expenses) that have
        # NOT yet been closed to Retained Earnings. The net of all P&L accounts
        # equals current-period net income, which effectively forms part of equity.
        # We include it in the equity side to make the equation balance.
        if tb is not None:
            merged = coa_classified.merge(tb, on="account_code", how="inner", suffixes=("_coa", "_tb"))
            merged["cb_net"] = merged["closing_debit"] - merged["closing_credit"]

            assets = merged[merged["bs_category"] == "Assets"]["cb_net"].sum()
            liab   = merged[merged["bs_category"] == "Liabilities"]["cb_net"].sum()
            equity = merged[merged["bs_category"] == "Equity"]["cb_net"].sum()

            # Net income = Revenue credits - Expense debits (pre-close)
            # In net Dr-Cr terms: Revenue is negative, Expenses are positive
            # Net income (credit-normal) is negative when profitable
            pl_net = merged[merged["financial_statement"] == "Income Statement"]["cb_net"].sum()

            # Assets = Liabilities + Equity + Net Income (pre-close)
            # => Assets + Liab + Equity + PL_net should = 0
            bs_diff = round(assets + liab + equity + pl_net, 2)
            report["balance_sheet_equation"] = {
                "total_assets_net":              round(float(assets), 2),
                "total_liabilities_net":         round(float(liab), 2),
                "total_equity_net":              round(float(equity), 2),
                "current_period_net_income":     round(float(-pl_net), 2),  # positive = profit
                "assets_vs_liab_equity_net_income": bs_diff,
                "balanced": abs(bs_diff) < 1.0,
                "note": "P&L accounts included pre-closing; net income flows into equity.",
            }

        return report


# ============================================================
# 3.  CONVENIENCE FUNCTION
# ============================================================

def classify_workbook(wb, **classifier_kwargs) -> pd.DataFrame:
    """
    Classify the COA from a LoadedWorkbook and validate against GL & TB.
    Returns (coa_classified_df, validation_report).
    """
    classifier = AccountClassifier(**classifier_kwargs)
    coa_c      = classifier.classify(wb.coa)
    val_report = classifier.validate(coa_c, gl=wb.gl, tb=wb.tb)
    return coa_c, val_report


# ============================================================
# 4.  SELF-TEST
# ============================================================

if __name__ == "__main__":
    import json
    from pathlib import Path
    from src.data_loader import load_workbook

    WB = Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx")
    wb = load_workbook(WB, header_row=3)

    classifier = AccountClassifier()
    coa_c, val  = classifier.classify(wb.coa), classifier.validate(classifier.classify(wb.coa), wb.gl, wb.tb)
    coa_c       = classifier.classify(wb.coa)
    val         = classifier.validate(coa_c, wb.gl, wb.tb)

    print("\n" + "="*68)
    print("CLASSIFIED CHART OF ACCOUNTS")
    print("="*68)
    display_cols = [
        "account_code", "account_name", "account_type",
        "financial_statement", "bs_category", "bs_sub_category",
        "pl_category", "pl_sub_category", "grouping_label",
        "is_contra", "sort_order"
    ]
    for _, row in coa_c[display_cols].iterrows():
        fs  = row["financial_statement"] or "UNCLASSIFIED"
        bsc = row["bs_sub_category"] or row["pl_sub_category"] or ""
        grp = row["grouping_label"] or ""
        contra = " [CONTRA]" if row["is_contra"] else ""
        print(f"  {str(row['account_code']):>6}  {str(row['account_name']):<44} | {fs:<18} | {bsc:<35} | {grp}{contra}")

    print("\n" + "="*68)
    print("VALIDATION REPORT")
    print("="*68)
    print(json.dumps(val, indent=2, default=str))

    # Summary by financial_statement / bs_category / pl_category
    print("\n" + "="*68)
    print("CLASSIFICATION SUMMARY")
    print("="*68)

    bs = coa_c[coa_c["financial_statement"] == "Balance Sheet"]
    pl = coa_c[coa_c["financial_statement"] == "Income Statement"]
    uc = coa_c[coa_c["financial_statement"].isna()]

    print(f"\n  Balance Sheet accounts  : {len(bs)}")
    for sub, grp in bs.groupby("bs_sub_category", sort=False):
        codes = grp["account_code"].tolist()
        print(f"    [{sub}]  {len(grp)} accounts  {codes}")

    print(f"\n  Income Statement accounts: {len(pl)}")
    for sub, grp in pl.groupby("pl_category", sort=False):
        codes = grp["account_code"].tolist()
        print(f"    [{sub}]  {len(grp)} accounts  {codes}")

    if len(uc):
        print(f"\n  *** UNCLASSIFIED: {len(uc)} accounts ***")
        print(uc[["account_code","account_name","account_type"]])
    else:
        print(f"\n  Unclassified accounts   : 0  (all accounts mapped)")

    # Save enriched COA
    out = Path("data/processed/coa_classified.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    coa_c.to_csv(out, index=False)
    print(f"\nSaved: {out}")
