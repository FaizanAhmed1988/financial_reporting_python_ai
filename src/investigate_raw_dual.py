import pandas as pd
from pathlib import Path

WB = Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx")
HEADER_ROW = 3   # 0-indexed => Excel row 4
gl = pd.read_excel(WB, sheet_name="General Ledger", header=HEADER_ROW, dtype=str)

gl["Debit"]  = pd.to_numeric(gl["Debit"],  errors="coerce").fillna(0)
gl["Credit"] = pd.to_numeric(gl["Credit"], errors="coerce").fillna(0)

both = gl[(gl["Debit"] > 0) & (gl["Credit"] > 0)]
print(f"Count: {len(both)}")
print(both)
