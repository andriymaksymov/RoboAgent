from pathlib import Path

from .paths import resolve_in_workdir


def write_file(path: str, content: str, workdir: Path) -> str:
    """Create or fully overwrite a file under AGENT_WORKDIR."""
    try:
        full_path = resolve_in_workdir(workdir, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        return f"[Success]: '{full_path}' written."
    except Exception as exc:
        return f"[Write error]: {exc}"
