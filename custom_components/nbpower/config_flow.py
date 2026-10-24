"""Email / OTP login. OTP is used in memory and never saved in config data."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NBPowerOptionsFlow(config_entry)

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


class NBPowerOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title='', data={**self.entry.options, **user_input})
        old = self.entry.options
        fields = {
            vol.Optional('enable_controls', default=old.get('enable_controls', False)): bool,
            vol.Optional('max_current_a', default=old.get('max_current_a', 6)): vol.All(vol.Coerce(float), vol.Range(min=6,max=32)),
            vol.Optional('max_power_w', default=old.get('max_power_w', 5000)): vol.All(vol.Coerce(float), vol.Range(min=1400,max=22000)),
            vol.Optional('grid_limit_w', default=old.get('grid_limit_w', 6000)): vol.All(vol.Coerce(float), vol.Range(min=2000,max=50000)),
            vol.Optional('grid_reserve_w', default=old.get('grid_reserve_w', 300)): vol.All(vol.Coerce(float), vol.Range(min=0,max=3000)),
            vol.Optional('battery_limit_w', default=old.get('battery_limit_w', 2000)): vol.All(vol.Coerce(float), vol.Range(min=0,max=22000)),
            vol.Optional('session_minutes', default=old.get('session_minutes', 480)): vol.All(vol.Coerce(int), vol.Range(min=1,max=1440)),
        }
        for key in ('house_power_entity','grid_power_entity','pv_power_entity','battery_power_entity','losses_power_entity',
                    'car_soc_entity','car_target_soc_entity','car_data_age_entity'):
            fields[vol.Optional(key,default=old.get(key,''))] = str
        return self.async_show_form(step_id='init',data_schema=vol.Schema(fields))
