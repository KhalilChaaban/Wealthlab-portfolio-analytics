"""Publication-style matplotlib figures; no remote JavaScript or chart service."""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter

from .analytics import drawdown, monthly_returns
from .config import ClientConfig, ensure_directory
from .currency import format_money
from .planning import ProjectionResult
from .portfolio import BacktestResult

NAVY, TEAL, GOLD, RED, MUTED = "#142D4E", "#008D83", "#C89135", "#BE5260", "#64748B"
PALETTE = [TEAL, NAVY, GOLD, "#7B88B8", "#6EB3C4", "#A77B9D", "#91A77B", "#B4BBC5"]


def _style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
        "axes.titleweight": "bold", "axes.labelcolor": MUTED, "text.color": NAVY,
        "axes.edgecolor": "#E2E8F0", "axes.spines.top": False, "axes.spines.right": False,
        "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": "#E6EBF0",
        "grid.alpha": .8, "figure.facecolor": "#F7F9FC", "axes.facecolor": "white",
        "savefig.facecolor": "#F7F9FC", "legend.frameon": False,
    })


def _finish(fig, title: str, subtitle: str, source_label: str, path: Path) -> Path:
    # Lay out axes before adding the header, avoiding double reservation by tight_layout.
    fig.tight_layout(rect=(.02, .06, .99, .86), h_pad=3, w_pad=3)
    fig.suptitle(title, x=.065, y=.98, ha="left", fontsize=20, weight="bold", color=NAVY)
    fig.text(.065, .91, subtitle, color=MUTED, fontsize=10)
    fig.text(.065, .018, source_label, color=RED if "SYNTHETIC" in source_label else MUTED,
             fontsize=9, weight="bold")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _money(x, _, currency="AED"):
    return f"{currency} {x/1e6:.1f}m" if abs(x) >= 1e6 else f"{currency} {x/1000:,.0f}k"


