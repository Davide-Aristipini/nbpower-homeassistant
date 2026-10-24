"""Protocol robustness and authentication tests, with synthetic (not captured) fixtures."""
import asyncio
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('api', ROOT / 'custom_components/nbpower/api.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def frame(command, payload):
    return [len(payload)+2, command, 1, *payload]


def heartbeat():
    charge = [3, 68, 255, 90, 255, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 255, 1]
    return [4, 15, 0, 0, 0] + frame(1, [45, 31, 1]) + frame(49, charge) + frame(8, [8, 207, 0, 215, 18, 240, 0, 3])


class ParserTests(unittest.TestCase):
    def test_meter_and_unknown_temperature(self):
        values = api.parse_heartbeat(heartbeat())
        self.assertEqual(values['voltage'], 225.5)
        self.assertEqual(values['current'], 21.5)
        self.assertEqual(values['power'], 4848)
        self.assertEqual(values['session_energy'], .03)
        self.assertEqual(values['temperature'], 28)
        self.assertIsNone(values['temperature_2'])
        self.assertIsNone(values['temperature_3'])
        self.assertEqual(values['state'], 'charging')

    def test_all_truncated_frames_rejected(self):
        data = heartbeat()
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(api.APIError):
                api.parse_heartbeat(data[:length])

    def test_invalid_bytes(self):
        for data in ([], None, [True], [256], [-1], ['4']):
            with self.assertRaises(api.APIError):
                api.parse_heartbeat(data)

    def test_multiphase_requires_all_meters(self):
        data = heartbeat()
        data[30] = 3  # charge payload phase byte, offset 11 + 3 + 16
        with self.assertRaises(api.APIError):
            api.parse_heartbeat(data)

    def test_freshness(self):
        response = {'activeTime': 1000000, 'heartDB': {'data': heartbeat()}}
        self.assertEqual(api.telemetry(response, now=1001)['state'], 'charging')
        with self.assertRaises(api.APIError):
            api.telemetry(response, now=1201)
        response['activeTime'] = '2026-01-01 00:00:00'
        with self.assertRaises(api.APIError):
            api.telemetry(response)

    def test_untrusted_origins(self):
        for url in ('http://g.echgr.com', 'https://echgr.com.evil.test', 'https://g.echgr.com/a',
                    'https://user:secret@g.echgr.com', 'https://g.echgr.com:444'):
            with self.assertRaises(api.APIError):
                api.server_origin(url)
        self.assertEqual(api.server_origin('g.echgr.com'), 'https://g.echgr.com')

    def test_signature_reference(self):
        fixture = json.loads((ROOT / 'tests/signature_fixture.json').read_text())
        actual = api.signed_payload(fixture['params'], timestamp=fixture['timestamp'])
        self.assertEqual(actual['sig'], fixture['signature'])


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_charger_registry_preferred_over_hanging_regional_route(self):
        seen=[]
        async def transport(url,payload):
            seen.append(url)
            if url.endswith('getChargerServer'):
                self.assertTrue(url.startswith('https://c.echgr.com/'))
                return {'code':0,'server':'g.echgr.com'}
            return {'code':0}
        client=api.NBPowerClient(transport,user_server='g.echgr.com')
        await client.status('synthetic-imei')
        self.assertEqual(len(seen),2)

    async def test_fresh_device_meter_temporarily_overrides_stale_cloud_meter(self):
        old=heartbeat()
        fresh=[8,207,0,60,5,73,0,4]
        async def transport(url,payload):
            if url.endswith('getChargerServer'):
                return {'code':0,'server':'g.echgr.com'}
            if url.endswith('ctrlNBP'):
                return {'code':0,'res':{'data':[10,8,42,*fresh]}}
            return {'code':0,'activeTime':1000000,'heartDB':{'data':old}}
        client=api.NBPowerClient(transport,user_server='g.echgr.com')
        await client.read_command('synthetic-imei',8)
        result=await client.status('synthetic-imei')
        values=api.parse_heartbeat(result['heartDB']['data'])
        self.assertEqual(values['current'],6)
        self.assertEqual(values['power'],1353)
        self.assertEqual(result['_meter_source'],'direct_device_read')
        self.assertEqual(api.parse_heartbeat(old)['current'],21.5)

    async def test_device_read_accepts_cloud_rewritten_request_id(self):
        async def transport(url, payload):
            if url.endswith('getChargerServer'):
                return {'code': 0, 'server': 'g.echgr.com'}
            self.assertEqual(payload['db'], [1, 1])
            return {'code': 0, 'res': {'data': [8, 1, 145, 45, 31, 1, 0, 0, 1]}}
        client = api.NBPowerClient(transport, user_server='g.echgr.com')
        self.assertEqual(await client.read_command('synthetic-imei', 1), [45, 31, 1, 0, 0, 1])

    async def test_read_allowlist_does_not_accept_start_commands(self):
        async def transport(url, payload):
            self.fail('A disallowed read must never send an HTTP request')
        client = api.NBPowerClient(transport, user_server='g.echgr.com')
        with self.assertRaises(api.APIError):
            await client.read_command('synthetic-imei', 67)

    async def test_bootstrap_fallback(self):
        seen = []
        async def transport(url, payload):
            seen.append(url)
            if url.startswith(api.BOOTSTRAP):
                raise api.APIError('HTTPS request failed')
            return {'code': 0, 'data': {'server': 'g.echgr.com'}}
        client = api.NBPowerClient(transport)
        self.assertEqual(await client.discover(), 'https://g.echgr.com')
        self.assertEqual(len(seen), 2)

    async def test_refresh_retries_once_and_persists(self):
        refreshed = []
        async def transport(url, payload):
            if url.endswith('refreshtoken'):
                return {'code': 0, 'accesstoken': 'synthetic-new', 'refreshtoken': 'synthetic-refresh'}
            if payload.get('accesstoken') != 'synthetic-new':
                return {'code': 10000}
            return {'code': 0, 'list': []}
        client = api.NBPowerClient(transport, access_token='synthetic-old', refresh_token='synthetic-refresh',
                                   user_server='g.echgr.com', on_tokens=lambda *args: refreshed.append(args))
        self.assertEqual(await client.chargers(), [])
        self.assertEqual(len(refreshed), 1)

    async def test_failed_refresh_does_not_loop_or_expose_tokens(self):
        calls = []
        async def transport(url, payload):
            calls.append(url)
            return {'code': 10000, 'msg': 'synthetic-secret-must-not-leak'}
        client = api.NBPowerClient(transport, access_token='synthetic-old', refresh_token='synthetic-refresh',
                                   user_server='g.echgr.com')
        with self.assertRaises(api.AuthenticationError) as caught:
            await client.chargers()
        self.assertNotIn('synthetic', str(caught.exception))
        self.assertEqual(len(calls), 2)

    async def test_parallel_refresh_is_serialized(self):
        count = 0
        async def transport(url, payload):
            nonlocal count
            await asyncio.sleep(.001)
            if url.endswith('refreshtoken'):
                count += 1
                return {'code': 0, 'accesstoken': 'synthetic-new'}
            return {'code': 0, 'list': []} if payload.get('accesstoken') == 'synthetic-new' else {'code': 10000}
        client = api.NBPowerClient(transport, access_token='synthetic-old', refresh_token='synthetic-refresh', user_server='g.echgr.com')
        await asyncio.gather(client.chargers(), client.chargers())
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
