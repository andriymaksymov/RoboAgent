import logging
from pathlib import Path

from git import GitCommandError

from .utils import open_repo, resolve_in_workdir

logger = logging.getLogger(__name__)


def git_restore(
    repo_path: str,
    pathspec: str,
    workdir: Path,
    staged: bool = False,
    source: str | None = None,
) -> str:
    """Discard working tree changes, or unstage changes, for a pathspec under AGENT_WORKDIR.

    With a source revision (e.g. HEAD), restore both the index and the working tree from it,
    unless staged is set, in which case only the index is restored.
    """
    logger.debug(
        "Running git restore for repo_path=%s pathspec=%s staged=%s source=%s",
        repo_path,
        pathspec,
        staged,
        source,
    )
    try:
        repo = open_repo(workdir, repo_path)
        resolved_repo = resolve_in_workdir(workdir, repo_path)
        resolved_target = resolve_in_workdir(resolved_repo, pathspec)
        relative_target = resolved_target.relative_to(resolved_repo).as_posix()

        args = []
        if source:
            args.append(f"--source={source}")
        if staged:
            args.append("--staged")
        elif source:
            args.extend(["--staged", "--worktree"])
        repo.git.restore(*args, "--", relative_target)

        if source and staged:
            action = f"Restored index from '{source}' for"
        elif source:
            action = f"Restored staged and working tree changes from '{source}' for"
        elif staged:
            action = "Unstaged"
        else:
            action = "Discarded working tree changes in"
        return f"[Success]: {action} '{relative_target}' in '{repo_path}'."
    except (ValueError, GitCommandError) as exc:
        logger.exception("git restore failed for repo_path=%s pathspec=%s", repo_path, pathspec)
        return f"[Git restore error]: {exc}"
