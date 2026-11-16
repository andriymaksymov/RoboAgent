import os
from pathlib import Path

from .registry import tool
from .utils import MAX_ENTRIES, cap_entries, resolve_dir


@tool
def folder_content(path: str, workdir: Path, agent_dir: Path | None) -> str:
    """List the files and directories in a directory (not recursive; hidden entries are skipped). One entry per line: directories end with '/', files show their size in bytes. At most 200 entries.

    Args:
        path: Directory path relative to the workdir.
    """
    contents = []
    with os.scandir(resolve_dir(workdir, path, agent_dir)) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                line = f"{entry.name}/" if entry.is_dir() else f"{entry.name}  {entry.stat().st_size}"
            except OSError:
                continue
            contents.append(line)

    if not contents:
        return "Directory is empty."
    return cap_entries(sorted(contents), MAX_ENTRIES, "list a subdirectory or use file_search")
