"""Explicit start/stop actions; setup never invokes these actions."""
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from .entity import NBPowerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.controls_enabled:
        async_add_entities([NBPowerButton(coordinator, False), NBPowerButton(coordinator, True)])


class NBPowerButton(NBPowerEntity, ButtonEntity):
    def __init__(self, coordinator, stop):
        super().__init__(coordinator, 'stop_charging' if stop else 'start_charging')
        self.stop = stop
        self._attr_name = 'Stop charging' if stop else 'Start charging'
        self._attr_icon = 'mdi:stop-circle-outline' if stop else 'mdi:play-circle-outline'

    async def async_press(self):
        if self.stop:
            await self.coordinator.async_stop()
        else:
            await self.coordinator.async_start()

    @property
    def available(self):
        return self.stop or super().available