def create_charts(result: BacktestResult, benchmark: BacktestResult, frictionless: BacktestResult,
                  asset_returns: pd.DataFrame, risk: pd.DataFrame, attribution: pd.Series,
                  stress: pd.DataFrame, projection: ProjectionResult, sensitivity: pd.DataFrame,
                  client: ClientConfig, output_dir: str | Path, source_label: str,
                  periods_per_year: int = 252) -> dict[str, Path]:
    _style()
    if len({result.currency, benchmark.currency, frictionless.currency, client.currency}) != 1:
        raise ValueError("Charts require a consistent reporting currency.")
    currency = client.currency
    money = lambda x, pos: _money(x, pos, currency)
    output = ensure_directory(output_dir)
    paths = {}
    # 1. Portfolio review: comparable return, drawdown, capital, and risk views.
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    ax = axes[0, 0]
    for run, label, color, ls in [(result, "Client portfolio · net", TEAL, "-"),
                                   (benchmark, "Strategic benchmark · net", NAVY, "-"),
                                   (frictionless, "Client · before modeled fees/costs", MUTED, "--")]:
        ax.plot(run.history.index, run.history.nav / run.initial_capital, label=label,
                color=color, linewidth=1.7, linestyle=ls)
    ax.set(title=f"Growth of {currency} 1", ylabel="Wealth multiple")
    ax.grid(axis="y")
    ax.legend(fontsize=8, loc="upper left")
    ax = axes[0, 1]
    for run, label, color in [(result, "Client", TEAL), (benchmark, "Benchmark", NAVY)]:
        dd = drawdown(run)
        ax.plot(dd.index, dd, color=color, linewidth=1.4, label=label)
    ax.fill_between(result.history.index, drawdown(result), 0, color=TEAL, alpha=.12)
    ax.set(title="Drawdown from prior peak", ylabel="Decline")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y")
    ax = axes[1, 0]
    final_weights = result.weights.iloc[-1]
    ax.bar(final_weights.index, final_weights.values, color=PALETTE)
    ax.set(title="Current capital allocation", ylabel="Portfolio weight")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y")
    ax = axes[1, 1]
    x = np.arange(len(risk))
    ax.bar(x - .18, risk.capital_weight, width=.36, color=NAVY, label="Capital weight")
    ax.bar(x + .18, risk.risk_share, width=.36, color=TEAL, label="Trailing risk share")
    ax.set_xticks(x, risk.index)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title="Capital weight versus volatility contribution", ylabel="Share")
    ax.legend(fontsize=8)
    ax.grid(axis="y")
    paths["overview"] = _finish(fig, "WEALTHLAB / Portfolio review",
        "Fixed strategic weights · drifting holdings · explicit trading costs and advisory fees",
        source_label, output / "01_portfolio_overview.png")

    # 2. Time-series diagnostics and co-movement.
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    ax = axes[0, 0]
    rolling = result.returns.iloc[1:].rolling(63).std() * np.sqrt(periods_per_year)
    ax.plot(rolling.index, rolling, color=TEAL, linewidth=1.5)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title="63-session rolling volatility", ylabel="Annualized volatility")
    ax.grid(axis="y")
    ax = axes[0, 1]
    corr = asset_returns.corr()
    im = ax.imshow(corr, vmin=-1, vmax=1, cmap="BrBG")
    ax.set_xticks(range(len(corr)), corr.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(corr)), corr.index)
    ax.set_title("Asset return correlation")
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.iloc[i,j]:.1f}", ha="center", va="center", fontsize=7,
                    color="white" if abs(corr.iloc[i,j]) > .65 else NAVY)
    fig.colorbar(im, ax=ax, fraction=.04, pad=.03)
    ax = axes[1, 0]
    monthly = monthly_returns(result)
    table = pd.DataFrame({"year": monthly.index.year, "month": monthly.index.month,
                          "return": monthly.values}).pivot(index="year", columns="month", values="return")
    table = table.reindex(columns=range(1, 13))
    bound = max(.02, float(np.nanmax(np.abs(table.to_numpy()))))
    im = ax.imshow(table, aspect="auto", cmap="BrBG", vmin=-bound, vmax=bound)
    ax.set_xticks(range(12), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks(range(len(table)), table.index)
    ax.set_title("Monthly net returns (first/last months may be partial)")
    for i in range(len(table)):
        for j in range(12):
            value = table.iloc[i, j]
            if pd.notna(value):
                ax.text(j, i, f"{value:.0%}", ha="center", va="center", fontsize=7,
                        color="white" if abs(value) > bound * .65 else NAVY)
    ax = axes[1, 1]
    r = result.returns.iloc[1:]
    ax.hist(r, bins=60, color=TEAL, alpha=.8, edgecolor="white")
    threshold = r.quantile(.05)
    ax.axvline(threshold, color=RED, linestyle="--", label=f"5th percentile: {threshold:.2%}")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title="Daily net-return distribution", ylabel="Observations")
    ax.legend(fontsize=8)
    paths["diagnostics"] = _finish(fig, "WEALTHLAB / Risk diagnostics",
        "Daily-sample estimates · correlation and historical tails are not forecasts",
        source_label, output / "02_risk_diagnostics.png")

    # 3. Exact monetary attribution and drift.
    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5), gridspec_kw={"height_ratios": [1, 1.1]})
    ax = axes[0]
    bars = ax.bar(attribution.index, attribution.values,
                  color=[TEAL if v >= 0 else RED for v in attribution])
    ax.axhline(0, color=MUTED, linewidth=.8)
    ax.yaxis.set_major_formatter(FuncFormatter(money))
    ax.bar_label(bars, labels=[_money(v, None, currency) for v in attribution], fontsize=8, padding=3)
    ax.set(title="Additive P&L attribution", ylabel=f"{currency} contribution")
    ax.margins(y=.25)
    ax.grid(axis="y")
    ax = axes[1]
    ax.stackplot(result.weights.index, result.weights.T.to_numpy(), labels=result.weights.columns,
                 colors=PALETTE, alpha=.9)
    ax.set(title="Held weights after fees and any scheduled rebalance", ylabel="Portfolio weight", ylim=(0, 1))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.legend(ncol=8, fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.12))
    paths["attribution"] = _finish(fig, "WEALTHLAB / Performance explained",
        "Asset P&L minus trading costs and advisory fees reconciles to ending NAV minus starting capital",
        source_label, output / "03_attribution_and_weights.png")

    paths.update(create_planning_charts(projection, sensitivity, stress, client, output, source_label))
    return paths


