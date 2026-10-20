"""Built-in tools.

Each tool module registers itself in ``REGISTRY`` via the ``@tool`` decorator on import.
To add a tool, create a module with a decorated function and import it below.
"""

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
from .registry import REGISTRY, Tool, ToolError, ToolRegistry, tool
from .run_command import run_command

TOOLS = REGISTRY.schemas

__all__ = [
    "REGISTRY",
    "TOOLS",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "tool",
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
