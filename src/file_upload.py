"""
src/file_upload.py
==================
Streamlit UI component for the Upload Financial Data section.
Handles: upload, preview, auto-detection, and column-mapping display/override.

PHASE 1 SCOPE ONLY: No data is pushed into the financial engine here.
All state is stored in st.session_state for use in Phase 2/3.
"""

from __future__ import annotations
import io
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

USER_HINT_OPTIONS = ["Auto Detect"] + [k for k in FILE_TYPE_SIGNATURES if k != "Other / Unknown"] + ["Other / Unknown"]


def _read_uploaded_file(uploaded_file) -> tuple[Optional[pd.DataFrame], str, list[str], Optional[str]]:
    """
    Parse the uploaded file into a DataFrame.
    Returns (df, file_type_ext, sheet_names, selected_sheet).
    """
    name = uploaded_file.name
    ext = name.rsplit(".", 1)[-1].lower()

    if ext == "csv":
        df = pd.read_csv(uploaded_file, dtype=str)
        return df, "csv", [], None

    elif ext in ("xlsx", "xls"):
        raw = pd.ExcelFile(uploaded_file)
        sheet_names = raw.sheet_names
        return None, ext, sheet_names, None  # Caller handles sheet selection

    return None, ext, [], None


def render_upload_section():
    """
    Renders the full Upload Financial Data section inside the Streamlit app.
    """
    st.header("📂 Upload Financial Data")
    st.markdown(
        "Upload a General Ledger, Trial Balance, Chart of Accounts, or any other "
        "accounting export. The system will auto-detect the file type and map the columns. "
        "No data is processed into the financial engine at this stage."
    )

    # ── User hint dropdown ────────────────────────────────────────────────────
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
            else:
                selected_sheet = st.selectbox(
                    "📋 Multi-sheet file detected — select a sheet to preview:",
                    options=sheet_names,
                    key="upload_sheet_select",
                )

            df = pd.read_excel(excel_file, sheet_name=selected_sheet, dtype=str)

            # Auto-strip 3-row decorative headers if top row looks non-tabular
            for skip in range(6):
                candidate = pd.read_excel(
                    excel_file, sheet_name=selected_sheet,
                    dtype=str, header=skip
                )
                mapper_probe = ConfigurableColumnMapper()
                probe_map = mapper_probe.build_rename_map(list(candidate.columns))
                if len(probe_map) >= 2:
                    df = candidate
                    break

        except Exception as e:
            st.error(f"Could not read Excel file: {e}")
            return

    if df is None or df.empty:
        st.warning("The selected sheet appears to be empty.")
        return

    # Strip whitespace from all column names
    df.columns = [str(c).strip() for c in df.columns]
    # Drop fully empty rows
    df = df.dropna(how="all").reset_index(drop=True)

    # ── Detection ─────────────────────────────────────────────────────────────
    mapper = ConfigurableColumnMapper()
    detected_type, confidence, rename_map = detect_file_type(df, mapper, user_hint)
    quality_status = get_file_quality_status(df, rename_map)
    confidence_pct = f"{confidence * 100:.1f}%"

    # ── File Metadata card ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 File Summary")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("File Name", name)
    m2.metric("Format", ext.upper())
    if selected_sheet:
        m3.metric("Sheet", selected_sheet)
    else:
        m3.metric("Type", "CSV")
    m4.metric("Rows × Columns", f"{len(df):,} × {len(df.columns)}")

    d1, d2, d3 = st.columns(3)
    d1.metric("Detected Type", detected_type)
    d2.metric("Confidence Score", confidence_pct)
    d3.metric("Data Quality", quality_status)

    # Confidence bar
    bar_color = "green" if confidence >= 0.7 else "orange" if confidence >= 0.4 else "red"
    st.markdown(
        f"""
        <div style="background:#e0e0e0;border-radius:8px;height:14px;width:100%;margin-bottom:12px;">
          <div style="background:{bar_color};border-radius:8px;height:14px;width:{confidence*100:.0f}%;
                      transition:width 0.4s ease;"></div>
        </div>
        <p style="font-size:0.82rem;color:#666;margin-top:-6px;">
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
        "field names. You can override any mapping using the **Override Mapping** dropdown. "
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

    # ── Save to session state ─────────────────────────────────────────────────
    renamed_df, override_map = apply_user_overrides(df, edited_mapping)

    st.session_state["uploaded_df_raw"]     = df
    st.session_state["uploaded_df_mapped"]  = renamed_df
    st.session_state["uploaded_override_map"] = override_map
    st.session_state["uploaded_file_name"]  = name
    st.session_state["uploaded_detected_type"] = detected_type
    st.session_state["uploaded_confidence"] = confidence
    st.session_state["uploaded_sheet"]      = selected_sheet

    # ── Status banner ─────────────────────────────────────────────────────────
    unresolved = edited_mapping[edited_mapping["Status"].str.startswith("❌")]
    if unresolved.empty:
        st.success(
            f"✅ Column mapping complete. **{len(override_map)}** columns mapped. "
            "This configuration is saved in session and ready for Phase 2 validation."
        )
    else:
        st.warning(
            f"⚠️ **{len(unresolved)} required column(s) are unresolved**. "
            "Please use the Override Mapping dropdowns above to assign them before proceeding."
        )
        st.dataframe(unresolved[["Source Column", "Override Mapping", "Status"]],
                     use_container_width=True, hide_index=True)

    st.info(
        "🔒 **Phase 1 complete:** File has been previewed and mapped but not yet "
        "processed into the financial engine. Processing will occur in Phase 2 (COA Validation) "
        "and Phase 3 (Engine Integration)."
    )
