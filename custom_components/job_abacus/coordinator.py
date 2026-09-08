"""Koordinátor stahování jídelníčku z Job Abacus Pro."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import JobAbacusAuthError, JobAbacusClient, JobAbacusError
from .const import DEFAULT_SUMMARY_MODE, DOMAIN, OPT_SUMMARY_MODE, UPDATE_INTERVAL
from .parser import LunchDay, build_lunch_days, parse_menu

_LOGGER = logging.getLogger(__name__)

type JobAbacusConfigEntry = ConfigEntry[JobAbacusCoordinator]


class JobAbacusCoordinator(DataUpdateCoordinator[list[LunchDay]]):
    """Stahuje jídelníček a připravuje ho pro kalendářovou entitu."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: JobAbacusConfigEntry,
        client: JobAbacusClient,
    ) -> None:
        """Inicializuje koordinátor."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self.client = client

    @property
    def summary_mode(self) -> str:
        """Vrátí zvolený režim názvu události."""
        assert self.config_entry is not None
        return self.config_entry.options.get(OPT_SUMMARY_MODE, DEFAULT_SUMMARY_MODE)

    async def _async_update_data(self) -> list[LunchDay]:
        """Načte jídelníček z API nebo ze stránek web klienta."""
        try:
            sources = await self.client.async_fetch_menu_sources()
        except JobAbacusAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except JobAbacusError as err:
            raise UpdateFailed(str(err)) from err

        # Stránka jídelníčku uvádí u některých dnů datum bez roku.
        menu = parse_menu(
            sources.api_payload,
            sources.grid_html,
            sources.detail_pages,
            dt_util.now().year,
        )
        lunch_days = build_lunch_days(menu, self.summary_mode)

        if not lunch_days:
            raise UpdateFailed(
                "V odpovědi serveru se nepodařilo najít žádný jídelníček"
            )

        _LOGGER.debug("Načteno %d dnů jídelníčku", len(lunch_days))
        return lunch_days
