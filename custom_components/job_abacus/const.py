"""Constants for the Job Abacus Pro integration."""

from __future__ import annotations

from datetime import timedelta

from .parser import SUMMARY_MODE_ALL, SUMMARY_MODE_ORDERED

DOMAIN = "job_abacus"
MANUFACTURER = "GACC Job Abacus Pro"
ATTRIBUTION = "Data poskytuje Job Abacus Pro WEB Client"

CONF_BASE_URL = "base_url"

OPT_SUMMARY_MODE = "summary_mode"

SUMMARY_MODES = [SUMMARY_MODE_ORDERED, SUMMARY_MODE_ALL]
DEFAULT_SUMMARY_MODE = SUMMARY_MODE_ORDERED

UPDATE_INTERVAL = timedelta(hours=2)

# Kódování, které web klient deklaruje ve všech odpovědích.
PAGE_ENCODING = "windows-1250"
