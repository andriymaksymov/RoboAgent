"""pip_show – show an installed package's version, location and dependencies."""

import re
from pathlib import Path

from .process import format_result, run_module
from .registry import ToolError, tool

_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@tool
def pip_show(package: str, workdir: Path, verbose: bool, agent_dir: Path | None) -> str:
    """Show an installed package's version, location and dependencies.

    Args:
        package: Distribution name, e.g. 'requests'.
    """
    if not _PACKAGE_NAME.match(package or ""):
        raise ToolError(f"Invalid package name: '{package}'.")
    result = run_module(
        "pip_show", ["pip", "show", "--disable-pip-version-check", package],
        run_cwd=workdir, cwd_label=".", timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    return format_result(result)
