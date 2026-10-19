from pathlib import Path

from .paths import resolve_in_workdir


def read_file(path: str, workdir: Path) -> str:
    """Read a local file from AGENT_WORKDIR."""
    try:
        full_path = resolve_in_workdir(workdir, path)
        with full_path.open("r", encoding="utf-8") as handle:
            return handle.read()
    except Exception as exc:
        return f"[Read error]: {exc}"
