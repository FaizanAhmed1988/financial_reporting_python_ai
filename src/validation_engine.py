"""
src/validation_engine.py
========================
UP2 — Data validation for uploaded files.

Runs a battery of accounting-aware checks against a column-mapped upload
(produced by UP1) for a given session slot, and returns a structured
ValidationReport the review screen renders as Pass / Warning / Error.

CHECKS
------
  missing_values         Blanks in the canonical fields the slot requires.
  duplicate_transactions Byte-identical rows across the slot's identity fields.
  invalid_account_codes  Blank codes, or codes the platform cannot resolve.
  invalid_dates          Values in `date` that will not parse.
  debit_credit_format    Rows with both sides populated, or neither.
  non_numeric_amounts    Amount cells that are not numbers.
  unmapped_accounts      Accounts with no reference COA entry and no confirmed
                         user mapping (fed in from coa_mapper).
  unbalanced_journals    Per-voucher Dr/Cr imbalance, plus the dataset total.

SEVERITY MODEL
--------------
  ERROR   — would corrupt the financial engine if processed as-is.
  WARNING — needs a human look; the engine could still run.
  INFO    — context, not a defect.

Overall status is the worst severity present: ERROR > WARNING > PASS.

HONESTY RULE
------------
A check that could not run (because the column it needs is absent) is recorded
in `checks_skipped`, never silently counted as a pass. `validate_dataset` will
not claim an upload is clean on the strength of data it never saw.

ARCHITECTURE COMPLIANCE
-----------------------
- NO streamlit import — pure logic, unit-testable headlessly. Rendering lives
  in `src/file_upload.py`.
- Required-field definitions are reused from `column_mapper.py`, not restated,
  so there is exactly one source of truth for what each file type needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from src.column_mapper import get_required_canonical_columns

# ============================================================
# 1. CONSTANTS
# ============================================================

#: Currency rounding tolerance for balance comparisons.
TOLERANCE = 0.01

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

STATUS_PASS = "PASS"
STATUS_WARNING = "WARNING"
STATUS_ERROR = "ERROR"

_SEVERITY_RANK = {SEVERITY_INFO: 0, SEVERITY_WARNING: 1, SEVERITY_ERROR: 2}

#: Session slot -> the display file type used by column_mapper's required-field
#: table. Mirrors file_upload._TYPE_SLUG; kept here so this module stays free of
#: the streamlit-dependent UI layer.
SLOT_TO_FILE_TYPE: Dict[str, str] = {
    "general_ledger":        "General Ledger",
    "trial_balance":         "Trial Balance",
    "chart_of_accounts":     "Chart of Accounts",
    "opening_trial_balance": "Opening Trial Balance",
    "bank_statement":        "Bank Statement",
    "other":                 "Other / Unknown",
}

#: Amount columns to numeric-check per slot.
AMOUNT_FIELDS_BY_SLOT: Dict[str, List[str]] = {
    "general_ledger":        ["debit", "credit"],
    "trial_balance":         ["opening_debit", "opening_credit",
                              "period_debit", "period_credit",
                              "closing_debit", "closing_credit"],
    "opening_trial_balance": ["opening_debit", "opening_credit"],
    "chart_of_accounts":     [],
    "bank_statement":        ["bank_debit", "bank_credit", "bank_amount", "bank_balance"],
    "other":                 [],
}

#: Fields that together identify a transaction, for duplicate detection.
IDENTITY_FIELDS_BY_SLOT: Dict[str, List[str]] = {
    "general_ledger":        ["txn_no", "date", "voucher_no", "account_code",
                              "narration", "debit", "credit"],
    "trial_balance":         ["account_code"],
    "opening_trial_balance": ["account_code"],
    "chart_of_accounts":     ["account_code"],
    "bank_statement":        ["date", "narration", "bank_amount", "bank_balance"],
    "other":                 [],
}

_BLANK_TOKENS = {"", "nan", "none", "<na>", "nat", "null"}


# ============================================================
# 2. RESULT TYPES
# ============================================================

@dataclass
class ValidationIssue:
    """A single finding. `sample_rows` holds up to `SAMPLE_LIMIT` examples."""
    severity: str
    code: str
    title: str
    message: str
    count: int = 0
    sample_rows: List[Dict[str, Any]] = field(default_factory=list)

    SAMPLE_LIMIT = 10

    @property
    def sample_table(self) -> pd.DataFrame:
        return pd.DataFrame(self.sample_rows)


@dataclass
class ValidationReport:
    """Full validation outcome for one uploaded dataset."""
    slot: str
    status: str = STATUS_PASS
    row_count: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    balance: Dict[str, Any] = field(default_factory=dict)
    checks_run: List[str] = field(default_factory=list)
    checks_skipped: List[Dict[str, str]] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == SEVERITY_INFO]

    def issue_table(self, severity: Optional[str] = None) -> pd.DataFrame:
        """Flat table of findings for display."""
        items = self.issues if severity is None else [
            i for i in self.issues if i.severity == severity
        ]
        if not items:
            return pd.DataFrame(columns=["Severity", "Check", "Finding", "Rows Affected"])
        return pd.DataFrame([
            {
                "Severity": i.severity,
                "Check": i.title,
                "Finding": i.message,
                "Rows Affected": i.count,
            }
            for i in items
        ])

    def balance_table(self) -> pd.DataFrame:
        """Debit/credit summary for display, or an empty frame when N/A."""
        if not self.balance:
            return pd.DataFrame()
        rows = []
        for block in self.balance.get("blocks", []):
            rows.append({
                "Check": block["label"],
                "Total Debit": block["debit"],
                "Total Credit": block["credit"],
                "Difference": block["difference"],
                "Result": block["status"],
            })
        return pd.DataFrame(rows)


# ============================================================
# 3. HELPERS
# ============================================================

def get_required_fields_for_slot(slot: str) -> List[str]:
    """Required canonical fields for a slot, reusing column_mapper's table."""
    return get_required_canonical_columns(SLOT_TO_FILE_TYPE.get(slot, "Other / Unknown"))


