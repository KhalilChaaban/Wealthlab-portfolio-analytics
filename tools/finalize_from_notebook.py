"""Finalize a Yahoo case from an executed notebook without inventing missing data.

Reads JSON, literal configuration dictionaries, displayed tables, and saved PNGs.
It never executes uploaded source code. The daily price cache is not reconstructed
from charts or table summaries; its absence is explicit in provenance.
"""

from base64 import b64decode
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
import argparse
import ast
import json
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from wealthlab.config import ResearchConfig, ClientConfig
from wealthlab.currency import conversion_factor, currency_metadata
from wealthlab.charts import create_planning_charts, create_saved_summary_charts
from wealthlab.findings import build_findings
from wealthlab.planning import simulate_client
from wealthlab.report import create_html_report, write_json


def joined(value):
    return ''.join(value) if isinstance(value, list) else str(value)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], []
        self.in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in {'th', 'td'}:
            self.in_cell, self.cell = True, []

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {'th', 'td'}:
            self.row.append(''.join(self.cell).strip())
            self.in_cell = False
        elif tag == 'tr' and self.row:
            self.rows.append(self.row)


def table(output) -> pd.DataFrame:
    parser = TableParser()
    parser.feed(joined(output['data']['text/html']))
    header, *body = parser.rows
    if any(len(row) != len(header) for row in body):
        raise ValueError('Unexpected displayed-table layout.')
    frame = pd.DataFrame([row[1:] for row in body], index=[row[0] for row in body], columns=header[1:])
    # A named index can add an all-empty header row beneath column names.
    return frame.apply(pd.to_numeric, errors='coerce').dropna(how='all')


def displays(cell):
    return [item for item in cell.get('outputs', []) if 'data' in item]


