"""
src/file_upload.py
==================
Streamlit UI component for the Upload Financial Data section.
Handles: upload, preview, auto-detection, and column-mapping display/override.

PHASE 1 SCOPE ONLY: No data is pushed into the financial engine here.
All state is stored in st.session_state["uploads"][slot] for use in Phase 2/3.

Session state structure (keyed by slot = detected_type slug):
  st.session_state["uploads"] = {
      "general_ledger": {
          "df_raw":        pd.DataFrame,
          "df_mapped":     pd.DataFrame,
          "override_map":  dict,
          "file_name":     str,
          "detected_type": str,
          "confidence":    float,
          "sheet":         str | None,
      },
      "trial_balance":    { ... },
      "chart_of_accounts": { ... },
      ...
  }
"""

from __future__ import annotations
from typing import Optional

import pandas as pd
import streamlit as st

from src.data_loader import ConfigurableColumnMapper
from src.file_detector import detect_file_type, get_file_quality_status, FILE_TYPE_SIGNATURES
from src.column_mapper import (
    generate_mapping_dataframe,
    apply_user_overrides,
    ALL_CANONICAL_OPTIONS,
)
from src.coa_mapper import (
    build_coa_comparison,
    confirm_mappings,
    known_account_codes,
    load_reference_coa,
    load_user_mappings,
    make_source_key,
    save_user_mappings,
    CATEGORY_OPTIONS,
    MAPPING_REQUIRED,
    MISSING_CODE_LABEL,
    STATUS_MATCHED,
    STATUS_NEW,
    STATUS_UNMAPPED,
)
from src.dataset_manager import (
    APPENDABLE_SLOTS,
    DATASET_MODES,
    MODE_APPEND,
    MODE_SEPARATE,
    ORIGINAL_DATASET_NAME,
    build_appended_dataset,
    build_separate_dataset,
    compute_statements,
    dataset_names,
    detect_duplicates,
    register as register_dataset,
)
from src.coa_mapper import get_remembered
import src.upload_history as uh
from src.security import sanitize_dataframe
from src.validation_engine import (
    validate_dataset,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    STATUS_ERROR,
    STATUS_PASS,
    STATUS_WARNING,
)

USER_HINT_OPTIONS = (
    ["Auto Detect"]
    + [k for k in FILE_TYPE_SIGNATURES if k != "Other / Unknown"]
    + ["Other / Unknown"]
)

# Slug mapping for session state keys (safe for dict keys)
_TYPE_SLUG = {
    "General Ledger":        "general_ledger",
    "Trial Balance":         "trial_balance",
    "Chart of Accounts":     "chart_of_accounts",
    "Opening Trial Balance": "opening_trial_balance",
    "Bank Statement":        "bank_statement",
    "Other / Unknown":       "other",
}


def _ensure_uploads_state():
    """Initialise the uploads dict in session state if not already present."""
    if "uploads" not in st.session_state:
        st.session_state["uploads"] = {}


def get_uploaded_slot(slot_key: str) -> Optional[dict]:
    """
    Public helper for other modules (UP2, UP3) to retrieve a specific
    uploaded and mapped dataset by slot key.

    Parameters
    ----------
    slot_key : str  e.g. "general_ledger", "trial_balance", "chart_of_accounts"

    Returns
    -------
    dict with keys: df_raw, df_mapped, override_map, file_name, detected_type,
                    confidence, sheet
    or None if nothing has been uploaded to that slot yet.
    """
    _ensure_uploads_state()
    return st.session_state["uploads"].get(slot_key)


