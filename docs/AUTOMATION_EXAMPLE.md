# Optional fast guards

The integration performs periodic management. A site can also add a fast
re-evaluation rule for grid/headroom changes. Replace all example entity IDs and
thresholds with the actual installation values. Do not trigger an overload for testing.

```yaml
alias: EV fast grid guard
mode: single
max_exceeded: silent
triggers:
  - trigger: numeric_state
    entity_id: sensor.example_grid_power
    above: 5700
    for: "00:00:03"
conditions:
  - condition: state
    entity_id: switch.example_automatic_power_management
    state: "on"
  - condition: state
    entity_id: switch.example_charging_authorized
    state: "on"
  - condition: template
    value_template: "{{ is_number(states('number.example_maximum_charging_current')) }}"
actions:
  - action: number.set_value
    target:
      entity_id: number.example_maximum_charging_current
    data:
      value: "{{ states('number.example_maximum_charging_current') | float(6) }}"
  - delay: "00:00:30"
```

Setting the existing ceiling to itself requests an immediate recalculation of
the current energy budget without changing the user's limit. Insufficient room
causes a managed pause, retaining charging authorization for later recovery.

For a vehicle integration, also stop charging authorization when **fresh** vehicle
telemetry confirms the configured target is reached. Use the NBPower stop button
for that action. This prevents attempts to restart a full vehicle after its cloud
frame becomes old. Check both the vehicle frame age and the telemetry publisher's
last-seen time; a cached SOC by itself is not a completion event.

These are software/cloud controls with observable latency. The installation's
electrical protection remains authoritative.
