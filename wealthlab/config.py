"""Validated, serializable assumptions; all financial rates are decimal values."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
import math
import pandas as pd


ASSET_NAMES = {
    "SPY": "US equities", "VEA": "Developed ex-US equities",
    "VWO": "Emerging-market equities", "AGG": "US investment-grade bonds",
    "TIP": "Inflation-linked bonds", "GLD": "Gold",
    "VNQ": "US listed real estate", "BIL": "Treasury-bill ETF",
}
DEFAULT_WEIGHTS = {
    "SPY": 0.28, "VEA": 0.12, "VWO": 0.08, "AGG": 0.25,
    "TIP": 0.10, "GLD": 0.07, "VNQ": 0.05, "BIL": 0.05,
}


def validate_weights(weights: dict[str, float], name: str = "weights") -> None:
    """Reject leverage, short positions, empty universes, and silent normalization."""
    if not weights or any(not isinstance(k, str) or not k.strip() for k in weights):
        raise ValueError(f"{name} must contain nonempty ticker names.")
    values = list(weights.values())
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError(f"{name} must be finite and long-only.")
    if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
        raise ValueError(f"{name} must sum to 1, received {sum(values):.8f}.")


@dataclass(frozen=True)
class ResearchConfig:
    """Research mandate. End is exclusive, matching Yahoo's download convention."""

    source: str = "demo"
    start: str = "2015-01-01"
    end: str = "2026-01-01"
    weights: dict[str, float] = field(default_factory=lambda: DEFAULT_WEIGHTS.copy())
    benchmark: dict[str, float] = field(default_factory=lambda: {"SPY": 0.60, "AGG": 0.40})
    initial_capital: float = 1_000_000.0
    trading_cost_bps: float = 5.0
    advisory_fee_annual: float = 0.005
    rebalance: str = "monthly"
    annual_risk_free_rate: float = 0.025
    risk_free_source: str = "constant"
    periods_per_year: int = 252
    min_observations: int = 253
    max_calendar_gap_days: int = 7
    seed: int = 42

    def __post_init__(self) -> None:
        validate_weights(self.weights)
        validate_weights(self.benchmark, "benchmark")
        if set(self.benchmark) - set(self.weights):
            raise ValueError("Benchmark tickers must be included in the portfolio universe.")
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if start.tz is not None or end.tz is not None or start >= end:
            raise ValueError("Use timezone-free dates with start strictly before end.")
        if self.source not in {"demo", "yahoo"}:
            raise ValueError("source must be 'demo' or 'yahoo'; no silent fallback is used.")
        if self.risk_free_source not in {"constant", "fred"}:
            raise ValueError("risk_free_source must be 'constant' or 'fred'.")
        if self.rebalance not in {"monthly", "quarterly", "none"}:
            raise ValueError("rebalance must be monthly, quarterly, or none.")
        for name in ("initial_capital", "trading_cost_bps", "advisory_fee_annual",
                     "annual_risk_free_rate"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite.")
        if self.initial_capital <= 0 or not 0 <= self.trading_cost_bps <= 100:
            raise ValueError("Capital must be positive and transaction costs within 0–100 bps.")
        if not 0 <= self.advisory_fee_annual < 0.20:
            raise ValueError("Advisory fee must be within [0, 20%).")
        if not -0.1 < self.annual_risk_free_rate < 0.5:
            raise ValueError("Risk-free assumption is outside supported bounds.")
        if self.periods_per_year <= 0 or self.min_observations < 3:
            raise ValueError("Invalid observation or annualization configuration.")
        if self.max_calendar_gap_days < 1:
            raise ValueError("max_calendar_gap_days must be positive.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ClientConfig:
    """Fictional planning case, separate from the historical backtest capital."""

    label: str = "Illustrative family mandate"
    current_wealth: float = 2_000_000.0
    annual_spending_today: float = 72_000.0
    horizon_years: int = 20
    inflation: float = 0.025
    expected_annual_return: float = 0.06
    annual_volatility: float = 0.12
    legacy_goal_today: float = 500_000.0
    paths: int = 5_000
    seed: int = 2026
    # Keys are one-based simulation months; values are today's dollars.
    one_off_spending: dict[int, float] = field(default_factory=lambda: {24: 250_000.0})

    def __post_init__(self) -> None:
        for name in ("current_wealth", "annual_spending_today", "inflation",
                     "expected_annual_return", "annual_volatility", "legacy_goal_today"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite.")
        if self.current_wealth <= 0 or self.annual_spending_today < 0 or self.legacy_goal_today < 0:
            raise ValueError("Wealth must be positive; spending and legacy goal nonnegative.")
        if not isinstance(self.horizon_years, int) or not 1 <= self.horizon_years <= 60:
            raise ValueError("horizon_years must be an integer within 1–60.")
        if not isinstance(self.paths, int) or not 100 <= self.paths <= 50_000:
            raise ValueError("paths must be an integer within 100–50,000.")
        if not -0.10 < self.inflation < 0.30 or not -0.95 < self.expected_annual_return < 1:
            raise ValueError("Inflation or return is outside supported bounds.")
        if not 0 <= self.annual_volatility <= 1:
            raise ValueError("Volatility must be within [0, 1].")
        for month, amount in self.one_off_spending.items():
            if (not isinstance(month, int) or not 1 <= month <= 12 * self.horizon_years
                    or not math.isfinite(amount) or amount < 0):
                raise ValueError("One-off spending needs valid one-based months and nonnegative amounts.")
        if self.paths * (12 * self.horizon_years + 1) > 15_000_000:
            raise ValueError("Reduce paths or horizon to keep Colab memory usage bounded.")

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
