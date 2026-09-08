"""Pomocníci pro testy bez nutnosti instalovat Home Assistant.

Modul `parser` nemá žádnou závislost na Home Assistantu, ale leží v balíčku,
jehož `__init__.py` HA importuje. Proto se nahrává přímo ze souboru.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "job_abacus"


def load_module(name: str) -> ModuleType:
    """Nahraje modul integrace přímo ze souboru."""
    path = COMPONENT_DIR / f"{name}.py"
    module_name = f"job_abacus_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass sahá na sys.modules[__module__], proto registrace před spuštěním.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
