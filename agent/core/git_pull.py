from pathlib import Path

from .registry import tool
from .utils import open_repo


@tool
def git_pull(repo_path: str, workdir: Path) -> str:
    """Pull remote changes for a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
    """
    return open_repo(workdir, repo_path).git.pull() or "Already up to date."
