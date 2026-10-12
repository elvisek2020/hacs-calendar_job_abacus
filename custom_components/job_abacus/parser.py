"""Čtení jídelníčku z Job Abacus Pro WEB Client.

Web klient je tabulkové HTML z roku 2011 a jídelníček podává na dvě stránky:

* `index.php` vykreslí **týdenní mřížku** `table.cant`, kde jsou dny sloupce.
  V buňkách nejsou názvy jídel, jen stav (`ordered`, `expired`, `empty`)
  a odkaz `index.php?ShowMenu=<id>` na detail dne.
* `index.php?ShowMenu=<id>` přidá k mřížce překryv `div.to-overlay`
  s tabulkou `table.cant-menu`, kde teprve jsou názvy jídel, ceny
  a objednané množství.

Názvy jídel proto nejde získat jinak než dotažením detailu ke každému dni;
`parse_menu` obě části spojí.

Novější instalace mají navíc endpoint `api.php` s JSON. Ten nemá zveřejněnou
dokumentaci, takže `parse_api_menu` hledá klíče podle názvu.

Vše je psané tolerantně: co se nepodaří rozpoznat, se vynechá, aby jedna
změna na serveru neshodila celou integraci.

Modul nezávisí na Home Assistantu ani na externích knihovnách, aby se dal
testovat samostatně.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from html.parser import HTMLParser
from typing import Any

SUMMARY_MODE_ORDERED = "ordered"
SUMMARY_MODE_ALL = "all"

NOT_ORDERED_SUMMARY = "Neobjednáno"

# `api.php` vrací Status 3, dokud není navázaná přihlášená session.
API_STATUS_NOT_LOGGED_IN = 3

# Třídy tabulek web klienta.
GRID_TABLE_CLASS = "cant"
DETAIL_TABLE_CLASS = "cant-menu"

# Stavy, které mřížka označuje třídou odkazu v buňce.
STATUS_ORDERED = "ordered"
STATUS_CLOSED = "expired"
STATUS_NONE = "empty"
STATUS_OPEN = "open"

# "8.9.2026", "07.09.26" i "8.9." bez roku.
DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{2,4})?(?!\d)")
ISO_DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
DETAIL_DATE_PATTERN = re.compile(r"<h2>\s*Nab[íi]dka\s+([\d.\s]+?)\s*</h2>", re.I)
MENU_ID_PATTERN = re.compile(r"ShowMenu=(\d+)")

# "1. kuřecí maso na paprice, …" – číslo varianty na začátku názvu.
VARIANT_PATTERN = re.compile(r"^(\d{1,2})\s*\.\s*")
# "… [1,7,9]" – čísla alergenů na konci názvu.
ALLERGEN_PATTERN = re.compile(r"\s*\[\s*([\d,\s]+)\s*\]\s*$")
# "1×" v buňce s objednaným množstvím.
QUANTITY_PATTERN = re.compile(r"(\d+)\s*[×x]", re.I)

PRICE_PATTERN = re.compile(r"^-?\d+([.,]\d+)?\s*(K[čc]|CZK)?$", re.IGNORECASE)
ORDERED_PATTERN = re.compile(r"(objedn[aá]n|vyzvednut|✓)", re.IGNORECASE)

# Klíče, pod kterými GACC JSON vrací kolekci řádků.
ROW_COLLECTION_KEYS = ("Rows", "Data", "Items", "Records", "List", "Table", "Table0")

DATE_KEY_HINTS = ("date", "datum", "den", "day")
NAME_KEY_HINTS = ("name", "nazev", "název", "jidlo", "jídlo", "meal", "text", "popis")
LABEL_KEY_HINTS = ("variant", "druh", "chod", "type", "typ", "kind")
ORDERED_KEY_HINTS = ("ordered", "objedn", "selected", "checked", "state", "stav")

TRUTHY = {"1", "true", "yes", "ano", "a", "y", "objednano", "objednáno"}


@dataclass(frozen=True)
class Meal:
    """Jedno jídlo v jídelníčku."""

    name: str
    label: str | None = None
    ordered: bool = False
    price: str | None = None
    allergens: str | None = None


@dataclass(frozen=True)
class DayOffer:
    """Jeden den z týdenní mřížky."""

    day: date
    group: str | None
    status: str
    menu_id: int | None


@dataclass(frozen=True)
class LunchDay:
    """Jeden den jídelníčku připravený jako celodenní událost."""

    uid: str
    day: date
    summary: str
    description: str | None


@dataclass
class Cell:
    """Buňka tabulky včetně tříd a odkazů, podle kterých se pozná stav."""

    parts: list[str] = field(default_factory=list)
    checked: bool = False
    classes: set[str] = field(default_factory=set)
    # Třídy `<a>` a `<span>` uvnitř buňky; mřížka jimi značí stav dne.
    inner_classes: set[str] = field(default_factory=set)
    hrefs: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Vrátí vyčištěný text buňky."""
        return _clean("".join(self.parts))


