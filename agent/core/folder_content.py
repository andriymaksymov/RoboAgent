import json
import logging
import os
from pathlib import Path

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)


def folder_content(path: str, workdir: Path) -> str:
    """
    Return a list of all files and directories in the specified path with their names, sizes, and types.
    Ignore hidden files and directories.
    """
    logger.info("Listing folder content at path=%s", path)
    try:
        full_path = resolve_in_workdir(workdir, path)

        contents = []
        with os.scandir(full_path) as entries:
            for entry in entries:
                if entry.name.startswith("."):
                    continue

                try:
                    entry_size = entry.stat().st_size
                    entry_type = "directory" if entry.is_dir() else "file"
                except OSError:
                    continue

                contents.append(
                    {
                        "name": entry.name,
                        "size": entry_size,
                        "type": entry_type,
                    }
                )

        return json.dumps(contents)
    except FileNotFoundError:
        logger.exception("Path not found while listing folder content at path=%s", path)
        return f"[Error]: Path not found: '{path}'."
    except NotADirectoryError:
        logger.exception("Non-directory path while listing folder content at path=%s", path)
        return f"[Error]: Path is not a directory: '{path}'."
    except PermissionError:
        logger.exception("Permission denied while listing folder content at path=%s", path)
        return f"[Error]: Permission denied for path: '{path}'."
    except Exception as exc:
        logger.exception("Failed to list folder content at path=%s", path)
        return f"[Error]: Failed to read folder content for '{path}': {exc}"
