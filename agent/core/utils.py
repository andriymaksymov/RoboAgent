from pathlib import Path

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from .registry import ToolError

# Paths starting with this prefix address the agent's own repository (``agent_dir``)
# instead of the workdir, e.g. '@agent/agent/plugin/foo.py'.
AGENT_PREFIX = "@agent"


def _split_root(workdir: Path, user_path: str, agent_dir: Path | None) -> tuple[Path, str]:
    """Return the root directory a path refers to and the path relative to it."""
    head, sep, rest = user_path.replace("\\", "/").partition("/")
    if head != AGENT_PREFIX:
        return workdir, user_path
    if agent_dir is None:
        raise ToolError(f"'{AGENT_PREFIX}' paths are disabled: 'agent_dir' is not configured.")
    return agent_dir, rest if sep else "."


def resolve_in_workdir(workdir: Path, user_path: str, agent_dir: Path | None = None) -> Path:
    """Resolve a path inside the workdir, or inside agent_dir for '@agent/...' paths."""
    root, relative = _split_root(workdir, user_path, agent_dir)
    allowed = [root.resolve()]
    if root is workdir and agent_dir is not None:
        allowed.append(agent_dir.resolve())  # absolute paths may point into either root

    candidate = (allowed[0] / relative).resolve()  # an absolute 'relative' replaces the base
    if not any(candidate == base or base in candidate.parents for base in allowed):
        raise ToolError(f"Path '{user_path}' is outside the workdir")

    return candidate


def resolve_dir(workdir: Path, path: str, agent_dir: Path | None = None) -> Path:
    directory = resolve_in_workdir(workdir, path, agent_dir)
    if not directory.exists():
        raise ToolError(f"Path not found: '{path}'.")
    if not directory.is_dir():
        raise ToolError(f"Path is not a directory: '{path}'.")
    return directory


def open_repo(workdir: Path, repo_path: str = ".", agent_dir: Path | None = None) -> Repo:
    resolved_path = resolve_in_workdir(workdir, repo_path, agent_dir)
    try:
        return Repo(resolved_path)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise ToolError(f"Invalid git repository: '{repo_path}'") from exc
