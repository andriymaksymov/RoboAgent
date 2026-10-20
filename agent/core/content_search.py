import json
import logging
import re
from fnmatch import fnmatch
from pathlib import Path

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)


def content_search(path: str, query: str, workdir: Path, file_pattern: str | None = None) -> str:
    """Search file contents under a directory tree and return grep-like matches."""
    logger.debug(
        "Searching content at path=%s with query=%s and file_pattern=%s",
        path,
        query,
        file_pattern,
    )
    try:
        root = resolve_in_workdir(workdir, path)
        if not root.exists():
            return f"[Error]: Path not found: '{path}'."
        if not root.is_dir():
            return f"[Error]: Path is not a directory: '{path}'."

        pattern = re.compile(query)
        results = []

        for candidate in root.rglob("*"):
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
                        submatches = [
                            {
                                "match": match.group(0),
                                "start": match.start(),
                                "end": match.end(),
                            }
                            for match in pattern.finditer(line)
                        ]
                        if submatches:
                            results.append(
                                {
                                    "path": relative_path,
                                    "line_number": line_number,
                                    "line": line.rstrip("\n"),
                                    "submatches": submatches,
                                }
                            )
            except UnicodeDecodeError:
                logger.debug("Skipping non-text file during content search: %s", candidate)
                continue

        return json.dumps(results)
    except re.error as exc:
        logger.exception("Invalid regex for content search query=%s", query)
        return f"[Error]: Invalid search pattern '{query}': {exc}"
    except Exception as exc:
        logger.exception("Failed content search at path=%s with query=%s", path, query)
        return f"[Error]: Failed to search file contents in '{path}': {exc}"
