from pathlib import Path

from .registry import tool
from .utils import open_repo


@tool
def git_diff(repo_path: str, workdir: Path, rev: str | None = None) -> str:
    """Return git diff output for a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        rev: Optional revision or range to diff against, e.g. 'HEAD~1' or '--cached'.
    """
    repo = open_repo(workdir, repo_path)
    return repo.git.diff(rev) if rev else repo.git.diff()
