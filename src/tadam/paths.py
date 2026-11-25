"""Where the kit's own parts are: the engine, the schemas, the rigs and the fonts.

The kit is used from a clone of its repository (`pip install -e .`): the engine and the schemas sit at the clone's
root, next to `src/`. `TADAM_KIT` points somewhere else (a test, or a copy of the kit) when it is set.
The package's own data (rigs, fonts) always travels with the package.
"""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
DATA = PACKAGE / "data"
RIGS = DATA / "rigs"
FONTS = DATA / "fonts"


def kit_root() -> Path:
    forced = os.environ.get("TADAM_KIT", "").strip()
    if forced:
        return Path(forced).expanduser().resolve()
    return PACKAGE.parent.parent          # <clone>/src/tadam -> <clone>


def engine_dir() -> Path:
    return kit_root() / "engine"


def schema_dir() -> Path:
    return kit_root() / "schema"
