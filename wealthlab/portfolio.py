"""Self-financing, long-only accounting with drifting weights and explicit costs."""

from dataclasses import dataclass
import numpy as np
import pandas as pd

from .config import validate_weights


@dataclass
class BacktestResult:
    history: pd.DataFrame
    weights: pd.DataFrame
    asset_pnl: pd.DataFrame
    initial_capital: float
    target_weights: pd.Series

    @property
    def returns(self) -> pd.Series:
        """First observation contains initial purchase cost; later rows are close-to-close."""
        return self.history["net_return"]


def self_financing_rebalance(holdings: np.ndarray, total_nav: float,
                             target: np.ndarray, cost_rate: float) -> tuple[np.ndarray, float, float]:
    """Solve V_after + c * sum(abs(w * V_after - holdings)) = V_before.

    The same convention applies to initial deployment from cash (holdings=0).
    Bisection avoids approximating costs using a pre-cost target portfolio.
    Turnover is gross traded notional / pre-trade NAV (buys plus sells).
    """
    if total_nav <= 0 or not np.isfinite(total_nav):
        raise ValueError("Rebalance NAV must be finite and positive.")
    if not np.isfinite(cost_rate) or not 0 <= cost_rate <= .01:
        raise ValueError("Cost rate must be within [0, 1%].")
    holdings, target = np.asarray(holdings, float), np.asarray(target, float)
    if (holdings.shape != target.shape or holdings.ndim != 1
            or not np.isfinite(holdings).all() or not np.isfinite(target).all()
            or (holdings < 0).any() or (target < 0).any()
            or not np.isclose(target.sum(), 1, atol=1e-10)):
        raise ValueError("Invalid holdings or target allocation.")
    if holdings.sum() > total_nav * (1 + 1e-10):
        raise ValueError("Holdings cannot exceed NAV in this unlevered engine.")
    if cost_rate == 0:
        invested = total_nav
    else:
        low, high = 0.0, total_nav
        for _ in range(55):
            mid = (low + high) / 2
            residual = mid + cost_rate * np.abs(mid * target - holdings).sum() - total_nav
            if residual > 0:
                high = mid
            else:
                low = mid
        invested = (low + high) / 2
    new_holdings = target * invested
    traded = float(np.abs(new_holdings - holdings).sum())
    return new_holdings, traded * cost_rate, traded / total_nav


def run_backtest(prices: pd.DataFrame, target_weights: dict[str, float],
                 initial_capital: float = 1_000_000, trading_cost_bps: float = 5,
                 advisory_fee_annual: float = .005, rebalance: str = "monthly") -> BacktestResult:
    """Accrue asset returns, deduct fees, then execute predetermined close rebalances.

    Rebalance on the first available close in a new month/quarter. Target
    weights are fixed before the test. No external flows, shorting, fractional
    share constraints, taxes, or uninvested cash are modeled after deployment.
    """
    validate_weights(target_weights)
    if (len(prices) < 2 or prices.empty or prices.index.has_duplicates
            or prices.columns.has_duplicates or not prices.index.is_monotonic_increasing
            or not isinstance(prices.index, pd.DatetimeIndex)):
        raise ValueError("Provide at least two unique, increasing daily price observations.")
    if not set(target_weights).issubset(prices.columns):
        raise ValueError("Prices omit a target asset.")
    raw = prices.to_numpy(dtype=float)
    if not np.isfinite(raw).all() or (raw <= 0).any():
        raise ValueError("Backtest requires finite positive prices without missing values.")
    if (not np.isfinite(initial_capital) or initial_capital <= 0
            or not np.isfinite(advisory_fee_annual) or not 0 <= advisory_fee_annual < .2
            or not np.isfinite(trading_cost_bps) or not 0 <= trading_cost_bps <= 100):
        raise ValueError("Invalid capital, advisory fee, or transaction cost.")
    if rebalance not in {"monthly", "quarterly", "none"}:
        raise ValueError("Unknown rebalance schedule.")
    target = pd.Series(target_weights).reindex(prices.columns, fill_value=0.0)
    n, k = raw.shape
    asset_returns = np.vstack([np.zeros(k), raw[1:] / raw[:-1] - 1])
    asset_pnl = np.zeros((n, k))
    weights = np.zeros((n, k))
    nav = np.zeros(n)
    costs, fees, turnover, net_returns = (np.zeros(n) for _ in range(4))
    flags = np.zeros(n, dtype=bool)
    holdings, costs[0], turnover[0] = self_financing_rebalance(
        np.zeros(k), initial_capital, target.to_numpy(), trading_cost_bps / 10_000)
    nav[0], weights[0], flags[0] = holdings.sum(), target.to_numpy(), True
    net_returns[0] = nav[0] / initial_capital - 1
    periods = (prices.index.to_period("M") if rebalance == "monthly"
               else prices.index.to_period("Q"))
    for i in range(1, n):
        asset_pnl[i] = holdings * asset_returns[i]
        holdings = holdings + asset_pnl[i]
        gross_nav = float(holdings.sum())
        days = (prices.index[i] - prices.index[i-1]).days
        fee_fraction = -np.expm1(np.log1p(-advisory_fee_annual) * days / 365.25)
        fees[i] = gross_nav * fee_fraction
        holdings *= 1 - fee_fraction
        if rebalance != "none" and periods[i] != periods[i-1]:
            holdings, costs[i], turnover[i] = self_financing_rebalance(
                holdings, float(holdings.sum()), target.to_numpy(), trading_cost_bps / 10_000)
            flags[i] = True
        nav[i] = holdings.sum()
        weights[i] = holdings / nav[i]
        net_returns[i] = nav[i] / nav[i-1] - 1
    history = pd.DataFrame({
        "nav": nav, "net_return": net_returns, "transaction_cost": costs,
        "advisory_fee": fees, "gross_traded_nav_fraction": turnover, "rebalanced": flags,
    }, index=prices.index).rename_axis("date")
    pnl = pd.DataFrame(asset_pnl, index=prices.index, columns=prices.columns).rename_axis("date")
    # Accounting identity, independent of the performance-metric implementation.
    explained_profit = pnl.to_numpy().sum() - costs.sum() - fees.sum()
    if not np.isclose(nav[-1] - initial_capital, explained_profit, atol=1e-6, rtol=1e-10):
        raise ArithmeticError("Portfolio P&L attribution failed to reconcile.")
    return BacktestResult(history, pd.DataFrame(weights, index=prices.index,
                           columns=prices.columns).rename_axis("date"), pnl, initial_capital, target)
