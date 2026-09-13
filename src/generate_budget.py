import pandas as pd
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.data_loader import load_workbook
from src.account_classifier import AccountClassifier

def generate_synthetic_budget():
    wb_path = project_root / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"
    wb = load_workbook(wb_path, header_row=3)
    classifier = AccountClassifier()
    coa_classified = classifier.classify(wb.coa)
    
    tb = wb.tb
    merged = coa_classified.merge(tb, on="account_code", how="inner")
    merged["cb_net"] = merged["closing_debit"] - merged["closing_credit"]
    
    pl_accounts = merged[merged["financial_statement"] == "Income Statement"].copy()
    
    budget_data = []
    
    for _, r in pl_accounts.iterrows():
        cat = r["pl_category"]
        name = r["grouping_label"]
        actual = r["cb_net"]
        acct_name = r.get("account_name_x", r.get("account_name_y", r.get("account_name", "")))
        
        if cat == "Revenue":
            actual_val = -actual
            budget_val = round(actual_val * 1.1, -2)
        elif cat == "Cost of Sales":
            actual_val = actual
            budget_val = round(actual_val * 1.05, -2)
        elif cat == "Operating Expenses":
            actual_val = actual
            if "Salaries" in name:
                budget_val = round(actual_val * 0.7, -2)
            else:
                budget_val = round(actual_val * 0.95, -2)
        elif cat == "Finance Costs":
            actual_val = actual
            budget_val = round(actual_val * 1.0, -2)
        else:
            budget_val = 0
            
        budget_data.append({
            "account_code": r["account_code"],
            "account_name": acct_name,
            "grouping_label": name,
            "pl_category": cat,
            "budget_amount": budget_val
        })
        
    df = pd.DataFrame(budget_data)
    out_dir = project_root / "data" / "synthetic"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "budget_q1_2026.csv", index=False)
    print(f"Generated synthetic budget at {out_dir / 'budget_q1_2026.csv'}")

if __name__ == "__main__":
    generate_synthetic_budget()
