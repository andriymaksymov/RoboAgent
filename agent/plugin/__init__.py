"""Plugin tools — auto-discovered and registered at import time, hot-reloaded at runtime.

To add a new tool, drop a ``.py`` file that contains one or more ``@tool``-decorated
functions into this directory.  No other changes are required; the file is loaded when
the agent starts, and a file written or changed while the agent runs is picked up after
the current batch of tool calls (see ``agent.plugin_loader``).

See ``echo.py`` in this directory for a minimal working example.
"""

from ..plugin_loader import PLUGINS

# A broken plugin never prevents the agent from starting: it is logged and skipped.
PLUGINS.refresh()
