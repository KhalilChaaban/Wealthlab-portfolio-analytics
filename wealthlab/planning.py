"""Transparent client cash-flow simulation, separate from historical performance."""

from dataclasses import dataclass, replace
import numpy as np
import pandas as pd

from .config import ClientConfig


@dataclass
class ProjectionResult:
    quantiles_real: pd.DataFrame
    terminal_real: np.ndarray
    funded_all_spending: np.ndarray
    success_probability: float
    survival_probability: float
    success_mc_standard_error: float
    depletion_probability: pd.Series


def simulate_client(client: ClientConfig, advisory_fee_annual: float = .005,
                    shocks: np.ndarray | None = None) -> ProjectionResult:
    """Monthly lognormal scenarios; beginning-of-month spending, then return and fee.

    mu is expected SIMPLE annual nominal return before advisory fees:
    log increment = [log(1+mu)-sigma^2/2]/12 + sigma/sqrt(12)*Z.
    Expenses escalate with deterministic inflation. Once a spending payment
    cannot be met, wealth remains zero; there are no contributions or borrowing.
    'Success' means all payments funded AND final real wealth >= legacy goal.
    """
    if not np.isfinite(advisory_fee_annual) or not 0 <= advisory_fee_annual < .2:
        raise ValueError("Invalid advisory fee.")
    months = client.horizon_years * 12
    if shocks is None:
        shocks = np.random.default_rng(client.seed).standard_normal((months, client.paths))
    if shocks.shape != (months, client.paths) or not np.isfinite(shocks).all():
        raise ValueError("Simulation shocks have the wrong shape or nonfinite values.")
    balances = np.empty((months + 1, client.paths), dtype=np.float64)
    balances[0] = client.current_wealth
    funded = np.ones(client.paths, dtype=bool)
    depletion = np.zeros(months + 1)
    sigma = client.annual_volatility
    drift = (np.log1p(client.expected_annual_return) - .5 * sigma ** 2) / 12
    scale = sigma / np.sqrt(12)
    fee_factor = (1 - advisory_fee_annual) ** (1 / 12)
    for m in range(1, months + 1):
        # Month 1 spending is today's nominal amount; the real-value basis is t=0.
        inflation_factor = (1 + client.inflation) ** ((m - 1) / 12)
        payment = (client.annual_spending_today / 12 + client.one_off_spending.get(m, 0)) * inflation_factor
        funded &= balances[m - 1] >= payment
        remainder = np.maximum(balances[m - 1] - payment, 0)
        balances[m] = remainder * np.exp(drift + scale * shocks[m - 1]) * fee_factor
        depletion[m] = 1 - funded.mean()
    deflator = (1 + client.inflation) ** (np.arange(months + 1) / 12)
    balances /= deflator[:, None]
    quantiles = np.quantile(balances, [.05, .25, .50, .75, .95], axis=1).T
    index = pd.Index(np.arange(months + 1) / 12, name="year")
    terminal = balances[-1].copy()
    success = funded & (terminal >= client.legacy_goal_today)
    probability = float(success.mean())
    return ProjectionResult(
        pd.DataFrame(quantiles, index=index, columns=["p05", "p25", "p50", "p75", "p95"]),
        terminal, funded, probability, float(funded.mean()),
        float(np.sqrt(probability * (1 - probability) / client.paths)),
        pd.Series(depletion, index=index, name="unfunded_spending_probability"),
    )


def planning_sensitivity(client: ClientConfig, advisory_fee_annual: float) -> pd.DataFrame:
    """Compare return/spending assumptions using common random numbers."""
    shocks = np.random.default_rng(client.seed).standard_normal((client.horizon_years * 12, client.paths))
    means = [client.expected_annual_return - .02, client.expected_annual_return,
             client.expected_annual_return + .02]
    spending = [client.annual_spending_today * .8, client.annual_spending_today,
                client.annual_spending_today * 1.2]
    table = pd.DataFrame(index=spending, columns=means, dtype=float)
    table.index.name = f"annual_spending_today_{client.currency.lower()}"
    table.columns.name = "expected_nominal_return"
    for expense in spending:
        for mean in means:
            case = replace(client, annual_spending_today=expense, expected_annual_return=mean)
            table.loc[expense, mean] = simulate_client(case, advisory_fee_annual, shocks).success_probability
    return table
