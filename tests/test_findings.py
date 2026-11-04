"""Check that report wording follows the supplied data and escapes HTML."""

from dataclasses import replace
import unittest

import pandas as pd

from wealthlab.config import ResearchConfig, ClientConfig
from wealthlab.findings import build_findings, findings_to_html
from wealthlab.planning import simulate_client


class FindingsTests(unittest.TestCase):
    def test_renderer_escapes_untrusted_text(self):
        html = findings_to_html('## Results\n\n<script>alert(1)</script>\n\n**Safe** text.')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('<strong>Safe</strong>', html)

    def test_generated_source_label_and_comparison_follow_inputs(self):
        cfg = ResearchConfig()
        client = ClientConfig(horizon_years=1, paths=100, one_off_spending={})
        m = pd.DataFrame({'Client portfolio': {'CAGR': .08, 'Total return': .1,
            'Annualized volatility': .09, 'Maximum drawdown': -.2, 'Sharpe ratio': .5,
            'Ending NAV AED': 1100000, 'Advisory fees AED': 1000, 'Transaction costs AED': 100},
            'Strategic benchmark': {'CAGR': .05, 'Total return': .08,
            'Annualized volatility': .1, 'Maximum drawdown': -.22, 'Sharpe ratio': .3,
            'Ending NAV AED': 1080000}})
        risk = pd.DataFrame({'capital_weight': [.3,.4], 'risk_share': [.6,.1]}, index=['SPY','AGG'])
        pnl = pd.Series({'SPY': 100000., 'AGG': 1100., 'Trading costs': -100., 'Advisory fees': -1000.})
        stress = pd.DataFrame({'portfolio_return': [-.1]}, index=['Test shock'])
        projection = simulate_client(client)
        sensitivity = pd.DataFrame([[.4,.6,.8]], index=[client.annual_spending_today], columns=[.04,.06,.08])
        quality = {'first_observation': '2015-01-02', 'last_observation': '2025-12-31', 'retained_rows': 2766}
        arguments = (client,m,risk,pnl,stress,projection,sensitivity,quality)
        demo = build_findings(cfg,*arguments)
        yahoo = build_findings(replace(cfg,source='yahoo'),*arguments)
        self.assertIn('synthetic demonstration',demo)
        self.assertIn('real Yahoo Finance prices',yahoo)
        self.assertNotIn('synthetic demonstration',yahoo)
        self.assertIn('earned a higher annualized return',yahoo)
        self.assertIn('8.00%',yahoo)
        fred = build_findings(replace(cfg, source='yahoo', risk_free_source='fred'), *arguments)
        self.assertIn('lagged FRED DGS3MO yield proxy', fred)
        self.assertNotIn('explicit **2.50% annual risk-free assumption**', fred)
