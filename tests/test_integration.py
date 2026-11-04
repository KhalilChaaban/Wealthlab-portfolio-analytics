"""Exercise the exported run contract using a short synthetic mandate."""

import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import tempfile
import unittest
from zipfile import ZipFile

from wealthlab.config import ClientConfig, ResearchConfig
from wealthlab.pipeline import run_project
from wealthlab.export import export_run


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.targets.extend(value for key, value in attrs if key == "href")


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
            root, maintained = Path(temp), Path(__file__).resolve().parents[1]
            shutil.copytree(maintained / "wealthlab", root / "wealthlab",
                            ignore=shutil.ignore_patterns("__pycache__"))
            for name in ("requirements.txt", "requirements-live.txt"):
                shutil.copy2(maintained / name, root / name)
            (root / "START_HERE.html").write_text('<a href="examples/yahoo/missing.html">Stale</a>')
            (root / "FINDINGS.md").write_text("Stale findings from another run")
            archive_path = export_run(result, cfg, client, root)
            with ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(len(archive.namelist()), len(set(archive.namelist())))
                self.assertFalse(any(name.startswith("data/cache/") for name in archive.namelist()))
                self.assertEqual(archive.read("FINDINGS.md"), (result.output_dir / "FINDINGS.md").read_bytes())
                self.assertIn("SYNTHETIC DEMO", archive.read("README.md").decode())
                payload = json.loads(archive.read("config/current_run.json"))
                self.assertEqual(payload["research"], cfg.to_dict())
                self.assertEqual(payload["client"], client.to_dict())
                parser = Links()
                parser.feed(archive.read("START_HERE.html").decode())
                self.assertEqual(len(parser.targets), 2)
                for target in parser.targets:
                    self.assertIn(target, archive.namelist())


if __name__ == "__main__":
    unittest.main()
