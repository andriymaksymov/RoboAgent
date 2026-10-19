import logging
from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

logger = logging.getLogger(__name__)


def resolve_in_workdir(workdir: Path, user_path: str) -> Path:
    base = workdir.resolve()
    candidate = (base / user_path).resolve() if not Path(user_path).is_absolute() else Path(user_path).resolve()

    if base not in candidate.parents and candidate != base:
        raise ValueError(f"Path '{user_path}' is outside AGENT_WORKDIR")

    return candidate


def open_repo(workdir: Path, repo_path: str = ".") -> Repo:
    resolved_path = resolve_in_workdir(workdir, repo_path)
    logger.info("Opening git repository at %s", resolved_path)
    try:
        return Repo(resolved_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        logger.exception("Failed to open git repository at %s", resolved_path)
        raise ValueError(f"Invalid git repository: '{repo_path}'") from exc
