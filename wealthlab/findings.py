"""Generate readable findings directly from the run's reported numbers.

The same function is used for freshly calculated runs and the finalized Yahoo
snapshot recovered from the user's executed notebook. Snapshot precision and
lineage are recorded separately; unavailable observations are never invented.
"""

from html import escape
import re
import textwrap

import pandas as pd

from .config import ClientConfig, ResearchConfig
from .planning import ProjectionResult


def build_findings(config: ResearchConfig, client: ClientConfig, metrics: pd.DataFrame,
                   risk: pd.DataFrame, attribution: pd.Series, stress: pd.DataFrame,
                   projection: ProjectionResult, sensitivity: pd.DataFrame,
                   quality: dict) -> str:
    """Write a complete case discussion without hard-coding investment results."""
    portfolio = metrics["Client portfolio"]
    benchmark = metrics["Strategic benchmark"]
    synthetic = config.source == "demo"
    source = ("synthetic data representing eight asset classes" if synthetic
              else "Yahoo Finance daily adjusted-close history for eight USD-listed ETFs")
    scope = ("**This is a synthetic demonstration, not actual ETF performance.**" if synthetic
             else "**The historical analysis uses real Yahoo Finance prices. Portfolio returns are a hypothetical backtest; client projections and stress scenarios remain simulations.**")
    smaller_vol = portfolio["Annualized volatility"] < benchmark["Annualized volatility"]
    higher_return = portfolio["CAGR"] > benchmark["CAGR"]
    comparison = (f"The portfolio had {'lower' if smaller_vol else 'higher'} volatility than the benchmark "
                  f"and earned a {'higher' if higher_return else 'lower'} annualized return. "
                  "This is a useful reminder to evaluate return and risk together when comparing allocations.")
    asset_pnl = attribution.drop(labels=["Trading costs", "Advisory fees"], errors="ignore")
    best = asset_pnl.idxmax()
    negative = asset_pnl[asset_pnl < 0]
    extra_attribution = (f"The largest negative asset contribution came from {negative.idxmin()}, "
                         f"at approximately **${negative.min():,.0f}**." if len(negative)
                         else "Every asset made a positive cumulative dollar contribution in this sample.")
    table_metrics = ["Total return", "CAGR", "Annualized volatility", "Maximum drawdown", "Sharpe ratio"]
    labels = ["Total return", "Annualized return (CAGR)", "Annualized volatility", "Maximum drawdown", "Sharpe ratio"]
    rows = ["| Metric | Client portfolio | Strategic benchmark |", "|---|---:|---:|"]
    for key, label in zip(table_metrics, labels):
        fmt = ".2f" if key == "Sharpe ratio" else ".2%"
        rows.append(f"| {label} | {format(portfolio[key], fmt)} | {format(benchmark[key], fmt)} |")
    stress_lines = "\n".join(f"- **{abs(row['portfolio_return']):.2%} loss**: {name.lower()}."
                             for name, row in stress.iterrows())
    spy = risk.loc["SPY"]
    agg = risk.loc["AGG"]
    low_return = float(sensitivity.columns.min())
    spending = min(sensitivity.index, key=lambda value: abs(float(value)-client.annual_spending_today))
    low_success = float(sensitivity.loc[spending, low_return])
    one_off = "; ".join(f"${value:,.0f} in month {month}" for month, value in sorted(client.one_off_spending.items())) or "none"
    text = f"""
## Findings and Conclusions

### What this project looked at

This project explored how a diversified portfolio performed, where its risk came from, and how an investment plan might support a client's spending goals.

The historical analysis used {source}, covering **{quality['first_observation']} to {quality['last_observation']}**, with **{quality['retained_rows']:,} common price observations**. The portfolio started with **${config.initial_capital:,.0f}**, rebalanced {config.rebalance}, and included **{config.trading_cost_bps:g} basis points** of cost per dollar traded and a **{config.advisory_fee_annual:.2%} annual advisory fee**.

{scope}

### How the portfolio performed

{chr(10).join(rows)}

The portfolio finished at approximately **${portfolio['Ending NAV USD']:,.0f}**, compared with **${benchmark['Ending NAV USD']:,.0f}** for the benchmark. {comparison}

The Sharpe ratio used an explicit **{config.annual_risk_free_rate:.2%} annual risk-free assumption** in this case. It is a comparison assumption, not an observed cash-investment return series.

Fees also added up. The portfolio paid approximately **${portfolio['Advisory fees USD']:,.0f} in advisory fees** and **${portfolio['Transaction costs USD']:,.0f} in trading costs**. These direct deductions are different from the full terminal-wealth effect, which also reflects compounding.

### Where the returns and risk came from

**{best}** made the largest positive dollar contribution, approximately **${asset_pnl.loc[best]:,.0f}**. {extra_attribution}

At the final observation, SPY represented **{spy['capital_weight']:.2%} of portfolio capital but {spy['risk_share']:.2%} of estimated volatility**. AGG represented **{agg['capital_weight']:.2%} of capital and {agg['risk_share']:.2%} of estimated volatility**. Risk contributions use the final trailing 252-return sample, rather than the entire performance window.

This makes the difference between allocating money and allocating risk clear. Position weights alone do not tell the whole story.

### What happened under stress

The hypothetical shocks to the final holdings produced:

{stress_lines}

These are assumed asset-price shocks. They are not reconstructions of actual crisis returns and do not model recovery, liquidity costs, or changes in holdings during a crisis.

### What the client planning model showed

The planning exercise was separate from the historical backtest. It started with **${client.current_wealth:,.0f}**, annual spending of **${client.annual_spending_today:,.0f}**, additional spending of **{one_off}**, and a **${client.legacy_goal_today:,.0f} terminal legacy target after {client.horizon_years} years**. Spending and goals were expressed in today's purchasing power.

The model used **{client.expected_annual_return:.0%} expected annual nominal return before advisory fees, {client.annual_volatility:.0%} volatility, and {client.inflation:.1%} inflation**, across **{client.paths:,} simulated paths**. These forward assumptions were set explicitly; they were not automatically inferred from historical returns.

- **{projection.survival_probability:.2%}** of paths covered every planned spending payment.
- **{projection.success_probability:.2%}** covered every payment and also reached the legacy target.

Lowering the annual return assumption to **{low_return:.0%}** reduced the joint success frequency to **{low_success:.2%}** at the same spending level. The size of that change shows how sensitive a financial plan can be to assumptions. These are model frequencies, not guarantees.

### Final takeaway and limitations

The most useful part of this project was connecting portfolio numbers with questions a wealth manager would discuss with a client: how much risk the portfolio carries, what fees cost, and whether spending goals remain achievable under different assumptions.

The historical portfolio is hypothetical and uses a retrospectively selected ETF universe, fractional holdings, adjusted-price proxies, and simplified close execution. Taxes, borrowing, account restrictions, and suitability are outside this version. The planning model also assumes lognormal returns, constant volatility, and deterministic inflation.

The project provides a transparent way to explore investment performance and planning trade-offs while keeping those limits visible. Past performance does not establish future results.
"""
    return textwrap.dedent(text).strip() + "\n"


