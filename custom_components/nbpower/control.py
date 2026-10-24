"""Development backend for controlled AC charge tests; not exposed by HA yet.

Implements the official app's cloud challenge flow. Callers must obtain the
owner's consent before physical tests. No polling/startup path calls this module.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import time

from .api import APIError, telemetry


@dataclass(frozen=True)
class ChargingPolicy:
    max_current_a: float
    max_power_w: float
    voltage_ceiling_v: float

    def __post_init__(self):
        values = (self.max_current_a, self.max_power_w, self.voltage_ceiling_v)
        if any(not math.isfinite(value) or value <= 0 for value in values):
            raise APIError('Invalid charging policy')
        if self.max_current_a < 6 or self.voltage_ceiling_v < 230:
            raise APIError('Unsupported AC charging policy')

    def pwm(self, requested_amps, *, hardware_max_a, measured_voltage_v):
        if not all(math.isfinite(value) for value in (requested_amps, hardware_max_a, measured_voltage_v)):
            raise APIError('Invalid current or voltage')
        if measured_voltage_v <= 0 or measured_voltage_v > self.voltage_ceiling_v:
            raise APIError('Voltage outside the configured control envelope')
        maximum = min(self.max_current_a, hardware_max_a, self.max_power_w/self.voltage_ceiling_v)
        if requested_amps < 6 or requested_amps > maximum:
            raise APIError('Requested current exceeds configured limits')
        # PWM granularity is 0.24 A. Round down to avoid increasing the request.
        pwm = math.floor(requested_amps*250/60 + 1e-9)
        if not 25 <= pwm <= 255:
            raise APIError('Current outside supported PWM range')
        return pwm


def start_payload(challenge, minutes, pwm):
    """Match app startCharge(), including its fixed last three auth bytes."""
    if not isinstance(minutes, int) or not 0 <= minutes <= 1440:
        raise APIError('Invalid session duration')
    if len(challenge) < 5 or any(type(b) is not int or not 0 <= b <= 255 for b in challenge):
        raise APIError('Invalid challenge')
    high, low = minutes >> 8, minutes & 255
    auth = []
    for index in range(3):
        denominator = ((high + index + 1) | low) & 255
        value = challenge[index]*256 + challenge[index+1]
        auth.append((value % denominator) & 255 if denominator else 0)
    return [*auth, 1, 1, 0, high, low, 0, 0, pwm]


class NBPowerChargeController:
    """Serialized commands; session ownership is lost after a process restart."""
    def __init__(self, client, imei, policy):
        self.client = client
        self.imei = imei
        self.policy = policy
        self.lock = asyncio.Lock()
        self.deadline = None
        self.hardware_max_a = None

    async def device_info(self):
        version = await self.client.read_command(self.imei, 1)
        config = await self.client.read_command(self.imei, 47)
        if len(version) < 3 or len(config) < 11:
            raise APIError('Truncated device information')
        if version[0] <= 27 or version[1] == 30:
            raise APIError('Charger not supported by this AC control backend')
        # Unlike the app, do not silently substitute 32 A when the value is absent.
        maximum = config[10]
        if not 6 <= maximum <= 50:
            raise APIError('Missing or invalid hardware current limit')
        self.hardware_max_a = maximum
        return {'firmware': version[0], 'device_num': version[1],
                'meter_count': version[2], 'hardware_max_current_a': maximum,
                'run_mode': config[4]}

    async def _send_session(self, minutes, pwm):
        challenge = await self.client._device_command(self.imei, 66)
        reply = await self.client._device_command(self.imei, 67, start_payload(challenge, minutes, pwm))
        if len(reply) < 3 or (minutes and reply[0] < 2):
            raise APIError('Device rejected charge command')
        if reply[1]*256 + reply[2] != minutes:
            raise APIError('Unexpected charge duration acknowledgement')

    async def _checked_pwm(self, amps):
        if self.hardware_max_a is None:
            await self.device_info()
        values = telemetry(await self.client.status(self.imei))
        if values['error_code'] != 0 or values['state_code'] not in (1, 3, 4):
            raise APIError('Charger not ready for current control')
        return self.policy.pwm(amps, hardware_max_a=self.hardware_max_a,
                               measured_voltage_v=values['voltage'])

    async def start(self, amps, *, minutes):
        if type(minutes) is not int or not 1 <= minutes <= 1440:
            raise APIError('A finite nonzero charge duration is required')
        async with self.lock:
            pwm = await self._checked_pwm(amps)
            await self._send_session(minutes, pwm)
            self.deadline = time.monotonic() + minutes*60

    async def update_current(self, amps):
        async with self.lock:
            if self.deadline is None:
                raise APIError('Cannot adopt an existing charge session automatically')
            minutes = math.ceil((self.deadline-time.monotonic())/60)
            if minutes <= 0:
                raise APIError('Owned charge session has expired')
            pwm = await self._checked_pwm(amps)
            await self._send_session(minutes, pwm)
            # Do not move the original deadline when changing current.

    async def stop(self):
        async with self.lock:
            # App stops with CMD 67 and minutes=0; no protection/config writes.
            await self._send_session(0, 25)
            self.deadline = None
