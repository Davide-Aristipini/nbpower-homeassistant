"""Bounded, serialized AC commands confirmed against the device telemetry."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import time

from .api import APIError, AuthenticationError, telemetry


@dataclass(frozen=True)
class ChargingPolicy:
    max_current_a: float
    max_power_w: float
    voltage_ceiling_v: float

    def __post_init__(self):
        if any(not math.isfinite(v) or v<=0 for v in (self.max_current_a,self.max_power_w,self.voltage_ceiling_v)):
            raise APIError('Invalid charging policy')
        if self.max_current_a<6 or self.voltage_ceiling_v<230:
            raise APIError('Unsupported AC charging policy')

    def pwm(self, requested_amps, *, hardware_max_a, measured_voltage_v):
        if not all(math.isfinite(v) for v in (requested_amps,hardware_max_a,measured_voltage_v)):
            raise APIError('Invalid current or voltage')
        if not 0<measured_voltage_v<=self.voltage_ceiling_v:
            raise APIError('Voltage outside configured envelope')
        maximum=min(self.max_current_a,hardware_max_a,self.max_power_w/self.voltage_ceiling_v)
        if not 6<=requested_amps<=maximum:
            raise APIError('Requested current exceeds configured limits')
        pwm=math.floor(requested_amps*250/60+1e-9)
        if not 25<=pwm<=255:
            raise APIError('Current outside supported PWM range')
        return pwm


def start_payload(challenge, minutes, pwm, *, update=False):
    if type(minutes) is not int or not (0<=minutes<=1440 or update and minutes==65535):
        raise APIError('Invalid session duration')
    high,low=minutes>>8,minutes&255
    if update:
        # Official app pay(true)/startCharge(..., true), only for a running,
        # explicitly adopted session. Not used to start an idle charger.
        auth=[1,1,1]
    else:
        if len(challenge)<5 or any(type(b) is not int or not 0<=b<=255 for b in challenge):
            raise APIError('Invalid challenge')
        auth=[]
        for index in range(3):
            denominator=((high+index+1)|low)&255
            value=challenge[index]*256+challenge[index+1]
            auth.append(value%denominator if denominator else 0)
    return [*auth,1,1,0,high,low,0,0,pwm]


class NBPowerChargeController:
    def __init__(self, client, imei, policy):
        self.client,self.imei,self.policy=client,imei,policy
        self.lock=asyncio.Lock()
        self.deadline=None
        self.owned=False
        self.hardware_max_a=None
        self.last_confirmation=None
        self.confirmation_timeout=32
        self.confirmation_interval=3

    async def device_info(self):
        version=await self.client.read_command(self.imei,1)
        config=await self.client.read_command(self.imei,47)
        if len(version)<3 or len(config)<11:
            raise APIError('Truncated device information')
        if version[0]<=27 or version[1]==30 or version[2]!=1:
            raise APIError('Only the verified single-meter AC protocol is supported for controls')
        maximum=config[10]
        if not 6<=maximum<=50:
            raise APIError('Missing hardware current limit')
        self.hardware_max_a=maximum
        return {'firmware':version[0],'device_num':version[1],'meter_count':version[2],
                'hardware_max_current_a':maximum,'run_mode':config[4]}

    async def _status(self):
        return telemetry(await self.client.status(self.imei),max_age=45)

    async def _checked_pwm(self, amps):
        if self.hardware_max_a is None:
            await self.device_info()
        values=await self._status()
        if values['error_code'] or values['state_code'] not in (1,3,4) or values['phases']!=1:
            raise APIError('Charger not ready for single-phase control')
        return self.policy.pwm(amps,hardware_max_a=self.hardware_max_a,measured_voltage_v=values['voltage'])

    async def _confirm(self, minutes, pwm, sent_at):
        end=time.monotonic()+self.confirmation_timeout
        while True:
            try:
                await self.client.read_command(self.imei,8)
                values=await self._status()
                fresh=values['last_seen'].timestamp()>=sent_at-3
                if minutes==0:
                    matched=fresh and values['state_code'] in (0,1) and values['power']<=10
                else:
                    matched=(fresh and values['state_code'] in (3,4)
                             and values['current_limit_pwm']==pwm
                             and values['power']>25 and values['current']>0.1
                             and values['current']<=pwm*60/250+0.6)
                if matched:
                    if minutes:
                        timer=await self.client.read_command(self.imei,69)
                        remaining=timer[1]*256+timer[2] if len(timer)>=5 else -1
                        if not (remaining==65535 if minutes==65535 else max(1,minutes-2)<=remaining<=minutes):
                            raise APIError('Requested session timer not confirmed')
                    self.last_confirmation='fresh_telemetry'
                    return
            except AuthenticationError:
                raise
            except APIError:
                pass
            if time.monotonic()>=end:
                raise APIError('Command outcome unconfirmed; no command retry was performed')
            await asyncio.sleep(self.confirmation_interval)

    async def _send_session(self, minutes, pwm, *, update=False):
        challenge=[] if update else await self.client._device_command(self.imei,66)
        sent_at=time.time()
        reply=None
        try:
            reply=await self.client._device_command(self.imei,67,start_payload(challenge,minutes,pwm,update=update))
        except AuthenticationError:
            raise
        except APIError as error:
            if error.code not in (None,2):
                raise
            # A timeout is not a rejection. Observe the intent, without resending.
        if minutes and reply and reply[0]<2:
            raise APIError('Device rejected charge command')
        if minutes and reply and len(reply)>=3:
            if reply[1]*256+reply[2]!=minutes:
                raise APIError('Unexpected charge duration acknowledgement')
            await self._confirm(minutes,pwm,sent_at)
            self.last_confirmation='device_reply_and_telemetry'
        else:
            # Stops may legitimately return a short ACK on firmware 45.
            await self._confirm(minutes,pwm,sent_at)

    async def adopt_current_session(self):
        """Explicit takeover only; callers must obtain the owner's permission."""
        async with self.lock:
            values=await self._status()
            timer=await self.client.read_command(self.imei,69)
            if values['state_code'] not in (3,4) or len(timer)<5 or timer[0]<2 or timer[3]*256+timer[4]:
                raise APIError('Cannot adopt a stopped or scheduled session')
            minutes=timer[1]*256+timer[2]
            if not minutes:
                raise APIError('Invalid running timer')
            self.deadline=None if minutes==65535 else time.monotonic()+minutes*60
            self.owned=True

    async def start(self, amps, *, minutes):
        if type(minutes) is not int or not 1<=minutes<=1440:
            raise APIError('A finite charge duration is required')
        async with self.lock:
            pwm=await self._checked_pwm(amps)
            await self._send_session(minutes,pwm)
            self.deadline=time.monotonic()+minutes*60
            self.owned=True

    async def update_current(self, amps):
        async with self.lock:
            if not self.owned:
                raise APIError('Explicit session adoption required')
            minutes=65535 if self.deadline is None else math.ceil((self.deadline-time.monotonic())/60)
            if minutes<=0:
                raise APIError('Owned session expired')
            pwm=await self._checked_pwm(amps)
            await self._send_session(minutes,pwm,update=True)

    async def stop(self):
        async with self.lock:
            await self._send_session(0,25)
            self.deadline=None
            self.owned=False

    async def reduce_hardware_limit(self, amps, *, maximum_power_w=5500):
        """Lower only the limit byte, preserve all protection bytes, then verify."""
        async with self.lock:
            value=await self._status()
            if value['state_code'] not in (0,1) or value['power']>10:
                raise APIError('Hardware limit changes require an idle charger')
            before=await self.client.read_command(self.imei,47)
            if len(before)<11 or type(amps) is not int or not 6<=amps<=before[10]:
                raise APIError('Only a verified reduction is allowed')
            if amps*self.policy.voltage_ceiling_v>maximum_power_w:
                raise APIError('Hardware limit exceeds the authorized power ceiling')
            after=list(before)
            after[10]=amps
            if after!=before:
                try:
                    await self.client._device_command(self.imei,48,after)
                except AuthenticationError:
                    raise
                except APIError:
                    pass
            verified=await self.client.read_command(self.imei,47)
            if verified!=after:
                raise APIError('Hardware limit/protection preservation not verified')
            self.hardware_max_a=amps
            return {'before':before,'after':verified}
