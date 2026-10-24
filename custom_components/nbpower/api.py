"""NBPower cloud protocol, evidenced by the official Android app 2.0.16.

Polling performs telemetry reads only. No response bodies are logged.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

BOOTSTRAP = 'https://g.echgr.com'


class APIError(Exception):
    """Sanitized transport, protocol or server error."""


class AuthenticationError(APIError):
    """A new OTP login is required."""


def server_origin(server: str) -> str:
    """Accept only HTTPS origins in the evidenced manufacturer's domain."""
    if '://' not in server:
        server = 'https://' + server
    parsed = urlsplit(server)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or not (host == 'echgr.com' or host.endswith('.echgr.com'))
            or parsed.port not in (None, 443) or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise APIError('Unsupported server origin')
    return 'https://' + host


def _decode(values):
    return ''.join(chr(value-index) for index, value in enumerate(values))


def _js_string(value):
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return str(value)


def signed_payload(params, token=None, timestamp=None):
    """Replicate post.vue sorting, encodeURIComponent and middle-16 MD5."""
    data = {**params}
    if token:
        data['accesstoken'] = token
    data.update({'_platform': 'android', '_system': 'Android', '_brand': 'NBPower',
                 '_model': 'Home Assistant', '_businessID': 2, '_locale': 'en',
                 '_version': '2.0.16', '_versionCode': 20016,
                 '_proj': _decode([78, 67, 82, 114, 123, 106, 120]),
                 '_sig_ts': int(time.time() if timestamp is None else timestamp)})
    data.pop('sig', None)
    data = {key: value for key, value in data.items() if value is not None}
    encoded = '&'.join(key + '=' + quote(_js_string(data[key]), safe="~()*!.'-_")
                       for key in sorted(data))
    prefix = _decode([65, 69, 119, 111, 79, 80, 74, 45, 88, 124, 114, 66, 80, 88, 71, 99])
    data['sig'] = hashlib.md5((prefix + '&' + encoded).encode()).hexdigest()[8:24]
    return data


async def urllib_transport(url, payload):
    """Dependency-free CLI transport. Credentials exist only in memory."""
    def request():
        try:
            body = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
            req = Request(url, data=body, headers={'Content-Type': 'application/json'})
            with urlopen(req, timeout=15) as response:
                data = json.loads(response.read(2 * 1024 * 1024))
            if not isinstance(data, dict):
                raise APIError('Unexpected response type')
            return data
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            raise APIError('HTTPS request failed') from None
    return await asyncio.to_thread(request)


class NBPowerClient:
    def __init__(self, transport=urllib_transport, *, access_token=None,
                 refresh_token=None, user_server=None, on_tokens=None):
        self.transport = transport
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.user_server = server_origin(user_server) if user_server else None
        self.on_tokens = on_tokens
        self.address = None
        self._refresh_lock = asyncio.Lock()
        self._charger_servers = {}

    async def discover(self):
        payload = {'accesstoken': self.access_token} if self.access_token else {}
        try:
            response = await self.transport(BOOTSTRAP + '/api/getUserServer', payload)
        except APIError:
            # Both origins are present in post.vue; regional bootstrap may time out.
            response = await self.transport('https://c.echgr.com/api/getUserServer', payload)
        self._check(response)
        try:
            self.user_server = server_origin(response['data']['server'])
            self.address = response['data'].get('address')
        except (KeyError, TypeError):
            raise APIError('Missing user server') from None
        return self.user_server

    @staticmethod
    def _check(response):
        if response.get('code') == 10000:
            raise AuthenticationError('Session expired')
        if response.get('code') != 0:
            code = response.get('code')
            raise APIError('API rejected request (code %s)' % (code if isinstance(code, int) else 'unknown'))

    def _save_tokens(self, response):
        if not isinstance(response.get('accesstoken'), str) or not response['accesstoken']:
            raise AuthenticationError('Missing access token')
        self.access_token = response['accesstoken']
        self.refresh_token = response.get('refreshtoken', self.refresh_token)
        if self.on_tokens:
            self.on_tokens(self.access_token, self.refresh_token, self.user_server)

    async def call(self, endpoint, params=None, *, origin=None, retry=True):
        if not self.user_server:
            await self.discover()
        target = server_origin(origin or self.user_server)
        sent_token = self.access_token
        response = await self.transport(target + '/api/' + endpoint,
                                        signed_payload(params or {}, sent_token))
        if response.get('code') == 10000 and retry and self.refresh_token:
            async with self._refresh_lock:
                if sent_token == self.access_token:
                    refreshed = await self.call('refreshtoken', {'refreshtoken': self.refresh_token}, retry=False)
                    self._save_tokens(refreshed)
            return await self.call(endpoint, params, origin=origin, retry=False)
        self._check(response)
        return response

    async def request_otp(self, email, captcha='1234'):
        await self.call('getTelCode', {'mail': email.strip(), 'code': captcha})

    async def login(self, email, otp):
        response = await self.call('telLoginByCode', {'mail': email.strip(), 'code': otp.strip(), 'address': self.address})
        self._save_tokens(response)

    async def chargers(self):
        response = await self.call('getBindedChargers')
        chargers = response.get('list')
        if not isinstance(chargers, list) or not all(isinstance(c, dict) and c.get('imei') for c in chargers):
            raise APIError('Unexpected charger list')
        return chargers

    async def _charger_origin(self, imei):
        if imei not in self._charger_servers:
            response = await self.call('getChargerServer', {'imei': imei})
            self._charger_servers[imei] = server_origin(response.get('server', ''))
        return self._charger_servers[imei]

    async def status(self, imei):
        return await self.call('getNBPNetStatus', {'imei': imei}, origin=await self._charger_origin(imei))

    async def _device_command(self, imei, command, params=()):
        """Official cloud command envelope; never retry an uncertain transport failure."""
        packet = [command, 1, *params]
        if any(type(b) is not int or not 0 <= b <= 255 for b in packet):
            raise APIError('Invalid device command bytes')
        response = await self.call('ctrlNBP', {'imei': imei, 'db': packet},
                                   origin=await self._charger_origin(imei))
        try:
            data = response['res']['data']
            if (not isinstance(data, list) or len(data) < 3
                    or any(type(b) is not int or not 0 <= b <= 255 for b in data)
                    or data[0] != len(data)-1 or data[1] != command):
                raise APIError('Invalid command response')
            # The cloud replaces req_id: a real CMD 1 read echoed 145, not 1.
            return data[3:]
        except (KeyError, TypeError):
            raise APIError('Missing command response') from None

    async def read_command(self, imei, command):
        """Allowlisted reads evidenced in the official app; no settings writes."""
        if command not in (1, 47, 69):
            raise APIError('Not an allowlisted read command')
        return await self._device_command(imei, command)


