"""
Phase 1 - Source Data Audit Script
Inspects every sheet of GL_COA_TB_Dummy_Dataset.xlsx and produces a
comprehensive accounting data-quality report.
"""

import json
import warnings
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

warnings.filterwarnings("ignore")

WORKBOOK_PATH = Path(__file__).parent.parent / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _coerce_numeric(series):
    try:
        return pd.to_numeric(series, errors="coerce")
    except Exception:
        return series


def _find_column(columns, candidates):
    """Case-insensitive fuzzy match for column name candidates."""
    col_lower = {c.lower().strip(): c for c in columns}
    for cand in candidates:
        if cand.lower().strip() in col_lower:
            return col_lower[cand.lower().strip()]
    return None


def _summary_block(df):
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing_values": df.isnull().sum().to_dict(),
        "missing_pct": (df.isnull().mean() * 100).round(2).to_dict(),
        "duplicate_rows": int(df.duplicated().sum()),
    }


# ---------------------------------------------------------------------------
# Sheet-specific inspectors
# ---------------------------------------------------------------------------

def inspect_chart_of_accounts(df):
    result = _summary_block(df)
    result["sample_rows"] = df.head(5).to_dict(orient="records")

    acct_col = _find_column(df.columns, ["Account Code","Acct No","Account No","Account Number","GL Code","Code"])
    name_col = _find_column(df.columns, ["Account Name","Account Description","Description","Name"])
    cat_col  = _find_column(df.columns, ["Category","Account Category","Type","Account Type","Classification"])
    sub_col  = _find_column(df.columns, ["Sub Category","Sub-Category","SubCategory","Sub Type"])
    dept_col = _find_column(df.columns, ["Department","Dept","Cost Center","CC"])
    curr_col = _find_column(df.columns, ["Currency","CCY","Ccy"])

    result["detected_columns"] = {
        "account_code": acct_col, "account_name": name_col,
        "category": cat_col, "sub_category": sub_col,
        "department": dept_col, "currency": curr_col,
    }
    if acct_col:
        result["total_accounts"] = int(df[acct_col].nunique())
        result["duplicate_account_codes"] = int(df[acct_col].duplicated().sum())
    if cat_col:
        result["categories"] = df[cat_col].value_counts().to_dict()
    if sub_col:
        result["sub_categories"] = df[sub_col].value_counts().to_dict()
    if dept_col:
        result["departments"] = df[dept_col].value_counts().to_dict()
    if curr_col:
        result["currencies"] = df[curr_col].value_counts().to_dict()
    return result


def inspect_general_ledger(df):
    result = _summary_block(df)
    result["sample_rows"] = df.head(5).to_dict(orient="records")

    acct_col = _find_column(df.columns, ["Account Code","Acct No","Account No","Account Number","GL Code","Code"])
    name_col = _find_column(df.columns, ["Account Name","Description","Account Description","Name","Narration"])
    date_col = _find_column(df.columns, ["Date","Transaction Date","Txn Date","Posting Date","GL Date"])
    dr_col   = _find_column(df.columns, ["Debit","Dr","Debit Amount","Dr Amount"])
    cr_col   = _find_column(df.columns, ["Credit","Cr","Credit Amount","Cr Amount"])
    dept_col = _find_column(df.columns, ["Department","Dept","Cost Center","CC"])
    curr_col = _find_column(df.columns, ["Currency","CCY","Ccy"])
    ref_col  = _find_column(df.columns, ["Reference","Ref","Voucher No","Journal No","Txn ID","Transaction ID"])

    result["detected_columns"] = {
        "account_code": acct_col, "account_name": name_col,
        "date": date_col, "debit": dr_col, "credit": cr_col,
        "department": dept_col, "currency": curr_col, "reference": ref_col,
    }

    if dr_col:
        df = df.copy()
        df["_debit_num"] = _coerce_numeric(df[dr_col])
    if cr_col:
        df["_credit_num"] = _coerce_numeric(df[cr_col])

    if dr_col and cr_col:
        total_dr = float(df["_debit_num"].sum())
        total_cr = float(df["_credit_num"].sum())
        result["total_debits"]  = round(total_dr, 2)
        result["total_credits"] = round(total_cr, 2)
        result["debit_credit_difference"] = round(total_dr - total_cr, 2)
        result["debit_credit_balanced"]   = abs(total_dr - total_cr) < 0.01

    if date_col:
        try:
            parsed = pd.to_datetime(df[date_col], errors="coerce")
            result["date_range"] = {"min": str(parsed.min()), "max": str(parsed.max())}
            result["unparseable_dates"] = int(parsed.isnull().sum())
        except Exception as e:
            result["date_parse_error"] = str(e)

    if acct_col:
        result["unique_accounts_in_gl"] = int(df[acct_col].nunique())
    if dept_col:
        result["departments"] = df[dept_col].value_counts().to_dict()
    if curr_col:
        result["currencies"] = df[curr_col].value_counts().to_dict()

    if dr_col and cr_col and "_debit_num" in df.columns and "_credit_num" in df.columns:
        both = df[(df["_debit_num"] > 0) & (df["_credit_num"] > 0)]
        result["entries_with_both_dr_and_cr"] = len(both)

    return result


