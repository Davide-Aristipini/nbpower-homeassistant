"""Cloud telemetry and opt-in single-phase current/load management."""
import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import APIError, AuthenticationError, NBPowerClient, telemetry
from .const import DOMAIN
from .control import ChargingPolicy, NBPowerChargeController
from .power_budget import PowerBudget
from .transport import ha_transport

LOGGER = logging.getLogger(__name__)


class NBPowerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, update_interval=timedelta(seconds=15), config_entry=entry)
        self.entry = entry
        self.settings = dict(entry.options)
        self.controls_enabled = bool(self.settings.get('enable_controls', False))
        self.runtime = {
            'automatic': bool(self.settings.get('automatic_default', False)),
            'desired': bool(self.settings.get('requested_default', False)),
            'max_current': float(self.settings.get('max_current_a', 6)),
            'end_epoch': float(self.settings.get('initial_end_epoch', 0)),
            'user_stopped': False,
        }
        self.client = NBPowerClient(ha_transport(hass), access_token=entry.data['access_token'],
            refresh_token=entry.data.get('refresh_token'), user_server=entry.data['user_server'], on_tokens=self.save_tokens)
        self.client.on_meter = self._direct_meter_update
        self.controller = NBPowerChargeController(self.client, entry.data['imei'],
            ChargingPolicy(self.runtime['max_current'], float(self.settings.get('max_power_w', 5000)), 253))
        self.store = Store(hass, 1, DOMAIN+'_'+entry.entry_id+'_runtime')
        self.ready = False
        self.closing = False
        self.reason = 'read_only' if not self.controls_enabled else 'waiting_for_energy_data'
        self.control_status = 'idle'
        self.plan = {'power_w': None, 'current_a': None, 'reason': self.reason}
        self._management_task = None
        self._operation_lock = asyncio.Lock()
        self._last_command = 0
        self._last_start = 0
        self._last_connected = None

    async def async_initialize(self):
        saved = await self.store.async_load()
        if saved:
            self.runtime.update(saved)
        self.runtime['max_current'] = min(float(self.runtime['max_current']),
            float(self.settings.get('max_current_a', 6)), float(self.settings.get('max_power_w', 5000))/253)
        if self.runtime['desired'] and not self.runtime['end_epoch']:
            self.runtime['end_epoch'] = time.time()+60*self.settings.get('session_minutes', 480)
        self._policy()

    def save_tokens(self, access, refresh, server):
        self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data,
            'access_token': access, 'refresh_token': refresh, 'user_server': server})

    def save_runtime(self):
        self.store.async_delay_save(lambda: dict(self.runtime), 1)

    def _direct_meter_update(self, raw, stamp):
        if self.data is None or self.data.get('firmware', 0)<=27 or self.data.get('phases')!=1 or len(raw)<8:
            return
        def u16(index):
            return raw[index]*256+raw[index+1]
        self.async_set_updated_data({**self.data, 'voltage':u16(0)/10, 'current':u16(2)/10,
            'power':u16(4), 'session_energy':u16(6)/100, 'meter_source':'direct_device_read'})

    def _policy(self):
        self.controller.policy = ChargingPolicy(float(self.runtime['max_current']),
            float(self.settings.get('max_power_w', 5000)), 253)

    def _power(self, key, *, optional=False):
        entity = self.settings.get(key)
        if not entity:
            return 0 if optional else None
        state = self.hass.states.get(entity)
        if state is None or state.state in ('unknown', 'unavailable', ''):
            return None
        try:
            value = float(state.state)
            unit = state.attributes.get('unit_of_measurement')
            if unit == 'kW':
                value *= 1000
            elif unit != 'W':
                return None
            if (dt_util.utcnow()-state.last_reported).total_seconds()>180:
                return None
            return value
        except (ValueError, TypeError):
            return None

    def calculate_plan(self, values):
        sources = {key: self._power(setting) for key, setting in (
            ('house_w', 'house_power_entity'), ('grid_w', 'grid_power_entity'),
            ('pv_w', 'pv_power_entity'), ('battery_w', 'battery_power_entity'))}
        loss = self._power('losses_power_entity', optional=True)
        if any(value is None for value in sources.values()) or loss is None:
            return {'power_w': 0, 'current_a': 0, 'reason': 'waiting_for_energy_data'}
        budget = PowerBudget(software_limit_w=float(self.settings.get('max_power_w', 5000)),
            grid_limit_w=float(self.settings.get('grid_limit_w', 6000)),
            grid_reserve_w=float(self.settings.get('grid_reserve_w', 300)),
            battery_limit_w=float(self.settings.get('battery_limit_w', 2000)),
            max_current_a=float(self.runtime['max_current']))
        return budget.calculate(ev_w=values['power'], losses_w=loss, **sources)

    def _car_full(self):
        soc = self.hass.states.get(self.settings.get('car_soc_entity', ''))
        target = self.hass.states.get(self.settings.get('car_target_soc_entity', ''))
        age = self.hass.states.get(self.settings.get('car_data_age_entity', ''))
        try:
            return bool(soc and target and age and float(age.state)<180
                        and float(soc.state)>=float(target.state))
        except (TypeError, ValueError):
            return False

    def _decorate(self, values):
        return {**values, 'available_charging_power': self.plan['power_w'],
                'target_current': self.plan['current_a'], 'management_reason': self.reason,
                'control_status': self.control_status,
                'automatic_management': bool(self.runtime['automatic']),
                'charging_authorized': bool(self.runtime['desired'])}

    def publish(self):
        if self.data is not None:
            self.async_set_updated_data(self._decorate(self.data))

    async def _async_update_data(self):
        try:
            values = telemetry(await self.client.status(self.entry.data['imei']))
            if self.controls_enabled:
                self.plan = self.calculate_plan(values)
                if self.control_status == 'idle' and self.runtime['desired']:
                    self.reason = self.plan['reason']
            result = self._decorate(values)
            if self.ready:
                self.schedule_management()
            return result
        except AuthenticationError:
            raise ConfigEntryAuthFailed('NBPower login required') from None
        except APIError as error:
            raise UpdateFailed(str(error)) from None

    def schedule_management(self):
        if self.ready and self.controls_enabled and (self._management_task is None or self._management_task.done()):
            self._management_task = self.hass.async_create_task(self._manage())

    async def _operate(self, kind, operation):
        self.control_status = kind
        self.publish()
        try:
            await operation()
            self._last_command = time.monotonic()
            self.reason = 'command_confirmed'
        except APIError as error:
            self.reason = 'command_unconfirmed'
            self._last_command = time.monotonic()
            LOGGER.warning('NBPower %s outcome: %s', kind, error)
            raise HomeAssistantError(str(error)) from None
        finally:
            self.control_status = 'idle'
            self.save_runtime()
            self.publish()
            if not self.closing:
                await self.async_request_refresh()

    async def _start_at(self, amps):
        remaining = max(0, min(1440, int((self.runtime['end_epoch']-time.time()+59)//60)))
        if not remaining:
            raise APIError('Authorized charge window has ended')
        fresh=await self.controller._status()
        if fresh['state_code'] in (3,4):
            await self._change_at(amps)
            return
        self._last_start = time.monotonic()
        await self.controller.start(amps, minutes=remaining)
        self.controller.deadline = time.monotonic()+max(0, self.runtime['end_epoch']-time.time())
        self._last_start = time.monotonic()

    async def _change_at(self, amps):
        if not self.controller.owned:
            await self.controller.adopt_current_session()
        self.controller.deadline = time.monotonic()+max(0, self.runtime['end_epoch']-time.time())
        await self.controller.update_current(amps)

    async def _manage(self):
        try:
            async with self._operation_lock:
                if not self.data or not self.last_update_success:
                    return
                value = self.data
                connected = value['state_code'] != 0
                if (self._last_connected is False and connected and self.runtime['automatic']):
                    self.runtime.update(desired=True, user_stopped=False,
                        end_epoch=time.time()+60*self.settings.get('session_minutes', 480))
                self._last_connected = connected
                charging_now = value['state_code'] in (3,4)
                if charging_now and value['voltage']>253:
                    self.reason='voltage_outside_control_envelope'
                    await self._operate('stopping',self.controller.stop)
                    return
                if not self.runtime['desired']:
                    self.reason = 'stopped_by_user' if self.runtime['user_stopped'] else 'idle'
                    if (self.runtime['user_stopped'] and value['state_code'] in (3,4)
                            and time.monotonic()-self._last_command>60):
                        await self._operate('stopping',self.controller.stop)
                    return
                if not self.runtime['automatic']:
                    return
                charging = value['state_code'] in (3, 4)
                if time.time() >= self.runtime['end_epoch']:
                    self.runtime['desired'] = False
                    self.reason = 'authorized_window_ended'
                    if charging:
                        await self._operate('stopping', self.controller.stop)
                    return
                if self._car_full():
                    self.reason = 'car_target_reached'
                    if charging:
                        await self._operate('stopping', self.controller.stop)
                    return
                if not connected or value['error_code'] or value['phases'] != 1:
                    self.reason = 'charger_not_ready'
                    return
                plan = self.calculate_plan(value)
                self.plan = plan
                self.reason = plan['reason']
                if plan['reason'] == 'energy_samples_updating':
                    return
                if (time.monotonic()-self._last_command < 35 and plan['current_a']>=6
                        and value['power']<=float(self.settings.get('max_power_w',5000))):
                    return
                amps = plan['current_a']
                if amps < 6:
                    if charging:
                        await self._operate('pausing_for_house', self.controller.stop)
                    return
                if charging:
                    applied = value['advertised_current']
                    if amps>applied:
                        amps=min(amps,applied+2)
                    if value['power']>float(self.settings.get('max_power_w',5000)):
                        amps=min(amps,applied-0.5)
                        if amps<6:
                            await self._operate('pausing_for_power_limit',self.controller.stop)
                            return
                    if abs(applied-amps) >= 0.40:
                        await self._operate('adjusting_current', lambda: self._change_at(amps))
                elif value['state_code'] == 1 and time.monotonic()-self._last_start >= 120:
                    await self._operate('starting', lambda: self._start_at(6))
        except HomeAssistantError:
            pass
        finally:
            self.save_runtime()
            self.publish()

    def _require_controls(self):
        if not self.controls_enabled:
            raise HomeAssistantError('Enable controls in the NBPower options first')

    async def async_start(self):
        self._require_controls()
        async with self._operation_lock:
            self.runtime.update(desired=True, user_stopped=False,
                end_epoch=time.time()+60*self.settings.get('session_minutes', 480))
            self.plan = self.calculate_plan(self.data)
            amps = self.plan['current_a']
            if amps < 6:
                self.reason = self.plan['reason']
                self.save_runtime()
                self.publish()
                return
            if self.data['state_code'] in (3, 4):
                await self._operate('adjusting_current', lambda: self._change_at(amps))
            else:
                await self._operate('starting', lambda: self._start_at(amps))

    async def async_stop(self):
        self._require_controls()
        async with self._operation_lock:
            self.runtime.update(desired=False, user_stopped=True)
            await self._operate('stopping', self.controller.stop)

    async def async_set_automatic(self, enabled):
        self._require_controls()
        self.runtime['automatic'] = enabled
        if enabled and not self.runtime['desired']:
            self.runtime.update(desired=True, user_stopped=False,
                end_epoch=time.time()+60*self.settings.get('session_minutes', 480))
        self.save_runtime()
        self.publish()
        self.schedule_management()

    async def async_set_ceiling(self, amps):
        self._require_controls()
        maximum = min(float(self.settings.get('max_current_a', 6)), float(self.settings.get('max_power_w', 5000))/253)
        if not 6 <= amps <= maximum:
            raise HomeAssistantError('Current ceiling exceeds configured limits')
        self.runtime['max_current'] = amps
        self._policy()
        self.save_runtime()
        self.publish()
        if self.runtime['desired'] and self.data and self.data['state_code'] in (3, 4):
            async with self._operation_lock:
                self.plan = self.calculate_plan(self.data)
                target = self.plan['current_a']
                if target >= 6:
                    await self._operate('adjusting_current', lambda: self._change_at(target))
                else:
                    await self._operate('pausing_for_house', self.controller.stop)

    async def async_shutdown(self):
        self.ready = False
        self.closing = True
        if self._management_task and not self._management_task.done():
            self._management_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._management_task
        await self.store.async_save(dict(self.runtime))
