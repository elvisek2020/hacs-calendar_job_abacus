"""Testy čtení jídelníčku z Job Abacus Pro WEB Client.

HTML v testech kopíruje skutečný výstup web klienta 2.15 ověřený proti
reálnému serveru, jen zkrácený a s vymyšlenými jídly.
"""

from __future__ import annotations

from datetime import date

from conftest import load_module

parser = load_module("parser")

# Týdenní mřížka: dny jsou sloupce, v buňkách je jen stav a odkaz na detail.
GRID_HTML = """
<div id="content">
  <h1>Jídelní lístek</h1>
  <div class="box" id="holder-box">
    <h2>Jídelní lístek od 07.09.2026</h2>
    <table class="cant">
      <tr>
        <th class='day day-0'><span>Pondělí</span> 07.09.26</th>
        <th class='day day-1'><span>Úterý</span> 08.09.26</th>
        <th class='day day-2'><span>Středa</span> 09.09.26</th>
        <th class='day day-3'><span>Čtvrtek</span> 10.09.26</th>
        <th class='day day-4'><span>Pátek</span> 11.09.26</th>
        <th class='day day-5'><span>Sobota</span> 12.09.26</th>
        <th class='day day-6'><span>Neděle</span> 13.09.26</th>
      </tr>
      <tr class='group odd'><td colspan='7'><div><span>Oběd</span></div></td></tr>
      <tr class='odd'>
        <td class='weekday '>
          <a href=index.php?ShowAlerg=0&ShowMenu=2346 class='expired'>Nabídka<br>uzavřena</a>
        </td>
        <td class='weekday '>
          <a href=index.php?ShowAlerg=0&ShowMenu=2347 class='expired'>Nabídka<br>uzavřena</a>
        </td>
        <td class='weekday '>
          <a href=index.php?ShowAlerg=0&ShowMenu=2348 class='expired'>Nabídka<br>uzavřena</a>
        </td>
        <td class='weekday '>
          <a href=index.php?ShowAlerg=0&ShowMenu=2349 class='order'>Objednat</a>
        </td>
        <td class='weekday '>
          <a href=index.php?ShowAlerg=0&ShowMenu=2350 class='ordered'>Objednáno</a>
        </td>
        <td class='weekend saturday'><span class='empty'>Není<br>nabídka</span></td>
        <td class='weekend '><span class='empty'>Není<br>nabídka</span></td>
      </tr>
    </table>
  </div>
</div>
"""


def detail_html(day: str, rows: str) -> str:
    """Sestaví detail dne; web klient ho přidává k téže mřížce."""
    return f"""
{GRID_HTML}
<div class="to-overlay">
  <div class="dialog-header"><h2>Nabídka {day}</h2></div>
  <div class="dialog-body cant-menu-list">
    <h3>Menu</h3>
    <table class="cant-menu">{rows}</table>
    <br>Výsledná cena: 45,00
  </div>
</div>
"""


# Objednané množství je ve druhém sloupci `count`, tady u varianty 2.
DETAIL_FRIDAY = detail_html(
    "11.09.2026",
    """
    <tr class='odd'>
      <td>1. kuřecí maso na paprice, těstoviny, ovoce [1,7,9]</td>
      <td class='count center'></td>
      <td class='count center'>&nbsp</td>
      <td class='price center'>45,- Kč</td>
      <td class='actions center'><a href=index.php?MenuAdd=4748 class="add">+</a></td>
    </tr>
    <tr class='even'>
      <td>2. bramborové šišky s mákem [1,3,7,9]</td>
      <td class='count center'></td>
      <td class='count center'>1&times;</td>
      <td class='price center'>45,- Kč</td>
      <td class='actions center'><a href=index.php?MenuDel=4749 class="sub">-</a></td>
    </tr>
    """,
)

