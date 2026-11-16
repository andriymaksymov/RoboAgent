import logging
import re
from fnmatch import fnmatch
from pathlib import Path

from .registry import ToolError, tool
from .utils import MAX_MATCHES, cap_entries, clip_line, resolve_dir

logger = logging.getLogger(__name__)


@tool
def content_search(
    path: str,
    query: str,
    workdir: Path,
    agent_dir: Path | None,
    file_pattern: str | None = None,
) -> str:
    """Search file contents under a folder and its subfolders, similar to grep. Returns one 'path:line: text' entry per matching line (at most 100). Optionally filter searched files with a gitignore-style glob pattern.

    Args:
        path: Directory to search, relative to the workdir.
        query: Python regular expression to search for.
        file_pattern: Optional glob pattern limiting which files are searched, e.g. '*.py'.
    """
    root = resolve_dir(workdir, path, agent_dir)
    try:
        pattern = re.compile(query)
    except re.error as exc:
        raise ToolError(f"Invalid search pattern '{query}': {exc}") from exc

    results = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_dir():
            continue

        relative_parts = candidate.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue

        relative_path = candidate.relative_to(root).as_posix()
        if file_pattern and not (fnmatch(relative_path, file_pattern) or fnmatch(candidate.name, file_pattern)):
            continue

        try:
            with candidate.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if pattern.search(line):
                        results.append(f"{relative_path}:{line_number}: {clip_line(line.strip())}")
        except UnicodeDecodeError:
            logger.debug("Skipping non-text file during content search: %s", candidate)

    if not results:
        return "No matches."
    return cap_entries(results, MAX_MATCHES, "narrow 'query', 'path' or 'file_pattern'")
