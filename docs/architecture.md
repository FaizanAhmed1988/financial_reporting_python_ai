# Platform Architecture

This document outlines the architecture of the Financial Reporting AI platform. The platform is designed with scalable Python data engineering principles, ensuring modularity, extensibility, and maintainability.

## 1. Directory Structure

```text
financial_reporting_python_ai/
├── data/
│   ├── raw/                  # Source Excel files (GL, COA, TB)
│   ├── processed/            # Intermediary classified COA output
│   └── synthetic/            # Demo budget data
├── dashboard/
│   └── app.py                # Main Streamlit application (canonical UI)
├── docs/                     # Architecture, Logic, and Status documentation
├── reports/
│   └── excel/                # Exported professional Excel workbooks
├── src/                      # Core business logic and accounting engine modules
│   ├── data_loader.py        # Configurable ingestion mapping
│   ├── account_classifier.py # ML/Rule-based COA classification
│   ├── profit_loss.py        # P&L statement logic
│   ├── balance_sheet.py      # Balance Sheet logic
│   ├── cash_flow.py          # Cash Flow (Indirect Method) logic
│   ├── ratios.py             # Financial Ratios calculation
│   ├── working_capital.py    # Working Capital Analysis
│   ├── ar_analysis.py        # Accounts Receivable sub-ledger analysis
│   ├── ap_analysis.py        # Accounts Payable sub-ledger analysis
│   ├── reconciliation.py     # Bank & Balance Sheet reconciliation
│   ├── budget_vs_actual.py   # BvA analytics
│   ├── controls.py           # Automated financial control tests
│   ├── anomaly_detection.py  # AI Isolation Forest anomaly detection
│   ├── forecasting.py        # Basic trend forecasting
│   ├── scenario_analysis.py  # FP&A Scenario modeling engine
│   ├── month_end_close.py    # Dynamic month-end close checklist
│   └── reporting.py          # Excel Export module
├── tests/                    # Unit testing suite (unittest)
├── README.md                 # Project README
└── requirements.txt          # Python dependencies
```

## 2. Core Architectural Principles

### 2.1 Configurable Column Mapping (No Hardcoding)
**The Problem**: Accounting data exports rarely have uniform column names. Hardcoding `GL["Date"]` breaks the moment a user uploads a system export with `GL["Posting Date"]`.
**The Solution**: `src/data_loader.py` introduces a `ConfigurableColumnMapper` dictionary. This abstraction layer maps various known external column names to standard internal aliases. All downstream modules reference the internal alias.

### 2.2 Standardized Account Classification (No Hardcoded Account Codes)
**The Problem**: Chart of Accounts structures vary wildly between businesses (e.g., Revenue might be 4000 in one company and 100 in another).
**The Solution**: `src/account_classifier.py` parses the Chart of Accounts and classifies every account dynamically into standard buckets (`pl_category`, `bs_category`, `grouping_label`). The P&L, Balance Sheet, and all analytics modules generate their logic based on these string buckets rather than raw numeric account codes.

### 2.3 Strict Modularity (Single Responsibility Principle)
Each module in `src/` does one thing. 
- `data_loader.py` only cleans and maps data.
- `profit_loss.py` only calculates the P&L.
- `reporting.py` only formats existing output into Excel (it does not recalculate).
This prevents spaghetti code and makes the platform easy to unit test.

## 3. Data Flow

```text
[Raw Excel Export]
       │
       ▼
(1) data_loader.py
    (Strips metadata, maps columns, aligns TB opening/closing balances)
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
(2) account_classifier.py          (3) GL Engine / Controls
    (Maps codes to categories)         (Controls tests, ML Anomaly Detection)
       │                                 │
       ▼                                 │
(4) Financial Engine                     │
    ├── profit_loss.py ◄────────(Consumes PL categories)
    ├── balance_sheet.py ◄──────(Consumes BS categories + Net Profit)
    └── cash_flow.py ◄──────────(Consumes BS changes + Net Profit)
       │                                 │
       ▼                                 │
(5) Analytics Layer                      │
    ├── ratios.py                        │
    ├── working_capital.py               │
    ├── ar/ap_analysis.py                │
    ├── scenario_analysis.py             │
    └── month_end_close.py               │
       │                                 │
       ▼                                 ▼
(6) Presentation Layer
    ├── dashboard/app.py (Streamlit UI)
    └── reporting.py (Excel Export)
```