def parse_heartbeat(data):
    """Decode length-prefixed heartDB records, rejecting incomplete data."""
    if not isinstance(data, list) or not data or any(type(b) is not int or not 0 <= b <= 255 for b in data):
        raise APIError('Invalid heartbeat bytes')
    pos = data[0] + 1
    if pos > len(data):
        raise APIError('Truncated network header')
    records = {}
    while pos < len(data):
        size = data[pos]
        if size < 2 or pos + size + 1 > len(data):
            raise APIError('Truncated heartbeat record')
        records[data[pos+1]] = data[pos+3:pos+size+1]
        pos += size + 1
    version = records.get(1, [])
    charge = records.get(49, [])
    if not version or len(charge) < 10:
        raise APIError('Heartbeat lacks version or charge state')
    result = {'firmware': version[0], 'state_code': charge[0],
              'state': {0: 'unplugged', 1: 'standby', 2: 'scheduled', 3: 'charging',
                        4: 'reduced_power', 5: 'cooling', 255: 'updating'}.get(charge[0], 'unknown'),
              'error_code': charge[5], 'error_info': (charge[6] << 8) | charge[7]}
    for name, index in [('temperature', 1), ('temperature_2', 4), ('temperature_3', 2), ('temperature_4', 15)]:
        result[name] = charge[index]-40 if len(charge) > index and charge[index] != 255 else None
    def meter(raw):
        if len(raw) < (8 if version[0] > 27 else 14):
            raise APIError('Truncated meter record')
        def u16(index):
            return raw[index] * 256 + raw[index+1]
        if version[0] > 27:
            return u16(0)/10, u16(2)/10, u16(4), u16(6)/100
        register = int.from_bytes(bytes(raw[5:8]), 'big')
        pulses = int(3600000000000 / (1.88 * register * 2)) if register else 0
        if not pulses:
            raise APIError('Invalid legacy meter calibration')
        return u16(1)/10, u16(3)/10, u16(8)/(1 if version[0] > 17 else 10), (65536*u16(10)+u16(12))/pulses
    if 8 not in records:
        raise APIError('Heartbeat lacks meter data')
    voltage, current, power, energy = meter(records[8])
    phases = charge[16] if version[0] > 27 and len(charge) > 16 else 1
    if phases > 1:
        for command in (13, 14):
            if command not in records:
                raise APIError('Missing phase meter')
            _, _, p, e = meter(records[command])
            power += p
            energy += e
    result.update(voltage=voltage, current=current, power=power, session_energy=energy)
    # Voltage and current above are first-phase values, as in the app.
    return result


def telemetry(response, *, now=None, max_age=120):
    """Require a dated heartbeat; never present cached cloud data as live."""
    try:
        active = response['activeTime']
        if isinstance(active, (int, float)):
            stamp = active / 1000  # app passes this value to new Date()
        elif isinstance(active, str):
            parsed = datetime.fromisoformat(active.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Ambiguous timezone')
            stamp = parsed.timestamp()
        else:
            raise ValueError('Invalid timestamp')
        age = (time.time() if now is None else now) - stamp
        if age < -60 or age > max_age:
            raise APIError('Heartbeat is stale')
        result = parse_heartbeat(response['heartDB']['data'])
        result['last_seen'] = datetime.fromtimestamp(stamp, timezone.utc)
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        raise APIError('Invalid status envelope or timestamp') from None