def _is_blank(series: pd.Series) -> pd.Series:
    """Boolean mask of blank / null-ish cells."""
    as_text = series.astype(str).str.strip().str.lower()
    return series.isna() | as_text.isin(_BLANK_TOKENS)


def coerce_amount(series: pd.Series) -> Tuple[pd.Series, pd.Index]:
    """
    Coerce an amount column to float, tolerating thousands separators, currency
    symbols and parenthesised negatives.

    Returns (coerced_series_with_blanks_as_zero, index_of_non_numeric_cells).
    Blank cells are not reported as non-numeric — that is the missing-values
    check's job.
    """
    raw = series.astype(str).str.strip()
    blank = _is_blank(series)
    cleaned = (
        raw.str.replace(r"[,$€£\s]", "", regex=True)
           .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )
    coerced = pd.to_numeric(cleaned, errors="coerce")
    bad_index = series.index[coerced.isna() & ~blank]
    return coerced.fillna(0.0), bad_index


def _sample(df: pd.DataFrame, index: Sequence, columns: Sequence[str]) -> List[Dict[str, Any]]:
    """Up to SAMPLE_LIMIT example rows, restricted to the columns that exist."""
    cols = [c for c in columns if c in df.columns]
    if not cols:
        cols = list(df.columns)[:5]
    idx = list(index)[: ValidationIssue.SAMPLE_LIMIT]
    if not idx:
        return []
    out = df.loc[idx, cols].copy()
    out.insert(0, "Row #", [int(i) + 2 for i in idx])  # +2 = 1-indexed incl. header
    return out.astype(str).to_dict(orient="records")


def _balance_block(label: str, debit: float, credit: float) -> Dict[str, Any]:
    diff = round(debit - credit, 2)
    return {
        "label": label,
        "debit": round(debit, 2),
        "credit": round(credit, 2),
        "difference": diff,
        "status": STATUS_PASS if abs(diff) <= TOLERANCE else STATUS_ERROR,
    }


# ============================================================
# 4. MAIN ENTRY POINT
# ============================================================

