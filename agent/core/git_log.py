import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo

logger = logging.getLogger(__name__)


def git_log(repo_path: str, workdir: Path, max_count: int = 10) -> str:
    """Return recent git log output for a repository under AGENT_WORKDIR."""
    logger.debug("Running git log for repo_path=%s max_count=%s", repo_path, max_count)
    try:
        repo = open_repo(workdir, repo_path)
        return repo.git.log(f"--max-count={max_count}", "--oneline")
    except (ValueError, GitCommandError) as exc:
        logger.exception("git log failed for repo_path=%s", repo_path)
        return f"[Git log error]: {exc}"
