# Reporting in UAE dirhams

WealthLab reports portfolio capital, ending wealth, P&L, fees, client spending,
and legacy goals in **UAE dirhams (AED)** by default. The existing USD case was
converted numerically using **1 USD = AED 3.6725**.

The rate was verified against the [Central Bank of the UAE exchange-rate
publication](https://centralbank.ae/en/forex-eibor/exchange-rates/) on 2026-11-04.
It is a fixed reporting assumption, not a live execution quote. No FX API or
API key is required.

| Case amount | AED value |
|---|---:|
| Historical starting capital | 3,672,500 |
| Client planning wealth | 7,345,000 |
| Annual spending in today's purchasing power | 264,420 |
| Additional spending in month 24, in today's purchasing power | 918,125 |
| Terminal real legacy target | 1,836,250 |

## Source quotes and accounting units

Yahoo ETF observations remain USD-denominated adjusted-price quotes. The raw
price cache, its checksum, and source provenance are not relabeled as AED.
The accounting engine uses each asset's percentage price changes and applies
them to holdings already expressed in the account's reporting currency. With
a constant USD/AED rate, this produces the translated AED balances without
converting the source prices or multiplying account values twice.

Fees, costs, and investment contributions scale by the same factor. Weights,
percentage returns, drawdowns, Sharpe ratios, and other dimensionless risk
measures retain their meaning. Translating all planning balances, spending,
and goals together preserves modeled goal frequencies under the same shocks.

The model assumes the same fixed USD/AED rate throughout history and future
planning. It does not model FX spreads, currency-conversion charges, a change
in the peg, or differences between UAE and US inflation. The planning inflation
assumption remains the explicitly chosen 2.5%; it is not a UAE CPI estimate.

## Configuration and exports

`ResearchConfig.currency` and `ClientConfig.currency` default to `AED` and must
match. Monetary inputs must already be expressed in that currency. Changing
the currency field alone does not convert user-supplied amounts. `USD` remains
supported for explicit comparisons using correctly denominated inputs.

Monetary metric rows carry an AED suffix. Attribution is exported as
`pnl_attribution.csv` with a `profit_aed` column. Other monetary CSVs use the
reporting currency stated in the run manifest; returns and weights remain
dimensionless. `planning_sensitivity.csv` names its spending index
`annual_spending_today_aed`. Each generated run records its currency convention
in `run_manifest.json`; the recorded example uses `provenance.json`.

## The saved Yahoo case

The original daily-price cache was not attached. The example translates the
recorded monetary summary values once and preserves their source precision;
it does not create new daily market observations. Monetary figures are redrawn
from those summaries, and planning is recalculated from the translated case.
The original risk-diagnostics image contains only dimensionless values and is
retained. The example provenance keeps the original USD assumptions, translation
factor, source notebook checksum, and original price checksum.

Run the notebook in Yahoo mode to retrieve prices and generate a new complete
AED daily account history. The offline validation uses an explicitly labeled
synthetic source and does not replace the saved Yahoo example.
