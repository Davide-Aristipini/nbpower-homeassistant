"""Sensors mapped only to evidenced heartbeat fields."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfPower, UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfTemperature, UnitOfEnergy
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import NBPowerEntity

DESCRIPTIONS = [
    ('power', 'Power', UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    ('current', 'Current (phase 1)', UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT, SensorStateClass.MEASUREMENT),
    ('voltage', 'Voltage (phase 1)', UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE, SensorStateClass.MEASUREMENT),
    ('temperature', 'Temperature 1', UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ('temperature_2', 'Temperature 2', UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ('temperature_3', 'Temperature 3', UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ('temperature_4', 'Temperature 4', UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    ('session_energy', 'Session energy', UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, None),
    ('state', 'Charge state', None, None, None),
    ('error_code', 'Error code', None, None, None),
    ('last_seen', 'Last seen', None, SensorDeviceClass.TIMESTAMP, None),
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NBPowerSensor(coordinator, *description) for description in DESCRIPTIONS])


class NBPowerSensor(NBPowerEntity, SensorEntity):
    def __init__(self, coordinator, key, name, unit, device_class, state_class):
        super().__init__(coordinator, key)
        self.key = key
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        if key in ('error_code', 'last_seen'):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self.coordinator.data.get(self.key)
