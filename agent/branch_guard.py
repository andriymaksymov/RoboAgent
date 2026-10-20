import logging
from pathlib import Path
from typing import Iterable, Iterator

from git import InvalidGitRepositoryError, Repo

logger = logging.getLogger(__name__)


def _candidate_repo_dirs(workdir: Path) -> Iterator[Path]:
    yield workdir
    for entry in sorted(workdir.iterdir()):
        if entry.is_dir() and not entry.name.startswith(".") and (entry / ".git").exists():
            yield entry


def find_protected_branch_repos(workdir: Path, protected_branches: Iterable[str]) -> list[str]:
    """Return '<repo>: <branch>' entries for repos in workdir checked out on a protected branch."""
    protected = set(protected_branches)
    violations = []
    for repo_dir in _candidate_repo_dirs(workdir):
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
