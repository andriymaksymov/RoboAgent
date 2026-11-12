from collections.abc import Iterable
from pathlib import Path

from .registry import ToolError, tool
from .utils import open_repo


@tool
def git_checkout(
    repo_path: str,
    branch: str,
    workdir: Path,
    agent_dir: Path | None,
    protected_branches: Iterable[str],
    create: bool = False,
    start_point: str | None = None,
) -> str:
    """Switch a repository in the workdir to another branch, or create a new branch and switch to it. Protected branches (e.g. main) cannot be checked out. Uncommitted changes are carried over; git refuses the switch if they would be overwritten.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself, '@agent' for the agent's own repository).
        branch: Branch name to switch to (or to create).
        create: Create the branch first (fails if it already exists).
        start_point: Commit or branch the new branch starts from (only with create=true; default: the current HEAD).
    """
    if not branch or branch.startswith("-"):
        raise ToolError(f"Invalid branch name: '{branch}'.")
    if branch in set(protected_branches):
        raise ToolError(
            f"Branch '{branch}' is protected and cannot be checked out by the agent. "
            "Work on a feature branch instead."
        )
    if start_point and not create:
        raise ToolError("'start_point' is only valid together with create=true.")
    if start_point and start_point.startswith("-"):
        raise ToolError(f"Invalid start point: '{start_point}'.")

    repo = open_repo(workdir, repo_path, agent_dir)
    git = repo.git
    try:
        git.check_ref_format("--branch", branch)
    except Exception as exc:
        raise ToolError(f"Invalid branch name: '{branch}'.") from exc

    if create:
        git.switch("-c", branch, *([start_point] if start_point else []))
        origin = f" from '{start_point}'" if start_point else ""
        return f"[Success]: Created and switched to branch '{branch}'{origin} in '{repo_path}'."

    git.switch(branch)
    return f"[Success]: Switched to branch '{branch}' in '{repo_path}'."
