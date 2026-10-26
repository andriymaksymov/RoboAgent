import json
import os
from pathlib import Path

from .registry import tool
from .utils import resolve_dir


@tool
def folder_content(path: str, workdir: Path, agent_dir: Path | None) -> str:
    """Return a list of all files and directories in the specified path with their names, sizes, and types. Ignore hidden files and directories.

    Args:
        path: Directory path relative to the workdir.
    """
    contents = []
    with os.scandir(resolve_dir(workdir, path, agent_dir)) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                entry_size = entry.stat().st_size
                entry_type = "directory" if entry.is_dir() else "file"
            except OSError:
                continue
            contents.append({"name": entry.name, "size": entry_size, "type": entry_type})

    return json.dumps(contents)
