from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_writer import write_file
from .folder_content import folder_content
from .git_add import git_add
from .git_commit import git_commit
from .git_diff import git_diff
from .git_log import git_log
from .git_pull import git_pull
from .git_status import git_status

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Execute Python code in a subprocess.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a local file from AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or fully overwrite a file in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "Replace the first matching text block in a file in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "target_text": {"type": "string"},
                    "replacement_text": {"type": "string"},
                },
                "required": ["path", "target_text", "replacement_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "folder_content",
            "description": "Return a list of all files and directories in the specified path with their names, sizes, and types. Ignore hidden files and directories.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_pull",
            "description": "Pull remote changes for a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Return git status output for a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {"repo_path": {"type": "string"}},
                "required": ["repo_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Return git diff output for a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "rev": {"type": "string"},
                },
                "required": ["repo_path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_add",
            "description": "Stage a file or pathspec in a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "pathspec": {"type": "string"},
                },
                "required": ["repo_path", "pathspec"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Create a git commit in a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["repo_path", "message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Return recent git log output for a repository in AGENT_WORKDIR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "max_count": {"type": "integer"},
                },
                "required": ["repo_path"],
                "additionalProperties": False,
            },
        },
    },
]

__all__ = [
    "TOOLS",
    "execute_python",
    "read_file",
    "replace_in_file",
    "write_file",
    "folder_content",
    "git_pull",
    "git_status",
    "git_diff",
    "git_add",
    "git_commit",
    "git_log",
]
