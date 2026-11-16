from fnmatch import fnmatch
from pathlib import Path

from .registry import tool
from .utils import MAX_ENTRIES, cap_entries, resolve_dir


@tool
def file_search(path: str, pattern: str, workdir: Path, agent_dir: Path | None) -> str:
    """Search for files under a folder and its subfolders using a gitignore-style glob pattern. Returns one relative path per line (at most 200).

    Args:
        path: Directory to search, relative to the workdir.
        pattern: Glob pattern matched against the relative path or file name, e.g. '*.py'.
    """
    root = resolve_dir(workdir, path, agent_dir)
    matches = []
    for candidate in sorted(root.rglob("*")):
        if any(part.startswith(".") for part in candidate.relative_to(root).parts):
            continue
        if candidate.is_dir():
            continue

        relative_path = candidate.relative_to(root).as_posix()
        if fnmatch(relative_path, pattern) or fnmatch(candidate.name, pattern):
            matches.append(relative_path)

    if not matches:
        return "No files found."
    return cap_entries(matches, MAX_ENTRIES, "narrow 'path' or 'pattern'")
