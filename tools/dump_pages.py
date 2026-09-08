#!/usr/bin/env python3
"""Discovery skript pro Job Abacus Pro WEB Client.

Každá instalace Job Abacusu má trochu jinou sadu stránek, a co je za
přihlášením, se z venku zjistit nedá. Skript se proto přihlásí, uloží HTML
stránek a osloví JSON endpoint `api.php`, aby bylo podle čeho napsat parser
jídelníčku.

Co se o serveru ví předem (zjištěno bez přihlášení):

* `login.php` – přihlašovací formulář, POST na `login.php?Act=Validate`
  s poli `Login` a `Pwd`, kódování windows-1250, session v cookie `PHPSESSID`.
* `index.php` – po nepřihlášeném přístupu přesměruje na `login.php`.
* `api.php` – vrací JSON `{"GACC_JAP_JSON_CONTENT":"4","Status":3,...}`.
  `Status: 3` znamená nepřihlášeno; kontrola proběhne dřív než čtení
  parametrů, takže skutečné parametry jde zjistit až se session.
* `strava.php` – chráněno HTTP Basic auth, jiný mechanismus než formulář.

Skript pouze čte. Jediný zápis je přihlašovací POST; odkazy a parametry, které
by mohly něco uložit, objednat nebo odhlásit, se přeskakují.

Použití:

    export ABACUS_URL="http://server:port"
    export ABACUS_USER="jmeno"
    export ABACUS_PASS="heslo"
    python3 tools/dump_pages.py --out /tmp/abacus

Heslo se nikam neukládá a ve výstupu se neobjeví. Vygenerované soubory ale
obsahují osobní údaje, proto je výchozí cíl `/tmp`, a ne repozitář.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_OUT = Path("/tmp/abacus")
ENCODING = "windows-1250"
TIMEOUT = 30

# Stránky, o kterých víme, že na serveru existují, plus obvyklé varianty.
SEED_PAGES = ["index.php", "strava.php"]

# Hodnoty `Act`, které se u api.php vyzkoušejí. Čtení jídelníčku a objednávek
# bývá pod některým z těchto názvů.
API_ACTIONS = [
    "",
    "Menu",
    "Food",
    "Strava",
    "Jidelnicek",
    "Orders",
    "Order",
    "Objednavky",
    "Transactions",
    "Account",
    "Balance",
    "User",
    "Info",
    "Status",
    "List",
]

# Nic, co by mohlo změnit stav nebo ukončit session.
SKIP_PATTERN = re.compile(
    r"(logout|odhlas|Act=(Logout|Save|Order|Insert|Update|Delete|Validate))",
    re.IGNORECASE,
)


class LinkCollector(HTMLParser):
    """Vybere hodnoty `href` a `action` ze stránky."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        wanted = {"a": "href", "form": "action", "frame": "src", "iframe": "src"}
        if (attribute := wanted.get(tag)) is None:
            return
        for name, value in attrs:
            if name == attribute and value:
                self.links.append(value)


def decode(response: requests.Response) -> str:
    """Dekóduje odpověď jako windows-1250, jak Job Abacus deklaruje."""
    return response.content.decode(ENCODING, errors="replace")


def safe_name(url: str) -> str:
    """Vyrobí z URL použitelné jméno souboru."""
    parsed = urlparse(url)
    name = f"{parsed.path.lstrip('/')}_{parsed.query}".strip("_")
    name = re.sub(r"[^A-Za-z0-9._=-]+", "_", name) or "index"
    return f"{name[:120]}.html"


def login(session: requests.Session, base_url: str, user: str, password: str) -> str:
    """Přihlásí se a vrátí HTML první stránky po přihlášení."""
    login_url = urljoin(base_url, "login.php?Act=Validate")
    response = session.post(
        login_url, data={"Login": user, "Pwd": password}, timeout=TIMEOUT
    )
    response.raise_for_status()
    html = decode(response)

    # Web klient po neúspěchu znovu zobrazí přihlašovací formulář.
    if 'name="Pwd"' in html:
        raise SystemExit(
            "Přihlášení selhalo: server vrátil znovu přihlašovací formulář. "
            "Zkontroluj ABACUS_USER a ABACUS_PASS."
        )

    return html


