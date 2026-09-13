import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Ensure src is in the path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.data_loader import load_workbook
from src.account_classifier import AccountClassifier
from src.profit_loss import generate_profit_loss
from src.balance_sheet import generate_balance_sheet
from src.cash_flow import generate_cash_flow
from src.ratios import calculate_ratios
from src.working_capital import analyze_working_capital
from src.ar_analysis import analyze_ar, ageing_report
from src.ap_analysis import analyze_ap, vendor_ageing_report
from src.reconciliation import analyze_reconciliation, reconcile_bank
from src.budget_vs_actual import generate_bva
from src.controls import run_control_tests
from src.anomaly_detection import run_ml_anomaly_detection
from src.forecasting import generate_forecast
from src.scenario_analysis import run_scenarios
from src.reporting import generate_excel_report
from src.month_end_close import build_checklist
from src.file_upload import render_upload_section
from pathlib import Path as _Path

st.set_page_config(page_title="Financial Reporting AI", layout="wide")
st.title("Financial Reporting AI")
st.markdown("Enterprise-grade AI-powered Financial Reporting & Control Platform")

@st.cache_data
def load_data():
    wb_path = project_root / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"
    wb = load_workbook(wb_path, header_row=3)
    classifier = AccountClassifier()
    coa_classified = classifier.classify(wb.coa)
    
    budget_path = project_root / "data" / "synthetic" / "budget_q1_2026.csv"
    budget_df = pd.read_csv(budget_path) if budget_path.exists() else pd.DataFrame()
    
    return wb, coa_classified, budget_df

