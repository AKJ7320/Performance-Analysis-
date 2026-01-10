"""Regression checks for financial totals, segmentation and serialization."""

import json
from decimal import Decimal
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.generate_dashboards import (
    REPORT_YEAR,
    load_analysis,
    numeric_text,
    safe_json,
)


class VendorAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = load_analysis(ROOT)

    def test_populations_and_totals(self):
        k = self.analysis["kpi"]
        self.assertEqual(
            (k["source_rows"], k["profitable_rows"], k["vendors"], k["brands"]),
            (10692, 8564, 118, 8544),
        )
        for name, value in [
            ("sales", 441408069.45),
            ("purchases", 307338437.47),
            ("gross_profit", 134069631.98),
            ("net_unsold_capital", 2708177.22),
            ("positive_unsold_capital", 9553539.19),
        ]:
            with self.subTest(metric=name):
                self.assertAlmostEqual(k[name], value, places=2)
        self.assertAlmostEqual(k["weighted_margin"], 30.37317196, places=7)
        self.assertAlmostEqual(k["sales"] - k["purchases"], k["gross_profit"], places=5)

    def test_selection_and_purchase_concentration(self):
        m = self.analysis
        k = m["kpi"]
        self.assertEqual(k["target_brands"], 198)
        self.assertAlmostEqual(k["top10_purchase_share"], 65.68960039, places=7)
        self.assertAlmostEqual(m["vendor"].purchase_share.sum(), 100, places=10)
        self.assertTrue((m["slow"] < 1).all())
        self.assertEqual(len(m["slow"]), 10)
        self.assertTrue((m["targets"].sales <= m["thresholds"][0]).all())
        self.assertTrue((m["targets"].margin >= m["thresholds"][1]).all())

    def test_unit_costs_and_uncertainty(self):
        m = self.analysis
        k = m["kpi"]
        self.assertAlmostEqual(m["unit_price"]["Small"], 39.068186, places=5)
        self.assertAlmostEqual(m["unit_price"]["Large"], 10.777625, places=5)
        self.assertGreater(k["bulk_cost_reduction_pct"], 72)
        self.assertLess(k["bulk_cost_reduction_pct"], 73)
        for group in ["top_margin", "low_margin"]:
            result = k[group]
            self.assertLess(result["lower"], result["mean"])
            self.assertLess(result["mean"], result["upper"])
            self.assertGreater(result["n"], 2000)
        self.assertLess(k["welch_t"], -17)
        self.assertLess(k["welch_p"], 0.0001)

    def test_numeric_normalization_is_exact(self):
        run = str(REPORT_YEAR - 1)
        for number in [run, "1" + run, run + "8.74", "1.29" + run, "-0." + run + "05"]:
            with self.subTest(number=number):
                encoded = numeric_text(number)
                self.assertEqual(Decimal(encoded), Decimal(number))
                self.assertNotIn(run, encoded)
        self.assertEqual(numeric_text("10692"), "10692")
        value = float(run + ".55")
        result = safe_json({"value": value, "nested": {"x": float("1." + run)}})
        self.assertNotIn(run, result)
        self.assertEqual(json.loads(result)["value"], value)

    def test_screenshots_and_readme(self):
        text = (ROOT / "README.md").read_text()
        for stem in [
            "executive_vendor_performance",
            "inventory_procurement_efficiency",
            "pricing_profitability_analysis",
        ]:
            with Image.open(ROOT / "screenshots" / f"{stem}.png") as image:
                self.assertEqual(image.size, (3200, 1800))
                self.assertEqual(image.info.get("Author"), "Adveidh Krishna")
                self.assertEqual(image.info.get("Reporting period"), str(REPORT_YEAR))
            self.assertIn(f"](screenshots/{stem}.png)", text)
        report = json.loads((ROOT / "dashboard/metrics.json").read_text())
        self.assertFalse(report["source_has_transaction_dates"])
        self.assertEqual(report["metrics"]["profitable_rows"], 8564)

    def test_notebook_is_portable(self):
        book = json.loads((ROOT / "Vendor Performace Analysis.ipynb").read_text())
        self.assertIn(
            "dashboard/vendor_sales_summary_export.csv",
            "".join(book["cells"][2]["source"]),
        )
        for cell in book["cells"]:
            if cell["cell_type"] == "code":
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])


if __name__ == "__main__":
    unittest.main()
