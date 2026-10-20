from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from .registry import ToolError


def resolve_in_workdir(workdir: Path, user_path: str) -> Path:
    base = workdir.resolve()
    candidate = (base / user_path).resolve() if not Path(user_path).is_absolute() else Path(user_path).resolve()

    if base not in candidate.parents and candidate != base:
        raise ToolError(f"Path '{user_path}' is outside the workdir")

    return candidate


def resolve_dir(workdir: Path, path: str) -> Path:
    directory = resolve_in_workdir(workdir, path)
    if not directory.exists():
        raise ToolError(f"Path not found: '{path}'.")
    if not directory.is_dir():
        raise ToolError(f"Path is not a directory: '{path}'.")
    return directory


def open_repo(workdir: Path, repo_path: str = ".") -> Repo:
    resolved_path = resolve_in_workdir(workdir, repo_path)
    try:
        return Repo(resolved_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise ToolError(f"Invalid git repository: '{repo_path}'") from exc