try:
    wb, coa_classified, budget_df = load_data()
    
    # Engine Calculations
    pl_df, pl_metrics = generate_profit_loss(coa_classified, wb.tb)
    net_profit = pl_metrics["Net Profit"]
    bs_df, bs_metrics = generate_balance_sheet(coa_classified, wb.tb, net_profit)
    cf_df, cf_metrics = generate_cash_flow(coa_classified, wb.tb, net_profit)
    ratios_df = calculate_ratios(pl_metrics, bs_metrics, bs_df, days_in_period=90)
    wc_df = analyze_working_capital(pl_metrics, bs_df, days_in_period=90)
    ar_metrics = analyze_ar(bs_df, wb.tb, coa_classified)
    ap_metrics = analyze_ap(bs_df, wb.tb, coa_classified)
    rec_metrics = analyze_reconciliation(wb.tb, coa_classified)
    bva_df = generate_bva(pl_df, budget_df) if not budget_df.empty else pd.DataFrame()
    controls_findings = run_control_tests(wb.gl)
    ml_anomalies = run_ml_anomaly_detection(wb.gl)
    forecast_results = generate_forecast(wb.tb, coa_classified, wb.gl)
    mec_df = build_checklist(bs_metrics, cf_metrics, rec_metrics, coa_classified)
    
    # Navigation Sidebar
    st.sidebar.title("Navigation")
    pages = ["Executive Summary", "Financial Statements", "Ratios & Working Capital", 
             "Sub-Ledgers", "Controls & AI", "Scenario Analysis", "Month-End Close",
             "Upload Financial Data"]
    selection = st.sidebar.radio("Go to", pages)
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Export")
    if st.sidebar.button("Export to Excel", key="export_btn"):
        with st.spinner("Generating Excel workbook..."):
            sc_df_export = run_scenarios(pl_metrics, bs_metrics, bs_df)
            out_path = project_root / "reports" / "excel" / "financial_report_Q1_2026.xlsx"
            excel_bytes = generate_excel_report(
                coa_classified, wb.gl, wb.tb, pl_df, pl_metrics,
                bs_df, bs_metrics, cf_df, cf_metrics, ratios_df, wc_df,
                ar_metrics, ap_metrics, bva_df, controls_findings,
                ml_anomalies, forecast_results, sc_df_export,
                output_path=out_path
            )
        st.sidebar.success(f"Saved to reports/excel/")
        st.sidebar.download_button(
            label="⬇ Download financial_report_Q1_2026.xlsx",
            data=excel_bytes,
            file_name="financial_report_Q1_2026.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_btn"
        )

    if selection == "Executive Summary":
        st.header("Executive Summary (Q1 2026)")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Revenue", f"{pl_metrics.get('Total Revenue', 0):,.0f}")
        col2.metric("Gross Profit", f"{pl_metrics.get('Gross Profit', 0):,.0f}")
        col3.metric("EBITDA", f"{pl_metrics.get('EBITDA', 0):,.0f}")
        col4.metric("Net Profit / (Loss)", f"{net_profit:,.0f}")
        
        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Cash Balance", f"{bs_df[bs_df['Line Item'].str.strip() == 'Cash & Cash Equivalents']['Amount'].iloc[0]:,.0f}")
        cr_val = float(wc_df[wc_df['Metric'] == 'Current Ratio']['Amount/Value'].iloc[0].replace('x', ''))
        col6.metric("Current Ratio", f"{cr_val:.2f}x")
        dso_val = float(wc_df[wc_df['Metric'] == 'AR Days (DSO)']['Amount/Value'].iloc[0].replace(' days', ''))
        col7.metric("DSO (Days)", f"{dso_val:.0f}")
        dpo_val = float(wc_df[wc_df['Metric'] == 'AP Days (DPO)']['Amount/Value'].iloc[0].replace(' days', ''))
        col8.metric("DPO (Days)", f"{dpo_val:.0f}")

        st.subheader("Chart of Accounts Overview")
        with st.expander("View Full Classified COA"):
            st.dataframe(coa_classified, use_container_width=True)

    elif selection == "Financial Statements":
        tab1, tab2, tab3 = st.tabs(["Profit & Loss", "Balance Sheet", "Cash Flow"])
        with tab1:
            st.header("Profit & Loss Statement")
            st.dataframe(pl_df, use_container_width=True, hide_index=True)
        with tab2:
            st.header("Balance Sheet")
            if bs_metrics["Is Balanced"]:
                st.success("✅ Balance Sheet is balanced")
            else:
                st.error(f"❌ Balance Sheet OUT OF BALANCE. Diff: {bs_metrics['Difference']:,.2f}")
            st.dataframe(bs_df, use_container_width=True, hide_index=True)
        with tab3:
            st.header("Cash Flow Statement")
            if cf_metrics["Reconciled"]:
                st.success("✅ Cash Flow reconciles")
            else:
                st.error(f"❌ Cash Flow DOES NOT RECONCILE. Diff: {cf_metrics['Difference']:,.2f}")
            st.dataframe(cf_df, use_container_width=True, hide_index=True)
            
    elif selection == "Ratios & Working Capital":
        st.header("Financial Ratios")
        st.warning("⚠️ **Limitation (Single Period Data):** Efficiency and Turnover ratios use period-end closing balances instead of averages. Ratios are based on Q1 2026 (90 days). No trend comparison available.")
        st.dataframe(ratios_df, use_container_width=True, hide_index=True)
        st.header("Working Capital Analysis")
        st.dataframe(wc_df, use_container_width=True, hide_index=True)
        
    elif selection == "Sub-Ledgers":
        st.header("Accounts Receivable Analytics")
        st.info(ar_metrics["Limitation"])
        col1, col2 = st.columns(2)
        col1.metric("Total AR Balance", f"{ar_metrics['Total AR Balance']:,.0f}")
        col2.metric("AR Movement (Period)", f"{ar_metrics['AR Movement (Period)']:,.0f}")
        
        st.header("Accounts Payable Analytics")
        st.info(ap_metrics["Limitation"])
        col3, col4 = st.columns(2)
        col3.metric("Total AP Balance", f"{ap_metrics['Total AP Balance']:,.0f}")
        col4.metric("AP Movement (Period)", f"{ap_metrics['AP Movement (Period)']:,.0f}")
        
        st.header("Bank Reconciliation")
        st.info(rec_metrics["Status"])
        st.metric("GL Bank Balance (Account 1010)", f"{rec_metrics['GL Bank Balance']:,.0f}")
        
    elif selection == "Controls & AI":
        tab1, tab2, tab3, tab4 = st.tabs(["Budget vs Actual", "Control Analytics", "AI Anomaly Detection", "Forecasting"])
        with tab1:
            st.warning("⚠️ **SYNTHETIC / DEMO DATA:** The budget figures below are synthetically generated for demonstration purposes. They are not part of the real company dataset.")
            if not bva_df.empty:
                st.dataframe(bva_df, use_container_width=True, hide_index=True)
        with tab2:
            st.markdown("Automated internal control tests run across 200 General Ledger transaction lines.")
            summary_data = [{"Control Test": k, "Findings": v["count"], "Status": v["label"]} for k,v in controls_findings.items()]
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
        with tab3:
            st.markdown("**Model Details:** " + ml_anomalies["model_explanation"])
            st.metric("Transactions Flagged by ML", ml_anomalies["count"])
            if ml_anomalies["count"] > 0:
                st.dataframe(ml_anomalies["findings"], use_container_width=True, hide_index=True)
        with tab4:
            st.warning("⚠️ **LIMITATION:** " + forecast_results["limitation_warning"])
            st.dataframe(forecast_results["forecast_df"], use_container_width=True, hide_index=True)
            
    elif selection == "Scenario Analysis":
        st.header("FP&A Scenario Modeling")
        st.markdown("Adjust assumptions below to generate Base, Best, and Worst case scenarios.")
        
        st.sidebar.markdown("### Scenario Assumptions")
        
        def render_sliders(case_name, defaults):
            st.sidebar.markdown(f"**{case_name}**")
            rg = st.sidebar.slider(f"{case_name} Rev Growth %", -50, 50, int(defaults["rev_growth"]*100), key=f"{case_name}_rg") / 100.0
            cg = st.sidebar.slider(f"{case_name} COGS %", 0, 100, int(defaults["cogs_pct"]*100), key=f"{case_name}_cg") / 100.0
            ox = st.sidebar.slider(f"{case_name} Opex %", 0, 200, int(defaults["opex_pct"]*100), key=f"{case_name}_ox") / 100.0
            dso = st.sidebar.slider(f"{case_name} DSO", 0, 150, int(defaults["dso"]), key=f"{case_name}_dso")
            dpo = st.sidebar.slider(f"{case_name} DPO", 0, 2000, int(defaults["dpo"]), key=f"{case_name}_dpo")
            return {"rev_growth": rg, "cogs_pct": cg, "opex_pct": ox, "dso": float(dso), "dpo": float(dpo)}
            
        assumptions = {
            "Base Case": render_sliders("Base Case", {"rev_growth": 0.0, "cogs_pct": 0.315, "opex_pct": 1.25, "dso": 68, "dpo": 1826}),
            "Best Case": render_sliders("Best Case", {"rev_growth": 0.10, "cogs_pct": 0.30, "opex_pct": 1.10, "dso": 45, "dpo": 90}),
            "Worst Case": render_sliders("Worst Case", {"rev_growth": -0.10, "cogs_pct": 0.35, "opex_pct": 1.40, "dso": 90, "dpo": 30})
        }
        
        scenario_df = run_scenarios(pl_metrics, bs_metrics, bs_df, days_in_period=90, assumptions=assumptions)
        
        # Format for display
        format_cols = ["Revenue", "Gross Profit", "Operating Profit", "Net Profit", "Simulated Cash"]
        for c in format_cols:
            scenario_df[c] = scenario_df[c].apply(lambda x: f"{x:,.0f}")
            
        st.dataframe(scenario_df, use_container_width=True, hide_index=True)
        
    elif selection == "Month-End Close":
        st.header("Month-End Close Checklist")
        st.markdown("Status is derived dynamically from actual dataset completeness. 'Completed' means the action is verifiably supported by the available data.")
        
        # Color coding function for status
        def color_status(val):
            if "Completed" in str(val):
                color = "green"
            elif "Pending" in str(val):
                color = "orange"
            elif "Exception" in str(val):
                color = "red"
            else:
                color = "grey"
            return f'color: {color}; font-weight: bold'
            
        styled_df = mec_df.style.map(color_status, subset=['Status'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

    elif selection == "Upload Financial Data":
        render_upload_section()

except Exception as e:
    st.error(f"Application Error: {e}")
