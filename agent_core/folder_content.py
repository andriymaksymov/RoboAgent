import os
from pathlib import Path

import json
from .paths import resolve_in_workdir

def folder_content(path: str, workdir: Path) -> str:
    """
    Return a list of all files and directories in the specified path with their names, sizes, and types. 
    Ignore hidden files and directories.
    """

    try:
        full_path = resolve_in_workdir(workdir, path)

        contents = []
        with os.scandir(full_path) as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue

                try:
                    entry_size = entry.stat().st_size
                    entry_type = 'directory' if entry.is_dir() else 'file'
                except OSError:
                    # Skip entries that cannot be stat'ed due to transient or permission errors.
                    continue

                contents.append(
                    {
                        'name': entry.name,
                        'size': entry_size,
                        'type': entry_type,
                    }
                )

        return json.dumps(contents)
    except FileNotFoundError:
        return f"[Error]: Path not found: '{path}'."
    except NotADirectoryError:
        return f"[Error]: Path is not a directory: '{path}'."
    except PermissionError:
        return f"[Error]: Permission denied for path: '{path}'."
    except Exception as exc:
        return f"[Error]: Failed to read folder content for '{path}': {exc}"