def inspect_trial_balance(df, label):
    result = _summary_block(df)
    result["label"] = label
    result["sample_rows"] = df.head(5).to_dict(orient="records")

    acct_col = _find_column(df.columns, ["Account Code","Acct No","Account No","Account Number","GL Code","Code"])
    name_col = _find_column(df.columns, ["Account Name","Description","Account Description","Name"])
    dr_col   = _find_column(df.columns, ["Debit","Dr","Debit Balance","Dr Balance","Debit Amount"])
    cr_col   = _find_column(df.columns, ["Credit","Cr","Credit Balance","Cr Balance","Credit Amount"])
    bal_col  = _find_column(df.columns, ["Balance","Net Balance","Closing Balance","Opening Balance"])
    cat_col  = _find_column(df.columns, ["Category","Account Category","Type","Account Type"])

    result["detected_columns"] = {
        "account_code": acct_col, "account_name": name_col,
        "debit": dr_col, "credit": cr_col,
        "balance": bal_col, "category": cat_col,
    }

    df = df.copy()
    if dr_col:
        df["_debit_num"] = _coerce_numeric(df[dr_col])
    if cr_col:
        df["_credit_num"] = _coerce_numeric(df[cr_col])

    if dr_col and cr_col:
        total_dr = float(df["_debit_num"].sum())
        total_cr = float(df["_credit_num"].sum())
        result["total_debits"]  = round(total_dr, 2)
        result["total_credits"] = round(total_cr, 2)
        result["debit_credit_difference"] = round(total_dr - total_cr, 2)
        result["debit_credit_balanced"]   = abs(total_dr - total_cr) < 0.01

    if bal_col:
        df["_bal_num"] = _coerce_numeric(df[bal_col])
        result["net_balance"] = round(float(df["_bal_num"].sum()), 2)

    if acct_col:
        result["total_accounts"] = int(df[acct_col].nunique())
    if cat_col:
        result["categories"] = df[cat_col].value_counts().to_dict()

    return result


# ---------------------------------------------------------------------------
# Cross-sheet validation
# ---------------------------------------------------------------------------

