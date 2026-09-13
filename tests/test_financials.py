import unittest
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

class TestFinancials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wb_path = project_root / "data" / "raw" / "GL_COA_TB_Dummy_Dataset.xlsx"
        cls.wb = load_workbook(wb_path, header_row=3)
        classifier = AccountClassifier()
        cls.coa_classified = classifier.classify(cls.wb.coa)

    def test_trial_balance(self):
        tb = self.wb.tb
        
        # Opening balances should match
        self.assertAlmostEqual(tb["opening_debit"].sum(), tb["opening_credit"].sum(), places=2)
        
        # Closing balances should match
        self.assertAlmostEqual(tb["closing_debit"].sum(), tb["closing_credit"].sum(), places=2)

    def test_coa_mapping(self):
        # Every account in GL must exist in COA
        gl_accounts = set(self.wb.gl["account_code"].unique())
        coa_accounts = set(self.coa_classified["account_code"].unique())
        
        orphans = gl_accounts - coa_accounts
        self.assertEqual(len(orphans), 0, f"Found orphan GL accounts: {orphans}")
        
        # Ensure all accounts got classified properly
        unclassified = self.coa_classified[
            (self.coa_classified["bs_category"].isna()) & 
            (self.coa_classified["pl_category"].isna())
        ]
        self.assertEqual(len(unclassified), 0, "Found unclassified COA accounts")

    def test_profit_loss(self):
        pl_df, pl_metrics = generate_profit_loss(self.coa_classified, self.wb.tb)
        
        self.assertEqual(pl_metrics["Total Revenue"], 897000.0)
        self.assertEqual(pl_metrics["Total COGS"], 282600.0)
        self.assertEqual(pl_metrics["Gross Profit"], 614400.0)
        self.assertEqual(pl_metrics["Net Profit"], -1216800.0)

    def test_balance_sheet(self):
        pl_df, pl_metrics = generate_profit_loss(self.coa_classified, self.wb.tb)
        bs_df, bs_metrics = generate_balance_sheet(self.coa_classified, self.wb.tb, pl_metrics["Net Profit"])
        
        self.assertTrue(bs_metrics["Is Balanced"])
        self.assertEqual(bs_metrics["Difference"], 0.0)
        self.assertEqual(bs_metrics["Total Assets"], 10509300.0)
        self.assertEqual(bs_metrics["Total Equity"] + bs_metrics["Total Liabilities"], 10509300.0)

    def test_cash_flow(self):
        pl_df, pl_metrics = generate_profit_loss(self.coa_classified, self.wb.tb)
        cf_df, cf_metrics = generate_cash_flow(self.coa_classified, self.wb.tb, pl_metrics["Net Profit"])
        
        self.assertTrue(cf_metrics["Reconciled"])
        self.assertEqual(cf_metrics["Difference"], 0.0)
        self.assertEqual(cf_metrics["Closing Cash (Calculated)"], 960100.0)

    def test_ratios(self):
        pl_df, pl_metrics = generate_profit_loss(self.coa_classified, self.wb.tb)
        bs_df, bs_metrics = generate_balance_sheet(self.coa_classified, self.wb.tb, pl_metrics["Net Profit"])
        
        ratios_df = calculate_ratios(pl_metrics, bs_metrics, bs_df, days_in_period=90)
        
        # Check Current Ratio (approx 0.62)
        cr = ratios_df[ratios_df["Ratio"] == "Current Ratio"]["Value"].iloc[0]
        self.assertAlmostEqual(cr, 0.62, places=2)
        
        # Check Gross Profit Margin
        gpm = ratios_df[ratios_df["Ratio"] == "Gross Profit Margin"]["Value"].iloc[0]
        self.assertIn("68.5%", str(gpm))

if __name__ == '__main__':
    unittest.main()
