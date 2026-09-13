import json
import pandas as pd
import numpy as np
from pathlib import Path

WB = Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx")
HEADER_ROW = 3   # 0-indexed => Excel row 4

sheets = {}
for name in ["Chart of Accounts", "Opening Balances-TB", "General Ledger", "Trial Balance"]:
    df = pd.read_excel(WB, sheet_name=name, header=HEADER_ROW, dtype=str)
    # strip whitespace
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].str.strip()
    # drop fully-blank rows
    df = df.dropna(how="all").reset_index(drop=True)
    sheets[name] = df

# ---- Print structural info per sheet ----
for name, df in sheets.items():
    print("")
    print("=" * 68)
    print("SHEET:", name)
    print("=" * 68)
    print("  Rows (after blank-row drop):", len(df))
    print("  Columns:", list(df.columns))
    print("  Dtypes:", df.dtypes.to_dict())
    print("  Missing values:", df.isnull().sum().to_dict())
    print("  Duplicate rows:", df.duplicated().sum())
    print("  First 5 rows:")
    for i, row in df.head(5).iterrows():
        print("    ", dict(row))

# ---- Chart of Accounts detail ----
coa = sheets["Chart of Accounts"]
print("")
print("COA - Account Types distribution:")
print(coa["Account Type"].value_counts().to_dict())
print("COA - Normal Balance distribution:")
print(coa["Normal Balance"].value_counts().to_dict())
print("COA - All account codes:")
for _, r in coa.iterrows():
    print(f"    {r['Account Code']:>6}  {r['Account Name']:<40}  {r['Account Type']:<12}  {r['Normal Balance']}")

# ---- Opening TB detail ----
otb = sheets["Opening Balances-TB"]
otb["Opening Debit"]  = pd.to_numeric(otb["Opening Debit"], errors="coerce").fillna(0)
otb["Opening Credit"] = pd.to_numeric(otb["Opening Credit"], errors="coerce").fillna(0)
total_ob_dr = otb["Opening Debit"].sum()
total_ob_cr = otb["Opening Credit"].sum()
ob_diff     = total_ob_dr - total_ob_cr
print("")
print("OPENING TRIAL BALANCE (01-Jan-2026)")
print(f"  Total Opening Debit  : {total_ob_dr:>18,.2f}")
print(f"  Total Opening Credit : {total_ob_cr:>18,.2f}")
print(f"  Difference           : {ob_diff:>18,.2f}  ({'BALANCED' if abs(ob_diff)<0.01 else '*** IMBALANCED ***'})")
print("  All rows:")
for _, r in otb.iterrows():
    print(f"    {str(r['Account Code']):>6}  {str(r['Account Name']):<40}  Dr={r['Opening Debit']:>12,.2f}  Cr={r['Opening Credit']:>12,.2f}")

# ---- General Ledger detail ----
gl = sheets["General Ledger"]
gl["Debit"]  = pd.to_numeric(gl["Debit"],  errors="coerce").fillna(0)
gl["Credit"] = pd.to_numeric(gl["Credit"], errors="coerce").fillna(0)
gl["Date"]   = pd.to_datetime(gl["Date"], errors="coerce")

total_gl_dr = gl["Debit"].sum()
total_gl_cr = gl["Credit"].sum()
gl_diff     = total_gl_dr - total_gl_cr
print("")
print("GENERAL LEDGER")
print(f"  Total posting lines  : {len(gl)}")
print(f"  Unique Txn Nos       : {gl['Txn No'].nunique()}")
print(f"  Date range           : {gl['Date'].min().date()} to {gl['Date'].max().date()}")
print(f"  Unparseable dates    : {gl['Date'].isnull().sum()}")
print(f"  Total Debits         : {total_gl_dr:>18,.2f}")
print(f"  Total Credits        : {total_gl_cr:>18,.2f}")
print(f"  Difference           : {gl_diff:>18,.2f}  ({'BALANCED' if abs(gl_diff)<0.01 else '*** IMBALANCED ***'})")
both = gl[(gl["Debit"]>0) & (gl["Credit"]>0)]
print(f"  Entries with BOTH Dr+Cr > 0: {len(both)}")
print(f"  Unique Account Codes in GL : {gl['Account Code'].nunique()}")
print(f"  Unique Voucher Nos         : {gl['Voucher No'].nunique()}")
print("  Missing values:", {c: int(v) for c, v in gl.isnull().sum().items() if v > 0})

