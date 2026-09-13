# Accounting Logic & Engine Mechanics

This document explains the accounting rules embedded into the Financial Reporting AI platform. The platform adheres to double-entry accounting principles and standard IFRS/GAAP statement logic.

## 1. General Principles
- **Debit Normal Accounts**: Assets, Expenses. Increases are Debits; decreases are Credits.
- **Credit Normal Accounts**: Liabilities, Equity, Revenue. Increases are Credits; decreases are Debits.
- **Trial Balance Normalization**: The TB is checked to ensure `Total Debit == Total Credit`. Balances are interpreted dynamically based on their COA classification (e.g., an Asset with a Net Credit is treated as a negative Asset balance, not moved to Liabilities).

## 2. Profit & Loss (Income Statement)
Calculated from closing balances in the Trial Balance mapped to P&L categories.
- **Revenue**: Calculated as `Credit - Debit` (Credit normal).
- **Cost of Sales (COGS)**: Calculated as `Debit - Credit` (Debit normal).
- **Gross Profit**: `Revenue - COGS`.
- **Operating Expenses (Opex)**: Calculated as `Debit - Credit`. Includes Salaries, Rent, Utilities, Depreciation, etc.
- **Operating Profit (EBIT)**: `Gross Profit - Total Opex`.
- **EBITDA**: `EBIT + Depreciation/Amortization`.
- **Finance Costs / Income Tax**: Calculated as `Debit - Credit`.
- **Net Profit**: `EBIT - Finance Costs - Income Tax`.

## 3. Balance Sheet
Calculated from closing balances in the Trial Balance mapped to BS categories.
- **Assets**: Calculated as `Debit - Credit`.
- **Liabilities**: Calculated as `Credit - Debit`.
- **Equity**: Calculated as `Credit - Debit`.
- **Retained Earnings / Current Year Profit Roll-Forward**: 
  The Trial Balance in this dataset is **unclosed** (the P&L accounts hold balances; they haven't been zeroed out into Retained Earnings). Therefore, to balance the Balance Sheet, the `Net Profit` generated from the P&L engine is dynamically injected into the Equity section as "Current Year Earnings".
- **Validation check**: The system asserts that `Total Assets == Total Liabilities + Total Equity`. If the variance > 0.01, it flags an out-of-balance error.

## 4. Cash Flow Statement (Indirect Method)
Derives cash flow movements by analyzing changes between the Opening Trial Balance and Closing Trial Balance.
1. **Starting Point**: `Net Profit` (imported from P&L module).
2. **Non-Cash Adjustments**: `Depreciation` expense is added back to Net Profit (since it reduces profit but doesn't consume cash).
3. **Operating Activities**: Calculates changes in Current Assets (excluding Cash) and Current Liabilities. 
   - An *increase* in an Asset (e.g., AR goes up) is a cash *outflow*.
   - An *increase* in a Liability (e.g., AP goes up) is a cash *inflow*.
4. **Investing Activities**: Calculates changes in Non-Current Assets (e.g., PPE purchases).
5. **Financing Activities**: Calculates changes in Long-Term Liabilities (e.g., paying down a loan) and Equity (e.g., dividends).
6. **Validation check**: Asserts that `Opening Cash + Net Cash Flow == Closing Cash`.

## 5. Working Capital & Ratios
- **Working Capital**: `Total Current Assets - Total Current Liabilities`.
- **Current Ratio**: `Total Current Assets / Total Current Liabilities`.
- **DSO (Days Sales Outstanding)**: `(Trade Receivables / Revenue) * Days in Period`.
- **DPO (Days Payable Outstanding)**: `(Trade Payables / COGS) * Days in Period`.
- *Note: Because this dataset covers only a single period (Q1), average balances cannot be calculated. Period-end closing balances are used instead, representing a documented limitation.*