DETAIL_MONDAY = detail_html(
    "07.09.2026",
    """
    <tr class='even'>
      <td>2. Studený balíček - chléb, oplatek, nápoj [1,2,3,7]</td>
      <td class='count center'></td>
      <td class='count center'>&nbsp</td>
      <td class='price center'>45,- Kč</td>
      <td class='actions center'>&nbsp</td>
    </tr>
    """,
)


# --------------------------------------------------------------------------
# Týdenní mřížka
# --------------------------------------------------------------------------


def test_grid_maps_cells_to_day_columns() -> None:
    offers = parser.parse_week_grid(GRID_HTML)

    assert [offer.day for offer in offers] == [
        date(2026, 9, 7),
        date(2026, 9, 8),
        date(2026, 9, 9),
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
        date(2026, 9, 13),
    ]


def test_grid_reads_two_digit_year() -> None:
    # Hlavička píše rok dvojmístně, například `07.09.26`.
    assert parser.parse_week_grid(GRID_HTML)[0].day.year == 2026


def test_grid_reads_statuses_from_link_classes() -> None:
    offers = parser.parse_week_grid(GRID_HTML)

    assert [offer.status for offer in offers] == [
        parser.STATUS_CLOSED,
        parser.STATUS_CLOSED,
        parser.STATUS_CLOSED,
        parser.STATUS_OPEN,
        parser.STATUS_ORDERED,
        parser.STATUS_NONE,
        parser.STATUS_NONE,
    ]


def test_grid_reads_menu_ids_and_group() -> None:
    offers = parser.parse_week_grid(GRID_HTML)

    assert [offer.menu_id for offer in offers] == [
        2346,
        2347,
        2348,
        2349,
        2350,
        None,
        None,
    ]
    assert {offer.group for offer in offers} == {"Oběd"}


def test_grid_without_table_yields_nothing() -> None:
    assert parser.parse_week_grid("<html><body>nic</body></html>") == []
    assert parser.parse_week_grid("") == []


# --------------------------------------------------------------------------
# Detail dne
# --------------------------------------------------------------------------


def test_detail_reads_date_from_dialog_header() -> None:
    day, _ = parser.parse_day_detail(DETAIL_FRIDAY)

    assert day == date(2026, 9, 11)


def test_detail_reads_name_price_and_allergens() -> None:
    _, meals = parser.parse_day_detail(DETAIL_FRIDAY)

    assert len(meals) == 2
    assert meals[0].name == "kuřecí maso na paprice, těstoviny, ovoce"
    assert meals[0].price == "45,- Kč"
    assert meals[0].allergens == "1,7,9"


def test_detail_marks_only_the_ordered_variant() -> None:
    # Objednávku prozradí `1×` ve sloupci s množstvím, ne stav celého dne.
    _, meals = parser.parse_day_detail(DETAIL_FRIDAY)

    assert [meal.ordered for meal in meals] == [False, True]


def test_detail_keeps_variant_number_as_label() -> None:
    _, meals = parser.parse_day_detail(DETAIL_FRIDAY)

    assert [meal.label for meal in meals] == ["1", "2"]


def test_detail_ignores_the_week_grid_on_the_same_page() -> None:
    # Stránka detailu obsahuje i mřížku; ta nesmí přidat žádné jídlo.
    _, meals = parser.parse_day_detail(DETAIL_MONDAY)

    assert [meal.name for meal in meals] == [
        "Studený balíček - chléb, oplatek, nápoj"
    ]


def test_detail_without_menu_table_yields_no_meals() -> None:
    day, meals = parser.parse_day_detail(GRID_HTML)

    assert day is None
    assert meals == []


# --------------------------------------------------------------------------
# Spojení mřížky a detailů
# --------------------------------------------------------------------------


def test_menu_combines_grid_group_with_details() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_MONDAY, DETAIL_FRIDAY])

    assert sorted(menu) == [date(2026, 9, 7), date(2026, 9, 11)]
    assert [meal.label for meal in menu[date(2026, 9, 11)]] == ["Oběd 1", "Oběd 2"]


