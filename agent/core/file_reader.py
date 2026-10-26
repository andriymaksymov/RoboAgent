from pathlib import Path

from .registry import tool
from .utils import resolve_in_workdir


@tool
def read_file(path: str, workdir: Path, agent_dir: Path | None) -> str:
    """Read a local file from the workdir.

    Args:
        path: File path relative to the workdir.
    """
    return resolve_in_workdir(workdir, path, agent_dir).read_text(encoding="utf-8")