def cross_validate(sheets):
    findings = {}
    gl_key  = next((k for k in sheets if "ledger" in k.lower() or ("gl" in k.lower() and "gl" == k.lower().strip())), None)
    if not gl_key:
        gl_key = next((k for k in sheets if "ledger" in k.lower()), None)
    otb_key = next((k for k in sheets if "open" in k.lower() and ("trial" in k.lower() or "balance" in k.lower() or "tb" in k.lower())), None)
    ctb_key = next((k for k in sheets if k != otb_key and ("clos" in k.lower() or "trial" in k.lower() or "tb" in k.lower())), None)

    findings["sheet_keys_used"] = {
        "general_ledger": gl_key, "opening_trial_bal": otb_key, "closing_trial_bal": ctb_key,
    }

    if not (gl_key and otb_key and ctb_key):
        findings["warning"] = "Could not auto-detect all three sheets for cross-validation."
        return findings

    gl  = sheets[gl_key].copy()
    otb = sheets[otb_key].copy()
    ctb = sheets[ctb_key].copy()

    def dc(df, cands): return _find_column(df.columns, cands)

    gl_acct = dc(gl,  ["Account Code","Acct No","Account No","GL Code","Code"])
    gl_dr   = dc(gl,  ["Debit","Dr","Debit Amount"])
    gl_cr   = dc(gl,  ["Credit","Cr","Credit Amount"])
    ob_acct = dc(otb, ["Account Code","Acct No","Account No","GL Code","Code"])
    ob_dr   = dc(otb, ["Debit","Dr","Debit Balance","Dr Balance","Debit Amount"])
    ob_cr   = dc(otb, ["Credit","Cr","Credit Balance","Cr Balance","Credit Amount"])
    ob_bal  = dc(otb, ["Balance","Opening Balance","Net Balance"])
    cb_acct = dc(ctb, ["Account Code","Acct No","Account No","GL Code","Code"])
    cb_dr   = dc(ctb, ["Debit","Dr","Debit Balance","Dr Balance","Debit Amount"])
    cb_cr   = dc(ctb, ["Credit","Cr","Credit Balance","Cr Balance","Credit Amount"])
    cb_bal  = dc(ctb, ["Balance","Closing Balance","Net Balance"])

    gl_net = ob_net = cb_net = None

    if gl_acct and gl_dr and gl_cr:
        gl["_dr"] = _coerce_numeric(gl[gl_dr])
        gl["_cr"] = _coerce_numeric(gl[gl_cr])
        gl["_net"] = gl["_dr"].fillna(0) - gl["_cr"].fillna(0)
        gl_net = gl.groupby(gl_acct)["_net"].sum().rename("gl_net_movement")

    if ob_acct and ob_dr and ob_cr:
        otb["_dr"] = _coerce_numeric(otb[ob_dr])
        otb["_cr"] = _coerce_numeric(otb[ob_cr])
        otb["_ob"] = otb["_dr"].fillna(0) - otb["_cr"].fillna(0)
        ob_net = otb.groupby(ob_acct)["_ob"].sum().rename("opening_balance")
    elif ob_acct and ob_bal:
        otb["_ob"] = _coerce_numeric(otb[ob_bal])
        ob_net = otb.groupby(ob_acct)["_ob"].sum().rename("opening_balance")

    if cb_acct and cb_dr and cb_cr:
        ctb["_dr"] = _coerce_numeric(ctb[cb_dr])
        ctb["_cr"] = _coerce_numeric(ctb[cb_cr])
        ctb["_cb"] = ctb["_dr"].fillna(0) - ctb["_cr"].fillna(0)
        cb_net = ctb.groupby(cb_acct)["_cb"].sum().rename("closing_balance")
    elif cb_acct and cb_bal:
        ctb["_cb"] = _coerce_numeric(ctb[cb_bal])
        cb_net = ctb.groupby(cb_acct)["_cb"].sum().rename("closing_balance")

    if gl_net is not None and ob_net is not None and cb_net is not None:
        recon = pd.concat([ob_net, gl_net, cb_net], axis=1).fillna(0)
        recon["expected_cb"] = recon["opening_balance"] + recon["gl_net_movement"]
        recon["variance"] = (recon["expected_cb"] - recon["closing_balance"]).round(2)
        recon["reconciled"] = recon["variance"].abs() < 0.01
        unreconciled = recon[~recon["reconciled"]]
        findings["ob_plus_gl_equals_cb"] = {
            "total_accounts_checked": len(recon),
            "reconciled_count": int(recon["reconciled"].sum()),
            "unreconciled_count": len(unreconciled),
            "total_variance": round(float(recon["variance"].sum()), 2),
            "all_reconciled": len(unreconciled) == 0,
        }
        if not unreconciled.empty:
            findings["unreconciled_accounts"] = unreconciled.reset_index().to_dict(orient="records")
    else:
        findings["reconciliation_skip"] = "Missing columns prevented OB+GL=CB check."

    return findings


# ---------------------------------------------------------------------------
# Main audit runner
# ---------------------------------------------------------------------------

