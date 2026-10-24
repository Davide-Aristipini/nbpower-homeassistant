# Charge-control development

The `feature/charge-control` branch now contains the v0.2.0b1 opt-in controller
and HA button/number/switch entities. v0.1.0 remains monitoring-only.
Controls are disabled unless explicitly enabled and configured.

## Verified reads

Official cloud CMD 1 and CMD 47 reads have succeeded on a charger reporting
firmware 45, device_num 15, one meter, a 32 A hardware maximum and run_mode 1.
These are model/configuration observations, not permission to use 32 A on any
installation. Run-mode behavior during remote control has not been field-tested.

The cloud rewrites request IDs: a request with req_id=1 returned a different
req_id. Command responses are therefore checked for byte validity, declared
length and command number; the HTTP response correlates the command request.

## Implemented backend

- Allowlisted read-only commands: 1 (version), 47 (configuration), 69 (timer).
- Serialized challenge CMD 66 followed by charge-session CMD 67.
- Explicit finite session start, current update of a session owned by the
  controller, and stop using minutes=0.
- Current changes do not advance the controller's original session deadline.
- Automatic adoption of sessions after a process restart is rejected.
- No retries of uncertain command transport failures.
- No hardware protection or configuration writes.

## Limits

`ChargingPolicy` requires explicit maximum current, power and voltage ceiling.
It limits current to the lowest of the installation policy, the read hardware
limit and `maximum_power / voltage_ceiling`. PWM is rounded down rather than up.

For example, with a 5,000 W budget and a 253 V ceiling, 19.5 A is an accepted
request while 20 A is rejected. This is an electrical operating-envelope bound,
not proof of a hardware-enforced instantaneous power limit. Measurements above
the configured ceiling and stale telemetry are rejected before start/update.
The source of all limits must be verified for each installation.

## Tests and remaining validation

36 protocol/client/controller/budget tests pass locally. Tests cover power/current
bounds, unknown limits, stale data, finite duration, rejected commands, response
correlation, and start/update/stop sequencing with a simulated transport.

Real single-phase firmware-45/device-15 tests have now verified active 6 A / 8 A
changes, return to 6 A, zero-power standby after stop, and finite-session restart.
Only the maximum-current byte was changed during an owner-authorized hardware
reduction; all other configuration bytes were preserved and reread.

The official active update uses the marker authentication bytes shown in the app,
only after explicit adoption of a running session. Idle starts still use CMD 66.
Stops may return a short reply; a transport timeout does not prove rejection.
The controller confirms the intended state/limit/timer without resending the write.

The firmware/cloud can update PWM before the meter cache (about twenty seconds
observed). Direct CMD 8 meter reads and a short override prevent the next poll
from replacing fresher measurements with the old cloud cache.

See README for required energy sensors, sign conventions and automatic budgets.
Other hardware variants and three-phase/DC controls remain unverified/unsupported.
