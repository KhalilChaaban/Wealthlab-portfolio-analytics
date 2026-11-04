# Research choices and open questions

This note explains the setup used in the saved case. The choices came from the
initial AI-assisted project design. They should be challenged as part of the
learning exercise; they were not selected through an optimization or a client
suitability assessment.

## What question does the case answer?

How did a diversified ETF portfolio compare with a simple 60/40 benchmark once
modeled trading costs and advisory fees were included?

The client spending exercise asks a separate question: under explicitly chosen
forward assumptions, how often would the fictional account fund its planned
spending and meet a terminal legacy target?

## Why these choices?

| Choice | Role in this example | What remains open |
|---|---|---|
| Eight USD-listed ETFs | Provides exposure to US, developed-market and emerging-market stocks, bonds, inflation-linked bonds, gold, real estate, and Treasury bills. | ETFs are proxies. Their exposures overlap, and the universe was selected retrospectively. |
| Fixed starting weights | Makes a strategic allocation easy to describe and reproduce. | The weights are illustrative and were not shown to be optimal or suitable for an actual client. |
| 60% SPY / 40% AGG benchmark | Gives the results a simple reference point using the same execution conventions. | Its asset exposures differ from the eight-ETF portfolio. That limits conclusions about the source of performance differences. |
| Monthly rebalancing | Provides a clear calendar rule with weight drift between trades. | Comparisons with quarterly rebalancing and buy-and-hold are planned, but have not been performed. |
| 5 bps trading cost and 0.50% advisory fee | Makes implementation costs explicit in portfolio accounting. | These are assumptions, not estimates fitted to actual broker fills or client fee agreements. |
| Constant 2.50% risk-free rate | Gives excess-return metrics a stated comparison assumption. | Actual cash rates varied over the period. The optional FRED path is a yield proxy and needs its own convention review. |
| Fixed planning return, volatility and inflation | Keeps the cash-flow simulation transparent. | The assumptions were not calibrated to a particular client's circumstances or validated as forecasts. |

## What do the saved results support?

The client portfolio earned 6.83% a year compared with 8.39% for the benchmark,
using the rounded saved metrics. Its annualized volatility was 9.38% compared
with 10.93%, and its maximum drawdown was about 20.07% compared with 21.49%.
The observed result is lower return and lower measured risk for this portfolio
over this sample.

These observations do not establish that broader diversification caused the
return difference or that another set of weights would have been preferable.
That would require additional controlled comparisons.

At the final observation, SPY held 27.93% of capital and contributed 53.02% of
estimated trailing volatility. That is a useful example of how capital weights
and risk contributions can differ. It does not establish that 27.93% was the
right allocation for a particular person.

## What the checks establish

The implementation tests include hand-calculated holdings cases, cost funding,
fee accrual, and P&L reconciliation. Those checks address whether covered parts
of the calculation behave as specified.

They do not establish that the portfolio will outperform, that the return
assumptions are reliable forecasts, or that the model meets a regulatory
validation standard. No independent third-party model validation is claimed.

## Planned extensions

### Exchange-session checks and an evidence report

Compare observed price dates for each ETF with the expected sessions from its
listing exchange's calendar, within the requested coverage period. Account for
exchange holidays and listing dates so those are not mistaken for missing data.
The current gap checks do not establish complete exchange-session coverage.

Produce a report with a row for each check: its name, observed result, threshold,
pass/fail status, and supporting evidence. For a missing-session check, the
evidence would identify the affected ticker and dates. State the thresholds
before evaluating a run and retain failures for review rather than silently
filling missing prices.

### Rebalancing policies across historical periods

Compare monthly, quarterly, and buy-and-hold policies using the same ETF
universe, starting allocation, price observations, initial capital, trading-cost
assumptions, and advisory-fee convention. Buy-and-hold would start from that
allocation and allow weights to drift without scheduled rebalancing.

Choose period boundaries before comparing results and apply the same start and
end dates to all three policies within each period. Compare annualized return,
volatility, maximum drawdown, turnover, and costs. This would test whether the
conclusions depend on the rebalancing rule or the historical period; it would
not establish which policy will perform best in the future.

Both extensions are planned work. No results from them are included in the
current findings.

## Other questions for the next version

- Do the main conclusions change under higher costs?
- How would rolling, out-of-sample risk forecasts perform?
- Can selected calculations be reproduced independently in Excel?
- How would a changing historical risk-free series affect the risk-adjusted metrics?

These are proposed follow-up questions. No results from those experiments are
included in the current findings. The saved Yahoo summaries also have limited
display precision, and the original daily-price cache was not attached. A fresh
data download is needed for those new historical experiments.
