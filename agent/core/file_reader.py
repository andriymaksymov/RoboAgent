import logging
from pathlib import Path

from .utils import resolve_in_workdir

logger = logging.getLogger(__name__)


def read_file(path: str, workdir: Path) -> str:
    """Read a local file from AGENT_WORKDIR."""
    logger.debug("Reading file at path=%s", path)
    try:
        full_path = resolve_in_workdir(workdir, path)
        with full_path.open("r", encoding="utf-8") as handle:
            return handle.read()
    except Exception as exc:
        logger.exception("Failed to read file at path=%s", path)
        return f"[Read error]: {exc}"
