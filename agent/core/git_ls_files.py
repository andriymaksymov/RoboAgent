from pathlib import Path

from .registry import tool
from .utils import open_repo


@tool
def git_ls_files(
    repo_path: str, workdir: Path, agent_dir: Path | None, pathspec: str | None = None
) -> str:
    """List all files tracked by git in a repository in the workdir, similar to `git ls-files`.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        pathspec: Optional path or pattern to restrict the listing (e.g. 'src/' or '*.py').
    """
    repo = open_repo(workdir, repo_path, agent_dir)
    return repo.git.ls_files(pathspec) if pathspec else repo.git.ls_files()
