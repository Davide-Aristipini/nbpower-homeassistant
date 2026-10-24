"""User ceiling; automatic management may apply a lower limit."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfElectricCurrent
from .const import DOMAIN
from .entity import NBPowerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.controls_enabled:
        async_add_entities([NBPowerCurrentCeiling(coordinator)])


class NBPowerCurrentCeiling(NBPowerEntity, NumberEntity):
    _attr_name = 'Maximum charging current'
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_native_min_value = 6
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator):
        super().__init__(coordinator, 'maximum_charging_current')
        self._attr_native_max_value = min(float(coordinator.settings.get('max_current_a', 6)),
                                          float(coordinator.settings.get('max_power_w', 5000))/253)

    @property
    def native_value(self):
        return self.coordinator.runtime['max_current']

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_ceiling(value)