def render_upload_section():
    """
    Renders the full Upload Financial Data section inside the Streamlit app.

    Multi-sheet handling:
    - Single-sheet files: auto-selected silently.
    - Multi-sheet files: user picks a sheet via selectbox.
    - Each distinct detected type is saved independently in
      st.session_state["uploads"][slot], so a user can process the GL
      sheet and the TB sheet from the same workbook as separate slots.

    Phase 1 scope: display, preview, detection, and mapping only.
    No data enters the financial engine.
    """
    _ensure_uploads_state()

    st.header("📂 Upload Financial Data")
    st.markdown(
        "Upload a General Ledger, Trial Balance, Chart of Accounts, or any other "
        "accounting export. The system will auto-detect the file type and map the columns. "
        "**Each file type is saved to its own slot** — you can process a GL and a TB "
        "separately without overwriting each other. No data enters the financial engine "
        "at this stage."
    )

    # ── Currently stored uploads summary ─────────────────────────────────────
    stored = st.session_state["uploads"]
    if stored:
        with st.expander(f"📦 Currently stored uploads ({len(stored)} slot(s))", expanded=False):
            for slot, info in stored.items():
                st.markdown(
                    f"- **{info['detected_type']}** — `{info['file_name']}`"
                    + (f" / Sheet: `{info['sheet']}`" if info.get("sheet") else "")
                    + f" — {len(info['df_raw'])} rows, confidence {info['confidence']*100:.0f}%"
                )

    st.markdown("---")

    # ── User hint + uploader ─────────────────────────────────────────────────
    col_hint, col_upload = st.columns([1, 2])
    with col_hint:
        user_hint = st.selectbox(
            "File Type Hint",
            options=USER_HINT_OPTIONS,
            index=0,
            help="Choose 'Auto Detect' to let the system determine the file type, or select manually to override.",
            key="upload_hint",
        )
    with col_upload:
        uploaded_files = st.file_uploader(
            "Choose file(s) to upload",
            type=["xlsx", "xls", "csv"],
            key="upload_file",
            accept_multiple_files=True,
            help="Supports .xlsx, .xls, and .csv. Select several files at once "
                 "(for example one General Ledger per month) and work through "
                 "them one at a time below.",
        )

    if not uploaded_files:
        st.info("👆 Upload one or more files above to begin.")
        render_history_panel()
        return

    # ── UP4: pick which staged file to work on ───────────────────────────────
    # Each file still goes through the identical single-file pipeline below;
    # multi-select only stages them so a monthly batch can be worked through
    # without re-picking files from disk each time.
    if len(uploaded_files) > 1:
        st.markdown("#### 📚 Staged files")
        staged = pd.DataFrame([
            {"File": f.name, "Size (KB)": f"{len(f.getvalue())/1024:,.1f}"}
            for f in uploaded_files
        ])
        st.dataframe(staged, use_container_width=True, hide_index=True)
        st.caption(
            f"{len(uploaded_files)} files staged. Work through them one at a time — "
            "each is detected, mapped, validated and processed on its own. To build "
            "one combined dataset from a monthly batch, process the first file, then "
            'process each remaining file with **"Add to Existing Dataset"** targeting '
            "the dataset the previous file created."
        )
        chosen = st.selectbox(
            "File to work on",
            options=[f.name for f in uploaded_files],
            key="upload_active_file",
        )
        uploaded_file = next(f for f in uploaded_files if f.name == chosen)
    else:
        uploaded_file = uploaded_files[0]

    # ── Parse file ────────────────────────────────────────────────────────────
    name = uploaded_file.name
    file_bytes = uploaded_file.getvalue()
    file_hash = uh.fingerprint(file_bytes)
    ext = name.rsplit(".", 1)[-1].lower()
    df: Optional[pd.DataFrame] = None
    selected_sheet: Optional[str] = None

    if ext == "csv":
        try:
            df = pd.read_csv(uploaded_file, dtype=str)
        except Exception as e:
            st.error(f"Could not read CSV: {e}")
            return

    elif ext in ("xlsx", "xls"):
        try:
            excel_file = pd.ExcelFile(uploaded_file)
            sheet_names = excel_file.sheet_names

            if len(sheet_names) == 1:
                selected_sheet = sheet_names[0]
                st.caption(f"Single-sheet workbook — using sheet: **{selected_sheet}**")
            else:
                st.info(
                    f"📋 **Multi-sheet workbook detected** ({len(sheet_names)} sheets). "
                    "Select one sheet below to preview and map. You can come back and "
                    "select a different sheet to process it as a separate slot."
                )
                selected_sheet = st.selectbox(
                    "Select sheet to analyse:",
                    options=sheet_names,
                    key="upload_sheet_select",
                )

            # Header probe: scan up to 6 rows to find the real header
            df = None
            for skip in range(6):
                candidate = pd.read_excel(
                    excel_file, sheet_name=selected_sheet, dtype=str, header=skip
                )
                candidate.columns = [str(c).strip() for c in candidate.columns]
                mapper_probe = ConfigurableColumnMapper()
                probe_map = mapper_probe.build_rename_map(list(candidate.columns))
                if len(probe_map) >= 2:
                    df = candidate
                    st.caption(
                        f"Header row auto-detected at row {skip + 1} "
                        f"({len(probe_map)} columns recognised)."
                    )
                    break

            if df is None:
                # Fall back to row 0 if nothing matched
                df = pd.read_excel(excel_file, sheet_name=selected_sheet, dtype=str)
                df.columns = [str(c).strip() for c in df.columns]
                st.warning("Could not auto-detect header row — using row 1. Use column overrides below if needed.")

        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return

    else:
        st.error(f"Unsupported file format: .{ext}")
        return

    if df is None or df.empty:
        st.warning("The selected sheet appears to be empty.")
        return

    df = df.dropna(how="all").reset_index(drop=True)

    # ── Detection ─────────────────────────────────────────────────────────────
    mapper = ConfigurableColumnMapper()
    detected_type, confidence, rename_map = detect_file_type(df, mapper, user_hint)
    quality_status = get_file_quality_status(df, rename_map)
    confidence_pct = f"{confidence * 100:.1f}%"
    slot_key = _TYPE_SLUG.get(detected_type, "other")

    # ── UP4: file-level duplicate prevention ─────────────────────────────────
    # Fingerprints the bytes, so a renamed copy is still recognised. Scoped to
    # the selected sheet: one workbook legitimately yields a GL dataset and a TB
    # dataset, which is not a duplicate. Reports, never blocks.
    history = uh.load_history()
    prior = uh.find_prior_uploads(history, file_hash, sheet=selected_sheet)
    if prior.seen:
        (st.warning if prior.was_processed else st.info)(
            f"🔁 **Already uploaded.** {prior.message()}"
        )

    # ── File Metadata card ────────────────────────────────────────────────────
    st.subheader("📊 File Summary")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("File Name", name)
    m2.metric("Format", ext.upper())
    m3.metric("Sheet", selected_sheet if selected_sheet else "N/A (CSV)")
    m4.metric("Rows × Columns", f"{len(df):,} × {len(df.columns)}")

    d1, d2, d3 = st.columns(3)
    d1.metric("Detected Type", detected_type)
    d2.metric("Confidence Score", confidence_pct)
    d3.metric("Data Quality", quality_status)

    bar_color = "green" if confidence >= 0.7 else "orange" if confidence >= 0.4 else "red"
    st.markdown(
        f"""
        <div style="background:#e0e0e0;border-radius:8px;height:14px;width:100%;margin-bottom:6px;">
          <div style="background:{bar_color};border-radius:8px;height:14px;width:{confidence*100:.0f}%;
                      transition:width 0.4s ease;"></div>
        </div>
        <p style="font-size:0.82rem;color:#666;margin-top:-2px;">
          Detection confidence: {confidence_pct} — {FILE_TYPE_SIGNATURES.get(detected_type, {}).get('description', '')}
        </p>
        """,
        unsafe_allow_html=True,
    )

    # ── Data Preview ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Data Preview (first 20 rows)")
    st.dataframe(df.head(20), use_container_width=True, hide_index=True)

    # ── Column Mapping ────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🗺️ Column Mapping")
    st.markdown(
        "The table below shows how your source columns map to the system's canonical "
        "field names. You can override any mapping in the **Override Mapping** column. "
        "Required columns marked ❌ must be resolved before this file can be processed."
    )

    mapping_df = generate_mapping_dataframe(df, rename_map, detected_type)

    edited_mapping = st.data_editor(
        mapping_df,
        column_config={
            "Source Column": st.column_config.TextColumn(
                "Source Column", disabled=True, width="medium"
            ),
            "Auto-Detected Mapping": st.column_config.TextColumn(
                "Auto-Detected", disabled=True, width="medium"
            ),
            "Override Mapping": st.column_config.SelectboxColumn(
                "Override Mapping",
                options=ALL_CANONICAL_OPTIONS,
                width="medium",
                help="Select the correct canonical field name for this source column.",
            ),
            "Required": st.column_config.TextColumn(
                "Required?", disabled=True, width="small"
            ),
            "Status": st.column_config.TextColumn(
                "Status", disabled=True, width="large"
            ),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="mapping_editor",
    )

    # ── Save to slot in session state ─────────────────────────────────────────
    renamed_df, override_map = apply_user_overrides(df, edited_mapping)

    slot_data = {
        "df_raw":        df,
        "df_mapped":     renamed_df,
        "override_map":  override_map,
        "file_name":     name,
        "detected_type": detected_type,
        "confidence":    confidence,
        "sheet":         selected_sheet,
    }
    st.session_state["uploads"][slot_key] = slot_data

    # ── Status banner ─────────────────────────────────────────────────────────
    unresolved = edited_mapping[edited_mapping["Status"].str.startswith("❌")]
    if unresolved.empty:
        st.success(
            f"✅ Saved to slot **`{slot_key}`**. "
            f"{len(override_map)} columns mapped. "
            "Switch to a different sheet above to process another data type without losing this."
        )
    else:
        st.warning(
            f"⚠️ **{len(unresolved)} required column(s) are unresolved** in slot `{slot_key}`. "
            "Use the Override Mapping dropdowns above to assign them."
        )
        st.dataframe(
            unresolved[["Source Column", "Override Mapping", "Status"]],
            use_container_width=True,
            hide_index=True,
        )

    # ── UP2: COA mapping, validation and review ──────────────────────────────
    render_review_screen(
        slot_key=slot_key,
        df_mapped=renamed_df,
        file_name=name,
        detected_type=detected_type,
        file_hash=file_hash,
        sheet=selected_sheet,
        confidence=confidence,
    )

    render_history_panel()


# ============================================================
# UP2 — COA MAPPING, VALIDATION & USER REVIEW SCREEN
# ============================================================

_SEVERITY_RENDER = {
    SEVERITY_ERROR:   ("⛔", st.error),
    SEVERITY_WARNING: ("⚠️", st.warning),
}


def _render_status_banner(status: str, slot_key: str):
    """Overall PASS / WARNING / ERROR banner for the validation result."""
    if status == STATUS_PASS:
        st.success(
            f"✅ **PASS** — slot `{slot_key}` passed every check that could be run."
        )
    elif status == STATUS_WARNING:
        st.warning(
            f"⚠️ **WARNING** — slot `{slot_key}` is usable but has findings that "
            "need a human review before processing."
        )
    else:
        st.error(
            f"⛔ **ERROR** — slot `{slot_key}` has blocking issues. It must not be "
            "processed into the financial engine until they are resolved."
        )


def _render_issue_list(issues, empty_message: str):
    """Render a list of ValidationIssue objects with their sample rows."""
    if not issues:
        st.success(empty_message)
        return
    for issue in issues:
        icon, _ = _SEVERITY_RENDER.get(issue.severity, ("•", st.info))
        with st.expander(
            f"{icon} {issue.title} — {issue.message[:110]}"
            + ("…" if len(issue.message) > 110 else ""),
            expanded=False,
        ):
            st.markdown(f"**{issue.message}**")
            if issue.count:
                st.caption(f"Rows affected: {issue.count}")
            sample = issue.sample_table
            if not sample.empty:
                st.caption("Sample (first 10):")
                st.dataframe(sample, use_container_width=True, hide_index=True)


def render_review_screen(
    slot_key: str,
    df_mapped: pd.DataFrame,
    file_name: str,
    detected_type: str,
    file_hash: str = "",
    sheet: Optional[str] = None,
    confidence: Optional[float] = None,
):
    """
    UP2 review screen — COA mapping, data validation, and the user's decision point.

    Renders, for the mapped upload currently in `slot_key`:
      • Data Preview (canonical columns, post-mapping)
      • Validation Results (PASS / WARNING / ERROR + debit/credit summary)
      • Account Mapping table (Matched / New / Unmapped / Duplicate)
      • Errors and Warnings lists
      • A "Process File" button

    NOTHING here pushes data into the financial engine — that is UP3. The button
    confirms intent only.
    """
    st.markdown("---")
    st.subheader("🧾 Review & Validate")
    st.markdown(
        "Your file is mapped but **not yet processed**. Resolve any account "
        "mappings and validation errors below, then confirm."
    )

    # ── Reference COA: live engine COA → coa_classified.csv → unavailable ────
    reference_coa, ref_available, ref_message = load_reference_coa(
        st.session_state.get("engine_coa_classified")
    )
    if ref_available:
        st.caption(f"📘 {ref_message}")
    else:
        st.warning(f"📘 {ref_message}")

    # ── COA comparison against the persisted user mappings ──────────────────
    store = load_user_mappings()
    source_key = make_source_key(file_name, slot_key)
    comparison = build_coa_comparison(
        df_mapped=df_mapped,
        slot=slot_key,
        reference_coa=reference_coa,
        store=store,
        source_key=source_key,
        reference_available=ref_available,
        reference_message=ref_message,
    )

    pending_codes = [
        c for c in comparison.requires_mapping.get("Account Code", pd.Series(dtype=str))
    ]
    # Count only accounts a user can actually act on. comparison.summary's
    # Unmapped total also includes the "rows with no account code" pseudo-entry,
    # which no dropdown can fix — it is reported under Errors instead.
    fixable_count = len(pending_codes)

    # ── Validation ──────────────────────────────────────────────────────────
    report = validate_dataset(
        df_mapped=df_mapped,
        slot=slot_key,
        known_codes=known_account_codes(reference_coa, store, source_key),
        reference_available=ref_available,
        unmapped_codes=pending_codes,
    )

    _render_status_banner(report.status, slot_key)

    tab_preview, tab_validation, tab_mapping, tab_errors, tab_warnings = st.tabs([
        "📄 Data Preview",
        "✅ Validation Results",
        f"🗂️ Account Mapping ({fixable_count} to fix)",
        f"⛔ Errors ({len(report.errors)})",
        f"⚠️ Warnings ({len(report.warnings)})",
    ])

    # ── Tab 1: Data Preview (mapped/canonical, distinct from UP1's raw view) ─
    with tab_preview:
        st.markdown(
            f"**{len(df_mapped):,} rows × {len(df_mapped.columns)} columns** — "
            "shown with canonical column names after your mapping overrides."
        )
        st.dataframe(df_mapped.head(20), use_container_width=True, hide_index=True)
        st.caption(f"Canonical columns: `{'`, `'.join(str(c) for c in df_mapped.columns)}`")

    # ── Tab 2: Validation Results ───────────────────────────────────────────
    with tab_validation:
        st.markdown(f"#### Validation summary — {detected_type}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows", f"{report.row_count:,}")
        c2.metric("Errors", len(report.errors))
        c3.metric("Warnings", len(report.warnings))
        c4.metric("Result", report.status)

        balance_df = report.balance_table()
        if not balance_df.empty:
            st.markdown("#### Debit / Credit control totals")
            for _, row in balance_df.iterrows():
                b1, b2, b3, b4 = st.columns(4)
                b1.metric(f"{row['Check']} — Debit", f"{row['Total Debit']:,.2f}")
                b2.metric("Credit", f"{row['Total Credit']:,.2f}")
                b3.metric("Difference", f"{row['Difference']:,.2f}")
                b4.metric("Result", row["Result"])
            st.dataframe(balance_df, use_container_width=True, hide_index=True)
        else:
            st.info(
                "No debit/credit control totals apply to this file type "
                f"({detected_type})."
            )

        st.markdown("#### Checks")
        if report.checks_run:
            st.markdown("**Run:** " + ", ".join(f"`{c}`" for c in report.checks_run))
        if report.checks_skipped:
            st.markdown("**Skipped — not verified:**")
            st.dataframe(
                pd.DataFrame(report.checks_skipped).rename(
                    columns={"check": "Check", "reason": "Why it was skipped"}
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "⚠️ A skipped check is **not** a pass. These aspects of the file "
                "were never verified."
            )

    # ── Tab 3: Account Mapping ──────────────────────────────────────────────
    with tab_mapping:
        summary = comparison.summary
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Matched", summary.get(STATUS_MATCHED, 0))
        m2.metric("New", summary.get(STATUS_NEW, 0))
        m3.metric("Unmapped", summary.get(STATUS_UNMAPPED, 0))
        m4.metric("Duplicate", summary.get("Duplicate", 0))

        if not comparison.expects_unique:
            st.caption(
                "ℹ️ Duplicate account codes are expected in a General Ledger "
                "(one row per transaction), so they are not flagged here. "
                "Duplicate *rows* are reported under Warnings."
            )
        if summary.get("Rows Without Account Code"):
            st.caption(
                f"ℹ️ {summary['Rows Without Account Code']} row(s) carry no account "
                "code at all and cannot be mapped — see Errors."
            )

        if comparison.table.empty:
            st.info(
                "No account codes to compare. Map an **Account Code** column in the "
                "Column Mapping table above."
            )
        else:
            st.markdown("#### All accounts in this file")
            st.dataframe(comparison.table, use_container_width=True, hide_index=True)

            to_map = comparison.requires_mapping
            if to_map.empty:
                st.success("✅ Every account in this file is mapped.")
            else:
                st.markdown("#### ⚠️ Mapping Required")
                st.markdown(
                    f"**{len(to_map)} account(s)** are not in the Chart of Accounts "
                    "and have no confirmed category. The system will **not** guess — "
                    "choose a category for each, then save."
                )
                editor_df = to_map[
                    ["Account Code", "Account Name", "Occurrences", "Assigned Category"]
                ].copy()
                editor_df["Assigned Category"] = MAPPING_REQUIRED

                edited = st.data_editor(
                    editor_df,
                    column_config={
                        "Account Code": st.column_config.TextColumn(
                            "Account Code", disabled=True, width="small"),
                        "Account Name": st.column_config.TextColumn(
                            "Account Name", disabled=True, width="medium"),
                        "Occurrences": st.column_config.NumberColumn(
                            "Rows", disabled=True, width="small"),
                        "Assigned Category": st.column_config.SelectboxColumn(
                            "Assign Category",
                            options=CATEGORY_OPTIONS,
                            width="medium",
                            help="Asset / Liability / Equity / Revenue / COGS / Expense / Other",
                        ),
                    },
                    use_container_width=True,
                    hide_index=True,
                    num_rows="fixed",
                    key=f"coa_mapping_editor_{slot_key}",
                )

                if st.button("💾 Save Account Mappings", key=f"save_coa_{slot_key}"):
                    decisions = {
                        str(r["Account Code"]): r["Assigned Category"]
                        for _, r in edited.iterrows()
                        if r["Assigned Category"] in CATEGORY_OPTIONS
                        and r["Assigned Category"] != MAPPING_REQUIRED
                    }
                    if not decisions:
                        st.warning(
                            "No categories selected — nothing saved. Pick a category "
                            "for at least one account."
                        )
                    else:
                        names = {
                            str(r["Account Code"]): str(r["Account Name"])
                            for _, r in edited.iterrows()
                        }
                        updated, written = confirm_mappings(
                            store, source_key, slot_key, file_name, decisions, names
                        )
                        path = save_user_mappings(updated)
                        st.success(
                            f"✅ Saved {written} account mapping(s) to `{path.name}`. "
                            "They will be remembered for future uploads from this source."
                        )
                        st.rerun()

    # ── Tab 4 / 5: Errors and Warnings ──────────────────────────────────────
    with tab_errors:
        _render_issue_list(report.errors, "✅ No errors found.")

    with tab_warnings:
        _render_issue_list(report.warnings, "✅ No warnings found.")

    # ── Process File — confirmation only, no engine hand-off (UP3) ──────────
    st.markdown("---")
    st.markdown("### ▶️ Process File")

    blockers = []
    if report.errors:
        blockers.append(f"{len(report.errors)} validation error(s)")
    if not comparison.is_fully_mapped:
        blockers.append(f"{len(comparison.requires_mapping)} unmapped account(s)")

    if blockers:
        st.error(
            "Cannot process yet — resolve " + " and ".join(blockers)
            + ". Fix the items in the Errors and Account Mapping tabs above."
        )
        st.button(
            "▶️ Process File",
            disabled=True,
            key=f"process_{slot_key}",
            help="Blocked until all errors are resolved and every account is mapped.",
        )
        _record_upload(
            file_name=file_name, slot=slot_key, detected_type=detected_type,
            df=df_mapped, report=report, outcome=uh.OUTCOME_BLOCKED,
            audit=dict(file_hash=file_hash, sheet=sheet, confidence=confidence),
            notes="; ".join(blockers),
        )
    else:
        render_process_section(
            slot_key=slot_key,
            df_mapped=df_mapped,
            file_name=file_name,
            detected_type=detected_type,
            report=report,
            comparison=comparison,
            store=store,
            source_key=source_key,
            audit=dict(file_hash=file_hash, sheet=sheet, confidence=confidence),
        )


# ============================================================
# UP3 — DATASET MODE SELECTION, DUPLICATE REVIEW & ENGINE HOOKUP
# ============================================================

def _confirmed_categories(comparison, store, source_key) -> tuple[dict, dict]:
    """
    Collect the user-confirmed categories for accounts in this upload that the
    reference COA does not know, so dataset_manager can translate them into the
    engine's COA schema. Only previously confirmed decisions are returned —
    nothing is inferred here.
    """
    categories, names = {}, {}
    if comparison.table.empty:
        return categories, names
    for _, row in comparison.table.iterrows():
        code = str(row["Account Code"])
        if row["Status"] != STATUS_NEW:
            continue
        category, _scope = get_remembered(store, source_key, code)
        if category:
            categories[code] = category
            names[code] = str(row["Account Name"])
    return categories, names


def _render_duplicate_review(base, df_mapped, slot_key):
    """
    Duplicate review for an append. Returns the DataFrame of rows the user has
    chosen to append, plus a note describing what was excluded.

    Nothing is dropped automatically: the two exclusion toggles are visible,
    the resulting row count is stated before the append button, and the
    matching rows themselves are shown.
    """
    dup = detect_duplicates(base.gl, df_mapped)
    counts = dup.counts

    st.markdown("#### 🔁 Duplicate check")
    st.caption(
        f"Matched on {', '.join('`'+f+'`' for f in dup.key_fields)}"
        + (f" — corroborated by {', '.join('`'+f+'`' for f in dup.corroborating_fields)}"
           if dup.corroborating_fields else
           " — no voucher/narration column is mapped, so a core match is the strongest "
           "signal available and is reported as confirmed.")
    )

    d1, d2, d3 = st.columns(3)
    d1.metric("New Transactions", counts["New Transactions"])
    d2.metric("Possible Duplicates", counts["Possible Duplicates"])
    d3.metric("Confirmed Duplicates", counts["Confirmed Duplicates"])

    if not dup.exact_duplicates.empty:
        with st.expander(f"⛔ {len(dup.exact_duplicates)} confirmed duplicate row(s) — "
                         "identical on every matched field", expanded=True):
            st.dataframe(dup.exact_duplicates.head(50), use_container_width=True, hide_index=True)
    if not dup.possible_duplicates.empty:
        with st.expander(f"⚠️ {len(dup.possible_duplicates)} possible duplicate row(s) — "
                         "same date, account and amounts but a different voucher or "
                         "narration", expanded=True):
            st.dataframe(dup.possible_duplicates.head(50), use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    include_exact = c1.checkbox(
        f"Append the {counts['Confirmed Duplicates']} confirmed duplicate(s) anyway",
        value=False, key=f"inc_exact_{slot_key}",
        help="Leave unticked to skip rows already present in the base ledger.",
    )
    include_possible = c2.checkbox(
        f"Append the {counts['Possible Duplicates']} possible duplicate(s)",
        value=True, key=f"inc_possible_{slot_key}",
        help="These may be legitimate repeated postings. Untick to exclude them.",
    )

    parts, excluded = [dup.new_rows], []
    if include_possible:
        parts.append(dup.possible_duplicates)
    elif len(dup.possible_duplicates):
        excluded.append(f"{len(dup.possible_duplicates)} possible duplicate(s)")
    if include_exact:
        parts.append(dup.exact_duplicates)
    elif len(dup.exact_duplicates):
        excluded.append(f"{len(dup.exact_duplicates)} confirmed duplicate(s)")

    to_append = pd.concat(parts, ignore_index=True) if parts else df_mapped.iloc[0:0]
    note = (f"Append excluded {' and '.join(excluded)} after user review."
            if excluded else None)

    if to_append.empty:
        st.error(
            "Every incoming row was excluded — there is nothing to append. "
            "The base dataset already contains this data."
        )
    else:
        st.success(
            f"**{len(to_append):,} row(s) will be appended** to "
            f"`{base.name}` ({len(base.gl):,} existing rows)."
            + (f" Excluded: {' and '.join(excluded)}." if excluded else "")
        )
    return to_append, note


def render_process_section(
    slot_key, df_mapped, file_name, detected_type, report, comparison, store,
    source_key, audit=None
):
    """
    UP3 — choose how the validated upload enters the platform, then build it.

    Creates a NEW dataset in st.session_state["datasets"]. The original dataset
    is never modified: an append copies its ledger and rebuilds a trial balance
    on the copy.
    """
    if "datasets" not in st.session_state:
        st.session_state["datasets"] = {}
    registry = st.session_state["datasets"]

    if slot_key not in ("general_ledger", "trial_balance", "opening_trial_balance"):
        st.info(
            f"ℹ️ A **{detected_type}** carries no balances, so it cannot be turned "
            "into an analysable dataset. Upload a General Ledger or Trial Balance."
        )
        return

    # ── Mode selection (required) ────────────────────────────────────────
    st.markdown("#### 1. How should this data be used?")
    can_append = slot_key in APPENDABLE_SLOTS and any(
        registry[n].has_gl for n in registry
    )
    modes = list(DATASET_MODES) if can_append else [MODE_SEPARATE]

    if slot_key not in APPENDABLE_SLOTS:
        st.caption(
            f"ℹ️ *Add to Existing Dataset* is unavailable for a **{detected_type}**. "
            "Appending balances to another period's balances is not a valid "
            "accounting operation — only transaction-level ledger data can be appended."
        )
    elif not can_append:
        st.caption("ℹ️ *Add to Existing Dataset* needs a base dataset with ledger data.")

    mode = st.radio(
        "Processing mode",
        options=modes,
        index=0,
        key=f"mode_{slot_key}",
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == MODE_SEPARATE:
        st.caption(
            "Creates an isolated dataset. It will not touch, merge with, or alter "
            "the original Q1 2026 data in any way."
        )
    else:
        st.caption(
            "Appends these transactions to a **copy** of the base dataset's ledger "
            "and rebuilds its trial balance. The base dataset itself is unchanged."
        )

    # ── Target / naming ──────────────────────────────────────────────────
    st.markdown("#### 2. Name the resulting dataset")
    base = None
    if mode == MODE_APPEND:
        base_names = [n for n in dataset_names(registry) if registry[n].has_gl]
        base_name = st.selectbox(
            "Base dataset to append to", options=base_names, index=0,
            key=f"base_{slot_key}",
        )
        base = registry[base_name]
        default_name = f"{base_name} + {file_name}"
    else:
        default_name = file_name or f"{detected_type} upload"

    # The key varies with mode so switching mode re-seeds the suggested name.
    # A single fixed key would keep the value Streamlit already holds and show
    # the separate-mode default while the user is configuring an append.
    new_name = st.text_input(
        "Dataset name", value=default_name,
        key=f"dsname_{slot_key}_{'append' if mode == MODE_APPEND else 'separate'}",
        help="Shown in the sidebar Dataset selector.",
    ).strip() or default_name

    # ── Duplicate review (append only) ───────────────────────────────────
    to_append, dup_note = None, None
    if mode == MODE_APPEND and base is not None:
        st.markdown("#### 3. Review duplicates")
        to_append, dup_note = _render_duplicate_review(base, df_mapped, slot_key)

    # ── Process ──────────────────────────────────────────────────────────
    st.markdown(f"#### {'4' if mode == MODE_APPEND else '3'}. Process")
    if report.warnings:
        st.warning(
            f"{len(report.warnings)} validation warning(s) will be carried into this "
            "dataset. Review them above before relying on the output."
        )

    disabled = mode == MODE_APPEND and (to_append is None or to_append.empty)
    if st.button("▶️ Process File", type="primary", key=f"process_{slot_key}",
                 disabled=disabled):
        categories, names = _confirmed_categories(comparison, store, source_key)
        reference_coa = st.session_state.get("engine_coa_classified")
        if reference_coa is None or reference_coa.empty:
            st.error(
                "No reference Chart of Accounts is loaded, so this upload cannot be "
                "classified into a dataset."
            )
            return
        try:
            if mode == MODE_SEPARATE:
                dataset = build_separate_dataset(
                    name=new_name, slot=slot_key, df_mapped=df_mapped,
                    coa_classified=reference_coa, user_categories=categories,
                    account_names=names, file_name=file_name,
                )
            else:
                dataset = build_appended_dataset(
                    name=new_name, base=base, rows_to_append=to_append,
                    file_name=file_name, duplicate_note=dup_note,
                    user_categories=categories, account_names=names,
                )
            stored_name = register_dataset(registry, dataset)
            stmts = compute_statements(dataset)
        except Exception as exc:
            st.error(f"Could not build the dataset: {exc}")
            return

        _record_upload(
            file_name=file_name, slot=slot_key, detected_type=detected_type,
            df=df_mapped, report=report, outcome=uh.OUTCOME_PROCESSED,
            audit=audit, mode=mode, dataset_name=stored_name,
            rows_appended=(len(to_append) if mode == MODE_APPEND else len(df_mapped)),
            duplicates_excluded=(
                len(df_mapped) - len(to_append) if mode == MODE_APPEND and to_append is not None else 0
            ),
            notes=dup_note or "",
            force=True,
        )

        st.success(
            f"✅ Dataset **{stored_name}** created from `{file_name}` "
            f"({mode}). Select it in the sidebar **Dataset** dropdown to view every "
            "section recalculated for it."
        )
        if stored_name != new_name:
            st.caption(
                f"A dataset named *{new_name}* already existed, so this one was "
                f"stored as *{stored_name}* — nothing was overwritten."
            )

        pl, bs = stmts["pl_metrics"], stmts["bs_metrics"]
        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Revenue", f"{pl['Total Revenue']:,.0f}")
        r2.metric("Net Profit", f"{pl['Net Profit']:,.0f}")
        r3.metric("Total Assets", f"{bs['Total Assets']:,.0f}")
        r4.metric("Balanced", "Yes" if bs["Is Balanced"] else "No")

        if dataset.limitations:
            st.warning(f"⚠️ {len(dataset.limitations)} limitation(s) apply to this dataset:")
            for note in dataset.limitations:
                st.markdown(f"- {note}")

        st.info(
            f"🔒 The original dataset (**{ORIGINAL_DATASET_NAME}**) is untouched. "
            "Uploads only ever add new datasets to the selector."
        )


# ============================================================
# UP4 — AUDIT TRAIL RECORDING & HISTORY PANEL
# ============================================================

def _record_upload(
    file_name, slot, detected_type, df, report, outcome, audit=None,
    mode=None, dataset_name=None, rows_appended=None, duplicates_excluded=None,
    notes="", force=False,
):
    """
    Append one entry to the persisted audit trail.

    Streamlit re-runs the whole script on every interaction, so a naive call
    here would write a fresh "Blocked" row every time the user ticks a checkbox.
    Non-forced records are therefore de-duplicated per session against the
    (file, sheet, slot, outcome, status) they describe. `force=True` is used for
    genuine one-off user actions such as processing a dataset.
    """
    audit = audit or {}
    guard_key = (
        audit.get("file_hash", ""), audit.get("sheet"), slot, outcome,
        getattr(report, "status", None), dataset_name,
    )
    seen = st.session_state.setdefault("_history_guard", set())
    if not force:
        if guard_key in seen:
            return
        seen.add(guard_key)

    entry = uh.new_entry(
        file_name=file_name,
        file_hash=audit.get("file_hash", ""),
        sheet=audit.get("sheet"),
        detected_type=detected_type,
        slot=slot,
        confidence=audit.get("confidence"),
        rows=int(len(df)) if df is not None else 0,
        columns=int(len(df.columns)) if df is not None else 0,
        validation_status=getattr(report, "status", None),
        errors=len(getattr(report, "errors", []) or []),
        warnings=len(getattr(report, "warnings", []) or []),
        mode=mode,
        dataset_name=dataset_name,
        outcome=outcome,
        rows_appended=rows_appended,
        duplicates_excluded=duplicates_excluded,
        notes=notes,
    )
    try:
        uh.save_history(uh.record(uh.load_history(), entry))
    except OSError as exc:
        # An unwritable audit trail must never cost the user their upload.
        st.caption(f"⚠️ Upload history could not be written: {exc}")


def render_history_panel():
    """
    UP4 — Upload History / Audit Trail.

    Append-only record of every upload attempt: what was uploaded, how it was
    detected, how validation ended, what the user chose, and which dataset came
    out. Persisted to `data/processed/upload_history.json` so it survives a
    browser refresh.
    """
    st.markdown("---")
    history = uh.load_history()
    counts = uh.summarise(history)
    table = uh.to_dataframe(history)

    with st.expander(
        f"🧾 Upload History / Audit Trail ({counts['Total Uploads']} entr"
        f"{'y' if counts['Total Uploads'] == 1 else 'ies'})",
        expanded=False,
    ):
        if table.empty:
            st.info(
                "No uploads recorded yet. Every upload attempt — processed, "
                "blocked or previewed — will be logged here."
            )
            return

        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Total Uploads", counts["Total Uploads"])
        h2.metric("Processed", counts["Processed"])
        h3.metric("Blocked", counts["Blocked"])
        h4.metric("Distinct Files", counts["Distinct Files"])

        st.dataframe(table, use_container_width=True, hide_index=True)
        st.caption(
            "Newest first. *Fingerprint* is the first 12 characters of the file's "
            "SHA-256 content hash — identical fingerprints mean identical file "
            "contents, even under a different filename. The trail is append-only "
            "and stored in `data/processed/upload_history.json`, which is "
            "gitignored so uploaded financial data never reaches the repository."
        )
        st.download_button(
            "⬇ Download audit trail (CSV)",
            data=sanitize_dataframe(table).to_csv(index=False).encode("utf-8"),
            file_name="upload_audit_trail.csv",
            mime="text/csv",
            key="dl_audit",
        )
