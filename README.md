# Job Abacus Pro

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/elvisek2020/hacs-calendar_job_abacus)](https://github.com/elvisek2020/hacs-calendar_job_abacus/releases)
[![Validate](https://github.com/elvisek2020/hacs-calendar_job_abacus/actions/workflows/validate.yml/badge.svg)](https://github.com/elvisek2020/hacs-calendar_job_abacus/actions/workflows/validate.yml)
[![Licence](https://img.shields.io/github/license/elvisek2020/hacs-calendar_job_abacus)](LICENSE)

[![Otevřít v HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=elvisek2020&repository=hacs-calendar_job_abacus&category=integration)

Neoficiální integrace, která vystaví **jídelníček** ze školní jídelny
provozované na Job Abacus Pro WEB Client (GACC spol. s r.o.) jako
kalendářovou entitu v Home Assistantu.

Integrace pouze čte. **Nic neobjednává ani neruší.**

- Jedna entita `calendar.<jmeno>_obedy` na účet.
- Každý den jídelníčku je jedna **celodenní** událost.
- V názvu události je podle nastavení buď objednané jídlo, nebo všechna jídla dne.
- V popisu události je celý jídelníček dne. Objednané jídlo je označené `✓`.
- Aktualizace každé 2 hodiny.

## Předpoklady a závislosti

- Home Assistant 2025.8.0 nebo novější.
- Účet do web klienta Job Abacus Pro školní jídelny.
- Integrace nemá žádné externí závislosti, používá `aiohttp` z Home Assistanta
  a HTML parser ze standardní knihovny Pythonu.

## Instalace

### HACS (doporučeno)

1. HACS → tři tečky vpravo nahoře → **Custom repositories**
2. Vlož URL `https://github.com/elvisek2020/hacs-calendar_job_abacus`, kategorie **Integration**
3. Nainstaluj **Job Abacus Pro**
4. Restartuj Home Assistant a přidej integraci v **Nastavení → Zařízení a služby → Přidat integraci**.

HACS nabízí aktualizace z GitHub releases.

### Ručně

Zkopíruj `custom_components/job_abacus` do `/config/custom_components/` a restartuj Home Assistant.

## Konfigurace

**Nastavení → Zařízení a služby → Přidat integraci → Job Abacus Pro**

Zadej adresu web klienta (tu, na které se přihlašuješ, bez `/login.php`),
uživatelské jméno a heslo.

Volby jsou v **Nastavení → Zařízení a služby → Job Abacus Pro → Konfigurovat**:

| Volba | Význam |
| --- | --- |
| Název události | `Objednané jídlo` (výchozí) nebo `Všechna jídla dne`. Celý jídelníček je vždy v popisu. |

## Jak to funguje

Web klient je PHP aplikace bez veřejné dokumentace. Zjištěné chování:

| Cesta | Zjištění |
| --- | --- |
| `login.php` | Přihlašovací formulář. POST na `login.php?Act=Validate` s poli `Login` a `Pwd`. Session v cookie `PHPSESSID`. |
| `index.php` | Týdenní mřížka jídelníčku. Nepřihlášený přístup přesměruje na `login.php`. |
| `index.php?ShowMenu=<id>` | Ke mřížce přidá překryv s nabídkou jednoho dne. |
| `api.php` | Vrací JSON s obálkou `{"GACC_JAP_JSON_CONTENT":"4","Status":…}`. `Status: 3` znamená nepřihlášenou session. |
| `strava.php` | Chráněno HTTP Basic auth, a to jinými údaji než web klient. Integrace ho nepoužívá. |

Všechny odpovědi jsou v kódování **windows-1250**, integrace je tak dekóduje.
Ve stejném kódování musí odejít i přihlašovací formulář, jinak server odmítne
jméno s diakritikou jako neplatné.

Web klient bývá vystavený na holé IP adrese (`http://<ip>:<port>`). Cookie
z takové adresy výchozí cookie jar aiohttpu podle RFC 2109 zahodí, takže
integrace používá vlastní session s `unsafe=True`. Bez toho přihlášení projde,
ale `PHPSESSID` se neuloží a další požadavek zase skončí na formuláři.

Jídelníček se čte na dva kroky, protože v mřížce názvy jídel nejsou:

1. `index.php` vykreslí `table.cant`, kde jsou **dny sloupce**. V buňkách je
   jen stav (`ordered`, `expired`, `empty`) a odkaz `ShowMenu=<id>`.
2. Ke každému odkazu se dotáhne detail dne s tabulkou `table.cant-menu`, kde
   jsou názvy jídel, ceny, alergeny a objednané množství (`1×`).

Nejdřív se zkusí `api.php`, protože JSON je stabilnější než HTML. Když API
jídelníček nevrátí, jde se přes stránky web klienta. Když session vyprší,
integrace se jednou znovu přihlásí; pokud selže i heslo, Home Assistant
zobrazí výzvu k opětovnému přihlášení.

## Bezpečnost

- Přihlašovací údaje se zadávají jen v UI a zůstávají v config entry
  Home Assistanta. Heslo se nikam nevypisuje ani neloguje.
- **Server běží na nešifrovaném HTTP.** Přihlašovací údaje tedy jdou po síti
  v otevřené podobě. Je to vlastnost školního serveru, kterou integrace nemůže
  obejít. Pokud je server dostupný z internetu, ber to v potaz.
- Web klient prozrazuje v chybových hlášeních absolutní cesty na serveru
  (například `events.php` vrací PHP fatal error s cestou k instalaci). To je
  věc školního serveru, ne integrace.
- Integrace posílá jen GET požadavky a jeden přihlašovací POST. Žádnou cestu
  k objednávání neobsahuje.

## Vývoj

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt ruff
.venv/bin/python -m pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

Testy pokrývají čtení jídelníčku z HTML i z JSON a nepotřebují instalaci
Home Assistanta ani přístup k serveru jídelny. GitHub Actions spouští
`hassfest`, validaci HACS, Ruff a Pytest.

## Vydání verze

1. Zvedni verzi v `custom_components/job_abacus/manifest.json` (SemVer).
2. Doplň sekci `## vX.Y.Z — RRRR-MM-DD` do `CHANGELOG.md`.
3. Commit `Release vX.Y.Z: …`, `git tag vX.Y.Z`, push commitu i tagu.
4. GitHub Actions vytvoří release s textem z CHANGELOG a HACS nabídne aktualizaci.

## Známá omezení

Job Abacus má na každé instalaci trochu jinou sadu stránek a jinou podobu
tabulek. Parser je proto napsaný tolerantně:

- Datum se hledá ve tvarech `YYYY-MM-DD`, `D.M.YYYY`, `D.M.RR` a `D.M.`
  (u posledního se doplní aktuální rok).
- Buňky detailu se poznávají podle tříd (`count`, `price`, `actions`), ne podle
  pozice, protože akční sloupec je jen tam, kde se dá objednávat.
- Objednaná varianta se pozná podle množství v posledním sloupci `count`.
- Dny bez nabídky (víkendy) žádnou událost nevytvoří.

Další omezení:

- Ověřeno proti web klientovi **verze 2.15** s jedním chodem („Oběd“) a dvěma
  variantami denně. Jiné rozvržení mřížky může vyžadovat doladění.
- Ke každému dni se stahuje samostatná stránka, takže jedna aktualizace udělá
  řádově sedm požadavků. Počet je zastropovaný, aby se server nezaplavil.
- `api.php` na ověřené instalaci vrací `Status: 3` i po přihlášení formulářem,
  takže se vždy použije HTML. Cesta přes API zůstává pro instalace, kde JSON
  session z formuláře přijme.

Pokud integrace jídelníček nenajde nebo ho přečte špatně, spusť discovery
skript a podle výstupu se parser doladí:

```bash
export ABACUS_URL="http://server:port"
export ABACUS_USER="jmeno"
read -rs ABACUS_PASS && export ABACUS_PASS

python3 tools/dump_pages.py --out /tmp/abacus
```

Podrobnosti jsou v [`tools/README.md`](tools/README.md). Výstup obsahuje osobní
údaje, proto nepatří do gitu.

## Autor

**[elvisek2020](https://github.com/elvisek2020)** — vzniklo pro rodinný školní
dashboard v Home Assistantu, kde jsou rozvrhy, obědy a kroužky v jedné kartě.
Licence MIT.

Projekt není nijak spojený se společností GACC spol. s r.o. Používáš ho na
vlastní odpovědnost.