# Net movement per account
gl_net = (gl.groupby("Account Code")[["Debit","Credit"]].sum())
gl_net["Net (Dr-Cr)"] = gl_net["Debit"] - gl_net["Credit"]
print("  GL Net Movement per Account Code:")
for code, row in gl_net.iterrows():
    print(f"    {code:>6}  Dr={row['Debit']:>12,.2f}  Cr={row['Credit']:>12,.2f}  Net={row['Net (Dr-Cr)']:>14,.2f}")

# ---- Trial Balance detail ----
tb = sheets["Trial Balance"]
for col in ["Opening Debit","Opening Credit","Period Debit","Period Credit","Closing Debit","Closing Credit"]:
    tb[col] = pd.to_numeric(tb[col], errors="coerce").fillna(0)

print("")
print("TRIAL BALANCE (31-Mar-2026)")
print(f"  Rows: {len(tb)}")
for col in ["Opening Debit","Opening Credit","Period Debit","Period Credit","Closing Debit","Closing Credit"]:
    print(f"  Total {col:<22}: {tb[col].sum():>18,.2f}")

ob_dr_tb   = tb["Opening Debit"].sum()
ob_cr_tb   = tb["Opening Credit"].sum()
pd_dr_tb   = tb["Period Debit"].sum()
pd_cr_tb   = tb["Period Credit"].sum()
cb_dr_tb   = tb["Closing Debit"].sum()
cb_cr_tb   = tb["Closing Credit"].sum()
print(f"  Opening Dr-Cr diff   : {ob_dr_tb-ob_cr_tb:>18,.2f}  ({'BALANCED' if abs(ob_dr_tb-ob_cr_tb)<0.01 else 'IMBALANCED'})")
print(f"  Period  Dr-Cr diff   : {pd_dr_tb-pd_cr_tb:>18,.2f}  ({'BALANCED' if abs(pd_dr_tb-pd_cr_tb)<0.01 else 'IMBALANCED'})")
print(f"  Closing Dr-Cr diff   : {cb_dr_tb-cb_cr_tb:>18,.2f}  ({'BALANCED' if abs(cb_dr_tb-cb_cr_tb)<0.01 else 'IMBALANCED'})")

# ---- Cross-validate: OB + GL net movement = Closing balance ----
print("")
print("CROSS-VALIDATION: OB + GL Period Movement = Closing Balance")
otb_idx = otb.set_index("Account Code")[["Opening Debit","Opening Credit"]].copy()
otb_idx["OB_net"] = otb_idx["Opening Debit"] - otb_idx["Opening Credit"]

tb_idx = tb.set_index("Account Code").copy()
tb_idx["OB_net_tb"] = tb_idx["Opening Debit"] - tb_idx["Opening Credit"]
tb_idx["CB_net_tb"] = tb_idx["Closing Debit"]  - tb_idx["Closing Credit"]

gl_net2 = gl.groupby("Account Code")[["Debit","Credit"]].sum()
gl_net2["gl_net"] = gl_net2["Debit"] - gl_net2["Credit"]

recon = tb_idx[["OB_net_tb","CB_net_tb"]].join(gl_net2["gl_net"], how="left").fillna(0)
recon["expected_CB"] = recon["OB_net_tb"] + recon["gl_net"]
recon["variance"]    = (recon["expected_CB"] - recon["CB_net_tb"]).round(2)
recon["ok"]          = recon["variance"].abs() < 0.01

print(f"  Accounts checked     : {len(recon)}")
print(f"  Fully reconciled     : {recon['ok'].sum()}")
print(f"  Unreconciled         : {(~recon['ok']).sum()}")
print(f"  Total variance       : {recon['variance'].sum():.2f}")
if (~recon["ok"]).any():
    print("  *** UNRECONCILED ACCOUNTS:")
    for code, row in recon[~recon["ok"]].iterrows():
        print(f"    {code:>6}  OB={row['OB_net_tb']:>12,.2f}  GL_Net={row['gl_net']:>12,.2f}  ExpCB={row['expected_CB']:>12,.2f}  ActCB={row['CB_net_tb']:>12,.2f}  Var={row['variance']:>10,.2f}")
else:
    print("  All accounts reconcile: OB + GL period movement = Closing Balance")

print("")
print("ALL ACCOUNTS in Trial Balance with Closing Balances:")
for _, r in tb.iterrows():
    ob  = r["Opening Debit"] - r["Opening Credit"]
    cb  = r["Closing Debit"] - r["Closing Credit"]
    print(f"  {str(r['Account Code']):>6}  {str(r['Account Name']):<38}  OB_net={ob:>12,.2f}  PeriodDr={r['Period Debit']:>12,.2f}  PeriodCr={r['Period Credit']:>12,.2f}  CB_net={cb:>12,.2f}")
