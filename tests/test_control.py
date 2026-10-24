"""Safety boundaries and command flow for the not-yet-exposed control backend."""
import importlib
from pathlib import Path
import sys
import time
import types
import unittest

from test_api import heartbeat

package = types.ModuleType('nbpower_control_test')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'custom_components/nbpower')]
sys.modules[package.__name__] = package
api = importlib.import_module('nbpower_control_test.api')
control = importlib.import_module('nbpower_control_test.control')


class FakeClient:
    def __init__(self):
        self.commands = []
        self.maximum = 32
        self.age = 0
        self.accept = True

    async def read_command(self, imei, command):
        if command == 1:
            return [45, 31, 1]
        if command == 47:
            return [0]*10 + [self.maximum]
        raise AssertionError('Unexpected read')

    async def status(self, imei):
        return {'activeTime': (time.time()-self.age)*1000, 'heartDB': {'data': heartbeat()}}

    async def _device_command(self, imei, command, params=()):
        self.commands.append((command, list(params)))
        if command == 66:
            return [17, 34, 51, 68, 85]
        if command == 67:
            return [2 if self.accept else 1, params[6], params[7]]
        raise AssertionError('Unexpected write')


class PolicyTests(unittest.TestCase):
    def test_power_ceiling_at_maximum_voltage(self):
        policy = control.ChargingPolicy(32, 5000, 253)
        pwm = policy.pwm(19.5, hardware_max_a=32, measured_voltage_v=231)
        self.assertLessEqual(pwm*60/250*253, 5000)
        self.assertLessEqual(pwm*60/250, 19.5)
        with self.assertRaises(api.APIError):
            policy.pwm(20, hardware_max_a=32, measured_voltage_v=231)

    def test_hardware_limit_and_invalid_voltage(self):
        policy = control.ChargingPolicy(32, 5000, 253)
        for amps, hardware, voltage in [(17, 16, 230), (6, 32, 254), (6, 32, 0), (5, 32, 230), (float('nan'), 32, 230)]:
            with self.subTest(amps=amps, voltage=voltage), self.assertRaises(api.APIError):
                policy.pwm(amps, hardware_max_a=hardware, measured_voltage_v=voltage)

    def test_challenge_matches_app_for_one_minute(self):
        self.assertEqual(control.start_payload([17, 34, 51, 68, 85], 1, 25),
                         [0, 1, 2, 1, 1, 0, 0, 1, 0, 0, 25])


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = FakeClient()
        self.controller = control.NBPowerChargeController(self.client, 'synthetic-imei',
                                                         control.ChargingPolicy(32, 5000, 253))

    async def test_finite_start_current_update_and_stop(self):
        await self.controller.start(6, minutes=1)
        deadline = self.controller.deadline
        await self.controller.update_current(8)
        self.assertEqual(self.controller.deadline, deadline)
        await self.controller.stop()
        self.assertIsNone(self.controller.deadline)
        self.assertEqual([c[0] for c in self.client.commands], [66, 67, 66, 67, 66, 67])
        self.assertEqual(self.client.commands[-1][1][6:8], [0, 0])

    async def test_stale_state_never_sends_start(self):
        self.client.age = 500
        with self.assertRaises(api.APIError):
            await self.controller.start(6, minutes=1)
        self.assertEqual(self.client.commands, [])

    async def test_missing_hardware_limit_never_defaults_to_32(self):
        self.client.maximum = 0
        with self.assertRaises(api.APIError):
            await self.controller.start(6, minutes=1)
        self.assertEqual(self.client.commands, [])

    async def test_does_not_adopt_existing_session(self):
        with self.assertRaises(api.APIError):
            await self.controller.update_current(6)
        self.assertEqual(self.client.commands, [])

    async def test_rejected_start_not_retried(self):
        self.client.accept = False
        with self.assertRaises(api.APIError):
            await self.controller.start(6, minutes=1)
        self.assertIsNone(self.controller.deadline)
        self.assertEqual(len(self.client.commands), 2)

    async def test_unbounded_or_excess_power_start_rejected(self):
        for amps, minutes in [(6, 0), (6, 1441), (22, 1)]:
            with self.subTest(amps=amps, minutes=minutes), self.assertRaises(api.APIError):
                await self.controller.start(amps, minutes=minutes)
        self.assertEqual(self.client.commands, [])


if __name__ == '__main__':
    unittest.main()
