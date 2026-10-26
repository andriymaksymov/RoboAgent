import logging
from pathlib import Path
from typing import Iterable, Iterator

from git import InvalidGitRepositoryError, Repo

logger = logging.getLogger(__name__)


def _candidate_repo_dirs(workdir: Path, extra_dirs: Iterable[Path]) -> Iterator[Path]:
    yield workdir
    for entry in sorted(workdir.iterdir()):
        if entry.is_dir() and not entry.name.startswith(".") and (entry / ".git").exists():
            yield entry
    yield from extra_dirs


def find_protected_branch_repos(
    workdir: Path, protected_branches: Iterable[str], extra_dirs: Iterable[Path] = ()
) -> list[str]:
    """Return '<repo>: <branch>' entries for repos checked out on a protected branch.

    Checks the workdir, its direct subfolders and ``extra_dirs`` (e.g. the agent's own repo).
    """
    protected = set(protected_branches)
    violations = []
    seen = set()
    for repo_dir in _candidate_repo_dirs(workdir, extra_dirs):
        if repo_dir.resolve() in seen:
            continue
        seen.add(repo_dir.resolve())
        try:
            repo = Repo(repo_dir)
        except InvalidGitRepositoryError:
            continue

        try:
            if repo.head.is_detached:
                continue
            branch = repo.active_branch.name
        finally:
            repo.close()

        logger.debug("Repository %s is on branch %s", repo_dir, branch)
        if branch in protected:
            violations.append(f"{repo_dir}: {branch}")
    return violations
