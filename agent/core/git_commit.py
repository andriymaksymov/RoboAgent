from pathlib import Path

from git import Actor

from .registry import tool
from .utils import open_repo


@tool
def git_commit(repo_path: str, message: str, workdir: Path) -> str:
    """Create a git commit in a repository in the workdir.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        message: Commit message (Conventional Commits style).
    """
    commit = open_repo(workdir, repo_path).index.commit(
        message,
        committer=Actor("RoboAgent", "roboagent@andriy-maksymov.de"),
    )
    return f"[Success]: Created commit {commit.hexsha}."
