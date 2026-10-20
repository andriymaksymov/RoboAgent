from pathlib import Path

from .registry import tool
from .utils import open_repo


@tool
def git_log(repo_path: str, workdir: Path, max_count: int = 10) -> str:
    """Return recent git log output for a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        max_count: Maximum number of commits to show (default 10).
    """
    return open_repo(workdir, repo_path).git.log(f"--max-count={max_count}", "--oneline")