def create_planning_charts(projection: ProjectionResult, sensitivity: pd.DataFrame,
                           stress: pd.DataFrame, client: ClientConfig,
                           output_dir: str | Path, source_label: str) -> dict[str, Path]:
    """Render planning from explicit cash-flow assumptions, independent of price history."""
    _style()
    output = ensure_directory(output_dir)
    paths = {}
    currency = client.currency
    money = lambda x, pos: _money(x, pos, currency)
    # 4. Client planning scenarios, deliberately separated from historical estimates.
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    q = projection.quantiles_real
    ax.fill_between(q.index, q.p05, q.p95, color=TEAL, alpha=.12, label="5–95% scenario range")
    ax.fill_between(q.index, q.p25, q.p75, color=TEAL, alpha=.25, label="25–75% range")
    ax.plot(q.index, q.p50, color=TEAL, linewidth=2, label="Median")
    ax.axhline(client.legacy_goal_today, color=GOLD, linestyle="--", label="Terminal legacy target")
    ax.yaxis.set_major_formatter(FuncFormatter(money))
    ax.set(title="Projected wealth after planned spending", xlabel="Years", ylabel=f"Today's {currency}")
    ax.grid(axis="y")
    ax.legend(fontsize=8)
    ax = axes[1]
    cutoff = max(1.0, float(np.quantile(projection.terminal_real, .99)))
    ax.hist(projection.terminal_real, bins=50, range=(0, cutoff), color=NAVY, alpha=.85)
    ax.axvline(client.legacy_goal_today, color=GOLD, linestyle="--")
    ax.xaxis.set_major_formatter(FuncFormatter(money))
    ax.tick_params(axis="x", labelrotation=25)
    ax.set(title="Terminal wealth · central 99%", xlabel=f"Today's {currency}", ylabel="Simulated paths")
    ax.xaxis.set_major_locator(MaxNLocator(5))
    paths["planning"] = _finish(fig, "WEALTHLAB / Goals and spending",
        f"Explicit assumptions: return {client.expected_annual_return:.1%}, volatility {client.annual_volatility:.1%}, "
        f"inflation {client.inflation:.1%} · {client.paths:,} simulated paths",
        "ILLUSTRATIVE MODEL SCENARIOS — NOT FORECASTS OR GUARANTEES", output / "04_client_projection.png")

    # 5. Model sensitivity and hypothetical stresses.
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.5))
    ax = axes[0]
    image = ax.imshow(sensitivity.to_numpy(), vmin=0, vmax=1, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(sensitivity.columns)), [f"{x:.0%}" for x in sensitivity.columns])
    ax.set_yticks(range(len(sensitivity)), [format_money(x, currency) for x in sensitivity.index])
    for i in range(len(sensitivity)):
        for j in range(len(sensitivity.columns)):
            value = sensitivity.iloc[i, j]
            ax.text(j, i, f"{value:.1%}", ha="center", va="center", fontsize=13,
                    color="white" if value > .55 else NAVY, weight="bold")
    ax.set(title="Spending funded AND legacy target met", xlabel="Assumed annual nominal return",
           ylabel=f"Annual spending in today's {currency}")
    fig.colorbar(image, ax=ax, fraction=.04, format=PercentFormatter(1))
    ax = axes[1]
    shock = stress["portfolio_return"]
    ax.barh(shock.index, shock, color=RED, alpha=.9)
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.xaxis.set_major_locator(MaxNLocator(5))
    ax.set(title="Hypothetical shocks to current holdings", xlabel="Instantaneous portfolio return")
    ax.grid(axis="x")
    paths["scenarios"] = _finish(fig, "WEALTHLAB / Assumptions under pressure",
        "Left: parametric planning sensitivity · Right: fixed-holdings shocks, without recovery or trading",
        source_label + " | STRESSES ARE HYPOTHETICAL", output / "05_sensitivity_and_stress.png")
    return paths


