# Validation record

The supplied artifact was checked on 2026-11-04 with Python 3.12.14, NumPy
2.3.5, pandas 2.2.3, SciPy 1.17.0, and matplotlib 3.10.8.

## Original core checks

- **38 offline tests passed.** Coverage includes hand-calculated buy-and-hold
  drift, month-boundary execution timing, the self-financing cost equation,
  initial purchase cost, weekend fee accrual, exact P&L reconciliation, and
  unchanged historical results when future observations are appended.
- Data-contract tests cover both Yahoo MultiIndex orientations, refusal to
  substitute unadjusted prices, explicit provider failure, source-separated
  caches, checksum corruption, duplicate conflicts, invalid prices, missing
  interior observations, late inception, and lagged cached FRED observations.
- Planning tests cover deterministic cash-flow solutions, annual growth and fee
  compounding, real-value deflation, one-off spending, absorbing depletion,
  legacy-target semantics, reproducible shocks, and spending sensitivity.
- An end-to-end test verifies the HTML report, five PNG figures, twelve CSVs
  including synthetic prices, JSON manifest, attribution reconciliation, and
  escaping of user-supplied report text.
- **All 23 notebook code cells executed successfully** in a fresh temporary
  workspace and separate Python process. The notebook produced its report and
  downloadable run ZIP. Optional widget rendering was disabled in this check.
- The default command-line demo completed. Five saved figure panels were
  visually inspected; title spacing and label density were corrected.

## Finalized Yahoo case

The user supplied an executed Colab notebook with Yahoo selected, saved Yahoo
price output, 2,766 common price observations from 2015-01-02 to 2025-12-31,
five Yahoo chart panels, and 38 passing tests. The notebook recorded yfinance
0.2.66 and a SHA-256 digest of the original adjusted-price CSV.

Finalization preserves these historical outputs and records their provenance
in `examples/yahoo/provenance.json`. The outdated synthetic findings were
replaced with findings based on the saved Yahoo tables. Summary CSV precision
reflects saved notebook displays; terminal NAVs additionally use the more
precise Colab table metadata. The uploaded UTF-16 notebook was normalized to
UTF-8 for compatibility.

The raw daily-price cache and original run ZIP were not attached. A new Yahoo
download could not be performed in the finalization environment. No daily
observations or historical return paths were reconstructed from the figures.
Run the Yahoo-configured notebook to retrieve fresh prices and full daily CSVs.
Client planning was independently recalculated from its saved assumptions.

Updated reporting includes automatically generated findings. Two additional
tests cover source-aware wording and safe HTML rendering. The previous finalization suite contained 40 passing tests. All 24 current code cells passed the isolated
computational notebook check with an explicit demo override; that check does
not replace or relabel the preserved Yahoo case.

## AED reporting update

The current suite has **47 passing offline tests**, including seven currency
tests. These verify fixed-rate translation, the converted default case, matching
USD/AED percentage returns and weights, scaled P&L and costs, unchanged planning
goal frequencies under the same shocks, currency validation, and rejection of
mixed reporting currencies before data access. The integration check verifies
AED report labels, monetary metric keys, and reconciliation.

Recorded Yahoo monetary summaries were multiplied by 3.6725 once; rate, source,
translation factor, and original USD assumptions are retained in provenance.
Percentage metrics and the original data checksum were preserved. Monetary
charts are redrawn from the available summaries and recalculated planning; no
missing daily history is inferred. The original dimensionless diagnostics panel
is retained. The updated notebook is checked separately in explicit offline
demo mode, which does not replace its saved Yahoo case.

## What these checks do not establish

The notebook was computationally executed as ordinary Python, not in an actual
Google Colab browser or Jupyter kernel. Live Yahoo and FRED requests were not
executed in the artifact-building environment. Their schema and failure
contracts were tested offline; current provider access, credentials, licensing,
and optional widget behavior still need a user-side smoke test.

No live client, brokerage integration, suitability review, tax calculation,
regulatory validation, or external GitHub deployment occurred. GitHub Actions
configuration is included but has not run on a remote repository.

## Reproduce

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tools/check_notebook.py --source demo
python -m wealthlab --source demo --root .
```

For a fixed core environment, use `requirements-tested.txt` on a compatible
Python interpreter. Test any dependency upgrades before relying on the results.
