import logging
from pathlib import Path

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)


def write_file(path: str, content: str, workdir: Path) -> str:
    """Create or fully overwrite a file under AGENT_WORKDIR."""
    logger.info("Writing file at path=%s", path)
    try:
        full_path = resolve_in_workdir(workdir, path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with full_path.open("w", encoding="utf-8") as handle:
            handle.write(content)
        return f"[Success]: '{full_path}' written."
    except Exception as exc:
        logger.exception("Failed to write file at path=%s", path)
        return f"[Write error]: {exc}"
