from pathlib import Path

from .registry import ToolError, tool
from .utils import resolve_in_workdir


@tool
def replace_in_file(path: str, target_text: str, replacement_text: str, workdir: Path) -> str:
    """Replace the first matching text block in a file in the workdir.

    Args:
        path: File path relative to the workdir.
        target_text: Exact text to replace.
        replacement_text: Text to insert instead.
    """
    full_path = resolve_in_workdir(workdir, path)
    if not full_path.exists():
        raise ToolError(f"'{full_path}' does not exist.")

    content = full_path.read_text(encoding="utf-8")
    if target_text not in content:
        raise ToolError(f"Target block not found in '{full_path}'.")

    full_path.write_text(content.replace(target_text, replacement_text, 1), encoding="utf-8")
    return f"[Success]: Replaced text in '{full_path}'."