@dataclass
class Row:
    """Řádek tabulky."""

    cells: list[Cell] = field(default_factory=list)
    classes: set[str] = field(default_factory=set)


@dataclass
class Table:
    """Tabulka i s třídami, aby se dala poznat mřížka od detailu."""

    rows: list[Row] = field(default_factory=list)
    classes: set[str] = field(default_factory=set)


def _clean(text: str) -> str:
    """Sloučí bílé znaky a odstraní nezlomitelné mezery."""
    return " ".join(text.replace("\xa0", " ").split())


def _classes(attrs: dict[str, str]) -> set[str]:
    """Rozdělí atribut `class` na jednotlivé názvy."""
    return set(attrs.get("class", "").split())


def _parse_date(text: str, default_year: int | None = None) -> date | None:
    """Najde v textu datum ve tvaru `YYYY-MM-DD`, `D.M.YYYY`, `D.M.RR` nebo `D.M.`."""
    if not text:
        return None

    if (iso := ISO_DATE_PATTERN.search(text)) is not None:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    match = DATE_PATTERN.search(text)
    if match is None:
        return None

    if (raw_year := match.group(3)) is None:
        year = default_year
    elif len(raw_year) == 2:
        # Mřížka píše rok dvojmístně, například `07.09.26`.
        year = 2000 + int(raw_year)
    else:
        year = int(raw_year)

    if year is None:
        return None

    try:
        return date(year, int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _is_price(text: str) -> bool:
    """Rozhodne, jestli je text jen cena nebo číslo."""
    return bool(text) and bool(PRICE_PATTERN.match(text))


def _is_truthy(value: Any) -> bool:
    """Vyhodnotí příznak objednávky napříč tvary, které server používá."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return _clean(value).lower() in TRUTHY
    return False


def _matching_key(row: dict[str, Any], hints: tuple[str, ...]) -> str | None:
    """Najde v řádku první klíč, jehož název obsahuje některou nápovědu."""
    for key in row:
        lowered = key.lower()
        if any(hint in lowered for hint in hints):
            return key
    return None


class TableParser(HTMLParser):
    """Vytáhne z HTML tabulky jako řádky a buňky včetně tříd a odkazů.

    Job Abacus sází stránky do vnořených tabulek, proto se tabulky drží
    na zásobníku a každá se uzavírá samostatně.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[Table] = []
        self._stack: list[Table] = []
        self._row: Row | None = None
        self._cell: Cell | None = None
        # Rozpracovaný řádek a buňka vnější tabulky, než se vnoří další.
        self._saved: list[tuple[Row | None, Cell | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: (value or "") for name, value in attrs}

        if tag == "table":
            self._saved.append((self._row, self._cell))
            self._row = None
            self._cell = None
            self._stack.append(Table(classes=_classes(attributes)))
        elif tag == "tr" and self._stack:
            self._close_row()
            self._row = Row(classes=_classes(attributes))
        elif tag in ("td", "th") and self._row is not None:
            self._close_cell()
            self._cell = Cell(classes=_classes(attributes))
        elif self._cell is None:
            return
        elif tag == "input":
            if (
                attributes.get("type", "").lower() in ("checkbox", "radio")
                and "checked" in attributes
            ):
                self._cell.checked = True
        elif tag in ("a", "span", "div", "img"):
            self._cell.inner_classes |= _classes(attributes)
            if href := attributes.get("href"):
                self._cell.hrefs.append(href)
        elif tag == "br":
            self._cell.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th"):
            self._close_cell()
        elif tag == "tr":
            self._close_row()
        elif tag == "table":
            self._close_row()
            if self._stack:
                self.tables.append(self._stack.pop())
            if self._saved:
                self._row, self._cell = self._saved.pop()

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.parts.append(data)

    def _close_cell(self) -> None:
        """Uloží rozpracovanou buňku do řádku."""
        if self._cell is not None and self._row is not None:
            self._row.cells.append(self._cell)
        self._cell = None

    def _close_row(self) -> None:
        """Uloží rozpracovaný řádek do aktuální tabulky."""
        self._close_cell()
        if self._row is not None and self._row.cells and self._stack:
            self._stack[-1].rows.append(self._row)
        self._row = None

    def close(self) -> None:
        """Dokončí parsování a uzavře i neuzavřené tabulky."""
        super().close()
        self._close_row()
        while self._stack:
            self.tables.append(self._stack.pop())
        self._saved.clear()


def _parse_tables(html: str) -> list[Table]:
    """Rozparsuje HTML na tabulky; poškozený vstup vrátí prázdný seznam."""
    parser = TableParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - poškozené HTML nesmí shodit integraci
        return []
    return parser.tables


def _find_table(tables: list[Table], css_class: str) -> Table | None:
    """Najde první tabulku s danou třídou."""
    for table in tables:
        if css_class in table.classes:
            return table
    return None


def _cell_status(cell: Cell) -> str:
    """Odvodí stav dne z tříd odkazu nebo popisku v buňce."""
    for status in (STATUS_ORDERED, STATUS_CLOSED, STATUS_NONE):
        if status in cell.inner_classes:
            return status
    if not cell.text:
        return STATUS_NONE
    return STATUS_OPEN


def _menu_id(cell: Cell) -> int | None:
    """Vytáhne z odkazu identifikátor detailu dne."""
    for href in cell.hrefs:
        if (match := MENU_ID_PATTERN.search(href)) is not None:
            menu_id = int(match.group(1))
            if menu_id > 0:
                return menu_id
    return None


def _is_day_header(row: Row) -> bool:
    """Rozhodne, jestli je řádek hlavičkou s datumy dnů."""
    return any("day" in cell.classes for cell in row.cells)


def parse_week_grid(html: str, default_year: int | None = None) -> list[DayOffer]:
    """Přečte z `index.php` týdenní mřížku dnů.

    Dny jsou ve mřížce sloupce, takže se buňky mapují na datumy z hlavičky
    podle pozice.
    """
    table = _find_table(_parse_tables(html), GRID_TABLE_CLASS)
    if table is None:
        return []

    days: list[date | None] = []
    group: str | None = None
    offers: list[DayOffer] = []

    for row in table.rows:
        if _is_day_header(row):
            days = [_parse_date(cell.text, default_year) for cell in row.cells]
            continue

        if not days:
            continue

        if "group" in row.classes or len(row.cells) == 1:
            # Řádek přes celou šířku pojmenovává chod, například `Oběd`.
            group = row.cells[0].text or None
            continue

        for index, cell in enumerate(row.cells):
            if index >= len(days) or (day := days[index]) is None:
                continue
            offers.append(
                DayOffer(
                    day=day,
                    group=group,
                    status=_cell_status(cell),
                    menu_id=_menu_id(cell),
                )
            )

    return offers


def _meal_from_detail_row(row: Row) -> Meal | None:
    """Přečte jedno jídlo z řádku tabulky detailu.

    Buňky se poznávají podle tříd, ne podle pozice, protože web klient
    přidává akční sloupce jen tam, kde se dá objednávat. Do `label` se
    uloží jen číslo varianty; název chodu zná až mřížka.
    """
    name_cell: Cell | None = None
    count_cells: list[Cell] = []
    price: str | None = None

    for cell in row.cells:
        if "count" in cell.classes:
            count_cells.append(cell)
        elif "price" in cell.classes:
            price = cell.text or None
        elif "actions" in cell.classes:
            continue
        elif name_cell is None and cell.text:
            name_cell = cell

    if name_cell is None:
        return None

    name = name_cell.text
    if len(name) < 3 or _is_price(name):
        return None

    allergens: str | None = None
    if (match := ALLERGEN_PATTERN.search(name)) is not None:
        allergens = _clean(match.group(1))
        name = name[: match.start()].strip()

    label: str | None = None
    if (match := VARIANT_PATTERN.match(name)) is not None:
        label = match.group(1)
        name = name[match.end() :].strip()

    if not name:
        return None

    # Objednané množství je v posledním sloupci `count`, například `1×`.
    ordered = any(
        QUANTITY_PATTERN.search(cell.text) for cell in count_cells if cell.text
    )

    return Meal(
        name=name,
        label=label,
        ordered=ordered,
        price=price,
        allergens=allergens,
    )


def _detail_date(html: str, default_year: int | None = None) -> date | None:
    """Vytáhne datum z hlavičky překryvu, například `Nabídka 11.09.2026`."""
    if (match := DETAIL_DATE_PATTERN.search(html)) is None:
        return None
    return _parse_date(match.group(1), default_year)


def parse_day_detail(
    html: str, default_year: int | None = None
) -> tuple[date | None, list[Meal]]:
    """Přečte z `index.php?ShowMenu=<id>` nabídku jednoho dne."""
    day = _detail_date(html, default_year)

    table = _find_table(_parse_tables(html), DETAIL_TABLE_CLASS)
    if table is None:
        return day, []

    meals = [
        meal for row in table.rows if (meal := _meal_from_detail_row(row)) is not None
    ]
    return day, meals


def _with_group(meal: Meal, group: str | None) -> Meal:
    """Doplní jídlu název chodu z mřížky, například `Oběd 2`."""
    if group is None:
        return meal

    label = f"{group} {meal.label}" if meal.label else group
    return Meal(
        name=meal.name,
        label=label,
        ordered=meal.ordered,
        price=meal.price,
        allergens=meal.allergens,
    )


def parse_html_menu(
    grid_html: str,
    detail_pages: list[str] | None = None,
    default_year: int | None = None,
) -> dict[date, list[Meal]]:
    """Spojí týdenní mřížku s detaily dnů na jídelníček podle dnů.

    Bez detailů zůstane jídelníček prázdný, protože mřížka názvy jídel
    neobsahuje.
    """
    if default_year is None:
        default_year = date.today().year

    offers = parse_week_grid(grid_html, default_year)
    groups = {offer.day: offer.group for offer in offers if offer.group}

    menu: dict[date, list[Meal]] = {}

    for page in detail_pages or []:
        day, meals = parse_day_detail(page, default_year)
        if day is None or not meals:
            continue

        # Název chodu je jen ve mřížce, do detailu se propíše až tady.
        group = groups.get(day)
        existing = menu.setdefault(day, [])
        for meal in (_with_group(meal, group) for meal in meals):
            if all(item.name != meal.name for item in existing):
                existing.append(meal)

    return {day: meals for day, meals in menu.items() if meals}


def _iter_row_dicts(payload: Any, depth: int = 0) -> list[dict[str, Any]]:
    """Najde v odpovědi API první kolekci řádků."""
    if depth > 4:
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ROW_COLLECTION_KEYS:
        if rows := _iter_row_dicts(payload.get(key), depth + 1):
            return rows

    for value in payload.values():
        if isinstance(value, (list, dict)) and (
            rows := _iter_row_dicts(value, depth + 1)
        ):
            return rows

    return []


def parse_api_menu(payload: Any) -> dict[date, list[Meal]]:
    """Přečte jídelníček z odpovědi `api.php`."""
    if isinstance(payload, dict) and payload.get("Status") == API_STATUS_NOT_LOGGED_IN:
        return {}

    menu: dict[date, list[Meal]] = {}

    for row in _iter_row_dicts(payload):
        date_key = _matching_key(row, DATE_KEY_HINTS)
        name_key = _matching_key(row, NAME_KEY_HINTS)
        if date_key is None or name_key is None:
            continue

        day = _parse_date(str(row.get(date_key) or ""))
        name = _clean(str(row.get(name_key) or ""))
        if day is None or len(name) < 3:
            continue

        label_key = _matching_key(row, LABEL_KEY_HINTS)
        ordered_key = _matching_key(row, ORDERED_KEY_HINTS)

        label = _clean(str(row.get(label_key) or "")) if label_key else None
        ordered = _is_truthy(row.get(ordered_key)) if ordered_key else False

        meals = menu.setdefault(day, [])
        if all(existing.name != name for existing in meals):
            meals.append(Meal(name=name, label=label or None, ordered=ordered))

    return menu


def _summary(meals: list[Meal], summary_mode: str) -> str:
    """Sestaví název celodenní události podle zvoleného režimu."""
    if summary_mode == SUMMARY_MODE_ALL:
        names = [meal.name for meal in meals]
        return " / ".join(names) if names else NOT_ORDERED_SUMMARY

    ordered = [meal.name for meal in meals if meal.ordered]
    return " + ".join(ordered) if ordered else NOT_ORDERED_SUMMARY


def _description(meals: list[Meal]) -> str | None:
    """Sestaví popis s celým jídelníčkem dne."""
    lines = []
    for meal in meals:
        marker = "✓" if meal.ordered else "·"
        label = f"{meal.label}: " if meal.label else ""
        line = f"{marker} {label}{meal.name}"
        if meal.price:
            line = f"{line} — {meal.price}"
        if meal.allergens:
            line = f"{line} [alergeny {meal.allergens}]"
        lines.append(line)
    return "\n".join(lines) or None


def build_lunch_days(menu: dict[date, list[Meal]], summary_mode: str) -> list[LunchDay]:
    """Převede jídelníček na celodenní záznamy řazené podle data."""
    return [
        LunchDay(
            uid=day.isoformat(),
            day=day,
            summary=_summary(meals, summary_mode),
            description=_description(meals),
        )
        for day, meals in sorted(menu.items())
    ]


def parse_menu(
    api_payload: Any,
    grid_html: str | None,
    detail_pages: list[str] | None = None,
    default_year: int | None = None,
) -> dict[date, list[Meal]]:
    """Přečte jídelníček z API, a když nic nevrátí, zkusí stránky web klienta."""
    if menu := parse_api_menu(api_payload):
        return menu
    if grid_html:
        return parse_html_menu(grid_html, detail_pages, default_year)
    return {}
