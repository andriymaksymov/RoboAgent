import json
import logging
from typing import Any, Dict, List

from openai import OpenAI
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from .config import load_config
from .core import (
    TOOLS,
    content_search,
    execute_python,
    file_search,
    folder_content,
    git_add,
    git_commit,
    git_diff,
    git_log,
    git_pull,
    git_status,
    read_file,
    replace_in_file,
    write_file,
)
from .system_prompt import load_system_prompt

logger = logging.getLogger(__name__)


def _run_tool(tool_name: str, arguments: Dict[str, Any], config) -> str:
    if tool_name == "execute_python":
        logger.info("Running python...")
        return execute_python(
            arguments.get("code", ""), 
            cwd=config.workdir
        )
    if tool_name == "read_file":
        logger.info("Reading %s ...", arguments.get("path", ""))
        return read_file(
            arguments.get("path", ""), 
            workdir=config.workdir
        )
    if tool_name == "write_file":
        logger.info("Writing %s ...", arguments.get("path", ""))
        return write_file(
            arguments.get("path", ""),
            arguments.get("content", ""),
            workdir=config.workdir,
        )
    if tool_name == "replace_in_file":
        logger.info("Replacing text in %s ...", arguments.get("path", ""))
        return replace_in_file(
            arguments.get("path", ""),
            arguments.get("target_text", ""),
            arguments.get("replacement_text", ""),
            workdir=config.workdir,
        )
    if tool_name == "folder_content":
        logger.info("Listing folder content %s...", arguments.get("path", ""))
        return folder_content(
            arguments.get("path", ""), 
            workdir=config.workdir
        )
    if tool_name == "file_search":
        logger.info("Searching files in %s ...", arguments.get("path", ""))
        return file_search(
            arguments.get("path", ""),
            arguments.get("pattern", ""),
            workdir=config.workdir,
        )
    if tool_name == "content_search":
        logger.info("Content search in %s ...", arguments.get("path", ""))
        return content_search(
            arguments.get("path", ""),
            arguments.get("query", ""),
            workdir=config.workdir,
            file_pattern=arguments.get("file_pattern"),
        )
    if tool_name == "git_pull":
        logger.info("git pull %s ...", arguments.get("repo_path", ""))
        return git_pull(
            arguments.get("repo_path", ""),
            workdir=config.workdir,
        )
    if tool_name == "git_status":
        logger.info("git status %s ...", arguments.get("repo_path", ""))
        return git_status(
            arguments.get("repo_path", ""), 
            workdir=config.workdir
        )
    if tool_name == "git_diff":
        logger.info("git diff %s ...", arguments.get("repo_path", ""))
        return git_diff(
            arguments.get("repo_path", ""),
            workdir=config.workdir,
            rev=arguments.get("rev"),
        )
    if tool_name == "git_add":
        logger.info("git add %s ...", arguments.get("repo_path", ""))
        return git_add(
            arguments.get("repo_path", ""),
            arguments.get("pathspec", ""),
            workdir=config.workdir,
        )
    if tool_name == "git_commit":
        logger.info("git commit %s ...", arguments.get("repo_path", ""))
        return git_commit(
            arguments.get("repo_path", ""),
            arguments.get("message", ""),
            workdir=config.workdir,
        )
    if tool_name == "git_log":
        logger.info("git log %s ...", arguments.get("repo_path", ""))
        return git_log(
            arguments.get("repo_path", ""),
            workdir=config.workdir,
            max_count=arguments.get("max_count", 10),
        )

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

    session: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for iteration in range(config.max_iterations):
        logger.info("Iteration %s", iteration + 1)

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
