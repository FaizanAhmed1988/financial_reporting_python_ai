# Financial Reporting AI

An enterprise-grade, AI-powered Financial Reporting, Accounting Analytics, and Financial Control platform built entirely in Python. 

This project demonstrates the intersection of traditional accounting logic (double-entry, IFRS/GAAP principles) with scalable data engineering and machine learning (anomaly detection/FP&A forecasting). It ingests raw accounting data (Trial Balance, General Ledger, Chart of Accounts), dynamically maps the accounts, and generates a full suite of financial statements and analytics.

---

## 1. Business Problem
Finance and accounting teams spend days at month-end downloading CSVs, mapping accounts manually in Excel via VLOOKUPs, and building static P&L and Balance Sheet reports. These manual processes are error-prone, hard to scale, and leave little time for actual financial analysis. Furthermore, traditional audit controls rely on static rules that fail to catch nuanced, multi-dimensional anomalies in the general ledger.

## 2. Business Objectives
- **Automate the Core Engine**: Build a Python pipeline that automatically digests a raw GL and TB, maps it against a dynamic Chart of Accounts, and spits out perfectly balanced Financial Statements.
- **Advanced Analytics**: Generate liquidity ratios, working capital metrics, and sub-ledger analytics on demand.
- **AI-Powered Controls**: Replace static audit rules with unsupervised Machine Learning (Isolation Forest) to detect unusual journal entries.
- **Presentation Ready**: Deliver the output via an interactive Streamlit dashboard and a professionally formatted 15-sheet Excel workbook export.

---

## 3. Architecture & Tech Stack
**Tech Stack**: Python, Pandas, NumPy, Scikit-learn, Streamlit, OpenPyXL.

### Data Flow
1. **Ingestion (`data_loader.py`)**: Reads the raw Excel export. Uses a configurable column mapper so the system isn't brittle to external column name changes.
2. **Classification (`account_classifier.py`)**: Uses rules to classify raw account codes into standard buckets (e.g., `Revenue`, `Current Assets`).
3. **Financial Engine**:
   - `profit_loss.py`: Computes the Income Statement.
   - `balance_sheet.py`: Computes Assets/Liabilities and injects the dynamic Net Profit to balance the sheet.
   - `cash_flow.py`: Uses the Indirect Method to reconcile Opening Cash to Closing Cash based on working capital movements.
4. **Analytics Layer**: Computes Financial Ratios, Budget vs Actual, and FP&A Scenario Analysis.
5. **AI Controls (`anomaly_detection.py`)**: Z-score scaled Isolation Forest flags statistical anomalies in the General Ledger.

---

## 4. Key Results & Findings (Based on Demo Dataset)

*Note: The platform is built around a dummy Q1 2026 dataset.*

- **Profitability**: The entity generated $897,000 in Revenue but posted a massive Net Loss of ($1,216,800), driven primarily by excessive Salaries & Wages ($1,048,200).
- **Liquidity Crisis**: The Current Ratio sits at a dangerous **0.62x**, and Working Capital is heavily negative at ($2,225,400).
- **Payables Buildup**: DPO (Days Payable Outstanding) is over 1,800 days, indicating a massive $5.7M buildup of unpaid trade payables relative to COGS.
- **AI Anomalies**: The Isolation Forest model successfully flagged 4 transactions out of the GL that deviated from normal posting patterns for their respective accounts.

---

## 5. Limitations (Honest Assessment)
The architecture is scalable and production-ready, but the *insights* are currently limited by the provided demo dataset:
- **Single Period**: The dataset covers only Q1 2026. Therefore, Ratios use period-end balances instead of averages, and time-series forecasting is fundamentally limited.
- **No Sub-Ledgers**: The GL contains aggregate AR/AP balances. Invoice-level ageing reports cannot be generated without invoice data.
- **No Bank Statement**: Bank reconciliation is built but marked as 'Pending' in the Month-End close checklist due to lack of a bank export file.
- **Synthetic Budget**: Because no budget data was provided, a synthetic budget was generated purely to demonstrate the Budget vs Actual engine.

---

## 6. Future Improvements
- **Multi-Currency Support**: Introduce an FX layer to handle consolidated reporting across multiple base currencies.
- **Sub-Ledger Integration**: Ingest invoice-level AR and AP extracts to generate true 30/60/90+ day ageing buckets.
- **LLM Narrative Generation**: Plug the final metrics into a local LLM to automatically generate the Management Summary text.

---

## 7. How to Run

### Installation
Clone the repository and install the dependencies:
```bash
git clone https://github.com/yourusername/financial_reporting_python_ai.git
cd financial_reporting_python_ai
pip install -r requirements.txt
```

### Launch the Dashboard
Run the canonical Streamlit application:
```bash
python -m streamlit run dashboard/app.py
```

### Run Unit Tests
Validate the accounting logic via pytest (if pytest is not installed, use python unittest):
```bash
python tests/test_financials.py
```

---

## 8. Screenshots
*(Placeholder: Add screenshots of the Streamlit dashboard tabs and the Excel export here)*