def create_saved_summary_charts(metrics: pd.DataFrame, risk: pd.DataFrame,
                                attribution: pd.Series, client: ClientConfig,
                                output_dir: str | Path, source_label: str) -> dict[str, Path]:
    """Plot captured summaries without fabricating an unavailable daily history."""
    _style()
    output = ensure_directory(output_dir)
    paths = {}
    names = ["Client portfolio", "Strategic benchmark"]
    labels = ["Client", "Benchmark"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    for ax, key, title in zip(axes.flat[:2], ["CAGR", "Maximum drawdown"],
                              ["Annualized net return", "Maximum drawdown"]):
        values = metrics.loc[key, names].to_numpy()
        bars = ax.bar(labels, values, color=[TEAL, NAVY], width=.5)
        ax.bar_label(bars, labels=[f"{v:.2%}" for v in values], padding=4)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title(title)
        ax.margins(y=.25)
        ax.grid(axis="y")
    x = np.arange(len(risk))
    ax = axes[1, 0]
    ax.bar(x - .18, risk.capital_weight, width=.36, color=NAVY, label="Capital weight")
    ax.bar(x + .18, risk.risk_share, width=.36, color=TEAL, label="Trailing risk share")
    ax.set_xticks(x, risk.index)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set(title="Final capital weights and volatility contributions", ylabel="Share")
    ax.legend(fontsize=8)
    ax.grid(axis="y")
    ax = axes[1, 1]
    values = metrics.loc[f"Ending NAV {client.currency}", names].to_numpy()
    bars = ax.bar(labels, values, color=[TEAL, NAVY], width=.5)
    ax.bar_label(bars, labels=[_money(v, None, client.currency) for v in values], padding=4)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: _money(v, pos, client.currency)))
    ax.set(title="Ending portfolio wealth", ylabel=client.currency)
    ax.margins(y=.25)
    ax.grid(axis="y")
    paths["overview"] = _finish(fig, "WEALTHLAB / Saved Yahoo case",
        "Captured summary statistics · currency-translated amounts · no reconstructed daily paths",
        source_label, output / "01_portfolio_overview.png")

    fig, axes = plt.subplots(2, 1, figsize=(13, 8.5))
    ax = axes[0]
    bars = ax.bar(attribution.index, attribution.values,
                  color=[TEAL if value >= 0 else RED for value in attribution])
    ax.axhline(0, color=MUTED, linewidth=.8)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: _money(v, pos, client.currency)))
    ax.bar_label(bars, labels=[_money(v, None, client.currency) for v in attribution], fontsize=8, padding=3)
    ax.set(title="Cumulative P&L and modeled costs", ylabel=f"{client.currency} contribution")
    ax.margins(y=.3)
    ax.grid(axis="y")
    ax = axes[1]
    bars = ax.bar(risk.index, risk.capital_weight, color=PALETTE)
    ax.bar_label(bars, labels=[f"{v:.1%}" for v in risk.capital_weight], padding=3)
    ax.set(title="Final capital allocation from the saved case", ylabel="Portfolio weight")
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.margins(y=.25)
    ax.grid(axis="y")
    paths["attribution"] = _finish(fig, "WEALTHLAB / Performance explained",
        "Saved cumulative contributions and final weights · daily holdings history is not included",
        source_label, output / "03_attribution_and_weights.png")
    return paths
