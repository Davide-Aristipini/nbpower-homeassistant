"""Shared device identity and availability."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN


class NBPowerEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.data['imei']}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.data['imei'])},
            name=coordinator.entry.title, manufacturer='NBPower',
            sw_version=str(coordinator.data.get('firmware', 'unknown')))
