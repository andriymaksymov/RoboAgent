"""Built-in tools.

Each tool lives in its own module, named after the tool, and registers itself in
``REGISTRY`` via the ``@tool`` decorator on import. To add a tool, create a module with a
decorated function and import it below. Helpers shared by several tools belong in
``utils.py`` (subprocess handling in ``process.py``), never in a tool module.
"""

from .content_search import content_search
from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_search import file_search
from .file_writer import write_file
from .folder_content import folder_content
from .format_code import format_code
from .git_add import git_add
from .git_checkout import git_checkout
from .git_clone import git_clone
from .git_commit import git_commit
from .git_diff import git_diff
from .git_log import git_log
from .git_ls_files import git_ls_files
from .git_pull import git_pull
from .git_restore import git_restore
from .git_status import git_status
from .lint import lint
from .pip_install import pip_install
from .pip_list import pip_list
from .pip_show import pip_show
from .registry import REGISTRY, Tool, ToolError, ToolRegistry, tool
from .run_command import run_command
from .run_tests import run_tests

TOOLS = REGISTRY.schemas

__all__ = [
    "REGISTRY",
    "TOOLS",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "content_search",
    "execute_python",
    "file_search",
    "folder_content",
    "format_code",
    "git_add",
    "git_checkout",
    "git_clone",
    "git_commit",
    "git_diff",
    "git_log",
    "git_ls_files",
    "git_pull",
    "git_restore",
    "git_status",
    "lint",
    "pip_install",
    "pip_list",
    "pip_show",
    "read_file",
    "replace_in_file",
    "run_command",
    "run_tests",
    "tool",
    "write_file",
]
