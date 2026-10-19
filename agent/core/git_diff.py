import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo

logger = logging.getLogger(__name__)


def git_diff(repo_path: str, workdir: Path, rev: str | None = None) -> str:
    """Return git diff output for a repository under AGENT_WORKDIR."""
    logger.debug("Running git diff for repo_path=%s rev=%s", repo_path, rev)
    try:
        repo = open_repo(workdir, repo_path)
        return repo.git.diff(rev) if rev else repo.git.diff()
    except (ValueError, GitCommandError) as exc:
        logger.exception("git diff failed for repo_path=%s rev=%s", repo_path, rev)
        return f"[Git diff error]: {exc}"
