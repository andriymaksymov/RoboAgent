import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo

logger = logging.getLogger(__name__)


def git_commit(repo_path: str, message: str, workdir: Path) -> str:
    """Create a git commit in a repository under AGENT_WORKDIR."""
    logger.info("Running git commit for repo_path=%s", repo_path)
    try:
        repo = open_repo(workdir, repo_path)
        commit = repo.index.commit(message)
        return f"[Success]: Created commit {commit.hexsha}."
    except (ValueError, GitCommandError) as exc:
        logger.exception("git commit failed for repo_path=%s", repo_path)
        return f"[Git commit error]: {exc}"
