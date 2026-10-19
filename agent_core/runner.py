import json
from typing import Any, Dict, List

from openai import OpenAI

from .config import load_config
from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_writer import write_file
from .system_prompt import load_system_prompt


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
]


def _run_tool(tool_name: str, arguments: Dict[str, Any], config) -> str:
    if tool_name == "execute_python":
        return execute_python(arguments.get("code", ""), cwd=config.workdir)
    if tool_name == "read_file":
        return read_file(arguments.get("path", ""), workdir=config.workdir)
    if tool_name == "write_file":
        return write_file(arguments.get("path", ""), arguments.get("content", ""), workdir=config.workdir)
    if tool_name == "replace_in_file":
        return replace_in_file(
            arguments.get("path", ""),
            arguments.get("target_text", ""),
            arguments.get("replacement_text", ""),
            workdir=config.workdir,
        )
    return f"[Error]: Unknown tool '{tool_name}'."


def run_agent(user_prompt: str) -> str:
    config = load_config()
    system_prompt = load_system_prompt(config.system_prompt_dir, config.system_prompt_file)

    client = OpenAI(
        api_key=config.api_key or "unused",
        base_url=config.base_url,
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(20):
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=TOOLS,
            temperature=0.1,
        )
        message = response.choices[0].message

        if message.tool_calls:
            assistant_tool_calls = []
            for tool_call in message.tool_calls:
                assistant_tool_calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                )

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": assistant_tool_calls,
                }
            )

            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                tool_output = _run_tool(tool_call.function.name, arguments, config)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": tool_output,
                    }
                )
            continue

        return message.content or ""

    return "[Error]: Reached max tool iterations without a final answer."
