from pathlib import Path

from .registry import tool
from .utils import MAX_TEXT_CHARS, clip_text, open_repo


@tool
def git_diff(
    repo_path: str,
    workdir: Path,
    agent_dir: Path | None,
    rev: str | None = None,
    path: str | None = None,
    stat: bool = False,
) -> str:
    """Return git diff output for a repository in the workdir (at most about 16,000 characters). For large changes, start with stat=true and then diff single files with path.

    Args:
        repo_path: Repository path relative to the workdir ('.' for the workdir itself).
        rev: Optional revision or range to diff against, e.g. 'HEAD~1' or '--cached'.
        path: Optional file or directory (relative to the repository) to limit the diff to.
        stat: Show only a summary of changed files and line counts.
    """
    repo = open_repo(workdir, repo_path, agent_dir)
    args = [rev] if rev else []
    if stat:
        args.append("--stat")
    if path:
        args += ["--", path]
    output = repo.git.diff(*args)
    if not output:
        return "No differences."
    return clip_text(output, MAX_TEXT_CHARS, "use stat=true and diff single files with 'path'")
