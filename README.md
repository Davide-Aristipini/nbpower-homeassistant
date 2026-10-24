# NBPower for Home Assistant

Experimental custom integration for Wi-Fi NBPower EV chargers using the official
NBPower cloud. Configure your account through Home Assistant using email and a
one-time verification code.

## Current status

**Monitoring release — charging controls are not available yet.**

- Email/OTP login, charger discovery and telemetry have worked against a real
  NBPower charger reporting firmware 45.
- Signed public requests have been accepted by the official servers; a negative
  signature control was rejected.
- Installed and configured in Home Assistant **2026.8.1**: 12 entities were created,
  and changing voltage plus recent timestamps were verified in the recorder.
- Token refresh and protocol error handling have unit tests; real token expiry
  and reconnection behavior still need field testing.
- No OCPP or local Wi-Fi API is claimed for this device.

The protocol was researched from the manufacturer-linked Android app 2.0.16.
This is an independent community project, not an official NBPower integration.

## Installation

### Manual

1. Copy `custom_components/nbpower` to `/config/custom_components/nbpower`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → NBPower**.
4. Enter your NBPower email address, then the code sent by email.
5. Select the charger associated with your account.

### HACS custom repository

1. Add `https://github.com/Davide-Aristipini/nbpower-homeassistant` to HACS custom
   repositories, category **Integration**.
2. Download NBPower, restart Home Assistant and follow the configuration steps above.

HACS installation has not yet been tested. Use the manual installation if HACS
reports a validation problem, and open an issue with the sanitized error.

## Entities

| Entity | Unit / behavior |
|---|---|
| Active power | W; sum of phase meters when present |
| Current | A, first phase |
| Voltage | V, first phase |
| Temperature 1–4 | °C; unsupported channels remain unknown |
| Session energy | kWh; may retain the previous session while idle |
| Charge state | Unplugged, standby, scheduled, charging, reduced power, cooling, updating |
| Error code | Raw device code; zero means no error code reported |
| Last seen | Timestamp of cloud telemetry |
| Connection | Whether recent telemetry was retrieved and decoded successfully |

Polling runs every 15 seconds. Heartbeats older than 120 seconds are rejected
instead of being displayed as current measurements. Cloud update frequency may
differ from the polling frequency.

Session energy does not have a statistics state class: reset semantics have not
been validated. It is not yet offered as a reliable Energy Dashboard counter.
There is no verified charger lifetime-energy entity in this release.

## Authentication and privacy

The OTP is used in memory and is not stored by the integration. Home Assistant
stores access/refresh tokens in its normal config-entry storage. Keep HA storage
and backups private. The client does not log response bodies, email codes,
passwords, tokens or session cookies.

For a command-line test without installing dependencies:

```console
python scripts/probe_cloud.py
```

Enter credentials interactively. Tokens are not saved by this script. Never
include credentials in command-line arguments, issue reports or screenshots.

## Solar-surplus charging roadmap

Solar-aware charging is a project goal, **not a feature of this monitoring release**.
It requires validated start/stop and current-limit commands, actual electrical
limits, grid import/export measurements and charge-session semantics.

Planned automation behavior includes bounded current regulation, start/stop
hysteresis, protection against stale measurements, and explicit treatment of
house batteries and grid import. Automations must not change the charger's
hardware protection settings or exceed the installation/cable limits.

## Development and diagnostics

```console
python -m unittest discover -s tests -v
python -m compileall -q custom_components scripts tests
node tests/signature_reference.js
python scripts/build_release.py
python scripts/network_diagnostics.py --host CHARGER_PRIVATE_IP
python scripts/discover_ha.py HOME_ASSISTANT_PRIVATE_IP
python scripts/probe_cloud.py --discover
```

`build_release.py` creates a clean integration ZIP in `dist/`. Python protocol
tests use synthetic fixtures, not account captures. The Node reference is an
independent signature oracle; Node is not needed for the integration or Python tests.

Additional research scripts inspect public web assets and the official APK.
Generated reports, downloaded source resources, captures and private deployment
notes are excluded from Git. Do not publish them without reviewing their contents.

See [protocol notes](docs/PROTOCOL.md) and [FRITZ!Box capture instructions](docs/CAPTURE.md).

## Reporting issues

Include the Home Assistant version, integration version, firmware family, and a
sanitized error description. Do not attach `.storage` files, access tokens, OTPs,
full HTTP responses, account details or unreviewed packet captures.

## License

MIT. See [LICENSE](LICENSE).
