"""Exercise the exported run contract using a short synthetic mandate."""

import json
from pathlib import Path
import tempfile
import unittest

from wealthlab.config import ClientConfig, ResearchConfig
from wealthlab.pipeline import run_project


class IntegrationTests(unittest.TestCase):
    def test_end_to_end_outputs_and_escaped_client_label(self):
        cfg = ResearchConfig(start="2023-01-01", end="2024-02-01")
        client = ClientConfig(label="Family <script>alert(1)</script>", horizon_years=1,
                              paths=100, one_off_spending={})
        with tempfile.TemporaryDirectory() as temp:
            result = run_project(cfg, client, temp)
            html = result.report_path.read_text()
            self.assertIn("SYNTHETIC DEMO", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn("<script>alert", html)
            self.assertNotIn('src="https://', html)
            self.assertEqual(len(result.chart_paths), 5)
            self.assertTrue(all(p.read_bytes().startswith(b"\x89PNG") for p in result.chart_paths.values()))
            manifest = json.loads((result.output_dir / "run_manifest.json").read_text())
            self.assertLess(abs(manifest["validation"]["attribution_residual_aed"]), 1e-6)
            self.assertEqual(manifest["currency"]["reporting_currency"], "AED")
            self.assertIn("Ending NAV AED", result.metrics.index)
            self.assertIn("AED 264,420", html)
            self.assertNotIn("Ending NAV USD", html)
            self.assertIn("source_code_sha256", manifest)
            self.assertEqual(len(list(Path(result.output_dir).glob("*.csv"))), 12)


if __name__ == "__main__":
    unittest.main()