def test_menu_needs_details_to_learn_meal_names() -> None:
    # Mřížka sama názvy jídel neobsahuje.
    assert parser.parse_html_menu(GRID_HTML, []) == {}


def test_menu_skips_days_without_offer() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY])

    assert date(2026, 9, 12) not in menu
    assert date(2026, 9, 13) not in menu


def test_menu_deduplicates_repeated_details() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY, DETAIL_FRIDAY])

    assert len(menu[date(2026, 9, 11)]) == 2


# --------------------------------------------------------------------------
# Celodenní události
# --------------------------------------------------------------------------


def test_ordered_mode_names_the_ordered_meal() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY])
    days = parser.build_lunch_days(menu, parser.SUMMARY_MODE_ORDERED)

    assert days[0].summary == "bramborové šišky s mákem"


def test_ordered_mode_falls_back_when_nothing_ordered() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_MONDAY])
    days = parser.build_lunch_days(menu, parser.SUMMARY_MODE_ORDERED)

    assert days[0].summary == parser.NOT_ORDERED_SUMMARY


def test_all_mode_lists_every_option() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY])
    days = parser.build_lunch_days(menu, parser.SUMMARY_MODE_ALL)

    assert days[0].summary == (
        "kuřecí maso na paprice, těstoviny, ovoce / bramborové šišky s mákem"
    )


def test_description_shows_marker_price_and_allergens() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY])
    days = parser.build_lunch_days(menu, parser.SUMMARY_MODE_ORDERED)

    assert days[0].description == (
        "· Oběd 1: kuřecí maso na paprice, těstoviny, ovoce"
        " — 45,- Kč [alergeny 1,7,9]\n"
        "✓ Oběd 2: bramborové šišky s mákem — 45,- Kč [alergeny 1,3,7,9]"
    )


def test_lunch_days_are_sorted_with_stable_uid() -> None:
    menu = parser.parse_html_menu(GRID_HTML, [DETAIL_FRIDAY, DETAIL_MONDAY])
    days = parser.build_lunch_days(menu, parser.SUMMARY_MODE_ORDERED)

    assert [day.day for day in days] == [date(2026, 9, 7), date(2026, 9, 11)]
    assert [day.uid for day in days] == ["2026-09-07", "2026-09-11"]


# --------------------------------------------------------------------------
# JSON z api.php
# --------------------------------------------------------------------------


def test_api_status_three_means_not_logged_in() -> None:
    payload = {"GACC_JAP_JSON_CONTENT": "4", "Status": 3, "Count": 0}

    assert parser.parse_api_menu(payload) == {}


def test_api_rows_are_read_by_key_names() -> None:
    payload = {
        "Status": 0,
        "Rows": [
            {"Datum": "2026-09-11", "Nazev": "Svíčková", "Objednano": "1"},
            {"Datum": "2026-09-11", "Nazev": "Rizoto", "Objednano": "0"},
        ],
    }

    menu = parser.parse_api_menu(payload)

    assert [(meal.name, meal.ordered) for meal in menu[date(2026, 9, 11)]] == [
        ("Svíčková", True),
        ("Rizoto", False),
    ]


def test_api_result_wins_over_html() -> None:
    payload = {"Rows": [{"Datum": "2026-09-11", "Nazev": "Z API"}]}

    menu = parser.parse_menu(payload, GRID_HTML, [DETAIL_FRIDAY])

    assert [meal.name for meal in menu[date(2026, 9, 11)]] == ["Z API"]


def test_html_is_used_when_api_returns_nothing() -> None:
    menu = parser.parse_menu(None, GRID_HTML, [DETAIL_FRIDAY])

    assert date(2026, 9, 11) in menu


def test_malformed_inputs_do_not_raise() -> None:
    assert parser.parse_menu(None, None, None) == {}
    assert parser.parse_menu("nope", "", []) == {}
    assert parser.parse_api_menu(None) == {}
    assert parser.parse_html_menu("<table class='cant'><tr><td>", []) == {}
