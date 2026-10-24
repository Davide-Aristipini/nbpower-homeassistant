"""Email / OTP login. OTP is used in memory and never saved in config data."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .api import APIError, AuthenticationError, NBPowerClient
from .const import DOMAIN
from .transport import ha_transport


class NBPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.client = None
        self.email = None
        self.chargers = []
        self.reauth_entry = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.email = user_input['email'].strip()
            if '@' not in self.email:
                errors['base'] = 'invalid_email'
            else:
                self.client = NBPowerClient(ha_transport(self.hass))
                try:
                    await self.client.request_otp(self.email)
                    return await self.async_step_otp()
                except APIError:
                    errors['base'] = 'cannot_connect'
        return self.async_show_form(step_id='user', data_schema=vol.Schema({vol.Required('email'): str}), errors=errors)

    async def async_step_otp(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                await self.client.login(self.email, user_input['otp'])
                self.chargers = await self.client.chargers()
                if not self.chargers:
                    return self.async_abort(reason='no_chargers')
                return await self.async_step_charger()
            except AuthenticationError:
                errors['base'] = 'invalid_auth'
            except APIError:
                errors['base'] = 'cannot_connect'
        return self.async_show_form(step_id='otp', errors=errors, data_schema=vol.Schema({
            vol.Required('otp'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}))

    async def async_step_charger(self, user_input=None):
        errors = {}
        if user_input is not None:
            imei = user_input['charger']
            charger = next((c for c in self.chargers if str(c['imei']) == imei), None)
            if charger is None:
                return self.async_abort(reason='unknown')
            if self.reauth_entry and self.reauth_entry.data['imei'] != imei:
                errors['base'] = 'wrong_charger'
            else:
                data = {'email': self.email, 'imei': imei,
                        'access_token': self.client.access_token,
                        'refresh_token': self.client.refresh_token,
                        'user_server': self.client.user_server}
                if self.reauth_entry:
                    self.hass.config_entries.async_update_entry(self.reauth_entry, data=data)
                    await self.hass.config_entries.async_reload(self.reauth_entry.entry_id)
                    return self.async_abort(reason='reauth_successful')
                await self.async_set_unique_id(imei)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=str(charger.get('mac') or 'NBPower'), data=data)
        choices = {str(c['imei']): str(c.get('mac') or f'NBPower {index+1}') for index, c in enumerate(self.chargers)}
        return self.async_show_form(step_id='charger', errors=errors,
                                    data_schema=vol.Schema({vol.Required('charger'): vol.In(choices)}))

    async def async_step_reauth(self, entry_data):
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context['entry_id'])
        return await self.async_step_user()
