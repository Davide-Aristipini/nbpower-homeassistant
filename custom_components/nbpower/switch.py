"""Authorization and automatic load management are distinct from actual charge state."""
from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
from .entity import NBPowerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.controls_enabled:
        async_add_entities([NBPowerSwitch(coordinator, False), NBPowerSwitch(coordinator, True)])


class NBPowerSwitch(NBPowerEntity, SwitchEntity):
    def __init__(self, coordinator, automatic):
        super().__init__(coordinator, 'automatic_power_management' if automatic else 'charging_authorized')
        self.automatic = automatic
        self._attr_name = 'Automatic power management' if automatic else 'Charging authorized'
        self._attr_icon = 'mdi:home-lightning-bolt' if automatic else 'mdi:ev-station'

    @property
    def is_on(self):
        return bool(self.coordinator.runtime['automatic' if self.automatic else 'desired'])

    async def async_turn_on(self, **kwargs):
        if self.automatic:
            await self.coordinator.async_set_automatic(True)
        else:
            await self.coordinator.async_start()

    async def async_turn_off(self, **kwargs):
        if self.automatic:
            await self.coordinator.async_set_automatic(False)
        else:
            await self.coordinator.async_stop()
