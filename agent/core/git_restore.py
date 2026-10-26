from pathlib import Path

from .registry import tool
from .utils import open_repo, resolve_in_workdir


@tool
def git_restore(
    repo_path: str,
    pathspec: str,
    workdir: Path,
    agent_dir: Path | None,
    staged: bool = False,
    source: str | None = None,
) -> str:
    """Discard uncommitted working tree changes for a file or pathspec in a repository in the workdir, restoring it to the staged/last committed version. With staged=true, unstage the changes instead (working tree is kept). With source='HEAD', discard both staged and unstaged changes at once, reverting to the last commit (files staged but not in HEAD are removed). Use '.' to restore the whole repository. Untracked files are not removed.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        pathspec: File path relative to the repository, or '.' for everything.
        staged: Only restore the index (unstage) and keep working tree changes.
        source: Revision to restore from, e.g. 'HEAD'.
    """
    repo = open_repo(workdir, repo_path, agent_dir)
    resolved_repo = resolve_in_workdir(workdir, repo_path, agent_dir)
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
