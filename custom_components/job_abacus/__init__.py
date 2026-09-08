"""Integrace Job Abacus Pro WEB Client pro Home Assistant."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import (
    JobAbacusAuthError,
    JobAbacusClient,
    JobAbacusError,
    create_cookie_jar,
)
from .const import CONF_BASE_URL
from .coordinator import JobAbacusConfigEntry, JobAbacusCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: JobAbacusConfigEntry) -> bool:
    """Nastaví integraci z config entry."""
    # Vlastní session, protože sdílená zahazuje cookie z IP adresy.
    client = JobAbacusClient(
        async_create_clientsession(hass, cookie_jar=create_cookie_jar()),
        entry.data[CONF_BASE_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    try:
        await client.async_login()
    except JobAbacusAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except JobAbacusError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = JobAbacusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: JobAbacusConfigEntry
) -> bool:
    """Odstraní integraci."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