def dump_html(
    session: requests.Session, base_url: str, out: Path, start_html: str, depth: int
) -> int:
    """Projde odkazy a uloží HTML stránek."""
    collector = LinkCollector()
    collector.feed(start_html)

    queue = [(urljoin(base_url, link), 1) for link in collector.links]
    queue += [(urljoin(base_url, page), 1) for page in SEED_PAGES]

    seen: set[str] = set()
    saved = 0

    while queue:
        url, level = queue.pop(0)
        if url in seen or level > depth:
            continue
        seen.add(url)

        if not url.startswith(base_url) or SKIP_PATTERN.search(url):
            continue

        try:
            response = session.get(url, timeout=TIMEOUT)
        except requests.RequestException as err:
            print(f"  chyba {url}: {err}")
            continue

        if response.status_code != 200:
            print(f"  HTTP {response.status_code}: {url}")
            continue

        html = decode(response)
        target = out / safe_name(url)
        target.write_text(html, encoding="utf-8")
        saved += 1
        print(f"  uloženo {target.name} ({len(html)} znaků) <- {url}")

        if level < depth:
            child = LinkCollector()
            child.feed(html)
            queue += [(urljoin(url, link), level + 1) for link in child.links]

    return saved


def dump_api(session: requests.Session, base_url: str, out: Path) -> None:
    """Osloví `api.php` se sadou akcí a uloží odpovědi."""
    api_url = urljoin(base_url, "api.php")
    results: dict[str, object] = {}

    for action in API_ACTIONS:
        params = {"Act": action} if action else None
        label = action or "(bez Act)"
        try:
            response = session.get(api_url, params=params, timeout=TIMEOUT)
        except requests.RequestException as err:
            results[label] = {"error": str(err)}
            print(f"  api.php {label}: chyba {err}")
            continue

        text = decode(response).strip()
        try:
            payload = json.loads(text)
        except ValueError:
            payload = {"raw": text[:2000]}

        results[label] = payload
        status = (
            payload.get("Status") if isinstance(payload, dict) else "?"
        )
        print(f"  api.php {label}: HTTP {response.status_code}, Status {status}")

    target = out / "api.json"
    target.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  uloženo {target.name}")


def main() -> int:
    """Spustí discovery a uloží stránky i odpovědi API."""
    argument_parser = argparse.ArgumentParser(
        description="Discovery Job Abacus Pro WEB Client"
    )
    argument_parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="výstupní složka"
    )
    argument_parser.add_argument(
        "--depth", type=int, default=2, help="do jaké hloubky následovat odkazy"
    )
    args = argument_parser.parse_args()

    base_url = os.environ.get("ABACUS_URL", "").strip()
    user = os.environ.get("ABACUS_USER", "").strip()
    password = os.environ.get("ABACUS_PASS", "")

    if not (base_url and user and password):
        print(
            "Chybí ABACUS_URL, ABACUS_USER nebo ABACUS_PASS. "
            "Návod je v docstringu skriptu.",
            file=sys.stderr,
        )
        return 2

    if not base_url.endswith("/"):
        base_url += "/"

    args.out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    print(f"Přihlašuji se na {base_url} jako {user}")
    html = login(session, base_url, user, password)
    (args.out / "00_after_login.html").write_text(html, encoding="utf-8")
    print("  uloženo 00_after_login.html")

    print("\nProcházím stránky:")
    saved = dump_html(session, base_url, args.out, html, args.depth)

    print("\nZkouším JSON API:")
    dump_api(session, base_url, args.out)

    print(f"\nHotovo. Uloženo {saved + 1} stránek a api.json do {args.out}")
    print(
        "Pošli mi prosím `api.json` a ty HTML soubory, ve kterých je jídelníček "
        "nebo přehled objednávek."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