def validate_dataset(
    df_mapped: pd.DataFrame,
    slot: str,
    known_codes: Optional[Set[str]] = None,
    reference_available: bool = True,
    unmapped_codes: Optional[Sequence[str]] = None,
) -> ValidationReport:
    """
    Validate one mapped upload.

    Parameters
    ----------
    df_mapped   : upload with canonical column names.
    slot        : "general_ledger" | "trial_balance" | "chart_of_accounts" | ...
    known_codes : account codes the platform can resolve (reference COA plus
                  user-confirmed mappings) — see coa_mapper.known_account_codes.
    reference_available : False when no reference COA exists, in which case the
                  account-resolution checks are skipped rather than reporting
                  every account as invalid.
    unmapped_codes : codes still awaiting a manual category, from coa_mapper.

    Returns
    -------
    ValidationReport
    """
    from src.coa_mapper import normalise_code  # local import avoids a cycle

    report = ValidationReport(slot=slot)

    if df_mapped is None or df_mapped.empty:
        report.status = STATUS_ERROR
        report.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="empty_file",
            title="Empty dataset",
            message="The uploaded dataset contains no rows.",
            count=0,
        ))
        return report

    df = df_mapped.reset_index(drop=True)
    report.row_count = len(df)
    required = get_required_fields_for_slot(slot)
    amount_fields = [c for c in AMOUNT_FIELDS_BY_SLOT.get(slot, []) if c in df.columns]

    # ── 0. Required columns present at all ───────────────────────────────────
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        report.issues.append(ValidationIssue(
            severity=SEVERITY_ERROR,
            code="missing_required_columns",
            title="Required columns not mapped",
            message=(
                f"{len(missing_cols)} required column(s) for a "
                f"{SLOT_TO_FILE_TYPE.get(slot, slot)} are not mapped: "
                f"{', '.join(missing_cols)}. Resolve these in the Column Mapping "
                "table above before processing."
            ),
            count=len(missing_cols),
            sample_rows=[{"Missing canonical field": c} for c in missing_cols],
        ))
    report.checks_run.append("required_columns")

    # ── 1. Missing values in required fields ─────────────────────────────────
    present_required = [c for c in required if c in df.columns]
    if present_required:
        # In a General Ledger each line posts to ONE side, so a blank debit or
        # blank credit is the normal shape of double entry, not a missing value.
        # The meaningful defect — a row blank on BOTH sides — is caught by the
        # debit/credit format check below, so flagging each side here would
        # warn on every well-formed GL and train users to ignore warnings.
        blank_exempt = {"debit", "credit"} if slot == "general_ledger" else set()
        for col in present_required:
            if col in blank_exempt:
                continue
            blanks = df.index[_is_blank(df[col])]
            if len(blanks):
                report.issues.append(ValidationIssue(
                    severity=SEVERITY_ERROR if col == "account_code" else SEVERITY_WARNING,
                    code=f"missing_values::{col}",
                    title="Missing values",
                    message=f"`{col}` is blank in {len(blanks)} row(s).",
                    count=len(blanks),
                    sample_rows=_sample(df, blanks, present_required + ["narration"]),
                ))
        report.checks_run.append("missing_values")
    else:
        report.checks_skipped.append({
            "check": "missing_values",
            "reason": "No required canonical fields are mapped for this file type.",
        })

    # ── 2. Non-numeric amounts ───────────────────────────────────────────────
    if amount_fields:
        for col in amount_fields:
            _, bad = coerce_amount(df[col])
            if len(bad):
                report.issues.append(ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code=f"non_numeric::{col}",
                    title="Non-numeric amount",
                    message=(
                        f"`{col}` contains {len(bad)} value(s) that are not numbers "
                        "and cannot be posted."
                    ),
                    count=len(bad),
                    sample_rows=_sample(df, bad, ["account_code", col, "narration"]),
                ))
        report.checks_run.append("non_numeric_amounts")
    else:
        report.checks_skipped.append({
            "check": "non_numeric_amounts",
            "reason": "No amount columns are mapped for this file type.",
        })

    # ── 3. Debit / credit format ─────────────────────────────────────────────
    if slot == "general_ledger" and {"debit", "credit"} <= set(df.columns):
        dr, _ = coerce_amount(df["debit"])
        cr, _ = coerce_amount(df["credit"])
        both = df.index[(dr != 0) & (cr != 0)]
        neither = df.index[(dr == 0) & (cr == 0)]
        if len(both):
            report.issues.append(ValidationIssue(
                severity=SEVERITY_WARNING,
                code="dual_sided_entry",
                title="Debit/credit format",
                message=(
                    f"{len(both)} row(s) carry a value in BOTH debit and credit. "
                    "A journal line normally posts to one side only."
                ),
                count=len(both),
                sample_rows=_sample(df, both, ["account_code", "debit", "credit", "narration"]),
            ))
        if len(neither):
            report.issues.append(ValidationIssue(
                severity=SEVERITY_WARNING,
                code="zero_value_entry",
                title="Debit/credit format",
                message=f"{len(neither)} row(s) have zero or blank on both sides.",
                count=len(neither),
                sample_rows=_sample(df, neither, ["account_code", "debit", "credit", "narration"]),
            ))
        report.checks_run.append("debit_credit_format")
    else:
        report.checks_skipped.append({
            "check": "debit_credit_format",
            "reason": "Applies to a General Ledger with mapped debit and credit columns.",
        })

    # ── 4. Invalid dates ─────────────────────────────────────────────────────
    if "date" in df.columns:
        non_blank = ~_is_blank(df["date"])
        parsed = pd.to_datetime(df["date"], errors="coerce", format="mixed")
        bad_dates = df.index[non_blank & parsed.isna()]
        if len(bad_dates):
            report.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="invalid_dates",
                title="Invalid dates",
                message=f"{len(bad_dates)} row(s) contain a date that cannot be parsed.",
                count=len(bad_dates),
                sample_rows=_sample(df, bad_dates, ["account_code", "date", "narration"]),
            ))
        blank_dates = df.index[_is_blank(df["date"])]
        if len(blank_dates):
            report.issues.append(ValidationIssue(
                severity=SEVERITY_WARNING,
                code="missing_dates",
                title="Missing dates",
                message=f"{len(blank_dates)} row(s) have no transaction date.",
                count=len(blank_dates),
                sample_rows=_sample(df, blank_dates, ["account_code", "date", "narration"]),
            ))
        report.checks_run.append("invalid_dates")
    else:
        report.checks_skipped.append({
            "check": "invalid_dates",
            "reason": "No `date` column is mapped, so dates could not be checked.",
        })

    # ── 5. Duplicate transactions ────────────────────────────────────────────
    identity = [c for c in IDENTITY_FIELDS_BY_SLOT.get(slot, []) if c in df.columns]
    # `account_code` is the minimum meaningful identity. Without it, "duplicates"
    # collapse onto an incidental column (e.g. every row sharing one narration),
    # which produces noise rather than a finding.
    if "account_code" not in identity:
        identity = []
    if identity:
        dupe_mask = df.duplicated(subset=identity, keep=False)
        dupes = df.index[dupe_mask]
        if len(dupes):
            group_count = int(df[dupe_mask].groupby(identity, dropna=False).ngroups)
            report.issues.append(ValidationIssue(
                severity=SEVERITY_WARNING,
                code="duplicate_transactions",
                title="Duplicate rows",
                message=(
                    f"{len(dupes)} row(s) across {group_count} group(s) are identical "
                    f"on {', '.join(identity)}. Possible double-posting."
                ),
                count=len(dupes),
                sample_rows=_sample(df, dupes, identity),
            ))
        report.checks_run.append("duplicate_transactions")
    else:
        report.checks_skipped.append({
            "check": "duplicate_transactions",
            "reason": "`account_code` is not mapped, so rows cannot be compared "
                      "on a meaningful identity.",
        })

    # ── 6. Invalid / unresolvable account codes ──────────────────────────────
    if "account_code" in df.columns:
        codes = df["account_code"].map(normalise_code)
        if reference_available and known_codes:
            unknown_mask = (codes != "") & (~codes.isin(known_codes))
            unknown_idx = df.index[unknown_mask]
            if len(unknown_idx):
                distinct = sorted(set(codes[unknown_mask]))
                report.issues.append(ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="invalid_account_codes",
                    title="Invalid account codes",
                    message=(
                        f"{len(distinct)} account code(s) across {len(unknown_idx)} row(s) "
                        "do not exist in the Chart of Accounts and have no confirmed "
                        "mapping: " + ", ".join(distinct[:12])
                        + (" …" if len(distinct) > 12 else "")
                    ),
                    count=len(unknown_idx),
                    sample_rows=_sample(df, unknown_idx, ["account_code", "account_name", "narration"]),
                ))
            report.checks_run.append("invalid_account_codes")
        else:
            report.checks_skipped.append({
                "check": "invalid_account_codes",
                "reason": (
                    "No reference Chart of Accounts is available, so account codes "
                    "could not be validated against a master list."
                ),
            })
            # An unverifiable upload must not be reported as clean. Downgrading
            # to WARNING keeps the overall status honest about what was skipped.
            report.issues.append(ValidationIssue(
                severity=SEVERITY_WARNING,
                code="coa_unavailable",
                title="Account validation skipped",
                message=(
                    "No reference Chart of Accounts was available, so account codes "
                    "in this file were NOT verified against a master list. Treat the "
                    "result below as incomplete."
                ),
                count=0,
            ))
    else:
        report.checks_skipped.append({
            "check": "invalid_account_codes",
            "reason": "No `account_code` column is mapped.",
        })

    # ── 7. Unmapped accounts (from coa_mapper) ───────────────────────────────
    if unmapped_codes:
        pending = [c for c in unmapped_codes if c]
        if pending:
            rows = df.index[df["account_code"].map(normalise_code).isin(pending)] \
                if "account_code" in df.columns else []
            report.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code="unmapped_accounts",
                title="Unmapped accounts",
                message=(
                    f"{len(pending)} account(s) still require a manual category: "
                    + ", ".join(pending[:12]) + (" …" if len(pending) > 12 else "")
                    + ". Assign a category in the Account Mapping table."
                ),
                count=len(rows),
                sample_rows=[{"Account Code": c} for c in pending[:ValidationIssue.SAMPLE_LIMIT]],
            ))
        report.checks_run.append("unmapped_accounts")

    # ── 8. Unbalanced journals + balance summary ─────────────────────────────
    blocks: List[Dict[str, Any]] = []

    if slot == "general_ledger" and {"debit", "credit"} <= set(df.columns):
        dr, _ = coerce_amount(df["debit"])
        cr, _ = coerce_amount(df["credit"])
        blocks.append(_balance_block("General Ledger total", dr.sum(), cr.sum()))

        group_col = next((c for c in ("voucher_no", "txn_no") if c in df.columns), None)
        if group_col:
            grouped = pd.DataFrame({"g": df[group_col].astype(str), "dr": dr, "cr": cr})
            sums = grouped.groupby("g", dropna=False)[["dr", "cr"]].sum()
            unbalanced = sums[(sums["dr"] - sums["cr"]).abs() > TOLERANCE]
            if len(unbalanced):
                report.issues.append(ValidationIssue(
                    severity=SEVERITY_ERROR,
                    code="unbalanced_journals",
                    title="Unbalanced journals",
                    message=(
                        f"{len(unbalanced)} journal(s) grouped by `{group_col}` do not "
                        "balance — debits do not equal credits."
                    ),
                    count=int(len(unbalanced)),
                    sample_rows=[
                        {
                            group_col: str(key),
                            "Debit": round(float(row["dr"]), 2),
                            "Credit": round(float(row["cr"]), 2),
                            "Difference": round(float(row["dr"] - row["cr"]), 2),
                        }
                        for key, row in unbalanced.head(ValidationIssue.SAMPLE_LIMIT).iterrows()
                    ],
                ))
            report.checks_run.append("unbalanced_journals")
        else:
            report.checks_skipped.append({
                "check": "unbalanced_journals (per voucher)",
                "reason": "Neither `voucher_no` nor `txn_no` is mapped, so journals "
                          "could not be grouped. Only the dataset total was checked.",
            })

    elif slot in ("trial_balance", "opening_trial_balance"):
        pairs = [
            ("Opening balances", "opening_debit", "opening_credit"),
            ("Period movement", "period_debit", "period_credit"),
            ("Closing balances", "closing_debit", "closing_credit"),
        ]
        for label, dcol, ccol in pairs:
            if {dcol, ccol} <= set(df.columns):
                d, _ = coerce_amount(df[dcol])
                c, _ = coerce_amount(df[ccol])
                blocks.append(_balance_block(label, d.sum(), c.sum()))
        report.checks_run.append("trial_balance_totals")

    for block in blocks:
        if block["status"] == STATUS_ERROR:
            report.issues.append(ValidationIssue(
                severity=SEVERITY_ERROR,
                code=f"unbalanced::{block['label']}",
                title="Unbalanced totals",
                message=(
                    f"{block['label']}: debits ({block['debit']:,.2f}) do not equal "
                    f"credits ({block['credit']:,.2f}). Difference "
                    f"{block['difference']:,.2f}."
                ),
                count=1,
            ))

    if blocks:
        report.balance = {"blocks": blocks}

    # ── Overall status ───────────────────────────────────────────────────────
    worst = max((_SEVERITY_RANK[i.severity] for i in report.issues), default=-1)
    report.status = {
        2: STATUS_ERROR,
        1: STATUS_WARNING,
        0: STATUS_PASS,
        -1: STATUS_PASS,
    }[worst]

    return report
