"""Hand-calculated cases that challenge the accounting, not just its syntax."""

import unittest
import numpy as np
import pandas as pd

from wealthlab.analytics import dollar_attribution, drawdown, performance_metrics, risk_contributions
from wealthlab.portfolio import run_backtest, self_financing_rebalance


def frame(values, dates=None):
    return pd.DataFrame(values, index=pd.to_datetime(dates or ["2024-01-02", "2024-01-03", "2024-01-04"]),
                        columns=["A", "B"])


class AccountingTests(unittest.TestCase):
    def test_buy_hold_drifts_instead_of_daily_rebalancing(self):
        prices = frame([[100, 100], [110, 100], [100, 100]])
        run = run_backtest(prices, {"A": .5, "B": .5}, 1000, 0, 0, "none")
        np.testing.assert_allclose(run.history.nav, [1000, 1050, 1000])
        self.assertAlmostEqual(run.weights.iloc[1].A, 550/1050)
        self.assertAlmostEqual(run.returns.iloc[-1], -50/1050)

    def test_month_boundary_executes_after_that_days_return(self):
        prices = frame([[100, 100], [110, 100], [110, 110]],
                       ["2024-01-30", "2024-02-01", "2024-02-02"])
        run = run_backtest(prices, {"A": .5, "B": .5}, 1000, 0, 0, "monthly")
        np.testing.assert_allclose(run.history.nav, [1000, 1050, 1102.5])
        np.testing.assert_allclose(run.weights.iloc[1], [.5, .5])

    def test_initial_deployment_pays_cost_from_cash(self):
        h, cost, turnover = self_financing_rebalance(np.zeros(2), 1000, np.array([.6, .4]), .01)
        self.assertAlmostEqual(h.sum(), 1000/1.01)
        self.assertAlmostEqual(cost, 1000-h.sum())
        self.assertAlmostEqual(turnover, h.sum()/1000)

    def test_cost_equation_holds_for_a_large_reallocation(self):
        holdings = np.array([900., 100.])
        target = np.array([.2, .8])
        h, cost, _ = self_financing_rebalance(holdings, 1000, target, .007)
        self.assertAlmostEqual(h.sum() + cost, 1000, places=9)
        self.assertAlmostEqual(cost, .007 * np.abs(h-holdings).sum(), places=9)
        np.testing.assert_allclose(h/h.sum(), target)

    def test_advisory_fee_accrues_over_weekend(self):
        prices = frame([[100, 100], [100, 100]], ["2024-01-05", "2024-01-08"])
        run = run_backtest(prices, {"A": 1., "B": 0.}, 1000, 0, .01, "none")
        self.assertAlmostEqual(run.history.nav.iloc[-1], 1000 * .99 ** (3/365.25))

    def test_attribution_reconciles_under_costs_and_rebalancing(self):
        dates = pd.bdate_range("2023-01-01", periods=300)
        rng = np.random.default_rng(4)
        prices = pd.DataFrame(100*np.exp(np.cumsum(rng.normal(0, .01, (300,2)), axis=0)),
                              index=dates, columns=["A", "B"])
        run = run_backtest(prices, {"A": .6, "B": .4}, 10000, 8, .009)
        self.assertAlmostEqual(dollar_attribution(run).sum(), run.history.nav.iloc[-1]-10000, places=7)
        self.assertAlmostEqual((1+run.returns).prod(), run.history.nav.iloc[-1]/10000, places=10)
        np.testing.assert_allclose(run.weights.sum(axis=1), 1)

    def test_initial_cost_is_visible_in_drawdown(self):
        run = run_backtest(frame([[100,100], [100,100], [100,100]]), {"A": .5,"B": .5}, 1000, 10, 0)
        self.assertLess(drawdown(run).iloc[0], 0)

    def test_prefix_results_do_not_change_when_future_data_added(self):
        dates = pd.bdate_range("2024-01-29", periods=8)
        prices = pd.DataFrame({"A": np.arange(100,108), "B": np.arange(100,92,-1)}, index=dates)
        small = run_backtest(prices.iloc[:5], {"A": .5,"B": .5}, trading_cost_bps=5)
        large = run_backtest(prices, {"A": .5,"B": .5}, trading_cost_bps=5)
        pd.testing.assert_frame_equal(small.history, large.history.iloc[:5])

    def test_zero_volatility_ratios_are_undefined(self):
        prices = frame([[100,100], [100,100], [100,100]])
        run = run_backtest(prices, {"A": .5,"B": .5}, 1000, 0, 0)
        metrics = performance_metrics(run, pd.Series(0., index=prices.index), run)
        self.assertTrue(np.isnan(metrics["Sharpe ratio"]))
        self.assertTrue(np.isnan(metrics["Information ratio"]))

    def test_risk_components_sum_to_portfolio_volatility(self):
        returns = pd.DataFrame(np.random.default_rng(4).normal(0,.01,(300,2)), columns=["A","B"])
        rc = risk_contributions(returns, pd.Series({"A": .6,"B": .4}))
        self.assertAlmostEqual(rc.risk_share.sum(), 1)

    def test_invalid_weights_or_prices_are_rejected(self):
        prices = frame([[100,100], [100,100], [100,100]])
        with self.assertRaises(ValueError):
            run_backtest(prices, {"A": .6,"B": .6})
        prices.iloc[1, 0] = np.nan
        with self.assertRaises(ValueError):
            run_backtest(prices, {"A": .5,"B": .5})


if __name__ == "__main__":
    unittest.main()
