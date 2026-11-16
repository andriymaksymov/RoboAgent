from pathlib import Path

from .registry import tool
from .utils import MAX_ENTRIES, cap_entries, open_repo


@tool
def git_ls_files(
    repo_path: str, workdir: Path, agent_dir: Path | None, pathspec: str | None = None
) -> str:
    """List the files tracked by git in a repository in the workdir, similar to `git ls-files` (at most 200; use pathspec to narrow).

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        pathspec: Optional path or pattern to restrict the listing (e.g. 'src/' or '*.py').
    """
    repo = open_repo(workdir, repo_path, agent_dir)
    output = repo.git.ls_files(pathspec) if pathspec else repo.git.ls_files()
    return cap_entries(output.splitlines(), MAX_ENTRIES, "narrow with 'pathspec', e.g. 'src/'")