def run_audit(workbook_path):
    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    sheet_names = wb.sheetnames
    wb.close()

    print(f"\n{'='*70}")
    print(f"PHASE 1 - SOURCE DATA AUDIT")
    print(f"Workbook : {workbook_path.name}")
    print(f"Sheets   : {sheet_names}")
    print(f"{'='*70}\n")

    all_dfs = {}
    for name in sheet_names:
        df = pd.read_excel(workbook_path, sheet_name=name, dtype=str)
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].str.strip()
        all_dfs[name] = df

    report = {
        "workbook": str(workbook_path.name),
        "sheet_names": sheet_names,
        "sheet_details": {},
        "cross_validation": {},
        "data_quality_flags": [],
    }

    for name, df in all_dfs.items():
        print(f"  Inspecting sheet: '{name}'  ({len(df)} rows x {len(df.columns)} cols)")
        nm = name.lower()
        if "chart" in nm or "coa" in nm or ("account" in nm and "gl" not in nm and "ledger" not in nm and "trial" not in nm and "balance" not in nm):
            detail = inspect_chart_of_accounts(df)
            detail["sheet_type"] = "Chart of Accounts"
        elif "ledger" in nm or nm.strip() == "gl":
            detail = inspect_general_ledger(df)
            detail["sheet_type"] = "General Ledger"
        elif "open" in nm and ("trial" in nm or "balance" in nm or "tb" in nm):
            detail = inspect_trial_balance(df, "Opening Trial Balance")
            detail["sheet_type"] = "Opening Trial Balance"
        elif "trial" in nm or "tb" in nm or "balance" in nm:
            detail = inspect_trial_balance(df, "Closing / Trial Balance")
            detail["sheet_type"] = "Closing / Trial Balance"
        else:
            detail = _summary_block(df)
            detail["sheet_type"] = "Unknown / Other"
            detail["sample_rows"] = df.head(5).to_dict(orient="records")

        report["sheet_details"][name] = detail

    print("\n  Running cross-sheet accounting validation...")
    report["cross_validation"] = cross_validate(all_dfs)

    flags = []
    for sheet, detail in report["sheet_details"].items():
        if detail.get("duplicate_rows", 0) > 0:
            flags.append(f"[{sheet}] {detail['duplicate_rows']} duplicate row(s).")
        mv = {k: v for k, v in detail.get("missing_values", {}).items() if v > 0}
        if mv:
            flags.append(f"[{sheet}] Missing values: {mv}")
        if detail.get("debit_credit_balanced") is False:
            flags.append(f"[{sheet}] *** DR/CR IMBALANCE: Delta = {detail.get('debit_credit_difference')}")
        if detail.get("entries_with_both_dr_and_cr", 0) > 0:
            flags.append(f"[{sheet}] {detail['entries_with_both_dr_and_cr']} entries have BOTH Dr AND Cr populated.")
        if detail.get("duplicate_account_codes", 0) > 0:
            flags.append(f"[{sheet}] {detail['duplicate_account_codes']} duplicate account code(s).")
        if detail.get("unparseable_dates", 0) > 0:
            flags.append(f"[{sheet}] {detail['unparseable_dates']} unparseable date(s).")

    cv = report["cross_validation"]
    if cv.get("ob_plus_gl_equals_cb", {}).get("all_reconciled") is False:
        unr = cv["ob_plus_gl_equals_cb"]["unreconciled_count"]
        var = cv["ob_plus_gl_equals_cb"]["total_variance"]
        flags.append(f"[Cross-Validation] *** {unr} account(s) where OB+GL != CB. Total variance={var}")

    report["data_quality_flags"] = flags if flags else ["No data quality issues detected."]
    return report


if __name__ == "__main__":
    report = run_audit(WORKBOOK_PATH)

    print(f"\n{'='*70}")
    print("SHEET SUMMARY")
    print(f"{'='*70}")
    for sheet, detail in report["sheet_details"].items():
        print(f"\n-- Sheet: '{sheet}' [{detail.get('sheet_type','?')}]")
        print(f"   Rows: {detail['rows']}  |  Columns: {detail['columns']}")
        print(f"   Column names : {detail['column_names']}")
        print(f"   Dtypes       : {detail['dtypes']}")
        mv = {k: v for k, v in detail.get("missing_values", {}).items() if v > 0}
        print(f"   Missing vals : {mv or 'None'}")
        print(f"   Dup rows     : {detail.get('duplicate_rows', 0)}")
        if "total_debits" in detail:
            print(f"   Total Debits  : {float(detail['total_debits']):>20,.2f}")
            print(f"   Total Credits : {float(detail['total_credits']):>20,.2f}")
            bal = "BALANCED" if detail["debit_credit_balanced"] else "*** IMBALANCED ***"
            print(f"   Difference    : {float(detail['debit_credit_difference']):>20,.2f}  [{bal}]")
        if "detected_columns" in detail:
            print(f"   Detected cols : {detail['detected_columns']}")
        if "categories" in detail:
            print(f"   Categories    : {detail['categories']}")
        if "date_range" in detail:
            print(f"   Date range    : {detail['date_range']}")
        if "departments" in detail:
            print(f"   Departments   : {detail['departments']}")
        if "currencies" in detail:
            print(f"   Currencies    : {detail['currencies']}")

    print(f"\n{'='*70}")
    print("CROSS-SHEET ACCOUNTING VALIDATION")
    print(f"{'='*70}")
    print(json.dumps(report["cross_validation"], indent=2, default=str))

    print(f"\n{'='*70}")
    print("DATA QUALITY FLAGS")
    print(f"{'='*70}")
    for f in report["data_quality_flags"]:
        print(f"  {f}")

    out_path = Path(__file__).parent.parent / "reports" / "phase1_audit_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fp:
        json.dump(report, fp, indent=2, default=str)
    print(f"\nFull JSON report saved: {out_path}")
