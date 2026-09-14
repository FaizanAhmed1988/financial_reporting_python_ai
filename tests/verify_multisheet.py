import sys, warnings
sys.path.append('.')
warnings.filterwarnings('ignore')
import pandas as pd
from src.data_loader import ConfigurableColumnMapper
from src.file_detector import detect_file_type
from src.column_mapper import generate_mapping_dataframe, apply_user_overrides

wb_path = 'data/raw/GL_COA_TB_Dummy_Dataset.xlsx'
excel_file = pd.ExcelFile(wb_path)
mapper = ConfigurableColumnMapper()

TYPE_SLUG = {
    'General Ledger':        'general_ledger',
    'Trial Balance':         'trial_balance',
    'Chart of Accounts':     'chart_of_accounts',
    'Opening Trial Balance': 'opening_trial_balance',
    'Other / Unknown':       'other',
}

# Simulate processing three sheets into separate session_state slots
uploads = {}
for sheet in ['General Ledger', 'Trial Balance', 'Chart of Accounts']:
    df = None
    for skip in range(6):
        candidate = pd.read_excel(excel_file, sheet_name=sheet, dtype=str, header=skip)
        candidate.columns = [str(c).strip() for c in candidate.columns]
        pm = mapper.build_rename_map(list(candidate.columns))
        if len(pm) >= 2:
            df = candidate.dropna(how='all').reset_index(drop=True)
            break

    detected, conf, rmap = detect_file_type(df, mapper, 'Auto Detect')
    mdf = generate_mapping_dataframe(df, rmap, detected)
    renamed_df, override_map = apply_user_overrides(df, mdf)
    slot = TYPE_SLUG.get(detected, 'other')
    uploads[slot] = {
        'df_raw':        df,
        'df_mapped':     renamed_df,
        'override_map':  override_map,
        'file_name':     'GL_COA_TB_Dummy_Dataset.xlsx',
        'detected_type': detected,
        'confidence':    conf,
        'sheet':         sheet,
    }

print("Slots stored independently:")
for k, v in uploads.items():
    print(f"  [{k}]")
    print(f"    sheet={v['sheet']}, rows={len(v['df_raw'])}, "
          f"mapped_cols={len(v['override_map'])}, "
          f"detected={v['detected_type']}, conf={v['confidence']*100:.0f}%")

print()
print("Slot isolation check (each must be a different object in memory):")
ids = {k: id(v['df_raw']) for k, v in uploads.items()}
for k, oid in ids.items():
    print(f"  {k}: id={oid}")
all_unique = len(set(ids.values())) == len(ids)
print(f"  All independent: {all_unique}")

print()
print("Required fields present in each slot:")
REQUIRED = {
    'general_ledger':    ['account_code', 'debit', 'credit'],
    'trial_balance':     ['account_code', 'closing_debit', 'closing_credit'],
    'chart_of_accounts': ['account_code', 'account_name', 'account_type'],
}
all_ok = True
for slot, fields in REQUIRED.items():
    if slot not in uploads:
        print(f"  {slot}: MISSING slot")
        all_ok = False
        continue
    cols = list(uploads[slot]['df_mapped'].columns)
    missing = [f for f in fields if f not in cols]
    if missing:
        print(f"  {slot}: MISSING required fields {missing}")
        all_ok = False
    else:
        print(f"  {slot}: OK — all required fields present ({fields})")

print()
print("OVERALL:", "PASS" if all_unique and all_ok else "FAIL")
