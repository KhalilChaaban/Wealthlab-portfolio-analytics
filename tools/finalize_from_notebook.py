"""Finalize a Yahoo case from an executed notebook without inventing missing data.

Reads JSON, literal configuration dictionaries, displayed tables, and saved PNGs.
It never executes uploaded source code. The daily price cache is not reconstructed
from charts or table summaries; its absence is explicit in provenance.
"""

from base64 import b64decode
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
    config = ResearchConfig(**configuration[0])
    client = ClientConfig(**configuration[1])
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
    attribution = table(displays(cells[14])[-1])['profit_usd']
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
            metrics.loc['Ending NAV USD', column] = value
    # Dollar attribution is saved to six decimal places and provides an
    # independent reconciliation, despite the coarser displayed metric table.
    reconciliation = config.initial_capital + attribution.sum() - metrics.loc['Ending NAV USD', 'Client portfolio']
    if abs(reconciliation) > .01:
        raise ValueError(f'Displayed Yahoo attribution does not reconcile: ${reconciliation:.6f}.')
    if not np.isfinite(metrics['Client portfolio']).all() or len(risk) != 8 or len(stress) != 3:
        raise ValueError('Required Yahoo summary outputs are incomplete.')
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
    chart_paths = {}
    for key, name, image in zip(keys, names, images):
        payload = b64decode(re.sub(r'\s+', '', image), validate=True)
        if not payload.startswith(b'\x89PNG'):
            raise ValueError('Captured chart is not a valid PNG.')
        path = figures / name
        path.write_bytes(payload)
        chart_paths[key] = path
    tables = {'metrics.csv': metrics, 'risk_contributions.csv': risk,
              'dollar_attribution.csv': attribution.to_frame(), 'hypothetical_stress.csv': stress,
              'planning_sensitivity.csv': sensitivity, 'projection_quantiles_real.csv': projection.quantiles_real}
    for name, frame in tables.items():
        frame.to_csv(output / name)
    manifest = {
        'source': 'Yahoo Finance; preserved results from the user-executed Colab notebook',
        'synthetic_market_data': False, 'source_notebook_sha256': sha256(raw).hexdigest(),
        'source_notebook_encoding': encoding, 'output_notebook_encoding': 'utf-8',
        'source_price_csv_sha256_recorded_in_notebook': checksum_match.group(1),
        'provider_recorded_in_notebook': provider_match.group(1),
        'quality': quality, 'research_config': config.to_dict(), 'client_assumptions': client.to_dict(),
        'precision': 'Metrics/risk: saved four-decimal DataFrames; attribution/stress: saved six-decimal display; NAV supplemented from Colab metadata.',
        'daily_price_cache_included': False,
        'independent_new_yahoo_download_performed': False,
        'limitation': 'Raw daily prices and the original run ZIP were not attached. Historical charts and summaries are preserved, not reconstructed. Rerun the Yahoo-configured notebook to obtain full daily CSV exports.',
        'attribution_reconciliation_residual_usd': float(reconciliation),
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
    (ROOT/'FINDINGS.md').write_text(findings, encoding='utf-8')
    (output/'FINDINGS.md').write_text(findings, encoding='utf-8')
    market_manifest = {'provider': provider_match.group(1), 'sha256': checksum_match.group(1),
                      'synthetic': False, 'retrieval_timestamp': None,
                      'provenance_note': manifest['limitation'],
                      'source_notebook_sha256': manifest['source_notebook_sha256']}
    report = create_html_report(output/'client_report.html', config, client, metrics, projection,
                               chart_paths, quality, market_manifest,
                               {'source': 'explicit constant effective-annual assumption',
                                'rate': config.annual_risk_free_rate}, findings_markdown=findings)
    html = report.read_text()
    note = ('<section><h2>About this saved Yahoo case</h2><p>This finalized report preserves the Yahoo '
            'figures and results saved in the supplied Colab notebook. Summary tables retain their '
            'saved display precision. The raw daily-price cache was not attached, and a new Yahoo '
            'download could not be performed in the finalization environment. Re-run the notebook '
            'to create fresh daily data exports. Client projections were independently recalculated '
            'from the saved assumptions.</p></section>')
    report.write_text(html.replace('<div class="cards">', note+'<div class="cards">',1),encoding='utf-8')
    (ROOT/'docs/images').mkdir(exist_ok=True)
    shutil.copy2(chart_paths['overview'],ROOT/'docs/images/portfolio_overview.png')
    # Build a maintainable notebook, then preserve the actual Yahoo outputs by cell number.
    subprocess.run([sys.executable,str(ROOT/'tools/build_notebook.py')],check=True)
    target = ROOT/'WealthLab_Colab.ipynb'
    finalized = json.loads(target.read_text())
    for number, cell in cell_map(finalized).items():
        if number in cells:
            captured = cells[number]
            cell['outputs'] = [item for item in captured.get('outputs',[])
                               if 'application/javascript' not in item.get('data',{})]
            cell['execution_count'] = captured.get('execution_count')
        if number in {9,10,20,22}:
            cell['execution_count'], cell['outputs'] = None, []
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
        'saved_outputs_source':'Uploaded, successfully executed Yahoo notebook',
        'source_notebook_sha256':manifest['source_notebook_sha256'],
        'findings_updated_to_match_yahoo':True, 'fresh_yahoo_download_during_finalization':False,
        'new_reporting_code_requires_rerun_for_a_fresh_run':True,
    }
    target.write_text(json.dumps(finalized,ensure_ascii=False,indent=1),encoding='utf-8')
    print(json.dumps({'market_source':config.source,'observations':quality['retained_rows'],
        'portfolio_cagr':float(metrics.loc['CAGR','Client portfolio']),
        'ending_nav':float(metrics.loc['Ending NAV USD','Client portfolio']),
        'attribution_residual':float(reconciliation),'saved_pngs':len(chart_paths),
        'notebook_cells':len(finalized['cells']),'report':str(report)},indent=2))


if __name__ == '__main__':
    main()
