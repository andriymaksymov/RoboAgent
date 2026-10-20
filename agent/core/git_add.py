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

        modified_files = {item.a_path for item in repo.index.diff(None)}
        untracked_files = set(repo.untracked_files)
        tracked_candidates = {str(relative_target), relative_target.as_posix()}

        if not any(candidate in modified_files or candidate in untracked_files for candidate in tracked_candidates):
            return f"[Git add error]: '{relative_target}' is neither modified nor untracked in '{repo_path}'."

        repo.index.add([str(relative_target)])
        return f"[Success]: Staged '{relative_target}' in '{repo_path}'."
    except (ValueError, GitCommandError) as exc:
        logger.exception("git add failed for repo_path=%s pathspec=%s", repo_path, pathspec)
        return f"[Git add error]: {exc}"
