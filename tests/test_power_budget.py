import importlib.util
from pathlib import Path
import sys
import unittest

spec=importlib.util.spec_from_file_location('nbpower_power_budget',Path(__file__).resolve().parents[1]/'custom_components/nbpower/power_budget.py')
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.budget=module.PowerBudget()

    def test_night_battery_does_not_power_car_above_two_kw(self):
        result=self.budget.calculate(ev_w=2735,house_w=3380,grid_w=516,pv_w=0,battery_w=3051,losses_w=187)
        self.assertEqual(result['reason'],'home_battery_capped')
        self.assertLessEqual(result['current_a']*253,2000)
        self.assertGreaterEqual(result['current_a'],6)

    def test_grid_still_charges_when_battery_is_no_longer_discharging(self):
        result=self.budget.calculate(ev_w=0,house_w=600,grid_w=600,pv_w=0,battery_w=0)
        self.assertGreater(result['current_a'],6)
        self.assertLessEqual(result['current_a']*253,5000)

    def test_small_battery_discharge_for_house_does_not_cap_grid_powered_ev(self):
        result=self.budget.calculate(ev_w=3000,house_w=3600,grid_w=3400,pv_w=0,battery_w=200)
        self.assertGreater(result['power_w'],2000)

    def test_six_kw_other_load_pauses_the_car(self):
        result=self.budget.calculate(ev_w=2000,house_w=8000,grid_w=8000,pv_w=0,battery_w=0)
        self.assertEqual(result['current_a'],0)

    def test_inadequate_grid_headroom_does_not_force_minimum_current(self):
        result=self.budget.calculate(ev_w=2000,house_w=7000,grid_w=7000,pv_w=0,battery_w=0)
        self.assertEqual(result['current_a'],0)

    def test_solar_surplus_adds_to_battery_cap(self):
        result=self.budget.calculate(ev_w=3000,house_w=4000,grid_w=0,pv_w=2500,battery_w=1500)
        self.assertGreater(result['power_w'],2000)
        self.assertLessEqual(result['power_w'],3500)

    def test_export_never_increases_car_past_software_cap(self):
        result=self.budget.calculate(ev_w=3000,house_w=4000,grid_w=-2000,pv_w=6500,battery_w=-500)
        self.assertLessEqual(result['current_a']*253,5000)


if __name__=='__main__':
    unittest.main()
