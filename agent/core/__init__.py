from .content_search import content_search
from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_search import file_search
from .file_writer import write_file
from .folder_content import folder_content
from .git_add import git_add
from .git_commit import git_commit
from .git_diff import git_diff
from .git_log import git_log
from .git_pull import git_pull
from .git_restore import git_restore
from .git_status import git_status
from .registry import Tool, ToolRegistry
from .run_command import run_command

_STRING = {"type": "string"}
_REPO_PATH = {"repo_path": _STRING}

REGISTRY = ToolRegistry(
    [
        Tool(
            name="execute_python",
            description="Execute Python code in a subprocess.",
            properties={"code": _STRING},
            required=("code",),
            handler=lambda args, config: execute_python(args.get("code", ""), cwd=config.workdir),
        ),
        Tool(
            name="run_command",
            description=(
                "Run an allowed developer tool (e.g. pytest, pip, ruff) in AGENT_WORKDIR without a "
                "shell. Pass the command as a list of arguments, e.g. [\"pytest\", \"-q\"] or "
                "[\"ruff\", \"check\", \".\"]. Returns the exit code, stdout and stderr. "
                "Optional cwd (relative to AGENT_WORKDIR) and timeout in seconds (max 600)."
            ),
            properties={
                "command": {"type": "array", "items": _STRING},
                "cwd": _STRING,
                "timeout": {"type": "integer"},
            },
            required=("command",),
            log_arg="command",
            handler=lambda args, config: run_command(
                args.get("command", []),
                workdir=config.workdir,
                allowed_commands=config.allowed_commands,
                cwd=args.get("cwd", "."),
                timeout=args.get("timeout"),
            ),
        ),
        Tool(
            name="read_file",
            description="Read a local file from AGENT_WORKDIR.",
            properties={"path": _STRING},
            required=("path",),
            log_arg="path",
            handler=lambda args, config: read_file(args.get("path", ""), workdir=config.workdir),
        ),
        Tool(
            name="write_file",
            description="Create or fully overwrite a file in AGENT_WORKDIR.",
            properties={"path": _STRING, "content": _STRING},
            required=("path", "content"),
            log_arg="path",
            handler=lambda args, config: write_file(
                args.get("path", ""),
                args.get("content", ""),
                workdir=config.workdir,
            ),
        ),
        Tool(
            name="replace_in_file",
            description="Replace the first matching text block in a file in AGENT_WORKDIR.",
            properties={"path": _STRING, "target_text": _STRING, "replacement_text": _STRING},
            required=("path", "target_text", "replacement_text"),
            log_arg="path",
            handler=lambda args, config: replace_in_file(
                args.get("path", ""),
                args.get("target_text", ""),
                args.get("replacement_text", ""),
                workdir=config.workdir,
            ),
        ),
        Tool(
            name="folder_content",
            description=(
                "Return a list of all files and directories in the specified path with their "
                "names, sizes, and types. Ignore hidden files and directories."
            ),
            properties={"path": _STRING},
            required=("path",),
            log_arg="path",
            handler=lambda args, config: folder_content(args.get("path", ""), workdir=config.workdir),
        ),
        Tool(
            name="file_search",
            description=(
                "Search for files under a folder and its subfolders using a gitignore-style "
                "glob pattern."
            ),
            properties={"path": _STRING, "pattern": _STRING},
            required=("path", "pattern"),
            log_arg="path",
            handler=lambda args, config: file_search(
                args.get("path", ""),
                args.get("pattern", ""),
                workdir=config.workdir,
            ),
        ),
        Tool(
            name="content_search",
            description=(
                "Search file contents under a folder and its subfolders, similar to grep. "
                "Optionally filter searched files with a gitignore-style glob pattern."
            ),
            properties={"path": _STRING, "query": _STRING, "file_pattern": _STRING},
            required=("path", "query"),
            log_arg="path",
            handler=lambda args, config: content_search(
                args.get("path", ""),
                args.get("query", ""),
                workdir=config.workdir,
                file_pattern=args.get("file_pattern"),
            ),
        ),
        Tool(
            name="git_pull",
            description="Pull remote changes for a repository in AGENT_WORKDIR.",
            properties=_REPO_PATH,
            required=("repo_path",),
            log_arg="repo_path",
            handler=lambda args, config: git_pull(args.get("repo_path", ""), workdir=config.workdir),
        ),
        Tool(
            name="git_status",
            description="Return git status output for a repository in AGENT_WORKDIR.",
            properties=_REPO_PATH,
            required=("repo_path",),
            log_arg="repo_path",
            handler=lambda args, config: git_status(args.get("repo_path", ""), workdir=config.workdir),
        ),
        Tool(
            name="git_diff",
            description="Return git diff output for a repository in AGENT_WORKDIR.",
            properties={**_REPO_PATH, "rev": _STRING},
            required=("repo_path",),
            log_arg="repo_path",
            handler=lambda args, config: git_diff(
                args.get("repo_path", ""),
                workdir=config.workdir,
                rev=args.get("rev"),
            ),
        ),
        Tool(
            name="git_add",
            description="Stage a file or pathspec in a repository in AGENT_WORKDIR.",
            properties={**_REPO_PATH, "pathspec": _STRING},
            required=("repo_path", "pathspec"),
            log_arg="repo_path",
            handler=lambda args, config: git_add(
                args.get("repo_path", ""),
                args.get("pathspec", ""),
                workdir=config.workdir,
            ),
        ),
        Tool(
            name="git_restore",
            description=(
                "Discard uncommitted working tree changes for a file or pathspec in a repository "
                "in AGENT_WORKDIR, restoring it to the staged/last committed version. "
                "With staged=true, unstage the changes instead (working tree is kept). "
                "With source='HEAD', discard both staged and unstaged changes at once, reverting "
                "to the last commit (files staged but not in HEAD are removed). "
                "Use '.' to restore the whole repository. Untracked files are not removed."
            ),
            properties={
                **_REPO_PATH,
                "pathspec": _STRING,
                "staged": {"type": "boolean"},
                "source": _STRING,
            },
            required=("repo_path", "pathspec"),
            log_arg="repo_path",
            handler=lambda args, config: git_restore(
                args.get("repo_path", ""),
                args.get("pathspec", ""),
                workdir=config.workdir,
                staged=bool(args.get("staged", False)),
                source=args.get("source"),
            ),
        ),
        Tool(
            name="git_commit",
            description="Create a git commit in a repository in AGENT_WORKDIR.",
            properties={**_REPO_PATH, "message": _STRING},
            required=("repo_path", "message"),
            log_arg="repo_path",
            handler=lambda args, config: git_commit(
                args.get("repo_path", ""),
                args.get("message", ""),
                workdir=config.workdir,
            ),
        ),
        Tool(
            name="git_log",
            description="Return recent git log output for a repository in AGENT_WORKDIR.",
            properties={**_REPO_PATH, "max_count": {"type": "integer"}},
            required=("repo_path",),
            log_arg="repo_path",
            handler=lambda args, config: git_log(
                args.get("repo_path", ""),
                workdir=config.workdir,
                max_count=args.get("max_count", 10),
            ),
        ),
    ]
)

TOOLS = REGISTRY.schemas

__all__ = [
    "REGISTRY",
    "TOOLS",
    "Tool",
    "ToolRegistry",
    "content_search",
    "execute_python",
    "read_file",
    "replace_in_file",
    "file_search",
    "write_file",
    "folder_content",
    "git_pull",
    "git_status",
    "git_diff",
    "git_add",
    "git_restore",
    "git_commit",
    "git_log",
    "run_command",
]
