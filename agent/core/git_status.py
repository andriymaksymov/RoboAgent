import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo

logger = logging.getLogger(__name__)


def git_status(repo_path: str, workdir: Path) -> str:
    """Return git status output for a repository under AGENT_WORKDIR."""
    logger.debug("Running git status for repo_path=%s", repo_path)
    try:
        repo = open_repo(workdir, repo_path)
        return repo.git.status()
    except (ValueError, GitCommandError) as exc:
        logger.exception("git status failed for repo_path=%s", repo_path)
        return f"[Git status error]: {exc}"
