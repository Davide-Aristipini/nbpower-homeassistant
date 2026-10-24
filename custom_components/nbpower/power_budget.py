"""Pure single-phase budget calculation: grid headroom and home-battery cap."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PowerBudget:
    software_limit_w: float = 5000
    grid_limit_w: float = 6000
    grid_reserve_w: float = 300
    battery_limit_w: float = 2000
    voltage_ceiling_v: float = 253
    max_current_a: float = 19.5

    def calculate(self, *, ev_w, house_w, grid_w, pv_w, battery_w, losses_w=0):
        values=(ev_w,house_w,grid_w,pv_w,battery_w,losses_w)
        if any(not math.isfinite(v) for v in values) or min(ev_w,house_w,pv_w)<0:
            return {'power_w':0,'current_a':0,'reason':'invalid_energy_data'}
        if ev_w>house_w+200:
            return {'power_w':0,'current_a':0,'reason':'energy_samples_updating'}
        other=max(0,house_w-ev_w)
        reserve_limit=self.grid_limit_w-self.grid_reserve_w
        if other>=reserve_limit:
            return {'power_w':0,'current_a':0,'reason':'house_load_limit'}
        target=min(self.software_limit_w,self.max_current_a*self.voltage_ceiling_v,
                   max(0,ev_w+reserve_limit-grid_w))
        reason='grid_and_solar_headroom'
        if battery_w>150 and (ev_w<50 or ev_w-max(grid_w,0)>150):
            surplus=max(0,pv_w-other-max(0,losses_w))
            target=min(target,surplus+self.battery_limit_w)
            reason='home_battery_capped' if surplus<100 else 'solar_plus_limited_battery'
        pwm=math.floor(target/(self.voltage_ceiling_v*60/250)+1e-9)
        if pwm<25:
            return {'power_w':0,'current_a':0,'reason':'insufficient_grid_headroom'}
        current=pwm*60/250
        return {'power_w':round(target),'current_a':round(current,2),'reason':reason}
