# Charge-control development

The `feature/charge-control` branch contains a development backend in
`custom_components/nbpower/control.py`. It is **not wired into Home Assistant
entities, startup, polling or automations**. The published v0.1.0 monitoring
release does not contain this backend.

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

22 protocol/client/controller tests pass locally. Tests cover power/current
bounds, unknown limits, stale data, finite duration, rejected commands, response
correlation, and start/update/stop sequencing with a simulated transport.

**No real start, current change or stop has been performed.** A physical test
was deferred because the vehicle was fully charged. Owner consent and a vehicle
ready to accept charge are required before invoking these methods on hardware.

Next steps are physical command validation, observation of run_mode behavior,
Home Assistant options and control entities, then solar-surplus automations.
No unattended charging automation should be based on this development backend
before these checks are completed.
