from pathlib import Path

from .registry import tool
from .utils import resolve_in_workdir


@tool
def write_file(path: str, content: str, workdir: Path, agent_dir: Path | None) -> str:
    """Create or fully overwrite a file in the workdir.

    Args:
        path: File path relative to the workdir.
        content: Complete new file content.
    """
    full_path = resolve_in_workdir(workdir, path, agent_dir)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return f"[Success]: '{full_path}' written."
