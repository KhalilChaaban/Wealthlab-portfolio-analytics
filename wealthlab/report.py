"""Portable HTML client report with embedded images and no remote dependencies."""

from base64 import b64encode
from html import escape
from pathlib import Path
import json
import numpy as np
import pandas as pd

from .config import ClientConfig, ResearchConfig
from .data import atomic_text
from .planning import ProjectionResult
from .findings import findings_to_html


def json_safe(value):
    """Convert numpy/pandas objects and undefined metrics to strict JSON values."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(json_safe(value), indent=2, allow_nan=False))


def _metric_value(name: str, value: float) -> str:
    if pd.isna(value):
        return "Undefined"
    if "USD" in name:
        return f"${value:,.0f}"
    if "ratio" in name.lower() or "Beta" in name:
        return f"{value:.2f}"
    return f"{value:.2%}"


def create_html_report(path: Path, config: ResearchConfig, client: ClientConfig,
                       metrics: pd.DataFrame, projection: ProjectionResult,
                       chart_paths: dict[str, Path], quality: dict, manifest: dict,
                       risk_free_metadata: dict, findings_markdown: str | None = None) -> Path:
    synthetic = config.source == "demo"
    badge = "SYNTHETIC DEMO · NOT MARKET PERFORMANCE" if synthetic else "YAHOO FINANCE · RESEARCH PROTOTYPE"
    values = metrics["Client portfolio"]
    cards = [("Annualized return", _metric_value("CAGR", values["CAGR"])),
             ("Maximum drawdown", _metric_value("Maximum drawdown", values["Maximum drawdown"])),
             ("Annualized volatility", _metric_value("Annualized volatility", values["Annualized volatility"])),
             ("Sharpe ratio", _metric_value("Sharpe ratio", values["Sharpe ratio"]))]
    card_html = "".join(f'<div class="card"><span>{escape(k)}</span><strong>{v}</strong></div>' for k, v in cards)
    rows = []
    for name, row in metrics.iterrows():
        rows.append("<tr><th>" + escape(name) + "</th>" + "".join(
            "<td>" + _metric_value(name, float(v)) + "</td>" for v in row) + "</tr>")
    table = ("<table><thead><tr><th>Metric</th>" + "".join(f"<th>{escape(c)}</th>" for c in metrics.columns)
             + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>")
    captions = {
        "overview": "Net historical analytics use the configured fees and trading costs. Risk shares use the latest 252 return observations.",
        "diagnostics": "Daily risk metrics exclude the zero-duration initial purchase. Monthly return aggregation includes that cost.",
        "attribution": "Exact dollar attribution; buy-and-sell gross turnover is reported without dividing by two.",
        "planning": "Planning starts from the fictional client's current wealth, not historical terminal NAV. The histogram omits the upper 1% for readability; all paths enter calculations.",
        "scenarios": "The planning sensitivity uses common random shocks. Stress scenarios are assumed asset shocks, not historical crisis replays.",
    }
    titles = {"overview": "Portfolio review", "diagnostics": "Risk diagnostics", "attribution": "Attribution",
              "planning": "Client goals", "scenarios": "Sensitivity & stress"}
    sections = []
    for key, image in chart_paths.items():
        embedded = b64encode(image.read_bytes()).decode("ascii")
        sections.append(f'<section id="{key}"><h2>{titles[key]}</h2><img loading="lazy" '
                        f'src="data:image/png;base64,{embedded}" alt="{escape(titles[key])}">'
                        f'<p class="caption">{captions[key]}</p></section>')
    probability = projection.success_probability
    navigation = "".join(f'<a href="#{k}">{v}</a>' for k, v in titles.items())
    findings_section = ('<section id="findings">' + findings_to_html(findings_markdown) + '</section>'
                        if findings_markdown else '')
    if findings_markdown:
        navigation += '<a href="#findings">Findings</a>'
    one_off = ", ".join(f"month {m}: ${v:,.0f}" for m, v in sorted(client.one_off_spending.items())) or "none"
    disclosures = {
        "research_config": config.to_dict(), "client_assumptions": client.to_dict(),
        "data_quality": quality, "price_provenance": manifest, "risk_free": risk_free_metadata,
    }
    html = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WealthLab | Client portfolio review</title><style>
:root{{--navy:#142d4e;--teal:#008d83;--muted:#64748b;--line:#e2e8f0}}
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6fa;color:var(--navy);font:16px/1.65 system-ui,sans-serif}}
header{{background:var(--navy);color:#fff;padding:48px max(5vw,24px) 36px}}header .eyebrow{{letter-spacing:.22em;font-size:12px;color:#90d8d0}}
h1{{font-size:clamp(28px,4vw,44px);line-height:1.2;margin:14px 0}}header p{{max-width:850px;color:#d3dfeb}}
.badge{{display:inline-block;padding:5px 11px;border:1px solid #91b9c7;border-radius:4px;font-size:12px;letter-spacing:.05em}}
main{{max-width:1400px;margin:auto;padding:24px}}nav{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px}}
a{{color:var(--teal)}}nav a{{text-decoration:none;background:white;border:1px solid var(--line);border-radius:6px;padding:8px 14px}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}.card,section{{background:#fff;border:1px solid var(--line);border-radius:10px}}
.card{{padding:22px}}.card span{{display:block;color:var(--muted);font-size:13px}}.card strong{{font-size:31px}}
section{{padding:24px;margin-top:24px;scroll-margin-top:20px}}h2{{margin:0 0 12px;font-size:23px}}img{{display:block;width:100%;height:auto}}
.caption,.muted{{font-size:13px;color:var(--muted)}}.planning-note{{border-left:4px solid var(--teal);padding:14px 20px;background:#edf8f6}}
.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:11px 14px;border-bottom:1px solid var(--line);text-align:right}}
th:first-child{{text-align:left}}thead{{background:#eef3f8}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f9fc;padding:18px;font-size:12px}}
footer{{padding:24px;color:var(--muted);font-size:13px}}button{{background:var(--teal);color:white;border:0;padding:9px 16px;border-radius:5px;cursor:pointer}}
@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}main{{padding:12px}}section{{padding:12px}}.card strong{{font-size:25px}}}}
@media print{{nav,button{{display:none}}header{{background:white;color:var(--navy)}}header p{{color:var(--muted)}}section{{break-inside:avoid}}}}
</style></head><body><header><div class="eyebrow">WEALTHLAB / PRIVATE WEALTH RESEARCH</div>
<h1>Client portfolio &amp; goals review</h1><div class="badge">{badge}</div>
<p>{escape(client.label)} · Historical window {quality['first_observation']} to {quality['last_observation']}.
Strategic allocation, transparent risk, and illustrative spending scenarios in one reproducible review.</p></header>
<main><nav>{navigation}<a href="#metrics">Metrics</a><a href="#assumptions">Assumptions</a></nav>
<div class="cards">{card_html}</div>
<section><h2>Client planning case</h2><p>Current investable wealth <b>${client.current_wealth:,.0f}</b>;
annual spending <b>${client.annual_spending_today:,.0f}</b> in today's dollars;
horizon <b>{client.horizon_years} years</b>; terminal legacy target <b>${client.legacy_goal_today:,.0f}</b> in today's dollars.</p>
<p>Additional spending in today's dollars: {escape(one_off)}. Annual advisory fee: {config.advisory_fee_annual:.2%}.</p>
<div class="planning-note"><b>{probability:.1%}</b> of modeled paths fund every planned payment and meet the terminal legacy target.
 Spending-only funding rate: <b>{projection.survival_probability:.1%}</b>.
Monte Carlo standard error of the joint success estimate: {projection.success_mc_standard_error:.2%}.
 These are assumption-dependent simulation frequencies, not personal forecasts or guarantees.</div></section>
{''.join(sections)}{findings_section}<section id="metrics"><h2>Performance metrics</h2><div class="table-wrap">{table}</div>
<p class="caption">Benchmark: 60% SPY / 40% AGG by default; same fees, dates, rebalance schedule, and trading-cost convention.
Sharpe uses {escape(risk_free_metadata['source'])}. Volatility annualization assumes {config.periods_per_year} sessions/year.</p></section>
<section id="assumptions"><h2>Assumptions, provenance &amp; limits</h2>
<p>USD-listed ETF adjusted prices approximate reinvested total returns. Distributions are not added twice.
Historical portfolios have no external cash flows. Fractional units and execution at the observed close plus proportional costs are assumed.
Current ETF selection was chosen retrospectively; this is not evidence of an investable historical discovery.</p>
<p>Planning uses user-specified lognormal returns, fixed volatility and inflation, beginning-of-month spending,
and absorbing depletion. Taxes, estate structures, borrowing, changing allocations, and fat-tail dynamics are outside this version.
The report supports a fictional case study; it does not determine suitability or make trade recommendations.</p>
<details><summary>Reproduce this run</summary><pre>{escape(json.dumps(json_safe(disclosures), indent=2))}</pre></details></section>
<footer>WealthLab 1.0 · Research and education · <button onclick="window.print()">Print report</button></footer>
</main></body></html>'''
    atomic_text(path, html)
    return path
