"""Konfigurační dialog integrace Job Abacus Pro."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import (
    JobAbacusAuthError,
    JobAbacusClient,
    JobAbacusError,
    create_cookie_jar,
)
from .const import (
    CONF_BASE_URL,
    DEFAULT_SUMMARY_MODE,
    DOMAIN,
    OPT_SUMMARY_MODE,
    SUMMARY_MODES,
)
from .coordinator import JobAbacusConfigEntry
from .parser import parse_menu

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BASE_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class JobAbacusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Průvodce přidáním účtu Job Abacus Pro."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: JobAbacusConfigEntry) -> OptionsFlow:
        """Vrátí dialog nastavení."""
        return JobAbacusOptionsFlow()

    async def _async_validate(
        self, base_url: str, username: str, password: str
    ) -> bool:
        """Zkusí se přihlásit a načíst jídelníček.

        Vrátí False, když přihlášení projde, ale jídelníček se přečíst
        nepodaří; jinak by účet vznikl s trvale prázdným kalendářem.
        """
        # Session s vlastní cookie jar, jinak se `PHPSESSID` z IP adresy zahodí.
        session = async_create_clientsession(self.hass, cookie_jar=create_cookie_jar())
        client = JobAbacusClient(session, base_url, username, password)
        try:
            await client.async_login()
            sources = await client.async_fetch_menu_sources()
        finally:
            session.detach()

        return bool(
            parse_menu(
                sources.api_payload,
                sources.grid_html,
                sources.detail_pages,
                dt_util.now().year,
            )
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zpracuje ruční přidání účtu."""
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip()
            username = user_input[CONF_USERNAME].strip()

            parsed = urlparse(base_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                errors[CONF_BASE_URL] = "invalid_url"
            else:
                try:
                    has_menu = await self._async_validate(
                        base_url, username, user_input[CONF_PASSWORD]
                    )
                except JobAbacusAuthError:
                    errors["base"] = "invalid_auth"
                except JobAbacusError:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001 - jinak spadne UI
                    _LOGGER.exception("Neočekávaná chyba při přihlášení")
                    errors["base"] = "unknown"
                else:
                    if not has_menu:
                        errors["base"] = "no_menu"
                    else:
                        await self.async_set_unique_id(
                            f"{parsed.netloc}_{username}".lower()
                        )
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"{username} ({parsed.hostname})",
                            data={
                                CONF_BASE_URL: base_url,
                                CONF_USERNAME: username,
                                CONF_PASSWORD: user_input[CONF_PASSWORD],
                            },
                        )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Spustí opětovné přihlášení po vypršení údajů."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Vyžádá nové heslo ke stávajícímu účtu."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                await self._async_validate(
                    entry.data[CONF_BASE_URL],
                    entry.data[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except JobAbacusAuthError:
                errors["base"] = "invalid_auth"
            except JobAbacusError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Neočekávaná chyba při opětovném přihlášení")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )


class JobAbacusOptionsFlow(OptionsFlowWithReload):
    """Nastavení zobrazení jídelníčku."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Uloží volby zobrazení."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    OPT_SUMMARY_MODE,
                    default=self.config_entry.options.get(
                        OPT_SUMMARY_MODE, DEFAULT_SUMMARY_MODE
                    ),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=SUMMARY_MODES,
                        translation_key=OPT_SUMMARY_MODE,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
