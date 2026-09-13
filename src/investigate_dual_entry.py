import pandas as pd
from pathlib import Path
from src.data_loader import load_workbook

wb = load_workbook(Path("data/raw/GL_COA_TB_Dummy_Dataset.xlsx"), header_row=3)
gl = wb.gl.copy()

# --- Find the dual Dr+Cr entry ---
both = gl[(gl["debit"] > 0) & (gl["credit"] > 0)]
print("=" * 72)
print("ENTRIES WITH BOTH DEBIT > 0 AND CREDIT > 0")
print("=" * 72)
print(f"Count: {len(both)}")
print()
for _, r in both.iterrows():
    print(f"  Txn No      : {r['txn_no']}")
    print(f"  Date        : {r['date']}")
    print(f"  Voucher No  : {r['voucher_no']}")
    print(f"  Account Code: {r['account_code']}")
    print(f"  Account Name: {r['account_name']}")
    print(f"  Debit       : {r['debit']:>14,.2f}")
    print(f"  Credit      : {r['credit']:>14,.2f}")
    print(f"  Net (Dr-Cr) : {r['debit']-r['credit']:>14,.2f}")
    print(f"  Narration   : {r['narration']}")
    print()

# --- Show the full journal for that Txn No ---
txn_no = both.iloc[0]["txn_no"]
print("=" * 72)
print(f"ALL POSTING LINES FOR Txn No {txn_no}")
print("=" * 72)
journal = gl[gl["txn_no"] == txn_no].sort_values("debit", ascending=False)
for _, r in journal.iterrows():
    print(f"  [{r['account_code']}] {str(r['account_name']):<44}  Dr={r['debit']:>12,.2f}  Cr={r['credit']:>12,.2f}  Net={r['debit']-r['credit']:>12,.2f}")
print(f"\n  Journal Dr total: {journal['debit'].sum():>12,.2f}")
print(f"  Journal Cr total: {journal['credit'].sum():>12,.2f}")
print(f"  Journal balanced: {abs(journal['debit'].sum() - journal['credit'].sum()) < 0.01}")

# --- Impact analysis: what if we treat net as the correct movement? ---
print()
print("=" * 72)
print("IMPACT ANALYSIS")
print("=" * 72)
row = both.iloc[0]
net = row["debit"] - row["credit"]
print(f"  As-posted Dr: {row['debit']:,.2f}  Cr: {row['credit']:,.2f}")
print(f"  Net Dr-Cr   : {net:,.2f}")
print(f"  If split into two lines, the net movement for account {row['account_code']} is unchanged.")
print(f"  The gross GL totals (Total Dr / Total Cr) would both DECREASE by {row['credit']:,.2f}")
print(f"  But the NET per-account movement = unchanged => no P&L / TB / BS impact.")

# --- Re-verify Dr=Cr totals including vs excluding this entry ---
total_dr_all = gl["debit"].sum()
total_cr_all = gl["credit"].sum()
total_dr_ex  = gl.loc[~gl.index.isin(both.index), "debit"].sum() + net  # replace with net debit
total_cr_ex  = gl.loc[~gl.index.isin(both.index), "credit"].sum()

print()
print(f"  GL Total Debits  (as-is):    {total_dr_all:>14,.2f}")
print(f"  GL Total Credits (as-is):    {total_cr_all:>14,.2f}")
print(f"  GL balanced (as-is):         {abs(total_dr_all - total_cr_all) < 0.01}")
print()
print(f"  If entry re-cast as net-only debit of {net:,.2f}:")
print(f"  GL Total Debits  (adjusted): {total_dr_ex:>14,.2f}")
print(f"  GL Total Credits (adjusted): {total_cr_ex:>14,.2f}")
print(f"  GL balanced (adjusted):      {abs(total_dr_ex - total_cr_ex) < 0.01}")
