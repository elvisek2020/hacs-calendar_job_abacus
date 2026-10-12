# Changelog

Poznámky k vydání. Sekce `## vX.Y.Z` se při releasu automaticky použije jako
text vydání na GitHubu — a ten Home Assistant / HACS ukazuje v okně aktualizace.

Nejnovější verze je nahoře.

## v1.0.1 — 2026-10-12

Údržbové vydání, integrace se chová stejně jako ve v1.0.0.

### ✨ Novinky

- README s tlačítkem „Otevřít v HACS“ a sjednocenou strukturou (předpoklady, instalace, konfigurace).
- Text vydání se teď bere z `CHANGELOG.md`, takže ho Home Assistant ukáže v okně aktualizace.

## v1.0.0 — 2026-09-08

První veřejná verze integrace Job Abacus Pro pro Home Assistant / HACS.

### ✨ Novinky

- Kalendářová entita s jídelníčkem z Job Abacus Pro WEB Client – každý den jako celodenní událost, objednané jídlo označené `✓`.
- Volba názvu události (objednané jídlo / všechna jídla dne).
- Nastavení přes UI (config flow) včetně opětovného přihlášení při změně hesla.
