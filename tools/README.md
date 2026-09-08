# Discovery Job Abacus Pro

Job Abacus Pro WEB Client nemá veřejnou dokumentaci a co je za přihlášením,
se z venku zjistit nedá. Skript `dump_pages.py` proto uloží skutečnou podobu
stránek a odpovědí API, aby se podle nich dal napsat a doladit parser.

## Co už o serveru víme (bez přihlášení)

| Cesta | Zjištění |
| --- | --- |
| `login.php` | Přihlašovací formulář. POST na `login.php?Act=Validate`, pole `Login` a `Pwd`, kódování `windows-1250`, session v cookie `PHPSESSID`. |
| `index.php` | Nepřihlášený přístup přesměruje na `login.php`. |
| `api.php` | Vrací JSON `{"GACC_JAP_JSON_CONTENT":"4","Status":3,"Count":0}`. `Status: 3` = nepřihlášeno. Kontrola session proběhne dřív než čtení parametrů, takže skutečné parametry jde odhalit až se session. |
| `strava.php` | Chráněno HTTP Basic auth, tedy jiný mechanismus než přihlašovací formulář. |

Integrace míří primárně na `api.php`, protože JSON je stabilnější než HTML.
Parser HTML slouží jako záloha, pokud by API na dané instalaci nefungovalo.

## Spuštění

Skript potřebuje `requests`:

```bash
python3 -m venv .venv
.venv/bin/pip install requests
```

Přihlašovací údaje se předávají proměnnými prostředí, aby se neobjevily
v historii shellu ani v souborech:

```bash
export ABACUS_URL="http://server:port"
export ABACUS_USER="jmeno"
read -rs ABACUS_PASS && export ABACUS_PASS

.venv/bin/python tools/dump_pages.py --out /tmp/abacus
```

## Co skript udělá

1. Přihlásí se přes `login.php?Act=Validate`.
2. Uloží HTML stránky po přihlášení a projde odkazy do zadané hloubky
   (`--depth`, výchozí 2).
3. Osloví `api.php` sadou hodnot `Act` a uloží odpovědi do `api.json`.

Skript pouze čte. Jediný zápis je přihlašovací POST. Odkazy a parametry, které
by mohly něco uložit, objednat nebo odhlásit session, se přeskakují.

## Pozor

- Výstup obsahuje osobní údaje (jméno, stav konta, objednávky). Výchozí cíl je
  proto `/tmp`, ne repozitář. Do gitu tyto soubory nepatří.
- Heslo se nikam neukládá a ve výstupu se nevyskytuje.
- Server běží na nešifrovaném HTTP, takže přihlašovací údaje jdou po síti
  v otevřené podobě. To je vlastnost školního serveru, kterou skript ani
  integrace nemohou obejít.
