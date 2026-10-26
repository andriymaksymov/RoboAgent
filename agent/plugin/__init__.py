"""Plugin tools — auto-discovered and registered at import time.

To add a new tool, drop a ``.py`` file that contains one or more ``@tool``-decorated
functions into this directory.  No other changes are required; the file is imported
automatically the next time the agent starts.

See ``echo.py`` in this directory for a minimal working example.
"""

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

for _path in sorted(Path(__file__).parent.glob("*.py")):
    if _path.stem == "__init__":
        continue
    _module_name = f"agent.plugin.{_path.stem}"
    try:
        importlib.import_module(_module_name)
        logger.debug("Loaded plugin: %s", _module_name)
    except Exception as exc:  # noqa: BLE001
        # A broken plugin must never prevent the agent from starting.
        logger.warning("Failed to load plugin %s: %s", _module_name, exc)
