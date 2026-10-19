from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_writer import write_file
from .folder_content import folder_content

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_python",
            "description": "Execute Python code in a subprocess.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"}
                },
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
                "properties": {
                    "path": {"type": "string"}
                },
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
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"],
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
    "folder_content"
]