def cell_map(notebook):
    result = {}
    for cell in notebook['cells']:
        if cell['cell_type'] != 'code':
            continue
        match = re.match(r'# CELL (\d+)\s*\|', joined(cell.get('source', [])))
        if match:
            result[int(match.group(1))] = cell
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notebook', type=Path)
    parser.add_argument('--currency', choices=['AED', 'USD'], default='AED')
    args = parser.parse_args()
    raw = args.notebook.read_bytes()
    encoding = 'utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    notebook = json.loads(raw.decode(encoding))
    cells = cell_map(notebook)
    errors = [item for cell in notebook['cells'] for item in cell.get('outputs', [])
              if item.get('output_type') == 'error']
    if errors:
        raise ValueError('The source notebook contains saved execution errors; inspect it first.')
    configuration = [ast.literal_eval(joined(item['data']['text/plain'])) for item in displays(cells[12])]
    # Older captured notebooks predate the currency field and used USD amounts.
    configuration[0].setdefault('currency', 'USD')
    configuration[1].setdefault('currency', 'USD')
    config = ResearchConfig(**configuration[0])
    client = ClientConfig(**configuration[1])
    if config.currency != client.currency:
        raise ValueError('Captured research and planning currencies do not match.')
    original_config, original_client = config, client
    source_currency = config.currency
    if config.source != 'yahoo':
        raise ValueError('This finalizer requires an actual saved Yahoo run, not a demo run.')
    quality = next(ast.literal_eval(joined(item['data']['text/plain']))
                   for item in displays(cells[13])
                   if joined(item['data'].get('text/plain', '')).lstrip().startswith('{'))
    source_output = '\n'.join(joined(item.get('text', '')) for item in cells[13]['outputs'])
    provider_match = re.search(r'Source: (.+)', source_output)
    checksum_match = re.search(r'Price SHA-256: ([a-f0-9]{64})', source_output)
    if not provider_match or 'Yahoo Finance' not in provider_match.group(1) or not checksum_match:
        raise ValueError('Saved Yahoo provenance is incomplete.')
    metric_output, risk_output, stress_output = displays(cells[15])
    metrics, risk, stress = table(metric_output), table(risk_output), table(stress_output)
    attribution = table(displays(cells[14])[-1])[f'profit_{source_currency.lower()}']
    sensitivity = table(displays(cells[16])[-1])
    sensitivity.index = sensitivity.index.astype(float)
    sensitivity.columns = sensitivity.columns.astype(float)

    # Colab's metadata preserves full four-decimal NAVs even when the HTML table
    # renders large values in scientific notation. Use only the known NAV maximum.
    intrinsic = metric_output['data'].get('application/vnd.google.colaboratory.intrinsic+json', {})
    summary = json.loads(intrinsic['summary']) if intrinsic.get('summary') else {}
    for field in summary.get('fields', []):
        column = field['column']
        value = field['properties'].get('max')
        if column in metrics and value and value > 100_000:
            metrics.loc[f'Ending NAV {source_currency}', column] = value
    # Monetary attribution is saved to six decimal places and provides an
    # independent reconciliation, despite the coarser displayed metric table.
    reconciliation = config.initial_capital + attribution.sum() - metrics.loc[f'Ending NAV {source_currency}', 'Client portfolio']
    if abs(reconciliation) > .01:
        raise ValueError(f'Displayed Yahoo attribution does not reconcile: {source_currency} {reconciliation:.6f}.')
    if not np.isfinite(metrics['Client portfolio']).all() or len(risk) != 8 or len(stress) != 3:
        raise ValueError('Required Yahoo summary outputs are incomplete.')

    # Translate recorded amounts once. Percentages, weights, returns and dates
    # retain their recorded values. Source quote observations remain USD.
    factor = conversion_factor(source_currency, args.currency)
    config = replace(config, currency=args.currency, initial_capital=config.initial_capital * factor)
    client = replace(client, currency=args.currency,
        current_wealth=client.current_wealth * factor,
        annual_spending_today=client.annual_spending_today * factor,
        legacy_goal_today=client.legacy_goal_today * factor,
        one_off_spending={month: value * factor for month, value in client.one_off_spending.items()})
    monetary_rows = [f'{name} {source_currency}' for name in
                     ('Ending NAV', 'Transaction costs', 'Advisory fees')]
    metrics.loc[monetary_rows] *= factor
    metrics.rename(index={name: name.rsplit(' ', 1)[0] + ' ' + args.currency
                          for name in monetary_rows}, inplace=True)
    attribution = (attribution * factor).rename(f'profit_{args.currency.lower()}')
    sensitivity.index = sensitivity.index * factor
    sensitivity.index.name = f'annual_spending_today_{args.currency.lower()}'
    sensitivity.columns.name = 'expected_nominal_return'
    reconciliation *= factor
    projection = simulate_client(client, config.advisory_fee_annual)
    if not np.isclose(projection.success_probability, sensitivity.loc[client.annual_spending_today,
            min(sensitivity.columns, key=lambda x: abs(x-client.expected_annual_return))]):
        raise ValueError('Planning assumptions do not reproduce the captured sensitivity table.')
    findings = build_findings(config, client, metrics, risk, attribution, stress,
                              projection, sensitivity, quality)
    output = ROOT / 'examples/yahoo'
    figures = output / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    images = [joined(item['data']['image/png']) for item in displays(cells[18]) if 'image/png' in item['data']]
    names = ['01_portfolio_overview.png', '02_risk_diagnostics.png', '03_attribution_and_weights.png',
             '04_client_projection.png', '05_sensitivity_and_stress.png']
    keys = ['overview', 'diagnostics', 'attribution', 'planning', 'scenarios']
    if len(images) != len(names):
        raise ValueError('Expected five preserved Yahoo figure panels.')
    # This panel contains only dimensionless diagnostics, so its original PNG
    # remains valid. Monetary panels are redrawn from available summaries and
    # planning assumptions; missing daily paths are never reconstructed.
    payload = b64decode(re.sub(r'\s+', '', images[1]), validate=True)
    if not payload.startswith(b'\x89PNG'):
        raise ValueError('Captured diagnostics chart is not a valid PNG.')
    diagnostic_path = figures / names[1]
    diagnostic_path.write_bytes(payload)
    source_label = f'YAHOO FINANCE / SAVED SUMMARY / {args.currency} REPORTING'
    redrawn = create_saved_summary_charts(metrics, risk, attribution, client, figures, source_label)
    redrawn.update(create_planning_charts(projection, sensitivity, stress, client, figures, source_label))
    redrawn['diagnostics'] = diagnostic_path
    chart_paths = {key: redrawn[key] for key in keys}
    tables = {'metrics.csv': metrics, 'risk_contributions.csv': risk,
              'pnl_attribution.csv': attribution.to_frame(), 'hypothetical_stress.csv': stress,
              'planning_sensitivity.csv': sensitivity, 'projection_quantiles_real.csv': projection.quantiles_real}
    for name, frame in tables.items():
        frame.to_csv(output / name)
    (output / 'dollar_attribution.csv').unlink(missing_ok=True)
    manifest = {
        'source': 'Yahoo Finance; preserved results from the user-executed Colab notebook',
        'synthetic_market_data': False, 'source_notebook_sha256': sha256(raw).hexdigest(),
        'source_notebook_encoding': encoding, 'output_notebook_encoding': 'utf-8',
        'source_price_csv_sha256_recorded_in_notebook': checksum_match.group(1),
        'provider_recorded_in_notebook': provider_match.group(1),
        'quality': quality, 'research_config': config.to_dict(), 'client_assumptions': client.to_dict(),
        'source_research_config': original_config.to_dict(),
        'source_client_assumptions': original_client.to_dict(),
        'currency': currency_metadata(args.currency),
        'currency_translation': {'source_currency': source_currency, 'target_currency': args.currency,
                                 'factor': factor, 'percentage_metrics_unchanged': True},
        'precision': 'Metrics/risk: saved four-decimal DataFrames; attribution/stress: saved six-decimal display; NAV supplemented from Colab metadata.',
        'daily_price_cache_included': False,
        'independent_new_yahoo_download_performed': False,
        'limitation': 'Raw daily prices and the original run ZIP were not attached. Recorded summaries are currency-translated; monetary panels are redrawn from those summaries. The original dimensionless diagnostics panel is preserved. No missing daily paths are reconstructed. Rerun the Yahoo-configured notebook to obtain full daily CSV exports.',
        f'attribution_reconciliation_residual_{args.currency.lower()}': float(reconciliation),
        'planning': {'success_frequency': projection.success_probability,
                     'spending_funded_frequency': projection.survival_probability,
                     'simulation_recalculated_from_saved_assumptions': True},
        'figure_sha256': {name: sha256((figures/name).read_bytes()).hexdigest() for name in names},
        'source_test_output': '\n'.join(joined(item.get('text','')) for item in cells[21]['outputs'])[-650:],
    }
    write_json(output / 'provenance.json', manifest)
    write_json(output / 'data_quality.json', quality)
    write_json(output / 'assumptions.json', {'research': config.to_dict(), 'client': client.to_dict()})
    (ROOT/'config/yahoo.json').write_text(json.dumps({'research': config.to_dict(), 'client': client.to_dict()},indent=2))
    reflection_links = ('\n## Project reflection\n\n'
        '[Personal reflection](docs/PERSONAL_REFLECTION.md) · '
        '[Research choices and planned extensions](docs/RESEARCH_NOTES.md)\n')
    (ROOT/'FINDINGS.md').write_text(findings + reflection_links, encoding='utf-8')
    (output/'FINDINGS.md').write_text(findings, encoding='utf-8')
    market_manifest = {'provider': provider_match.group(1), 'sha256': checksum_match.group(1),
                      'synthetic': False, 'retrieval_timestamp': None,
                      'provenance_note': manifest['limitation'],
                      'source_notebook_sha256': manifest['source_notebook_sha256']}
    market_manifest['saved_summary_only'] = True
    report = create_html_report(output/'client_report.html', config, client, metrics, projection,
                               chart_paths, quality, market_manifest,
                               {'source': 'explicit constant effective-annual assumption',
                                'rate': config.annual_risk_free_rate}, findings_markdown=findings)
    html = report.read_text()
    note = ('<section><h2>About this saved Yahoo case</h2><p>This report translates the recorded Yahoo '
            'summary results into the reporting currency. Monetary charts use those summaries, '
            'not reconstructed daily observations. The original dimensionless diagnostics chart '
            'is preserved. Summary tables retain the source display precision. The raw daily-price '
            'cache was not attached, and no fresh Yahoo download was performed. Re-run the notebook '
            'to create full daily exports. Client projections were recalculated from the '
            'currency-translated assumptions.</p></section>')
    report.write_text(html.replace('<div class="cards">', note+'<div class="cards">',1),encoding='utf-8')
    (ROOT/'docs/images').mkdir(exist_ok=True)
    shutil.copy2(chart_paths['overview'],ROOT/'docs/images/portfolio_overview.png')
    # Rebuild editable source, then attach clearly labeled translated case outputs.
    subprocess.run([sys.executable,str(ROOT/'tools/build_notebook.py')],check=True)
    target = ROOT/'WealthLab_Colab.ipynb'
    finalized = json.loads(target.read_text())
    def display_output(value):
        if isinstance(value, pd.DataFrame):
            data = {'text/html': value.to_html(), 'text/plain': value.to_string()}
        else:
            data = {'text/plain': repr(value)}
        return {'output_type': 'display_data', 'data': data, 'metadata': {}}
    def stream(text):
        return {'output_type': 'stream', 'name': 'stdout', 'text': text + '\n'}
    for number, cell in cell_map(finalized).items():
        cell['execution_count'], cell['outputs'] = None, []
        if number == 12:
            cell['outputs'] = [stream('Saved Yahoo case; amounts translated to ' + args.currency),
                               display_output(config.to_dict()), display_output(client.to_dict())]
        if number == 13:
            cell['outputs'] = [stream('Original Yahoo source quotes below are USD; no fresh download was performed.')]
            cell['outputs'] += [item for item in cells[13].get('outputs', [])
                                if 'application/javascript' not in item.get('data', {})]
        if number == 14:
            cell['outputs'] = [stream(f'Saved attribution translated to {args.currency}; full daily history is not attached.'),
                               display_output(attribution.to_frame())]
        if number == 15:
            cell['outputs'] = [display_output(frame) for frame in (metrics, risk, stress[['portfolio_return']])]
        if number == 16:
            cell['outputs'] = [stream(f'Planning recalculated in {args.currency}; joint success {projection.success_probability:.2%}, '
                                     f'all spending funded {projection.survival_probability:.2%}.'),
                               display_output(sensitivity)]
        if number == 18:
            for key, image_path in chart_paths.items():
                from base64 import b64encode
                cell['outputs'] += [stream(key.title()), {'output_type': 'display_data', 'metadata': {},
                    'data': {'image/png': b64encode(image_path.read_bytes()).decode('ascii'),
                             'text/plain': f'Saved Yahoo case / {args.currency} reporting / {key}'}}]
        if number == 23:
            guide = (ROOT/'docs/PROJECT_GUIDE.md').read_text()
            cell['execution_count'] = None
            cell['outputs'] = [{'output_type':'display_data','data':{'text/markdown':guide,
                               'text/plain':'WealthLab project guide'},'metadata':{}}]
        if number == 24:
            cell['execution_count'] = None
            cell['outputs'] = [{'output_type':'display_data','data':{'text/markdown':findings,
                               'text/plain':findings},'metadata':{}}]
    finalized['metadata']['wealthlab_finalization'] = {
        'saved_outputs_source':'Currency-translated summaries from the uploaded Yahoo notebook; this is not a fresh historical run',
        'source_notebook_sha256':manifest['source_notebook_sha256'],
        'findings_updated_to_match_yahoo':True, 'fresh_yahoo_download_during_finalization':False,
        'new_reporting_code_requires_rerun_for_a_fresh_run':True,
        'currency': currency_metadata(args.currency),
    }
    target.write_text(json.dumps(finalized,ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps({'market_source':config.source,'observations':quality['retained_rows'],
        'portfolio_cagr':float(metrics.loc['CAGR','Client portfolio']),
        'currency': args.currency,
        'ending_nav':float(metrics.loc[f'Ending NAV {args.currency}','Client portfolio']),
        'attribution_residual':float(reconciliation),'saved_pngs':len(chart_paths),
        'notebook_cells':len(finalized['cells']),'report':str(report)},indent=2))


if __name__ == '__main__':
    main()
