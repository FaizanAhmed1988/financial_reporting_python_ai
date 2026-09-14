"""
src/dataset_manager.py
======================
UP3 — Dataset Manager + Engine Hookup.

Turns a validated, column-mapped, COA-classified upload (from UP1/UP2) into a
named **Dataset** that the existing financial engine can consume, and keeps
every dataset isolated from every other one.

TWO MODES
---------
  Analyze Separately  — the upload becomes a standalone dataset with no
                        connection to the original Q1 2026 data.
  Add to Existing     — a GL upload's transactions are appended to a base
                        dataset's ledger and the trial balance is rebuilt.
                        Only meaningful for a General Ledger: appending a
                        Trial Balance or Chart of Accounts is not an
                        accounting operation, so those slots are refused.

THE ENGINE'S INPUT CONTRACT
---------------------------
Every engine function is driven by a **trial balance** keyed on `account_code`
with `opening_debit/credit`, `period_debit/credit` and `closing_debit/credit`.
Two identities hold in the source data and are preserved here:

    closing_net == opening_net + period_net
    GL debit/credit summed per account == TB period_debit/period_credit

`tb_from_gl()` therefore rebuilds a trial balance from ledger movements, and
`build_appended_dataset()` re-derives closing balances from opening + combined
period movement rather than mutating anything.

IMMUTABILITY
------------
The original dataset is never modified. Every Dataset holds deep copies, and
`register()` refuses to overwrite the original's entry. An upload can add a new
dataset; it can never alter an existing one.

ARCHITECTURE COMPLIANCE
-----------------------
- NO streamlit import — pure logic, headlessly testable, like coa_mapper and
  validation_engine. Rendering lives in file_upload.py / app.py.
- NO reimplemented accounting. `compute_statements()` is the single place that
  sequences the engine, and it calls the existing profit_loss / balance_sheet /
  cash_flow / ratios / working_capital functions unchanged.
- Manually-mapped accounts are translated through coa_mapper.CATEGORY_TO_ENGINE
  into the engine's own COA schema — no parallel classification vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.balance_sheet import generate_balance_sheet
from src.cash_flow import generate_cash_flow
from src.coa_mapper import CATEGORY_TO_ENGINE, normalise_code
from src.profit_loss import generate_profit_loss
from src.ratios import calculate_ratios
from src.working_capital import analyze_working_capital

# ============================================================
# 1. CONSTANTS
# ============================================================

ORIGINAL_DATASET_NAME = "Original Dataset (Q1 2026)"

MODE_SEPARATE = "Analyze Separately"
MODE_APPEND = "Add to Existing Dataset"
DATASET_MODES = [MODE_SEPARATE, MODE_APPEND]

#: Appending only makes accounting sense for transaction-level ledger data.
APPENDABLE_SLOTS = {"general_ledger"}

TOLERANCE = 0.01

#: Columns that identify a transaction for duplicate detection. `core` must
#: match for a row to be a *possible* duplicate; `core + corroborating` must all
#: match for it to be an *exact* duplicate.
DUP_CORE_FIELDS = ["date", "account_code", "debit", "credit"]
DUP_CORROBORATING_FIELDS = ["voucher_no", "narration"]

TB_NUMERIC_COLS = [
    "opening_debit", "opening_credit",
    "period_debit", "period_credit",
    "closing_debit", "closing_credit",
]


# ============================================================
# 2. DATASET
# ============================================================

@dataclass
class Dataset:
    """One self-contained, engine-ready dataset."""
    name: str
    origin: str                                   # original | separate | appended
    slot: str
    coa_classified: pd.DataFrame
    tb: pd.DataFrame
    gl: Optional[pd.DataFrame] = None
    limitations: List[str] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_original(self) -> bool:
        return self.origin == "original"

    @property
    def has_gl(self) -> bool:
        return self.gl is not None and not self.gl.empty

    def summary(self) -> Dict[str, Any]:
        return {
            "Dataset": self.name,
            "Origin": self.origin,
            "Source type": self.slot,
            "COA accounts": len(self.coa_classified),
            "TB rows": len(self.tb),
            "GL rows": len(self.gl) if self.has_gl else 0,
            "Limitations": len(self.limitations),
        }


# ============================================================
# 3. NORMALISATION
# ============================================================

def _to_num(series: pd.Series) -> pd.Series:
    """Coerce an amount column to float, blanks and junk becoming 0.0."""
    cleaned = (
        series.astype(str).str.strip()
        .str.replace(r"[,$€£\s]", "", regex=True)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def normalise_gl(df: pd.DataFrame) -> pd.DataFrame:
    """Return a GL frame with canonical dtypes: numeric amounts, parsed dates."""
    gl = df.copy()
    for col in ("debit", "credit"):
        gl[col] = _to_num(gl[col]) if col in gl.columns else 0.0
    if "account_code" in gl.columns:
        gl["account_code"] = gl["account_code"].map(normalise_code)
        gl = gl[gl["account_code"] != ""].copy()
    if "date" in gl.columns:
        gl["date"] = pd.to_datetime(gl["date"], errors="coerce", format="mixed")
    return gl.reset_index(drop=True)


def normalise_tb(df: pd.DataFrame) -> pd.DataFrame:
    """Return a TB frame with every balance column numeric and present."""
    tb = df.copy()
    if "account_code" in tb.columns:
        tb["account_code"] = tb["account_code"].map(normalise_code)
        tb = tb[tb["account_code"] != ""].copy()
    for col in TB_NUMERIC_COLS:
        tb[col] = _to_num(tb[col]) if col in tb.columns else 0.0
    return tb.reset_index(drop=True)


def _split_signed(net: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Split a signed net balance into (debit, credit) columns."""
    return net.clip(lower=0), (-net).clip(lower=0)


