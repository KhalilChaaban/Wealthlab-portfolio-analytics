"""Performance, drawdown, attribution, and ex-post risk diagnostics."""

import numpy as np
import pandas as pd

from .portfolio import BacktestResult


def drawdown(result: BacktestResult) -> pd.Series:
    """Include initial capital in the high-water mark, preserving initial trade cost."""
    peak = result.history["nav"].cummax().clip(lower=result.initial_capital)
    return (result.history["nav"] / peak - 1).rename("drawdown")


def performance_metrics(result: BacktestResult, risk_free: pd.Series,
                        benchmark: BacktestResult | None = None,
                        periods_per_year: int = 252) -> pd.Series:
    """Calendar-time CAGR; daily-sample volatility and Sharpe use n-1 return periods.

    Initial purchase cost enters total return/CAGR and monetary attribution. It
    is omitted from daily-distribution risk metrics because it has no elapsed
    return interval. Benchmark and portfolio use the same execution assumptions.
    """
    returns = result.returns.iloc[1:]
    if not returns.index.equals(risk_free.reindex(returns.index).dropna().index):
        raise ValueError("Risk-free returns must cover every portfolio return interval.")
    if not np.isfinite(risk_free.reindex(returns.index).to_numpy()).all():
        raise ValueError("Risk-free returns must be finite.")
    years = (result.history.index[-1] - result.history.index[0]).days / 365.25
    if years <= 0:
        raise ValueError("Performance requires a positive elapsed interval.")
    excess = returns - risk_free.reindex(returns.index)
    volatility = returns.std(ddof=1) * np.sqrt(periods_per_year)
    excess_std = excess.std(ddof=1)
    downside = np.sqrt(np.minimum(excess.to_numpy(), 0.0).dot(
        np.minimum(excess.to_numpy(), 0.0)) / len(excess))
    dd = drawdown(result)
    max_dd = float(dd.min())
    cagr = (result.history["nav"].iloc[-1] / result.initial_capital) ** (1 / years) - 1
    loss = -returns
    var = float(loss.quantile(.95))
    es = float(loss[loss >= var].mean())
    metrics = {
        "Total return": result.history["nav"].iloc[-1] / result.initial_capital - 1,
        "CAGR": cagr, "Annualized volatility": volatility,
        "Sharpe ratio": excess.mean() / excess_std * np.sqrt(periods_per_year)
        if excess_std > 1e-12 else np.nan,
        "Sortino ratio": excess.mean() / downside * np.sqrt(periods_per_year)
        if downside > 1e-12 else np.nan,
        "Maximum drawdown": max_dd,
        "Calmar ratio": cagr / abs(max_dd) if max_dd < -1e-12 else np.nan,
        "Historical daily VaR 95%": var, "Historical daily ES 95%": es,
        "Positive-return day fraction": float((returns > 0).mean()),
        "Annual gross turnover excl. initial": result.history["gross_traded_nav_fraction"].iloc[1:].sum() / years,
        f"Transaction costs {result.currency}": result.history["transaction_cost"].sum(),
        f"Advisory fees {result.currency}": result.history["advisory_fee"].sum(),
        f"Ending NAV {result.currency}": result.history["nav"].iloc[-1],
    }
    if benchmark is not None:
        if benchmark.currency != result.currency:
            raise ValueError("Portfolio and benchmark reporting currencies must match.")
        if not benchmark.returns.index.equals(result.returns.index):
            raise ValueError("Portfolio and benchmark dates must match exactly.")
        b = benchmark.returns.iloc[1:]
        active = returns - b
        te = active.std(ddof=1) * np.sqrt(periods_per_year)
        b_variance = float(b.var(ddof=1))
        beta = float(returns.cov(b) / b_variance) if b_variance > 1e-16 else np.nan
        metrics.update({"Tracking error": te,
                        "Information ratio": active.mean() * periods_per_year / te if te > 1e-12 else np.nan,
                        "Beta to benchmark": beta})
    return pd.Series(metrics, name="value")


def pnl_attribution(result: BacktestResult) -> pd.Series:
    """Exact additive P&L in the result's reporting currency."""
    contribution = result.asset_pnl.sum()
    contribution.loc["Trading costs"] = -result.history["transaction_cost"].sum()
    contribution.loc["Advisory fees"] = -result.history["advisory_fee"].sum()
    contribution.name = f"profit_{result.currency.lower()}"
    return contribution


def dollar_attribution(result: BacktestResult) -> pd.Series:
    """Compatibility alias; returned amounts use result.currency, including AED."""
    return pnl_attribution(result)


def risk_contributions(asset_returns: pd.DataFrame, weights: pd.Series,
                       periods_per_year: int = 252, lookback: int = 252) -> pd.DataFrame:
    """Trailing-sample Euler volatility decomposition at the latest held weights.

    Negative components are retained: they represent estimated diversification.
    This is ex-post risk diagnosis, not a forecast or return attribution.
    """
    sample = asset_returns.tail(lookback)
    if len(sample) < 30:
        raise ValueError("Risk decomposition needs at least 30 observations.")
    w = weights.reindex(sample.columns)
    if not np.isfinite(w.to_numpy()).all() or not np.isfinite(sample.to_numpy()).all():
        raise ValueError("Risk data or weights are invalid.")
    covariance = sample.cov().to_numpy() * periods_per_year
    vector = w.to_numpy()
    variance = float(vector @ covariance @ vector)
    if variance <= 1e-16:
        raise ValueError("Risk decomposition requires nonzero portfolio variance.")
    volatility = np.sqrt(variance)
    component = vector * (covariance @ vector) / volatility
    return pd.DataFrame({"capital_weight": vector, "component_volatility": component,
                         "risk_share": component / volatility}, index=sample.columns)


def monthly_returns(result: BacktestResult) -> pd.Series:
    return result.returns.resample("ME").apply(lambda x: (1 + x).prod() - 1).rename("monthly_return")


def hypothetical_stress(weights: pd.Series) -> pd.DataFrame:
    """Fixed-holdings shocks, not reconstructed historical crisis returns."""
    scenarios = {
        "Equity-led selloff": {"SPY": -.30, "VEA": -.32, "VWO": -.38, "AGG": .04,
                               "TIP": -.03, "GLD": .08, "VNQ": -.35, "BIL": 0},
        "Rates + inflation shock": {"SPY": -.15, "VEA": -.15, "VWO": -.18, "AGG": -.12,
                                    "TIP": -.08, "GLD": .05, "VNQ": -.22, "BIL": 0},
        "Broad liquidity shock": {"SPY": -.22, "VEA": -.25, "VWO": -.30, "AGG": -.08,
                                  "TIP": -.10, "GLD": -.08, "VNQ": -.30, "BIL": -.002},
    }
    if set(weights.index) - set(next(iter(scenarios.values()))):
        raise ValueError("Add documented stress assumptions for custom tickers before running.")
    rows = {}
    for label, shocks in scenarios.items():
        contributions = weights * pd.Series(shocks).reindex(weights.index)
        rows[label] = {**contributions.to_dict(), "portfolio_return": contributions.sum()}
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("scenario")
