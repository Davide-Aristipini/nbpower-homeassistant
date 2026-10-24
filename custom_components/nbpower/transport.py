"""Use Home Assistant's shared HTTP session, without response-body logging."""
import asyncio
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .api import APIError


def ha_transport(hass):
    session = async_get_clientsession(hass)

    async def request(url, payload):
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15),
                                    allow_redirects=False) as response:
                if response.status != 200:
                    raise APIError('HTTPS request rejected')
                data = await response.json()
                if not isinstance(data, dict):
                    raise APIError('Unexpected response type')
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            raise APIError('HTTPS request failed') from None
    return request
