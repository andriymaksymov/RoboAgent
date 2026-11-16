"""git_merge_from — merge a branch of another local repository (e.g. a sub-agent's copy).

Fetches ``branch`` from the local repository ``source_repo`` and merges it into the
current branch of ``repo_path`` with a merge commit, so the whole change can be reverted
in one step. Conflicts are reported by file; they are either left in place to resolve
(edit, ``git_add``, ``git_commit``) or aborted with ``abort_on_conflict=true``.
"""

from collections.abc import Iterable
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo

from agent.core.registry import ToolError, tool
from agent.core.utils import open_repo, resolve_dir


def _conflicted_files(repo: Repo) -> list[str]:
    output = repo.git.diff("--name-only", "--diff-filter=U")
    return [line for line in output.splitlines() if line.strip()]


@tool
def git_merge_from(
    repo_path: str,
    source_repo: str,
    branch: str,
    workdir: Path,
    agent_dir: Path | None,
    protected_branches: Iterable[str],
    abort_on_conflict: bool = False,
) -> str:
    """Fetch a branch from another local repository (e.g. a sub-agent's copy in '.subagents/<id>') and merge it into the current branch of a repository, with a merge commit. Reports conflicting files.

    Args:
        repo_path: Repository to merge into, relative to the workdir ('.' for the workdir itself, '@agent' for the agent's own repository).
        source_repo: Local repository to fetch from, relative to the workdir, e.g. '.subagents/20250101-120000-1'.
        branch: Branch in source_repo to merge, e.g. 'sub/20250101-120000-1'.
        abort_on_conflict: On conflicts, abort the merge and leave the repository unchanged (default false: keep the conflicts to resolve them, then git_add and git_commit).
    """
    if not branch or branch.startswith("-") or any(c.isspace() for c in branch):
        raise ToolError(f"Invalid branch name: '{branch}'.")

    source_dir = resolve_dir(workdir, source_repo, agent_dir)
    try:
        Repo(source_dir).close()
    except InvalidGitRepositoryError as exc:
        raise ToolError(f"Invalid git repository: '{source_repo}'") from exc

    repo = open_repo(workdir, repo_path, agent_dir)
    try:
        if repo.head.is_detached:
            raise ToolError(f"'{repo_path}' is in detached HEAD state; check out a branch first.")
        current = repo.active_branch.name
        if current in set(protected_branches):
            raise ToolError(
                f"'{repo_path}' is on protected branch '{current}'; switch to a feature branch first."
            )
        if (Path(repo.git_dir) / "MERGE_HEAD").exists():
            if abort_on_conflict:
                repo.git.merge("--abort")
                return f"[Success]: Aborted the merge in progress in '{repo_path}'; it is back at '{current}'."
            raise ToolError(
                f"A merge is in progress in '{repo_path}': resolve the conflicts, git_add and "
                f"git_commit, or call git_merge_from again with abort_on_conflict=true to abort it."
            )
        if repo.is_dirty(untracked_files=False):
            raise ToolError(
                f"'{repo_path}' has uncommitted changes; commit or restore them before merging."
            )

        try:
            repo.git.fetch(str(source_dir), branch)
        except GitCommandError as exc:
            raise ToolError(
                f"Could not fetch '{branch}' from '{source_repo}': {exc.stderr.strip()}"
            ) from exc

        message = f"merge: {branch} from {Path(source_repo).as_posix()}"
        try:
            output = repo.git.merge("--no-ff", "--no-edit", "-m", message, "FETCH_HEAD")
        except GitCommandError as exc:
            conflicts = _conflicted_files(repo)
            if not conflicts:
                raise ToolError(
                    f"Merge failed: {(exc.stderr or exc.stdout or str(exc)).strip()}"
                ) from exc
            files = "\n".join(f"  {name}" for name in conflicts)
            if abort_on_conflict:
                repo.git.merge("--abort")
                return (
                    f"[Conflict]: merging '{branch}' into '{current}' conflicts in {len(conflicts)} "
                    f"file(s); the merge was aborted and '{repo_path}' is unchanged:\n{files}"
                )
            return (
                f"[Conflict]: merging '{branch}' into '{current}' conflicts in {len(conflicts)} file(s):\n"
                f"{files}\nResolve the conflict markers in these files, then git_add them and "
                f"git_commit to conclude the merge (or call git_merge_from again with "
                f"abort_on_conflict=true to abort it)."
            )

        if "Already up to date" in output:
            return f"[Success]: '{current}' is already up to date with '{branch}' from '{source_repo}'."
        stat = repo.git.diff("--stat", "HEAD^1", "HEAD")
        return f"[Success]: Merged '{branch}' from '{source_repo}' into '{current}'.\n{stat}"
    finally:
        repo.close()
