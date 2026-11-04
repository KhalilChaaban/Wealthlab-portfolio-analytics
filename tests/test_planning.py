"""Planning boundary cases and deterministic analytical comparisons."""

from dataclasses import replace
import unittest
import numpy as np

from wealthlab.config import ClientConfig
from wealthlab.planning import simulate_client, planning_sensitivity


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.client = ClientConfig(current_wealth=1000, annual_spending_today=120,
                                   horizon_years=1, inflation=0, expected_annual_return=0,
                                   annual_volatility=0, legacy_goal_today=0, paths=100,
                                   one_off_spending={})

    def test_zero_return_cashflow_has_exact_solution(self):
        result = simulate_client(self.client, 0)
        np.testing.assert_allclose(result.terminal_real, 880)
        self.assertEqual(result.survival_probability, 1)

    def test_zero_volatility_growth_matches_expected_annual_return(self):
        client = replace(self.client, annual_spending_today=0, expected_annual_return=.06)
        result = simulate_client(client, 0)
        np.testing.assert_allclose(result.terminal_real, 1060)

    def test_fee_compounds_once_over_a_year(self):
        client = replace(self.client, annual_spending_today=0)
        np.testing.assert_allclose(simulate_client(client, .01).terminal_real, 990)

    def test_depletion_is_absorbing(self):
        client = replace(self.client, annual_spending_today=2400)
        result = simulate_client(client, 0)
        np.testing.assert_allclose(result.terminal_real, 0)
        self.assertEqual(result.survival_probability, 0)
        self.assertEqual(result.success_probability, 0)

    def test_legacy_goal_changes_joint_success_not_spending_funding(self):
        result = simulate_client(replace(self.client, legacy_goal_today=900), 0)
        self.assertEqual(result.survival_probability, 1)
        self.assertEqual(result.success_probability, 0)

    def test_one_off_spending_is_applied_once(self):
        client = replace(self.client, one_off_spending={6: 100})
        np.testing.assert_allclose(simulate_client(client, 0).terminal_real, 780)

    def test_real_wealth_deflates_nominal_balance(self):
        client = replace(self.client, annual_spending_today=0, inflation=.05)
        np.testing.assert_allclose(simulate_client(client, 0).terminal_real, 1000/1.05)

    def test_random_seed_is_reproducible(self):
        client = replace(self.client, annual_volatility=.2)
        a, b = simulate_client(client), simulate_client(client)
        np.testing.assert_array_equal(a.terminal_real, b.terminal_real)

    def test_more_spending_does_not_improve_success_with_common_shocks(self):
        table = planning_sensitivity(replace(self.client, legacy_goal_today=850, annual_volatility=.2), 0)
        self.assertTrue((table.diff().iloc[1:].to_numpy() <= 0).all())

    def test_invalid_shocks_rejected(self):
        with self.assertRaises(ValueError):
            simulate_client(self.client, shocks=np.zeros((2,2)))

    def test_invalid_inputs_rejected(self):
        for fields in [{"current_wealth": -1}, {"annual_spending_today": -1}, {"paths": 0},
                       {"inflation": float("nan")}, {"one_off_spending": {0: 100}}]:
            with self.assertRaises(ValueError):
                replace(self.client, **fields)


if __name__ == "__main__":
    unittest.main()
