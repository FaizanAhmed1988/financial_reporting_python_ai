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
        uploaded_file = st.file_uploader(
            "Choose a file to upload",
            type=["xlsx", "xls", "csv"],
            key="upload_file",
            help="Supports .xlsx, .xls, and .csv formats.",
        )

    if uploaded_file is None:
        st.info("👆 Upload a file above to begin.")
        return

    # ── Parse file ────────────────────────────────────────────────────────────
    name = uploaded_file.name
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

    st.info(
        "🔒 **Phase 1 complete:** File has been previewed and mapped but not yet "
        "processed into the financial engine. Processing occurs in Phase 2 (COA Validation) "
        "and Phase 3 (Engine Integration)."
    )
