import json
import logging
from typing import Any, Dict, List

from openai import OpenAI
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from .branch_guard import find_protected_branch_repos
from .config import load_config
from .core import REGISTRY
from .system_prompt import load_system_prompt

logger = logging.getLogger(__name__)


def _run_tool(tool_name: str, arguments: Dict[str, Any], config) -> str:
    tool = REGISTRY.get(tool_name)
    if tool is None:
        return f"[Error]: Unknown tool '{tool_name}'."

    if tool.log_arg:
        logger.info("Running %s %s ...", tool_name, arguments.get(tool.log_arg, ""))
    else:
        logger.info("Running %s ...", tool_name)

    try:
        return tool.handler(arguments, config)
    except Exception as exc:
        logger.exception("Tool %s failed", tool_name)
        return f"[Error]: Tool '{tool_name}' failed: {exc}"


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

    violations = find_protected_branch_repos(config.workdir, config.protected_branches)
    if violations:
        logger.error("Refusing to start: protected branch checked out (%s)", "; ".join(violations))
        return (
            "[Error]: Refusing to start. The following repositories are on a protected branch: "
            + "; ".join(violations)
            + ". Check out a feature branch before running the agent."
        )

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
            tools=REGISTRY.schemas,
            temperature=0.1,
        )

        message = response.choices[0].message
        if message.tool_calls:
            _process_completion(message, config, session)
            continue

        return message.content or ""

    return "[Error]: Reached max tool iterations without a final answer."
