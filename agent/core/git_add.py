from pathlib import Path

from .registry import ToolError, tool
from .utils import open_repo, resolve_in_workdir


@tool
def git_add(repo_path: str, pathspec: str, workdir: Path, agent_dir: Path | None) -> str:
    """Stage a file or pathspec in a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        pathspec: File path relative to the repository.
    """
    repo = open_repo(workdir, repo_path, agent_dir)
    resolved_repo = resolve_in_workdir(workdir, repo_path, agent_dir)
    resolved_target = resolve_in_workdir(resolved_repo, pathspec)
    relative_target = resolved_target.relative_to(resolved_repo)

    modified_files = {item.a_path for item in repo.index.diff(None)}
    untracked_files = set(repo.untracked_files)
    tracked_candidates = {str(relative_target), relative_target.as_posix()}

    if not any(candidate in modified_files or candidate in untracked_files for candidate in tracked_candidates):
        raise ToolError(f"'{relative_target}' is neither modified nor untracked in '{repo_path}'.")

    repo.index.add([str(relative_target)])
    return f"[Success]: Staged '{relative_target}' in '{repo_path}'."
