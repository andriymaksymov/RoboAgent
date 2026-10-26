import logging

from . import plugin as _plugin  # noqa: F401  side-effect: registers all plugin tools
from .branch_guard import find_protected_branch_repos
from .config import AgentConfig, load_config
from .core import REGISTRY
from .llm import LLMClient, LLMError, ToolResult, ToolSpec, create_client
from .system_prompt import load_system_prompt

logger = logging.getLogger(__name__)


def run_agent(
    user_prompt: str,
    config: AgentConfig | None = None,
    client: LLMClient | None = None,
) -> str:
    config = config or load_config()

    violations = find_protected_branch_repos(config.workdir, config.protected_branches)
    if violations:
        logger.error("Refusing to start: protected branch checked out (%s)", "; ".join(violations))
        return (
            "[Error]: Refusing to start. The following repositories are on a protected branch: "
            + "; ".join(violations)
            + ". Check out a feature branch before running the agent."
        )

    system_prompt = load_system_prompt(config.system_prompt)
    tools = [ToolSpec.from_schema(schema) for schema in REGISTRY.schemas]

    try:
        client = client or create_client(config.llm)
        client.start(system_prompt, user_prompt, tools)

        for iteration in range(config.max_iterations):
            logger.info("Iteration %s", iteration + 1)
            response = client.complete()
            if not response.tool_calls:
                return response.text

            if response.text:
                logger.info("Model: %s", response.text.strip())
            results = [
                ToolResult(call, REGISTRY.invoke(call.name, call.arguments, config))
                for call in response.tool_calls
            ]
            client.add_tool_results(results)
    except LLMError as exc:
        logger.error("%s", exc)
        return f"[Error]: {exc}"

    return "[Error]: Reached max tool iterations without a final answer."