# ============================================================
# 4. TRIAL BALANCE FROM LEDGER
# ============================================================

def tb_from_gl(
    gl: pd.DataFrame,
    opening_tb: Optional[pd.DataFrame] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Rebuild a trial balance from ledger movements.

    `opening_tb`, when supplied, provides the opening balances (its
    `opening_debit` / `opening_credit` columns); closing balances are then
    derived as opening + period, matching how the source data is constructed.

    Without it every account opens at zero, which is correct for Income
    Statement accounts but NOT for Balance Sheet ones — the caller is handed a
    limitation saying so rather than a silently wrong balance sheet.

    Returns (tb, limitations).
    """
    limitations: List[str] = []
    gl = normalise_gl(gl)

    movement = (
        gl.groupby("account_code", dropna=False)[["debit", "credit"]]
        .sum()
        .rename(columns={"debit": "period_debit", "credit": "period_credit"})
    )

    names = {}
    if "account_name" in gl.columns:
        for code, name in zip(gl["account_code"], gl["account_name"]):
            text = "" if name is None else str(name).strip()
            if code and code not in names and text and text.lower() not in ("nan", "none"):
                names[code] = text

    if opening_tb is not None and not opening_tb.empty:
        base = normalise_tb(opening_tb).set_index("account_code")
        opening = base[["opening_debit", "opening_credit"]]
        # Accounts present in either source
        tb = opening.join(movement, how="outer").fillna(0.0)
        if "account_name" in base.columns:
            names = {**base["account_name"].dropna().astype(str).to_dict(), **names}
    else:
        tb = movement.copy()
        tb["opening_debit"] = 0.0
        tb["opening_credit"] = 0.0
        limitations.append(
            "No opening balances were available for this upload, so every account "
            "opens at zero. Income Statement figures are unaffected — P&L accounts "
            "genuinely start each period at zero. The Balance Sheet and Cash Flow "
            "Statement still balance and reconcile internally (ledger movements are "
            "double-entry by construction), but they describe the period's "
            "**movement**, not the closing financial position: Total Assets, "
            "opening cash and every balance-sheet ratio will differ from the real "
            "figures by the opening balances that are absent. Upload a Trial "
            "Balance, or use \"Add to Existing Dataset\", to carry them in."
        )

    net = (tb["opening_debit"] - tb["opening_credit"]) + (tb["period_debit"] - tb["period_credit"])
    tb["closing_debit"], tb["closing_credit"] = _split_signed(net)

    tb = tb.reset_index()
    tb["account_name"] = tb["account_code"].map(names).fillna("")
    tb = tb[["account_code", "account_name"] + TB_NUMERIC_COLS]
    return tb.reset_index(drop=True), limitations


# ============================================================
# 5. COA EXTENSION FOR USER-MAPPED ACCOUNTS
# ============================================================

def extend_coa(
    coa_classified: pd.DataFrame,
    user_categories: Dict[str, str],
    account_names: Optional[Dict[str, str]] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Append rows for accounts a user categorised in UP2, translated into the
    engine's own COA schema via coa_mapper.CATEGORY_TO_ENGINE.

    The 7 manual categories are coarser than the engine's schema: they say
    "Asset" but not "Current" vs "Non-Current". Balance-sheet aggregation keys
    off `bs_sub_category`, so a default is unavoidable — Current is assumed and
    reported as a limitation rather than applied silently.

    Returns (extended_coa, limitations).
    """
    limitations: List[str] = []
    account_names = account_names or {}
    if not user_categories:
        return coa_classified.copy(), limitations

    existing = set(coa_classified["account_code"].map(normalise_code))
    sub_default = {
        "Asset": "Current Assets",
        "Liability": "Current Liabilities",
        "Equity": "Paid-In Capital",
    }
    rows = []
    assumed: List[str] = []
    for raw_code, category in user_categories.items():
        code = normalise_code(raw_code)
        if not code or code in existing or category not in CATEGORY_TO_ENGINE:
            continue
        eng = CATEGORY_TO_ENGINE[category]
        if category in sub_default:
            assumed.append(f"{code} ({category} -> {sub_default[category]})")
        rows.append({
            "account_code": code,
            "account_name": account_names.get(code, f"User-mapped {code}"),
            "account_type": category,
            "normal_balance": "Debit" if category in ("Asset", "COGS", "Expense") else "Credit",
            "financial_statement": eng["financial_statement"],
            "bs_category": eng["bs_category"],
            "bs_sub_category": sub_default.get(category),
            "pl_category": eng["pl_category"],
            "pl_sub_category": None,
            "grouping_label": f"User-Mapped — {category}",
            "sort_order": 9999,
            "is_contra": False,
        })

    if not rows:
        return coa_classified.copy(), limitations

    if assumed:
        limitations.append(
            "Manually-categorised balance sheet accounts were assumed to be "
            "**current** (the 7 upload categories do not distinguish current from "
            "non-current): " + "; ".join(assumed) + "."
        )
    unplaced = [normalise_code(c) for c, k in user_categories.items() if k == "Other"]
    if unplaced:
        limitations.append(
            "Account(s) categorised as **Other** carry no financial-statement "
            "placement and are excluded from the P&L and Balance Sheet: "
            + ", ".join(sorted(set(unplaced))) + "."
        )

    extended = pd.concat([coa_classified.copy(), pd.DataFrame(rows)], ignore_index=True)
    return extended, limitations


# ============================================================
# 6. DUPLICATE DETECTION
# ============================================================

@dataclass
class DuplicateReport:
    """Outcome of comparing an incoming ledger against an existing one."""
    new_rows: pd.DataFrame
    exact_duplicates: pd.DataFrame
    possible_duplicates: pd.DataFrame
    key_fields: List[str]
    corroborating_fields: List[str]

    @property
    def counts(self) -> Dict[str, int]:
        return {
            "New Transactions": len(self.new_rows),
            "Possible Duplicates": len(self.possible_duplicates),
            "Confirmed Duplicates": len(self.exact_duplicates),
        }

    @property
    def total(self) -> int:
        return len(self.new_rows) + len(self.possible_duplicates) + len(self.exact_duplicates)


def _dup_key(df: pd.DataFrame, fields: List[str]) -> pd.Series:
    """Build a comparable string key over the given fields."""
    parts = []
    for f in fields:
        if f == "date":
            col = pd.to_datetime(df[f], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        elif f in ("debit", "credit"):
            col = _to_num(df[f]).round(2).astype(str)
        elif f == "account_code":
            col = df[f].map(normalise_code)
        else:
            col = df[f].astype(str).str.strip().str.lower().replace("nan", "")
        parts.append(col)
    return parts[0].str.cat(parts[1:], sep="||") if len(parts) > 1 else parts[0]


def detect_duplicates(existing_gl: pd.DataFrame, incoming_gl: pd.DataFrame) -> DuplicateReport:
    """
    Classify every incoming ledger row against the existing ledger.

      Confirmed Duplicate — matches on date, account code, debit, credit AND
                            every corroborating field present (voucher number,
                            narration). Almost certainly the same posting.
      Possible Duplicate  — matches on date, account code, debit and credit but
                            differs on a corroborating field. Could be a genuine
                            repeated posting, could be a re-entry.
      New Transaction     — no match.

    Nothing is removed here. The caller decides what to append.
    """
    incoming = normalise_gl(incoming_gl)
    existing = normalise_gl(existing_gl) if existing_gl is not None else pd.DataFrame()

    core = [f for f in DUP_CORE_FIELDS if f in incoming.columns and f in existing.columns]
    corroborating = [
        f for f in DUP_CORROBORATING_FIELDS
        if f in incoming.columns and f in existing.columns
    ]

    if existing.empty or not core:
        return DuplicateReport(
            new_rows=incoming,
            exact_duplicates=incoming.iloc[0:0],
            possible_duplicates=incoming.iloc[0:0],
            key_fields=core,
            corroborating_fields=corroborating,
        )

    existing_core = set(_dup_key(existing, core))
    incoming_core = _dup_key(incoming, core)
    core_hit = incoming_core.isin(existing_core)

    if corroborating:
        full = core + corroborating
        existing_full = set(_dup_key(existing, full))
        full_hit = _dup_key(incoming, full).isin(existing_full)
    else:
        # Without corroborating fields a core match is the strongest signal
        # available, so treat it as exact rather than inventing certainty.
        full_hit = core_hit

    return DuplicateReport(
        new_rows=incoming[~core_hit].copy(),
        exact_duplicates=incoming[full_hit].copy(),
        possible_duplicates=incoming[core_hit & ~full_hit].copy(),
        key_fields=core,
        corroborating_fields=corroborating,
    )


# ============================================================
# 7. DATASET CONSTRUCTION
# ============================================================

def build_separate_dataset(
    name: str,
    slot: str,
    df_mapped: pd.DataFrame,
    coa_classified: pd.DataFrame,
    user_categories: Optional[Dict[str, str]] = None,
    account_names: Optional[Dict[str, str]] = None,
    file_name: str = "",
) -> Dataset:
    """Build a standalone dataset from one upload, independent of any other."""
    coa, limitations = extend_coa(coa_classified, user_categories or {}, account_names)

    if slot in ("trial_balance", "opening_trial_balance"):
        tb = normalise_tb(df_mapped)
        gl = None
        if tb[["opening_debit", "opening_credit"]].abs().sum().sum() < TOLERANCE:
            limitations.append(
                "This trial balance carries no opening balances, so the Cash Flow "
                "Statement cannot reconcile opening to closing cash and every "
                "movement-based figure is measured from zero."
            )
        limitations.append(
            "Uploaded as a Trial Balance: there is no transaction-level ledger, so "
            "Control Analytics, AI Anomaly Detection and Forecasting have nothing "
            "to test and are not meaningful for this dataset."
        )
    elif slot == "general_ledger":
        gl = normalise_gl(df_mapped)
        tb, tb_limits = tb_from_gl(gl)
        limitations.extend(tb_limits)
    else:
        raise ValueError(
            f"Slot '{slot}' cannot be processed into a dataset. "
            "Only General Ledger and Trial Balance uploads carry balances."
        )

    return Dataset(
        name=name,
        origin="separate",
        slot=slot,
        coa_classified=coa,
        tb=tb,
        gl=gl,
        limitations=limitations,
        provenance={
            "file_name": file_name,
            "mode": MODE_SEPARATE,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rows_in": int(len(df_mapped)),
        },
    )


def build_appended_dataset(
    name: str,
    base: Dataset,
    rows_to_append: pd.DataFrame,
    file_name: str = "",
    duplicate_note: Optional[str] = None,
    user_categories: Optional[Dict[str, str]] = None,
    account_names: Optional[Dict[str, str]] = None,
) -> Dataset:
    """
    Append ledger rows to a copy of `base` and rebuild the trial balance.

    The base dataset is NOT modified — a new Dataset is returned. Opening
    balances carry over from the base; closing balances are re-derived from
    opening + combined period movement.
    """
    if base.slot not in APPENDABLE_SLOTS and not base.is_original:
        raise ValueError(
            f"Base dataset '{base.name}' has no ledger to append to."
        )
    if not base.has_gl:
        raise ValueError(
            f"Base dataset '{base.name}' contains no General Ledger, so there is "
            "nothing to append transactions to."
        )

    coa, limitations = extend_coa(base.coa_classified, user_categories or {}, account_names)

    incoming = normalise_gl(rows_to_append)
    combined = pd.concat([base.gl.copy(), incoming], ignore_index=True)

    # Opening balances come from the base trial balance, untouched.
    opening = base.tb[["account_code", "account_name", "opening_debit", "opening_credit"]].copy()
    tb, tb_limits = tb_from_gl(combined, opening_tb=opening)
    limitations.extend(tb_limits)

    if duplicate_note:
        limitations.append(duplicate_note)

    dates = pd.to_datetime(incoming["date"], errors="coerce") if "date" in incoming.columns else pd.Series(dtype="datetime64[ns]")
    if dates.notna().any():
        limitations.append(
            f"Appended transactions span {dates.min().date()} to {dates.max().date()}. "
            "Period-based metrics still use the 90-day divisor configured for the "
            "base dataset, so day-count ratios (DSO, DPO, DIO) will understate the "
            "true period if the combined data covers more than one quarter."
        )

    return Dataset(
        name=name,
        origin="appended",
        slot="general_ledger",
        coa_classified=coa,
        tb=tb,
        gl=combined,
        limitations=limitations,
        provenance={
            "file_name": file_name,
            "mode": MODE_APPEND,
            "base_dataset": base.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rows_appended": int(len(incoming)),
            "base_gl_rows": int(len(base.gl)),
        },
    )


def build_original_dataset(coa_classified: pd.DataFrame, wb) -> Dataset:
    """Wrap the loaded source workbook as the immutable baseline dataset."""
    return Dataset(
        name=ORIGINAL_DATASET_NAME,
        origin="original",
        slot="general_ledger",
        coa_classified=coa_classified.copy(),
        tb=wb.tb.copy(),
        gl=wb.gl.copy() if wb.gl is not None else None,
        limitations=[],
        provenance={
            "file_name": getattr(wb.path, "name", str(getattr(wb, "path", ""))),
            "mode": "source",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


# ============================================================
# 8. ENGINE HOOKUP
# ============================================================

def compute_statements(dataset: Dataset, days_in_period: int = 90) -> Dict[str, Any]:
    """
    Run the EXISTING engine over a dataset. This is the only place the engine
    sequence is expressed; nothing here recomputes accounting itself.
    """
    coa, tb = dataset.coa_classified, dataset.tb

    pl_df, pl_metrics = generate_profit_loss(coa, tb)
    net_profit = pl_metrics["Net Profit"]
    bs_df, bs_metrics = generate_balance_sheet(coa, tb, net_profit)
    cf_df, cf_metrics = generate_cash_flow(coa, tb, net_profit)
    ratios_df = calculate_ratios(pl_metrics, bs_metrics, bs_df, days_in_period=days_in_period)
    wc_df = analyze_working_capital(pl_metrics, bs_df, days_in_period=days_in_period)

    return {
        "pl_df": pl_df, "pl_metrics": pl_metrics,
        "bs_df": bs_df, "bs_metrics": bs_metrics,
        "cf_df": cf_df, "cf_metrics": cf_metrics,
        "ratios_df": ratios_df, "wc_df": wc_df,
    }


# ============================================================
# 9. REGISTRY (session-state agnostic)
# ============================================================

def register(registry: Dict[str, Dataset], dataset: Dataset, overwrite: bool = False) -> str:
    """
    Add a dataset to the registry under a unique name.

    The original dataset can never be replaced. A colliding name is suffixed
    rather than overwritten, so an upload can only ever ADD to the registry.
    """
    if dataset.name == ORIGINAL_DATASET_NAME and ORIGINAL_DATASET_NAME in registry:
        if not overwrite:
            return ORIGINAL_DATASET_NAME

    name = dataset.name
    if name in registry and not overwrite:
        n = 2
        while f"{name} ({n})" in registry:
            n += 1
        name = f"{name} ({n})"
        dataset.name = name

    registry[name] = dataset
    return name


def dataset_names(registry: Dict[str, Dataset]) -> List[str]:
    """Original first, then the rest in insertion order."""
    names = [n for n in registry if n == ORIGINAL_DATASET_NAME]
    names += [n for n in registry if n != ORIGINAL_DATASET_NAME]
    return names
