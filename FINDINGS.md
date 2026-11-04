## Findings and Conclusions

### What this project looked at

This project explored how a diversified portfolio performed, where its risk came from, and how an investment plan might support a client's spending goals.

The historical analysis used Yahoo Finance daily adjusted-close history for eight USD-listed ETFs, covering **2015-01-02 to 2025-12-31**, with **2,766 common price observations**. The portfolio started with **AED 3,672,500**, rebalanced monthly, and included **5 basis points** of cost per unit of currency traded and a **0.50% annual advisory fee**.

**The historical analysis uses real Yahoo Finance prices. Portfolio returns are a hypothetical backtest; client projections and stress scenarios remain simulations.**

Amounts are in UAE dirhams (AED). The existing USD case is translated at a fixed reporting rate of 1 USD = AED 3.6725, verified against CBUAE on 2026-11-04. Yahoo ETF quotes remain USD source data; portfolio accounting applies their percentage returns to AED capital. A constant USD/AED rate is assumed throughout history and planning. FX spreads, conversion charges, and a change in the peg are not modeled.

### How the portfolio performed

| Metric | Client portfolio | Strategic benchmark |
|---|---:|---:|
| Total return | 106.87% | 142.53% |
| Annualized return (CAGR) | 6.83% | 8.39% |
| Annualized volatility | 9.38% | 10.93% |
| Maximum drawdown | -20.07% | -21.49% |
| Sharpe ratio | 0.49 | 0.57 |

The portfolio finished at approximately **AED 7,597,391**, compared with **AED 8,906,958** for the benchmark. The portfolio had lower volatility than the benchmark and earned a lower annualized return. This is a useful reminder to evaluate return and risk together when comparing allocations.

The Sharpe ratio used an explicit **2.50% annual risk-free assumption** in this case. It is a comparison assumption, not an observed cash-investment return series.

Fees also added up. The portfolio paid approximately **AED 277,392 in advisory fees** and **AED 8,299 in trading costs**. These direct deductions are different from the full terminal-wealth effect, which also reflects compounding.

### Where the returns and risk came from

**SPY** made the largest positive monetary contribution, approximately **AED 2,155,347**. Every asset made a positive cumulative monetary contribution in this sample.

At the final observation, SPY represented **27.93% of portfolio capital but 53.02% of estimated volatility**. AGG represented **24.85% of capital and 3.74% of estimated volatility**. Risk contributions use the final trailing 252-return sample, rather than the entire performance window.

This makes the difference between allocating money and allocating risk clear. Position weights alone do not tell the whole story.

### What happened under stress

The hypothetical shocks to the final holdings produced:

- **15.84% loss**: equity-led selloff.
- **11.99% loss**: rates + inflation shock.
- **16.66% loss**: broad liquidity shock.

These are assumed asset-price shocks. They are not reconstructions of actual crisis returns and do not model recovery, liquidity costs, or changes in holdings during a crisis.

### What the client planning model showed

The planning exercise was separate from the historical backtest. It started with **AED 7,345,000**, annual spending of **AED 264,420**, additional spending of **AED 918,125 in month 24**, and a **AED 1,836,250 terminal legacy target after 20 years**. Spending and goals were expressed in today's purchasing power.

The model used **6% expected annual nominal return before advisory fees, 12% volatility, and 2.5% inflation**, across **5,000 simulated paths**. These forward assumptions were set explicitly; they were not automatically inferred from historical returns.

- **89.32%** of paths covered every planned spending payment.
- **65.68%** covered every payment and also reached the legacy target.

Lowering the annual return assumption to **4%** reduced the joint success frequency to **40.40%** at the same spending level. The size of that change shows how sensitive a financial plan can be to assumptions. These are model frequencies, not guarantees.

### Final takeaway and limitations

The most useful part of this project was connecting portfolio numbers with questions a wealth manager would discuss with a client: how much risk the portfolio carries, what fees cost, and whether spending goals remain achievable under different assumptions.

The historical portfolio is hypothetical and uses a retrospectively selected ETF universe, fractional holdings, adjusted-price proxies, and simplified close execution. Taxes, borrowing, account restrictions, and suitability are outside this version. The planning model also assumes lognormal returns, constant volatility, and deterministic inflation.

The project provides a transparent way to explore investment performance and planning trade-offs while keeping those limits visible. Past performance does not establish future results.

## Project reflection

[Personal reflection](docs/PERSONAL_REFLECTION.md) · [Research choices and planned extensions](docs/RESEARCH_NOTES.md)
