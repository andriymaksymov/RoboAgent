from pathlib import Path

from .registry import tool
from .utils import open_repo


@tool
def git_status(repo_path: str, workdir: Path, agent_dir: Path | None) -> str:
    """Return git status output for a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
    """
    return open_repo(workdir, repo_path, agent_dir).git.status()
