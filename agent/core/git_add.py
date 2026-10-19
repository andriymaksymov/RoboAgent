import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo, resolve_in_workdir

logger = logging.getLogger(__name__)


def git_add(repo_path: str, pathspec: str, workdir: Path) -> str:
    """Stage a file or pathspec in a repository under AGENT_WORKDIR."""
    logger.debug("Running git add for repo_path=%s pathspec=%s", repo_path, pathspec)
    try:
        repo = open_repo(workdir, repo_path)
        resolved_repo = resolve_in_workdir(workdir, repo_path)
        resolved_target = resolve_in_workdir(resolved_repo, pathspec)
        relative_target = resolved_target.relative_to(resolved_repo)
        repo.index.add([str(relative_target)])
        return f"[Success]: Staged '{relative_target}' in '{repo_path}'."
    except (ValueError, GitCommandError) as exc:
        logger.exception("git add failed for repo_path=%s pathspec=%s", repo_path, pathspec)
        return f"[Git add error]: {exc}"
