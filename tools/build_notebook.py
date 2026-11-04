"""Generate a standalone, ordinary-Python notebook from the maintained package.

No nbformat dependency is required. All notebook code cells can also execute in
a standard interpreter; optional display integrations are guarded imports.
"""

from pathlib import Path
import json
import sys
import textwrap
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def markdown(source):
    return {"cell_type": "markdown", "id": uuid4().hex[:8], "metadata": {},
            "source": textwrap.dedent(source).strip().splitlines(keepends=True)}


def code(source):
    return {"cell_type": "code", "id": uuid4().hex[:8], "metadata": {},
            "execution_count": None, "outputs": [],
            "source": textwrap.dedent(source).strip().splitlines(keepends=True)}


def main():
    cells = [markdown('''
        # WealthLab | Multi-Asset Portfolio & Client Wealth Planning

        **Complete, self-contained Google Colab finance project.**

        Built for private banking, wealth management, and portfolio analytics.
        This notebook embeds all source modules and runs without uploading a repository.

        **Default: YAHOO FINANCE.** The finalized example preserves the real-price
        results from the supplied, successfully executed Colab notebook.
        Historical portfolio returns are hypothetical backtest returns. Client planning
        and stress scenarios remain models, not forecasts.
        The output is a research prototype, not a suitability decision or production platform.

        **Workflow:** setup → inspect/build modules → configure → collect/validate →
        account → analyze risk → simulate client goals → export a complete report.

        **Case:** a fictional family's portfolio and spending plan. Historical capital,
        current planning wealth, and forward-return assumptions are explicitly separate.
        **Reporting currency: UAE dirhams (AED).** Existing case amounts are
        translated at 1 USD = AED 3.6725. Yahoo quotes remain USD source data;
        a constant USD/AED reporting rate is assumed. Percentage results are unchanged.
        Full methodology, source references, and resume wording are included in the final cells.
    '''), markdown('''
        ## Cell 01 — Environment and dedicated workspace

        No GPU is required. Core dependencies install only if missing. The offline demo
        uses no API keys. Runtime files are temporary; use the export cell to retain work.
    '''), code('''
        # CELL 01 | Setup
        import importlib.util
        import os
        from pathlib import Path
        import subprocess
        import sys

        requirements = {"numpy": "numpy>=1.26,<3", "pandas": "pandas>=2.2,<3",
                        "scipy": "scipy>=1.11,<2", "matplotlib": "matplotlib>=3.8,<4"}
        missing = [spec for name, spec in requirements.items()
                   if importlib.util.find_spec(name) is None]
        if missing:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])
        # An environment override is useful for isolated local execution checks.
        default_root = Path("/content/wealthlab") if Path("/content").exists() else Path.cwd() / "wealthlab_colab"
        PROJECT_ROOT = Path(os.getenv("WEALTHLAB_NOTEBOOK_ROOT", str(default_root))).resolve()
        PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "wealthlab").mkdir(exist_ok=True)
        for folder in ("tests", "docs", "config"):
            (PROJECT_ROOT / folder).mkdir(exist_ok=True)
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        # Display adapters are optional outside Jupyter/Colab.
        try:
            from IPython.display import display, HTML, Image, Markdown
        except ImportError:
            def display(value):
                print(value)
            HTML = Markdown = lambda value: value
            Image = lambda filename: f"Saved figure: {filename}"
        print(f"Python {sys.version.split()[0]} | Workspace: {PROJECT_ROOT}")
    ''')]
    modules = [
        ("__init__.py", "Package identity", "Versioned, inspectable research code."),
        ("config.py", "Validated assumptions", "Rates are decimals; weights must sum to one. No silent normalization."),
        ("data.py", "Collection, caching, and cleaning", "Adjusted-price semantics, schema handling, retries, checksums, and explicit failure."),
        ("portfolio.py", "Self-financing portfolio accounting", "AED holdings drift between scheduled closes; costs are funded from portfolio value."),
        ("analytics.py", "Performance and risk algorithms", "Exact attribution and transparent reporting conventions."),
        ("planning.py", "Client cash-flow scenarios", "Monthly spending, one-off goals, inflation, depletion, and legacy targets."),
        ("charts.py", "Professional chart engine", "Saved, portable figures with prominent source labels."),
        ("report.py", "Offline HTML reporting", "Embedded images and safely escaped client text."),
        ("pipeline.py", "End-to-end orchestration", "A single function reproduces the complete run and audit bundle."),
        ("__main__.py", "Command-line interface", "The same project runs locally with python -m wealthlab."),
    ]
    number = 2
    for name, title, explanation in modules:
        source = (ROOT / "wealthlab" / name).read_text()
        # Each code cell visibly contains the complete editable source.
        literal = source.replace("\\", "\\\\").replace("'''", "\\'\\'\\'")
        cells.append(markdown(f"## Cell {number:02d} — {title}\n\n{explanation}\n\nThis cell writes `wealthlab/{name}`."))
        module_cell = f"# CELL {number:02d} | Build {name}\n" \
                          + f"module_source = '''{literal}'''\n" \
                          + f"(PROJECT_ROOT / 'wealthlab' / '{name}').write_text(module_source, encoding='utf-8')\n" \
                          + f"print('Created wealthlab/{name}')"
        for extra_name in ({"config.py": ["currency.py"], "report.py": ["findings.py"],
                            "pipeline.py": ["export.py"]}.get(name, [])):
            findings_source = (ROOT / "wealthlab" / extra_name).read_text()
            findings_literal = findings_source.replace("\\", "\\\\").replace("'''", "\\'\\'\\'")
            module_cell += (f"\nfindings_source = '''{findings_literal}'''\n"
                            f"(PROJECT_ROOT / 'wealthlab' / '{extra_name}').write_text(findings_source, encoding='utf-8')\n"
                            f"print('Created wealthlab/{extra_name}')")
        cells.append(code(module_cell))
        number += 1

    cells += [markdown('''
        ## Cell 12 — Configure the research mandate and client case

        `SOURCE="yahoo"` downloads real observations. Dates are fixed and end-exclusive.
        Set `SOURCE="demo"` only when you deliberately want an offline synthetic test.
        `USE_FRED=False` uses an explicit annual risk-free assumption, not observed rates.
        FRED mode reads your own secret; credentials are never printed or exported.
        Keep the documented eight ETF labels unless you extend the stress and demo mappings.
        All capital, spending, fees, and goals below are AED. Raw Yahoo prices
        remain USD quotes; their percentage changes drive AED portfolio accounting.
    '''), code('''
        # CELL 12 | User-editable configuration
        from dataclasses import replace
        import importlib
        # Rerunning source cells is supported: discard previously imported package modules.
        for module_name in list(sys.modules):
            if module_name == "wealthlab" or module_name.startswith("wealthlab."):
                del sys.modules[module_name]
        importlib.invalidate_caches()
        from wealthlab.config import ResearchConfig, ClientConfig

        SOURCE = "yahoo"                  # "yahoo" or explicit offline "demo"
        USE_FRED = False                  # Optional; personal FRED_API_KEY needed
        REFRESH_CACHE = False             # Explicitly replace a matching snapshot
        if SOURCE == "yahoo":
            live_requirements = {"yfinance": "yfinance>=0.2.54,<2", "requests": "requests>=2.32,<3"}
            missing = [spec for name, spec in live_requirements.items()
                       if importlib.util.find_spec(name) is None]
            if missing:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])
        if USE_FRED:
            if importlib.util.find_spec("requests") is None:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "requests>=2.32,<3"])
            if not os.getenv("FRED_API_KEY"):
                try:
                    from google.colab import userdata
                    os.environ["FRED_API_KEY"] = userdata.get("FRED_API_KEY")
                except Exception:
                    raise RuntimeError("Add your FRED_API_KEY to Colab Secrets or the environment.") from None

        CONFIG = ResearchConfig(
            source=SOURCE, start="2015-01-01", end="2026-01-01",
            currency="AED", initial_capital=3_672_500, trading_cost_bps=5,
            advisory_fee_annual=0.005, rebalance="monthly",
            annual_risk_free_rate=0.025,
            risk_free_source="fred" if USE_FRED else "constant",
        )
        CLIENT = ClientConfig(
            currency="AED", current_wealth=7_345_000, annual_spending_today=264_420,
            horizon_years=20, inflation=0.025, expected_annual_return=0.06,
            annual_volatility=0.12, legacy_goal_today=1_836_250,
            one_off_spending={24: 918_125}, paths=5_000,
        )
        print("SYNTHETIC DEMO — NOT MARKET DATA" if SOURCE == "demo" else "YAHOO MARKET-DATA RESEARCH")
        display(CONFIG.to_dict())
        display(CLIENT.to_dict())
        from wealthlab.currency import currency_disclosure
        print(currency_disclosure(CONFIG.currency))
    '''), markdown('''
        ## Cell 13 — Data collection and strict quality checks

        No forward-fill, backfill, or return clipping. Conflicting duplicates, interior
        missing values, stale observations, and insufficient common history fail explicitly.
        Yahoo failure does not substitute synthetic data. Adjusted returns already incorporate
        corporate-action adjustments; do not add dividends again.
    '''), code('''
        # CELL 13 | Collect → cache → validate → engineer returns
        from wealthlab.data import load_prices, clean_prices, risk_free_returns
        market = load_prices(CONFIG, PROJECT_ROOT / "data/cache", refresh=REFRESH_CACHE)
        prices, quality = clean_prices(market.prices, CONFIG)
        risk_free, risk_free_metadata = risk_free_returns(
            prices.index, CONFIG, PROJECT_ROOT / "data/cache", refresh=REFRESH_CACHE)
        asset_returns = prices.pct_change(fill_method=None).iloc[1:]
        print("Source ETF adjusted-price quotes: USD. Account and client amounts:", CONFIG.currency)
        display(prices.head())
        display(quality)
        print("Source:", market.manifest["provider"])
        print("Price SHA-256:", market.manifest["sha256"])
    '''), markdown('''
        ## Cell 14 — Portfolio accounting and exact reconciliation

        The engine accrues returns on held AED positions, deducts calendar-day fees,
        then rebalances at predetermined closes. The self-financing cost equation is solved
        numerically. Initial purchases also pay costs. No deposits or withdrawals enter
        this historical account; those belong to the client-planning track.
    '''), code('''
        # CELL 14 | Portfolio, benchmark, and frictionless comparison
        from wealthlab.portfolio import run_backtest
        from wealthlab.analytics import pnl_attribution
        execution = dict(initial_capital=CONFIG.initial_capital,
                         trading_cost_bps=CONFIG.trading_cost_bps,
                         advisory_fee_annual=CONFIG.advisory_fee_annual,
                         rebalance=CONFIG.rebalance, currency=CONFIG.currency)
        portfolio = run_backtest(prices, CONFIG.weights, **execution)
        benchmark = run_backtest(prices, CONFIG.benchmark, **execution)
        frictionless = run_backtest(prices, CONFIG.weights,
                                   initial_capital=CONFIG.initial_capital,
                                   trading_cost_bps=0, advisory_fee_annual=0,
                                   rebalance=CONFIG.rebalance, currency=CONFIG.currency)
        attribution = pnl_attribution(portfolio)
        residual = portfolio.history.nav.iloc[-1] - CONFIG.initial_capital - attribution.sum()
        print(f"Attribution residual: {CONFIG.currency} {residual:.10f}")
        display(portfolio.history.head())
        display(attribution.to_frame())
    '''), markdown('''
        ## Cell 15 — Performance metrics and risk decomposition

        CAGR uses elapsed calendar time. Daily risk statistics exclude the initial cost-only
        observation. Risk shares are a trailing-sample Euler volatility decomposition,
        not a prediction. Undefined ratios remain undefined instead of being replaced by zero.
    '''), code('''
        # CELL 15 | Metrics, capital weights, and risk shares
        import pandas as pd
        from wealthlab.analytics import performance_metrics, risk_contributions, hypothetical_stress
        metrics = pd.DataFrame({
            "Client portfolio": performance_metrics(portfolio, risk_free, benchmark, CONFIG.periods_per_year),
            "Strategic benchmark": performance_metrics(benchmark, risk_free, periods_per_year=CONFIG.periods_per_year),
            "Before modeled costs": performance_metrics(frictionless, risk_free, benchmark, CONFIG.periods_per_year),
        })
        risk = risk_contributions(asset_returns, portfolio.weights.iloc[-1], CONFIG.periods_per_year)
        stress = hypothetical_stress(portfolio.weights.iloc[-1])
        display(metrics.round(4))
        display(risk.round(4))
        display(stress[["portfolio_return"]])
    '''), markdown('''
        ## Cell 16 — Client spending and legacy scenarios

        Planning starts from CLIENT.current_wealth, independently of historical terminal NAV.
        Monthly lognormal returns use explicit forward assumptions. Spending occurs at the
        beginning of the month, inflation increases spending, and depletion is absorbing.
        Success requires all spending funded AND the terminal real legacy target achieved.
    '''), code('''
        # CELL 16 | Scenario model and common-random-number sensitivity
        from wealthlab.planning import simulate_client, planning_sensitivity
        projection = simulate_client(CLIENT, CONFIG.advisory_fee_annual)
        sensitivity = planning_sensitivity(CLIENT, CONFIG.advisory_fee_annual)
        print(f"Spending funded + legacy target achieved: {projection.success_probability:.1%}")
        print(f"All spending funded: {projection.survival_probability:.1%}")
        print(f"Monte Carlo standard error: {projection.success_mc_standard_error:.2%}")
        print("Simulation frequencies are conditional on assumptions, not guarantees.")
        display(sensitivity)
    '''), markdown('''
        ## Cell 17 — Generate the complete report and audit bundle

        The reusable pipeline recomputes the same analysis from the cached inputs and
        exports charts, CSVs, assumptions, quality checks, checksums, and package versions.
        The source-code digest contributes to the run ID.
    '''), code('''
        # CELL 17 | One-call reproducibility
        from wealthlab.pipeline import run_project
        RUN = run_project(CONFIG, CLIENT, root=PROJECT_ROOT)
        pd.testing.assert_frame_equal(RUN.portfolio.history, portfolio.history)
        print("Report:", RUN.report_path)
        print("Run bundle:", RUN.output_dir)
        display(HTML(f"<p><strong>Completed {CONFIG.source.upper()} run.</strong> "
                     "Download client_report.html below to open the complete offline dashboard.</p>"))
    '''), markdown('''
        ## Cell 18 — Review the saved figures

        Each historical chart identifies its source. The terminal-wealth histogram omits
        the upper 1% for readability; all paths enter calculations.
    '''), code('''
        # CELL 18 | Display charts
        for label, chart_path in RUN.chart_paths.items():
            print(label.replace("_", " ").title())
            display(Image(filename=str(chart_path)))
    '''), markdown('''
        ## Cell 19 — Optional interactive planning sensitivity

        Sliders rerun the planning model with a fixed seed. They are exploratory and do
        not change the saved report. To persist a changed case, edit CLIENT in Cell 12
        and rerun the analysis. The core project completes even without ipywidgets.
    '''), code('''
        # CELL 19 | Optional Colab controls
        if importlib.util.find_spec("ipywidgets") is not None and not os.getenv("WEALTHLAB_SKIP_WIDGETS"):
            import ipywidgets as widgets
            import matplotlib.pyplot as plt
            from matplotlib.ticker import FuncFormatter
            def explore(expected_return=6.0, spending_thousands=CLIENT.annual_spending_today/1000):
                case = replace(CLIENT, expected_annual_return=expected_return/100,
                               annual_spending_today=spending_thousands*1000)
                result = simulate_client(case, CONFIG.advisory_fee_annual)
                print(f"Joint goal success: {result.success_probability:.1%}; "
                      f"spending funded: {result.survival_probability:.1%}")
                fig, ax = plt.subplots(figsize=(10, 4))
                q = result.quantiles_real
                ax.fill_between(q.index, q.p05, q.p95, alpha=.15, color="#008d83")
                ax.plot(q.index, q.p50, color="#008d83", label="Median real wealth")
                ax.axhline(case.legacy_goal_today, color="#c89135", linestyle="--", label="Legacy goal")
                ax.set(xlabel="Years", ylabel=f"Today's {CLIENT.currency}", title="Illustrative planning sensitivity")
                ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f"{CLIENT.currency} {x/1e6:.1f}m"))
                ax.legend(); fig.tight_layout()
                display(fig)
                plt.close(fig)
            widgets.interact(explore,
                expected_return=widgets.FloatSlider(value=CLIENT.expected_annual_return*100,
                                                   min=0, max=12, step=.5, description="Return %"),
                spending_thousands=widgets.FloatSlider(value=CLIENT.annual_spending_today/1000,
                                                      min=CLIENT.annual_spending_today/1000*.25,
                                                      max=CLIENT.annual_spending_today/1000*2.25,
                                                      step=2, description=f"{CLIENT.currency} k/yr"))
        else:
            print("Optional widgets unavailable or disabled. All saved outputs remain complete.")
    ''')]

    # Embed tests and guide so the notebook remains a complete standalone deliverable.
    supplemental = [*sorted((ROOT / "tests").glob("test_*.py")), ROOT / "docs/PROJECT_GUIDE.md",
                    ROOT / "docs/VALIDATION.md", ROOT / "LICENSE", ROOT / "pyproject.toml",
                    ROOT / "docs/PERSONAL_REFLECTION.md", ROOT / "docs/RESEARCH_NOTES.md",
                    ROOT / "docs/CURRENCY.md",
                    ROOT / "config/demo.json", ROOT / ".gitignore", ROOT / ".github/workflows/ci.yml",
                    ROOT / "tools/check_notebook.py", ROOT / "tools/build_notebook.py",
                    ROOT / "README.md", ROOT / "FINDINGS.md", ROOT / "START_HERE.html",
                    ROOT / "config/yahoo.json", ROOT / "tools/finalize_from_notebook.py",
                    ROOT / "requirements.txt", ROOT / "requirements-live.txt",
                    ROOT / "requirements-tested.txt", ROOT / "requirements-colab.txt"]
    mapping = {str(p.relative_to(ROOT)): p.read_text() for p in supplemental}
    cells += [markdown('''
        ## Cell 20 — Materialize documentation and financial tests

        The embedded guide covers architecture, data conventions, equations, all metrics,
        finance use cases, upgrade priorities, and resume wording. Offline tests challenge
        the model using independent hand-calculated cases.
    '''), code("# CELL 20 | Build documentation and tests\n"
              "import json\n"
              f"supplemental = json.loads({json.dumps(json.dumps(mapping, ensure_ascii=False))})\n"
              "for relative_path, content in supplemental.items():\n"
              "    destination = PROJECT_ROOT / relative_path\n"
              "    destination.parent.mkdir(parents=True, exist_ok=True)\n"
              "    destination.write_text(content, encoding='utf-8')\n"
              "import shutil\n"
              "(PROJECT_ROOT / 'docs/images').mkdir(exist_ok=True)\n"
              "shutil.copy2(RUN.chart_paths['overview'], PROJECT_ROOT / 'docs/images/portfolio_overview.png')\n"
              "print(f'Created {len(supplemental)} documentation, tooling, and test files.')"),
        markdown('''
        ## Cell 21 — Run financial validation

        A successful run establishes the covered accounting and data-contract behavior.
        It does not certify live-provider availability, investment merit, or suitability.
    '''), code('''
        # CELL 21 | Offline test suite
        completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                                   cwd=PROJECT_ROOT, capture_output=True, text=True)
        print(completed.stdout)
        print(completed.stderr)
        completed.check_returncode()
    '''), markdown('''
        ## Cell 22 — Export and download

        The ZIP contains the generated run, emitted Python package, documentation, and tests.
        Its start page and root findings describe this run, and config/current_run.json
        retains the exact assumptions. The maintained notebook is a separate download.
        Live raw-data caches and credentials are excluded. Check provider rights before
        redistributing outputs derived from downloaded market data.
        Set DOWNLOAD_FILES=True to invoke Colab's browser downloads.
    '''), code('''
        # CELL 22 | Export artifacts
        from wealthlab.export import export_run
        EXPORT_PATH = export_run(RUN, CONFIG, CLIENT, PROJECT_ROOT)
        print("Complete export:", EXPORT_PATH)
        print("Offline dashboard:", RUN.report_path)
        DOWNLOAD_FILES = False
        if DOWNLOAD_FILES:
            try:
                from google.colab import files
                files.download(str(EXPORT_PATH))
                files.download(str(RUN.report_path))
            except ImportError:
                print("Outside Colab: open the printed local paths.")
    '''), markdown('''
        ## Cell 23 — Read the full project guide

        The guide includes the overview, real finance use case, architecture, source and
        library requirements, file structure, build guide, pipeline, cleaning, algorithms,
        dashboard, metrics, deliverables, resume description, and potential upgrades.
    '''), code('''
        # CELL 23 | Methodology and presentation
        display(Markdown((PROJECT_ROOT / "docs/PROJECT_GUIDE.md").read_text()))
    '''), markdown('''
        ## Cell 24 — Findings and Conclusions

        This discussion is generated from the current run, so its numbers and data-source
        labels match the report. Saved outputs show the uploaded Yahoo summary case
        translated to AED, with recalculated planning scenarios. They are not a new download.
    '''), code('''
        # CELL 24 | Findings generated from the actual run
        display(Markdown((RUN.output_dir / "FINDINGS.md").read_text(encoding="utf-8")))
    ''')]
    notebook = {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
        "colab": {"name": "WealthLab_Colab.ipynb", "provenance": []},
    }, "nbformat": 4, "nbformat_minor": 5}
    path = ROOT / "WealthLab_Colab.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Built {path.name}: {len(cells)} cells, {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
