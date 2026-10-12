"""Klient Job Abacus Pro WEB Client.

Web klient je PHP aplikace bez veřejného API. Přihlašuje se formulářem
(`login.php?Act=Validate`, pole `Login` a `Pwd`), session drží v cookie
`PHPSESSID` a všechny odpovědi posílá v kódování windows-1250.

Klient potřebuje vlastní session, viz `async_create_session`. Instalace
běžně stojí na holé IP adrese a výchozí cookie jar aiohttpu takové cookie
zahazuje, takže by přihlášení mlčky nedrželo.

Novější instalace mají navíc endpoint `api.php`, který vrací JSON. Klient ho
zkusí jako první, protože JSON je stabilnější než HTML, a když nic nevrátí,
sáhne po stránkách web klienta.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import aiohttp
from yarl import URL

from .const import PAGE_ENCODING
from .parser import parse_week_grid

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

FORM_CONTENT_TYPE = f"application/x-www-form-urlencoded; charset={PAGE_ENCODING}"

# Stránky, na kterých se jídelníček hledá, v pořadí, v jakém se zkoušejí.
MENU_PAGES = ("index.php",)

API_PAGE = "api.php"
API_ACTIONS = ("Menu", "Strava", "Food", "")

# Strop na počet detailů dne, aby se server nezaplavil, kdyby mřížka
# vrátila nesmyslně mnoho odkazů. Týden má sedm dnů a pár chodů.
MAX_DETAIL_PAGES = 20


@dataclass(frozen=True)
class MenuSources:
    """Podklady jídelníčku posbírané ze serveru.

    Kterákoli část může být prázdná; parser si vybere, z čeho jídelníček
    přečte.
    """

    api_payload: Any = None
    grid_html: str | None = None
    detail_pages: list[str] = field(default_factory=list)


def create_cookie_jar() -> aiohttp.CookieJar:
    """Vytvoří cookie jar, který přijme i cookie z holé IP adresy.

    Job Abacus bývá vystavený jako `http://<ip>:<port>` a výchozí jar
    aiohttpu takové cookie podle RFC 2109 zahodí. Přihlášení by pak
    prošlo, ale `PHPSESSID` by se neuložila a další požadavek by zase
    skončil na přihlašovacím formuláři.
    """
    return aiohttp.CookieJar(unsafe=True)


class JobAbacusError(Exception):
    """Obecná chyba komunikace s Job Abacusem."""


class JobAbacusAuthError(JobAbacusError):
    """Přihlášení bylo odmítnuto nebo session vypršela."""


class JobAbacusClient:
    """Drží přihlášenou session k web klientovi."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        """Uloží údaje bez připojení k serveru."""
        self._session = session
        self._base_url = base_url.rstrip("/") + "/"
        self._username = username
        self._password = password
        self._logged_in = False
        # Co se osvědčilo při prvním čtení, aby se dál nezkoušely všechny URL.
        self._api_action: str | None = None
        self._api_unavailable = False
        self._menu_page: str | None = None

    @property
    def base_url(self) -> str:
        """Vrátí základní URL web klienta."""
        return self._base_url

    def _url(self, path: str) -> URL:
        """Sestaví absolutní URL v rámci web klienta."""
        return URL(self._base_url).join(URL(path))

    @staticmethod
    def _looks_like_login_page(html: str) -> bool:
        """Rozhodne, jestli server vrátil přihlašovací formulář."""
        return 'name="Pwd"' in html or 'name="Login"' in html

    async def _read(self, response: aiohttp.ClientResponse) -> str:
        """Přečte odpověď v kódování, které web klient deklaruje."""
        raw = await response.read()
        return raw.decode(PAGE_ENCODING, errors="replace")

    def _encode_form(self, fields: dict[str, str]) -> bytes:
        """Zakóduje formulář do windows-1250, jak čeká web klient.

        Výchozí UTF-8 z aiohttpu server nepřijme: jméno s diakritikou
        (například `Král`) pak odmítne jako neplatné.
        """
        return urlencode(fields, encoding=PAGE_ENCODING).encode("ascii")

    async def async_login(self) -> None:
        """Přihlásí se přihlašovacím formulářem."""
        self._logged_in = False
        try:
            response = await self._session.post(
                self._url("login.php").with_query({"Act": "Validate"}),
                data=self._encode_form(
                    {"Login": self._username, "Pwd": self._password}
                ),
                headers={"Content-Type": FORM_CONTENT_TYPE},
                timeout=REQUEST_TIMEOUT,
            )
            html = await self._read(response)
        except aiohttp.ClientError as err:
            raise JobAbacusError(f"Nepodařilo se spojit se serverem: {err}") from err

        if response.status != 200:
            raise JobAbacusError(f"Přihlášení vrátilo HTTP {response.status}")

        if self._looks_like_login_page(html):
            raise JobAbacusAuthError("Neplatné uživatelské jméno nebo heslo")

        self._logged_in = True
        # S novou session může api.php začít odpovídat, i když dřív nešlo.
        self._api_unavailable = False
        self._api_action = None

    async def _async_ensure_login(self) -> None:
        """Přihlásí se, pokud ještě není navázaná session."""
        if not self._logged_in:
            await self.async_login()

    async def _async_get(
        self, path: str, params: dict[str, str] | None = None
    ) -> tuple[int, str]:
        """Načte stránku a vrátí `(HTTP status, text)`."""
        url = self._url(path)
        if params:
            url = url.with_query(params)

        try:
            response = await self._session.get(url, timeout=REQUEST_TIMEOUT)
            return response.status, await self._read(response)
        except aiohttp.ClientError as err:
            raise JobAbacusError(f"Chyba požadavku na {path}: {err}") from err

    async def async_fetch_menu_sources(self) -> MenuSources:
        """Posbírá zdroje jídelníčku.

        Při vypršené session se jednou znovu přihlásí.
        """
        await self._async_ensure_login()

        try:
            return await self._async_fetch_sources()
        except JobAbacusAuthError:
            _LOGGER.debug("Session Job Abacusu vypršela, přihlašuji se znovu")
            await self.async_login()
            return await self._async_fetch_sources()

    async def _async_fetch_sources(self) -> MenuSources:
        """Posbírá data z API i ze stránek aktuální session."""
        api_payload = await self._async_fetch_api()
        grid_html = await self._async_fetch_menu_html()

        if api_payload is None and grid_html is None:
            raise JobAbacusError(
                "Server nevrátil jídelníček ani přes api.php, ani přes stránky"
            )

        # Mřížka obsahuje jen stavy dnů, názvy jídel jsou až v detailech.
        details = (
            await self._async_fetch_details(grid_html) if grid_html is not None else []
        )

        return MenuSources(api_payload, grid_html, details)

    async def _async_fetch_details(self, grid_html: str) -> list[str]:
        """Dotáhne detail ke každému dni, na který mřížka odkazuje."""
        page = self._menu_page or MENU_PAGES[0]
        menu_ids = sorted(
            {
                offer.menu_id
                for offer in parse_week_grid(grid_html)
                if offer.menu_id is not None
            }
        )

        if not menu_ids:
            _LOGGER.debug("Mřížka neodkazuje na žádný detail dne")
            return []

        details: list[str] = []
        for menu_id in menu_ids[:MAX_DETAIL_PAGES]:
            status, html = await self._async_get(
                page, {"ShowAlerg": "0", "ShowMenu": str(menu_id)}
            )
            if status != 200 or not html.strip():
                continue
            if self._looks_like_login_page(html):
                raise JobAbacusAuthError(f"{page} vrátil přihlašovací formulář")
            details.append(html)

        return details

    async def _async_fetch_api(self) -> Any:
        """Zkusí přečíst jídelníček z `api.php`."""
        if self._api_unavailable:
            return None

        actions = (
            [self._api_action] if self._api_action is not None else list(API_ACTIONS)
        )

        for action in actions:
            params = {"Act": action} if action else None
            status, text = await self._async_get(API_PAGE, params)

            if status != 200 or not text.strip():
                continue

            try:
                payload = json.loads(text)
            except ValueError:
                _LOGGER.debug("api.php (Act=%s) nevrátil JSON", action or "-")
                continue

            # Status 3 znamená nepřihlášenou session. Na některých instalacích
            # api.php session z formuláře nepřijímá vůbec, proto se to nebere
            # jako chyba přihlášení - o tom rozhodne až čtení stránek.
            if isinstance(payload, dict) and payload.get("Status") == 3:
                _LOGGER.debug("api.php hlásí Status 3, zkusím stránky")
                self._api_unavailable = True
                return None

            self._api_action = action
            return payload

        self._api_unavailable = True
        return None

    async def _async_fetch_menu_html(self) -> str | None:
        """Zkusí najít stránku s jídelníčkem."""
        pages = [self._menu_page] if self._menu_page else list(MENU_PAGES)

        for page in pages:
            status, html = await self._async_get(page)

            if status != 200 or not html.strip():
                continue
            if self._looks_like_login_page(html):
                raise JobAbacusAuthError(f"{page} vrátil přihlašovací formulář")

            self._menu_page = page
            return html

        return None
