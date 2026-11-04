"""Orchestrate the research workflow and export an auditable run bundle."""

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata
from pathlib import Path
import json
import logging
import platform

import pandas as pd

from .analytics import (dollar_attribution, hypothetical_stress, monthly_returns,
                        performance_metrics, risk_contributions)
from .charts import create_charts
from .config import ClientConfig, ResearchConfig, ensure_directory
from .data import atomic_text, clean_prices, load_prices, risk_free_returns
from .findings import build_findings
from .planning import planning_sensitivity, simulate_client
from .portfolio import run_backtest
from .report import create_html_report, write_json

LOGGER = logging.getLogger(__name__)


@dataclass
class ProjectRun:
    output_dir: Path
    report_path: Path
    chart_paths: dict[str, Path]
    metrics: pd.DataFrame
    portfolio: object
    benchmark: object
    projection: object
    manifest: dict


def run_project(config: ResearchConfig | None = None, client: ClientConfig | None = None,
                root: str | Path = ".", refresh: bool = False) -> ProjectRun:
    config = config or ResearchConfig()
    client = client or ClientConfig()
    root = Path(root).resolve()
    LOGGER.info("Loading %s price data.", config.source)
    market = load_prices(config, root / "data/cache", refresh=refresh)
    prices, quality = clean_prices(market.prices, config)
    rf, rf_metadata = risk_free_returns(prices.index, config, root / "data/cache", refresh)
    kwargs = dict(initial_capital=config.initial_capital,
                  trading_cost_bps=config.trading_cost_bps,
                  advisory_fee_annual=config.advisory_fee_annual,
                  rebalance=config.rebalance)
    portfolio = run_backtest(prices, config.weights, **kwargs)
    benchmark = run_backtest(prices, config.benchmark, **kwargs)
    frictionless = run_backtest(prices, config.weights, initial_capital=config.initial_capital,
                                trading_cost_bps=0, advisory_fee_annual=0, rebalance=config.rebalance)
    metrics = pd.DataFrame({
        "Client portfolio": performance_metrics(portfolio, rf, benchmark, config.periods_per_year),
        "Strategic benchmark": performance_metrics(benchmark, rf, periods_per_year=config.periods_per_year),
        "Before modeled costs": performance_metrics(frictionless, rf, benchmark, config.periods_per_year),
    })
    asset_returns = prices.pct_change(fill_method=None).iloc[1:]
    risk = risk_contributions(asset_returns, portfolio.weights.iloc[-1], config.periods_per_year)
    attribution = dollar_attribution(portfolio)
    stress = hypothetical_stress(portfolio.weights.iloc[-1])
    projection = simulate_client(client, config.advisory_fee_annual)
    sensitivity = planning_sensitivity(client, config.advisory_fee_annual)
    code_digest = sha256()
    for module in sorted(Path(__file__).parent.glob("*.py")):
        code_digest.update(module.name.encode())
        code_digest.update(module.read_bytes())
    identity = {"code_version": "1.0.0", "source_code_sha256": code_digest.hexdigest(),
                "config": config.to_dict(), "client": client.to_dict(),
                "price_checksum": market.manifest["sha256"], "risk_free": rf_metadata}
    run_id = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
    output = ensure_directory(root / "reports" / config.source / run_id)
    source_label = ("SYNTHETIC DEMO — NOT ETF OBSERVATIONS OR MARKET PERFORMANCE" if config.source == "demo"
                    else "YAHOO FINANCE ADJUSTED CLOSES — RESEARCH PROTOTYPE")
    findings = build_findings(config, client, metrics, risk, attribution, stress,
                              projection, sensitivity, quality)
    atomic_text(output / "FINDINGS.md", findings)
    charts = create_charts(portfolio, benchmark, frictionless, asset_returns, risk, attribution,
                            stress, projection, sensitivity, client, output / "figures", source_label,
                            config.periods_per_year)
    report = create_html_report(output / "client_report.html", config, client, metrics,
                                projection, charts, quality, market.manifest, rf_metadata,
                                findings_markdown=findings)
    tables = {
        "metrics.csv": metrics,
        "portfolio_history.csv": portfolio.history,
        "benchmark_history.csv": benchmark.history,
        "held_weights.csv": portfolio.weights,
        "asset_pnl.csv": portfolio.asset_pnl,
        "dollar_attribution.csv": attribution.to_frame(),
        "risk_contributions.csv": risk,
        "monthly_returns.csv": monthly_returns(portfolio).to_frame(),
        "hypothetical_stress.csv": stress,
        "projection_quantiles_real.csv": projection.quantiles_real,
        "planning_sensitivity.csv": sensitivity,
    }
    # Generated demo data can be redistributed. Vendor data stays in local cache.
    if config.source == "demo":
        tables["synthetic_prices.csv"] = prices
    for name, table in tables.items():
        table.to_csv(output / name)
    versions = {}
    for package in ("numpy", "pandas", "scipy", "matplotlib", "yfinance", "requests"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = "not installed / optional"
    manifest = {
        **identity, "run_id": run_id, "python": platform.python_version(),
        "packages": versions, "data_provenance": market.manifest, "quality": quality,
        "source_label": source_label,
        "validation": {"attribution_residual_usd": float(
            portfolio.history.nav.iloc[-1] - config.initial_capital - attribution.sum())},
        "planning": {"joint_success_frequency": projection.success_probability,
                     "all_spending_funded_frequency": projection.survival_probability,
                     "success_mc_standard_error": projection.success_mc_standard_error},
        "limitations": [
            "Fixed, retrospectively chosen ETF universe; no point-in-time selection claim.",
            "Total-return proxy with fractional holdings, no taxes, and idealized close execution.",
            "No exchange-calendar completeness guarantee or independent provider reconciliation.",
            "Scenario assumptions are not return forecasts; no suitability determination.",
            "FRED optional yields are lagged latest-vintage proxies, not a vintage-perfect cash strategy.",
        ],
    }
    write_json(output / "run_manifest.json", manifest)
    write_json(output / "data_quality.json", quality)
    write_json(output / "assumptions.json", {"research": config.to_dict(), "client": client.to_dict()})
    LOGGER.info("Completed run %s; report at %s", run_id, report)
    return ProjectRun(output, report, charts, metrics, portfolio, benchmark, projection, manifest)
