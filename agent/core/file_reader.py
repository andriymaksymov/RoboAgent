from pathlib import Path

from .registry import tool
from .utils import resolve_in_workdir


@tool
def read_file(path: str, workdir: Path) -> str:
    """Read a local file from the workdir.

    Args:
        path: File path relative to the workdir.
    """
    return resolve_in_workdir(workdir, path).read_text(encoding="utf-8")
