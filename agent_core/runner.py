import json
from typing import Any, Dict, List, Iterable

from openai import OpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_message import ChatCompletionMessage

from . import TOOLS
from .config import load_config
from .execute_python import execute_python
from .file_reader import read_file
from .file_replacer import replace_in_file
from .file_writer import write_file
from .folder_content import folder_content
from .system_prompt import load_system_prompt


def _run_tool(tool_name: str, arguments: Dict[str, Any], config) -> str:
    print(f"Running tool: {tool_name} with arguments: {arguments}")  # Verbose logging

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
    if tool_name == "folder_content":
        return folder_content(arguments.get("path", ""), workdir=config.workdir)

    return f"[Error]: Unknown tool '{tool_name}'."


def _process_completion(message: ChatCompletionMessage, config, session):
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

    session.append(
        {
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": assistant_tool_calls,
        }
    )

    for tool_call in message.tool_calls:
        print(f"Calling '{tool_call.function.name}' ...")

        try:
            parsed_arguments = json.loads(tool_call.function.arguments or "{}")
            if isinstance(parsed_arguments, list):
                arguments = parsed_arguments[0] if parsed_arguments else {}
            elif isinstance(parsed_arguments, dict):
                arguments = parsed_arguments
            else:
                arguments = {}
        except (json.JSONDecodeError, TypeError):
            arguments = {}

        tool_output = _run_tool(tool_call.function.name, arguments, config)
        session.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": tool_output,
            }
        )


def run_agent(user_prompt: str) -> str:
    config = load_config()
    system_prompt = load_system_prompt(config.system_prompt_dir, config.system_prompt_file)

    client = OpenAI(
        api_key=config.api_key or "unused",
        base_url=config.base_url,
    )

    session: Iterable[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(20):
        print(f"Iteration {_+1}")

        response = client.chat.completions.create(
            model=config.model,
            messages=session,
            tools=TOOLS,
            temperature=0.1,
        )

        message = response.choices[0].message
        if message.tool_calls:
            _process_completion(message, config, session)
            continue

        return message.content or ""

    return "[Error]: Reached max tool iterations without a final answer."