def findings_to_html(markdown: str) -> str:
    """Render the small Markdown subset emitted above, escaping all source text."""
    def inline(value: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(value))
    lines = markdown.splitlines()
    result, index = [], 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("#"):
            level = min(4, len(line) - len(line.lstrip("#")))
            result.append(f"<h{level}>{inline(line.lstrip('#').strip())}</h{level}>")
        elif line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = lines[index].strip()
                if not re.fullmatch(r"[|:\- ]+", row):
                    rows.append([inline(value.strip()) for value in row.strip("|").split("|")])
                index += 1
            result.append('<div class="table-wrap"><table><thead><tr>' + ''.join(
                f"<th>{value}</th>" for value in rows[0]) + "</tr></thead><tbody>" + ''.join(
                "<tr>" + ''.join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows[1:])
                + "</tbody></table></div>")
            continue
        elif line.startswith("- "):
            bullets = []
            while index < len(lines) and lines[index].strip().startswith("- "):
                bullets.append("<li>" + inline(lines[index].strip()[2:]) + "</li>")
                index += 1
            result.append("<ul>" + ''.join(bullets) + "</ul>")
            continue
        else:
            paragraph = [line]
            while index + 1 < len(lines) and lines[index+1].strip():
                index += 1
                paragraph.append(lines[index].strip())
            result.append("<p>" + inline(" ".join(paragraph)) + "</p>")
        index += 1
    return "\n".join(result)
