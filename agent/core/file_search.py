import json
import logging
from pathlib import Path
from fnmatch import fnmatch

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)


def file_search(path: str, pattern: str, workdir: Path) -> str:
    """Search for files under a directory tree using glob-style patterns."""
    logger.debug("Searching files at path=%s with pattern=%s", path, pattern)
    try:
        root = resolve_in_workdir(workdir, path)
        if not root.exists():
            return f"[Error]: Path not found: '{path}'."
        if not root.is_dir():
            return f"[Error]: Path is not a directory: '{path}'.'"

        matches = []
        for candidate in root.rglob("*"):
            if any(part.startswith(".") for part in candidate.relative_to(root).parts):
                continue
            if candidate.is_dir():
                continue

            relative_path = candidate.relative_to(root).as_posix()
            if fnmatch(relative_path, pattern) or fnmatch(candidate.name, pattern):
                matches.append(relative_path)

        return json.dumps(matches)
    except Exception as exc:
        logger.exception("Failed file search at path=%s with pattern=%s", path, pattern)
        return f"[Error]: Failed to search files in '{path}': {exc}"
