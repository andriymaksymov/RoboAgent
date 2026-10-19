from pathlib import Path


def resolve_in_workdir(workdir: Path, user_path: str) -> Path:
    base = workdir.resolve()
    candidate = (base / user_path).resolve() if not Path(user_path).is_absolute() else Path(user_path).resolve()

    if base not in candidate.parents and candidate != base:
        raise ValueError(f"Path '{user_path}' is outside AGENT_WORKDIR")

    return candidate
