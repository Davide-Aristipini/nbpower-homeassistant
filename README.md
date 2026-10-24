# NBPower for Home Assistant

Experimental custom integration for Wi-Fi NBPower EV chargers using the official
NBPower cloud. Configure your account through Home Assistant using email and a
one-time verification code.

## Current status

**v0.2.0b1 — experimental monitoring, opt-in controls and power management.**

- Email/OTP login, charger discovery and telemetry have worked against a real
  NBPower charger reporting firmware 45.
- Signed public requests have been accepted by the official servers; a negative
  signature control was rejected.
- Installed and configured in Home Assistant **2026.8.1**. Readings, start/stop,
  active current changes and automatic charging have been field-tested on a
  **single-phase AC charger, firmware 45, device_num 15, one meter**.
- Physical tests changed the requested current from 6 A to 8 A, back to 6 A,
  confirmed zero-power standby after stop, and resumed finite-duration charging.
- Controls remain **disabled by default**. Three-phase/DC control is not supported.
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

When verified controls are enabled in the integration options, additional entities
provide start/stop buttons, charging authorization, an automatic-management switch,
a user current ceiling, the advertised limit, budget/current targets and control status.

Charging authorization is permission to charge; it is not a claim that the vehicle
is drawing energy. Use charge state and measured power for actual charging.

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

## Opt-in controls and power management

Open the integration options and configure verified installation limits and these
power sensors (W or kW):

- Total house load **including the EV charger**.
- Signed grid power: positive import, negative export.
- PV generation.
- Signed home-battery power: positive discharge, negative charge.
- Optional inverter losses and fresh vehicle SOC/target/age entities.

This beta requires these energy inputs for its control workflow. Enable the
automatic-management switch after configuration. A user stop clears charging
authorization, so normal load management does not immediately restart it.

The manager charges when there is headroom, including from the grid. It caps the
car's use of a discharging home battery, allows solar surplus in addition, and
reduces/pauses charging when the configured grid/house allowance is exhausted.
It does not force 6 A when there is insufficient room for the minimum current.
Increases are gradual; commands are serialized and have a cooldown.

Defaults are conservative examples, **not installation limits inferred for your
home**. Set the current/power/grid/battery limits for your own equipment.
Controls are limited to the verified single-meter AC protocol. The implementation
uses a 253 V upper operating envelope for current-to-power bounds.

Sessions have a finite configured duration (default eight hours). Active-session
takeover is explicit, uses the official app's update path and preserves the
authorized end time. No protection settings are written automatically on setup.

These are cloud controls, not instantaneous electrical protection. The device may
acknowledge a new PWM limit before cached power updates. The client reads the
device meter after commands and confirms outcomes from fresh telemetry rather
than blindly retrying uncertain writes. Actual vehicle draw can be below the limit.

The v0.1.0 monitoring-only prerelease remains available for installations that do
not need the experimental controls.

See [optional fast guards and vehicle-completion handling](docs/AUTOMATION_EXAMPLE.md)
for an installation-level automation example.

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
