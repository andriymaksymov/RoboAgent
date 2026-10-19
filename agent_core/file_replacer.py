from pathlib import Path

from .paths import resolve_in_workdir


def replace_in_file(path: str, target_text: str, replacement_text: str, workdir: Path) -> str:
    """Replace the first matching text block in a file under AGENT_WORKDIR."""
    try:
        full_path = resolve_in_workdir(workdir, path)

        if not full_path.exists():
            return f"[Error]: '{full_path}' does not exist."

        content = full_path.read_text(encoding="utf-8")
        if target_text not in content:
            return f"[Error]: Target block not found in '{full_path}'."

        updated = content.replace(target_text, replacement_text, 1)
        full_path.write_text(updated, encoding="utf-8")
        return f"[Success]: Replaced text in '{full_path}'."
    except Exception as exc:
        return f"[Replace error]: {exc}"
