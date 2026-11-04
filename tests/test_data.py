"""Deterministic pipeline and provider-contract checks without a network."""

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import os
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from wealthlab.config import ResearchConfig
from wealthlab.data import (DataError, DataQualityError, clean_prices,
                           extract_yahoo_adjusted_close, load_prices, risk_free_returns)


class DataTests(unittest.TestCase):
    def setUp(self):
        self.cfg = ResearchConfig(start="2024-01-01", end="2024-01-06", min_observations=3,
                                   weights={"SPY": .6,"AGG": .4}, benchmark={"SPY": .6,"AGG": .4})
        self.frame = pd.DataFrame({"SPY": [100,101,102,103,104], "AGG": [100,100,101,101,102]},
                                  index=pd.bdate_range("2024-01-01", periods=5)).astype(float)

    def test_demo_cache_roundtrip_is_exact(self):
        with tempfile.TemporaryDirectory() as temp:
            first = load_prices(self.cfg, temp)
            second = load_prices(self.cfg, temp)
            pd.testing.assert_frame_equal(first.prices, second.prices)
            self.assertFalse(first.manifest["cache_hit"])
            self.assertTrue(second.manifest["cache_hit"])
            self.assertTrue(second.manifest["synthetic"])

    def test_cache_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            load_prices(self.cfg, temp)
            next(Path(temp).glob("*.csv")).write_text("tampered")
            with self.assertRaises(DataError):
                load_prices(self.cfg, temp)

    def test_source_names_do_not_share_cache(self):
        raw = pd.concat({"Adj Close": self.frame}, axis=1)
        fake_yf = types.SimpleNamespace(__version__="mock", download=lambda *a,**k: raw)
        with tempfile.TemporaryDirectory() as temp, patch.dict("sys.modules", {"yfinance": fake_yf}):
            load_prices(self.cfg, temp)
            live = load_prices(replace(self.cfg, source="yahoo"), temp)
            self.assertEqual(len(list(Path(temp).glob("*.csv"))), 2)
            self.assertFalse(live.manifest["synthetic"])

    def test_provider_failure_never_silently_returns_demo(self):
        raw = pd.DataFrame()
        fake_yf = types.SimpleNamespace(__version__="mock", download=lambda *a,**k: raw)
        with tempfile.TemporaryDirectory() as temp, patch.dict("sys.modules", {"yfinance": fake_yf}), \
                patch("wealthlab.data.time.sleep"):
            with self.assertRaises(DataError):
                load_prices(replace(self.cfg, source="yahoo"), temp)
            self.assertEqual(list(Path(temp).glob("*.csv")), [])

    def test_yahoo_multiindex_field_first(self):
        raw = pd.concat({"Adj Close": self.frame, "Close": self.frame*2}, axis=1)
        selected = extract_yahoo_adjusted_close(raw, ["SPY","AGG"])
        np.testing.assert_allclose(selected, self.frame)

    def test_yahoo_multiindex_ticker_first(self):
        raw = pd.concat({"Adj Close": self.frame}, axis=1).swaplevel(axis=1)
        selected = extract_yahoo_adjusted_close(raw, ["SPY","AGG"])
        np.testing.assert_allclose(selected, self.frame)

    def test_unadjusted_prices_are_not_substituted(self):
        with self.assertRaises(DataError):
            extract_yahoo_adjusted_close(pd.DataFrame({"Close": [100]}), ["SPY"])

    def test_interior_missing_is_rejected_not_filled(self):
        self.frame.iloc[2,0] = np.nan
        with self.assertRaises(DataQualityError):
            clean_prices(self.frame, self.cfg)

    def test_identical_duplicates_are_removed(self):
        duplicate = pd.concat([self.frame, self.frame.iloc[[0]]])
        cleaned, quality = clean_prices(duplicate, self.cfg)
        self.assertEqual(len(cleaned), 5)
        self.assertEqual(quality["identical_duplicates_removed"], 1)

    def test_conflicting_duplicates_are_rejected(self):
        duplicate = self.frame.iloc[[0]].copy()
        duplicate.iloc[0,0] = 999
        with self.assertRaises(DataQualityError):
            clean_prices(pd.concat([self.frame, duplicate]), self.cfg)

    def test_nonpositive_and_infinite_prices_are_rejected(self):
        for value in [0, -1, np.inf]:
            changed = self.frame.copy()
            changed.iloc[1,0] = value
            with self.assertRaises(DataQualityError):
                clean_prices(changed, self.cfg)

    def test_late_inception_requires_explicit_start_change(self):
        cfg = replace(self.cfg, start="2023-01-01")
        with self.assertRaises(DataQualityError):
            clean_prices(self.frame, cfg)

    def test_risk_free_uses_calendar_days(self):
        dates = pd.to_datetime(["2024-01-05", "2024-01-08"])
        rf, _ = risk_free_returns(dates, replace(self.cfg, annual_risk_free_rate=.05), ".")
        self.assertEqual(rf.iloc[0], 0)
        self.assertAlmostEqual(rf.iloc[1], 1.05**(3/365.25)-1)

    def test_fred_missing_key_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(DataError, "FRED_API_KEY"):
                risk_free_returns(self.frame.index, replace(self.cfg, risk_free_source="fred"), temp)

    def test_fred_cached_yield_is_lagged(self):
        dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
        start = (dates[0] - pd.Timedelta(days=14)).date().isoformat()
        end = dates[-1].date().isoformat()
        key = sha256(f"fred-DGS3MO-{start}-{end}-v1".encode()).hexdigest()[:20]
        payload = {"observations": [{"date": "2024-01-01", "value": "2"},
                                    {"date": "2024-01-02", "value": "4"},
                                    {"date": "2024-01-03", "value": "8"}]}
        with tempfile.TemporaryDirectory() as temp:
            stored = {"payload": payload, "retrieved_at_utc": "fixture",
                      "sha256": sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}
            (Path(temp)/f"fred-{key}.json").write_text(json.dumps(stored))
            rf, _ = risk_free_returns(dates, replace(self.cfg, risk_free_source="fred"), temp)
            self.assertAlmostEqual(rf.iloc[1], 1.04**(1/365.25)-1)
            self.assertAlmostEqual(rf.iloc[2], 1.08**(1/365.25)-1)


if __name__ == "__main__":
    unittest.main()
