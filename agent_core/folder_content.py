import os
from pathlib import Path

import json
from .paths import resolve_in_workdir

def folder_content(path: str, workdir: Path) -> str:
    """
    Return a list of all files and directories in the specified path with their names, sizes, and types. 
    Ignore hidden files and directories.
    """

    full_path = resolve_in_workdir(workdir, path)

    contents = []
    for entry in os.scandir(full_path):
        if not entry.name.startswith('.'):  # Ignore hidden files and directories
            contents.append({
                'name': entry.name,
                'size': entry.stat().st_size,
                'type': 'directory' if entry.is_dir() else 'file'
            })
    return json.dumps(contents)
