from collections.abc import Iterable
from pathlib import Path

from git import Repo

from .registry import ToolError, tool
from .utils import open_repo, resolve_in_workdir


@tool
def git_clone(
    source: str,
    destination: str,
    workdir: Path,
    agent_dir: Path | None,
    protected_branches: Iterable[str],
    branch: str | None = None,
) -> str:
    """Clone a local repository (the workdir, a repository inside it, or the agent's own repository '@agent') into a new directory inside the workdir, e.g. to try a risky change on a copy. Remote URLs are not supported. The clone's 'origin' remote points at the source.

    Args:
        source: Repository path relative to the workdir ('.' for the workdir itself, '@agent' for the agent's own repository).
        destination: New directory relative to the workdir; it must not exist or must be empty.
        branch: Branch to check out in the clone (default: the source's current branch). Protected branches are not allowed.
    """
    if "://" in source or source.startswith("git@"):
        raise ToolError("Only local repositories can be cloned; remote URLs are not supported.")
    protected = set(protected_branches)
    if branch is not None and (not branch or branch.startswith("-")):
        raise ToolError(f"Invalid branch name: '{branch}'.")
    if branch in protected:
        raise ToolError(f"Branch '{branch}' is protected; clone a feature branch instead.")

    source_repo = open_repo(workdir, source, agent_dir)
    try:
        source_dir = Path(source_repo.working_tree_dir or source_repo.git_dir)
        if branch is None and not source_repo.head.is_detached:
            branch = source_repo.active_branch.name
    finally:
        source_repo.close()

    target = resolve_in_workdir(workdir, destination, agent_dir)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ToolError(f"Destination '{destination}' already exists and is not an empty directory.")

    options = {"branch": branch} if branch else {}
    clone = Repo.clone_from(str(source_dir), str(target), **options)
    try:
        current = None if clone.head.is_detached else clone.active_branch.name
    finally:
        clone.close()

    message = f"[Success]: Cloned '{source}' into '{destination}'"
    message += f" on branch '{current}'." if current else " (detached HEAD)."
    if current in protected:
        message += (
            f" Note: '{current}' is a protected branch; create a feature branch with "
            f"git_checkout(\"{destination}\", <name>, create=true) before changing it."
        )
    return message
