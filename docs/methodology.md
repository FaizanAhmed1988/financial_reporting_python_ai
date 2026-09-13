# AI Methodology & Analytics Approach

This document outlines the approach used for the Machine Learning (AI) anomaly detection and forecasting components of the Financial Reporting platform.

## 1. AI Anomaly Detection (Isolation Forest)

### 1.1 The Business Problem
Traditional financial controls rely on static, rule-based tests (e.g., "flag transactions over $10k", "flag weekend postings"). While these catch known risk patterns, they fail to detect subtle, multi-dimensional anomalies where a transaction's amount, frequency, and timing are individually acceptable but unusual when combined for a specific account.

### 1.2 The Machine Learning Approach
We use an unsupervised Machine Learning model, specifically an **Isolation Forest**, from `scikit-learn`.
- **Why Unsupervised?**: We do not have a labeled dataset of "fraudulent" vs "clean" transactions. The model must learn what is "normal" from the raw GL data and flag statistical outliers.
- **Why Isolation Forest?**: It is highly effective for tabular anomaly detection. Rather than trying to profile "normal" data (like One-Class SVM), it attempts to isolate anomalies by randomly partitioning the data. Since anomalies are "few and different", they require fewer splits to isolate, resulting in shorter path lengths in the forest.

### 1.3 Feature Engineering
Before feeding the GL data into the model, we engineer the following features:
- **Transaction Amount**: The absolute value of the debit or credit.
- **Z-Score Scaling**: Transaction amounts are grouped by `account_code` and scaled using a Z-score. A $5,000 transaction might be completely normal for "Rent Expense" but an extreme outlier for "Office Supplies". Scaling per account allows the model to detect relative anomalies.
- *Future capabilities*: In a larger dataset, features like `Day_of_Month`, `Vendor_ID`, and `Time_Since_Last_Posting` would be engineered.

### 1.4 Business Interpretation
The model outputs an anomaly score. Items flagged (-1) are presented in the dashboard as "Potential Anomalies". They are not guaranteed fraud. The AI's job is to reduce a 10,000-line GL into a 50-line list for targeted human audit, dramatically increasing audit efficiency.

## 2. Forecasting Methodology

### 2.1 The Approach
The forecasting module uses a time-series aggregation to predict future balances (e.g., Revenue for the next 3 months) using historical GL transaction postings grouped by month.

### 2.2 Stated Limitations & Synthetic Policy
- **Data Scarcity**: The provided dataset only contains 3 months of data (Q1 2026). This is completely insufficient for robust time-series forecasting (e.g., ARIMA or Prophet models require at least 24 months to detect seasonality and trend).
- **Current Implementation**: The model utilizes a basic Simple Moving Average (SMA) / Naive approach for illustrative architecture purposes only.
- **Transparency**: The forecasting dashboard explicitly flags this limitation with a visible warning banner. No data is fabricated to force a better model fit.

## 3. Synthetic Data Policy
When data is required to demonstrate architectural capability but is absent from the source files, synthetic data is generated.
- **Rule**: Synthetic data must be strictly isolated to `data/synthetic/`.
- **Transparency**: Any output utilizing synthetic data (e.g., Budget vs Actual) must carry an unmissable "SYNTHETIC / DEMO DATA" warning in the UI and exported reports. No synthetic data is ever blended into the raw Financial Statements.
