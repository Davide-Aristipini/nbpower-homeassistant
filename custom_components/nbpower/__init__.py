"""NBPower cloud telemetry integration."""
from .const import DOMAIN, PLATFORMS
from .coordinator import NBPowerCoordinator


async def _options_updated(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and dict(entry.options) != coordinator.settings:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass, entry):
    coordinator = NBPowerCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    coordinator.ready = True
    coordinator.schedule_management()
    return True


async def async_unload_entry(hass, entry):
    await hass.data[DOMAIN][entry.entry_id].async_shutdown()
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
