"""Currency equivalence checks using the same returns, costs, and scenario shocks."""

from dataclasses import replace
import tempfile
import unittest

import numpy as np
import pandas as pd

from wealthlab.analytics import performance_metrics, pnl_attribution
from wealthlab.config import ClientConfig, ResearchConfig
from wealthlab.currency import AED_PER_USD, conversion_factor, format_money
from wealthlab.pipeline import run_project
from wealthlab.planning import simulate_client
from wealthlab.portfolio import run_backtest


class CurrencyTests(unittest.TestCase):
    def test_fixed_translation_and_round_trip(self):
        self.assertEqual(1_000_000 * conversion_factor("USD", "AED"), 3_672_500)
        self.assertEqual(72_000 * conversion_factor("USD", "AED"), 264_420)
        self.assertAlmostEqual(conversion_factor("USD", "AED") * conversion_factor("AED", "USD"), 1)
        self.assertEqual(conversion_factor("AED", "AED"), 1)

    def test_default_case_preserves_original_purchasing_amounts(self):
        cfg, client = ResearchConfig(), ClientConfig()
        self.assertEqual(cfg.initial_capital, 1_000_000 * AED_PER_USD)
        self.assertEqual(client.current_wealth, 2_000_000 * AED_PER_USD)
        self.assertEqual(client.annual_spending_today, 72_000 * AED_PER_USD)
        self.assertEqual(client.legacy_goal_today, 500_000 * AED_PER_USD)
        self.assertEqual(client.one_off_spending[24], 250_000 * AED_PER_USD)

    def test_backtest_scales_money_and_preserves_returns_and_weights(self):
        prices = pd.DataFrame({"A": [100, 110, 95, 105, 120], "B": [50, 49, 52, 55, 54]},
            index=pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-03-01", "2024-04-01"]))
        original_prices = prices.copy()
        usd = run_backtest(prices, {"A": .6, "B": .4}, initial_capital=10_000, currency="USD")
        aed = run_backtest(prices, {"A": .6, "B": .4}, initial_capital=36_725, currency="AED")
        monetary = ["nav", "transaction_cost", "advisory_fee"]
        np.testing.assert_allclose(aed.history[monetary], usd.history[monetary] * AED_PER_USD, rtol=1e-12)
        np.testing.assert_allclose(aed.asset_pnl, usd.asset_pnl * AED_PER_USD, rtol=1e-12, atol=1e-10)
        np.testing.assert_allclose(aed.returns, usd.returns, atol=1e-14)
        np.testing.assert_allclose(aed.weights, usd.weights, atol=1e-14)
        self.assertEqual(pnl_attribution(aed).name, "profit_aed")
        self.assertAlmostEqual(pnl_attribution(aed).sum(), aed.history.nav.iloc[-1] - 36_725, places=8)
        pd.testing.assert_frame_equal(prices, original_prices)
        rf = pd.Series(0., index=prices.index[1:])
        usd_metrics, aed_metrics = performance_metrics(usd, rf), performance_metrics(aed, rf)
        for name, value in usd_metrics.items():
            if name.endswith(" USD"):
                self.assertAlmostEqual(aed_metrics[name[:-3] + "AED"], value * AED_PER_USD, places=7)
            else:
                np.testing.assert_allclose(aed_metrics[name], value, rtol=1e-10, atol=1e-12)
        with self.assertRaises(ValueError):
            performance_metrics(aed, rf, benchmark=usd)

    def test_planning_scales_wealth_without_changing_goal_frequencies(self):
        usd = ClientConfig(currency="USD", current_wealth=120_000, annual_spending_today=5_000,
            legacy_goal_today=50_000, one_off_spending={12: 10_000}, horizon_years=2, paths=200)
        aed = replace(usd, currency="AED", current_wealth=usd.current_wealth * AED_PER_USD,
            annual_spending_today=usd.annual_spending_today * AED_PER_USD,
            legacy_goal_today=usd.legacy_goal_today * AED_PER_USD,
            one_off_spending={12: 10_000 * AED_PER_USD})
        left, right = simulate_client(usd), simulate_client(aed)
        np.testing.assert_allclose(right.quantiles_real, left.quantiles_real * AED_PER_USD, rtol=1e-12)
        np.testing.assert_array_equal(right.funded_all_spending, left.funded_all_spending)
        self.assertEqual(right.success_probability, left.success_probability)
        self.assertEqual(right.survival_probability, left.survival_probability)

    def test_mixed_currencies_rejected_before_data_access(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            run_project(ResearchConfig(source="yahoo"), ClientConfig(currency="USD"), temp)

    def test_unsupported_currency_rejected(self):
        for constructor in (ResearchConfig, ClientConfig):
            with self.assertRaises(ValueError):
                constructor(currency="MAD")

    def test_money_format_is_explicit_and_rejects_nonfinite_values(self):
        self.assertEqual(format_money(264420), "AED 264,420")
        self.assertEqual(format_money(-1000, "AED", 2), "AED -1,000.00")
        with self.assertRaises(ValueError):
            format_money(float("nan"))


if __name__ == "__main__":
    unittest.main()
