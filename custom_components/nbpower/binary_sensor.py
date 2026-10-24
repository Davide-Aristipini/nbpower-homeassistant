"""Connection is true only when a recent heartbeat has been validated."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import NBPowerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NBPowerConnection(hass.data[DOMAIN][entry.entry_id])])


class NBPowerConnection(NBPowerEntity, BinarySensorEntity):
    _attr_name = 'Connection'
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator, 'connection')

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.last_update_success
