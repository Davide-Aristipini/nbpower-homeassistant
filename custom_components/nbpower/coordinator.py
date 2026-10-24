"""Poll validated, timestamped telemetry and refresh account sessions."""
from datetime import timedelta
import logging
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .api import APIError, AuthenticationError, NBPowerClient, telemetry
from .const import DOMAIN
from .transport import ha_transport


class NBPowerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logging.getLogger(__name__), name=DOMAIN,
                         update_interval=timedelta(seconds=15), config_entry=entry)
        self.entry = entry
        self.client = NBPowerClient(ha_transport(hass), access_token=entry.data['access_token'],
                                   refresh_token=entry.data.get('refresh_token'),
                                   user_server=entry.data['user_server'], on_tokens=self.save_tokens)

    def save_tokens(self, access, refresh, server):
        self.hass.config_entries.async_update_entry(self.entry, data={**self.entry.data,
            'access_token': access, 'refresh_token': refresh, 'user_server': server})

    async def _async_update_data(self):
        try:
            return telemetry(await self.client.status(self.entry.data['imei']))
        except AuthenticationError:
            raise ConfigEntryAuthFailed('NBPower login required') from None
        except APIError as error:
            raise UpdateFailed(str(error)) from None
