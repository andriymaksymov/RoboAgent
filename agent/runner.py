import logging

from . import plugin as _plugin  # noqa: F401  side-effect: registers all plugin tools
from .branch_guard import find_protected_branch_repos
from .config import AgentConfig, load_config
from .core import REGISTRY
from .llm import LLMClient, LLMError, ToolResult, ToolSpec, create_client
from .plugin_loader import PLUGINS, PluginEvent, PluginReport
from .system_prompt import load_system_prompt

logger = logging.getLogger(__name__)


def run_agent(
    user_prompt: str,
    config: AgentConfig | None = None,
    client: LLMClient | None = None,
) -> str:
    config = config or load_config()

    extra_dirs = [config.agent_dir] if config.agent_dir else []
    violations = find_protected_branch_repos(config.workdir, config.protected_branches, extra_dirs)
    if violations:
        logger.error("Refusing to start: protected branch checked out (%s)", "; ".join(violations))
        return (
            "[Error]: Refusing to start. The following repositories are on a protected branch: "
            + "; ".join(violations)
            + ". Check out a feature branch before running the agent."
        )

    system_prompt = load_system_prompt(config.system_prompt)
    report = PluginReport(PLUGINS.failures)
    report.add(PLUGINS.refresh())  # plugins changed since import, e.g. between two runs

    try:
        client = client or create_client(config.llm)
        client.start(system_prompt, user_prompt, _tool_specs())

        for iteration in range(config.max_iterations):
            logger.info("Iteration %s", iteration + 1)
            response = client.complete()
            if not response.tool_calls:
                return _with_report(response.text, report)

            if response.text:
                logger.info("Model:📝 %s", response.text.strip())
            results = [
                ToolResult(call, REGISTRY.invoke(call.name, call.arguments, config))
                for call in response.tool_calls
            ]

            # Hot-reload plugins the model just wrote, so it can use them on its next turn.
            events = PLUGINS.refresh()
            if events:
                report.add(events)
                client.set_tools(_tool_specs())
                last = results[-1]
                results[-1] = ToolResult(last.call, f"{last.output}\n\n{_plugin_notice(events)}")
            client.add_tool_results(results)
    except LLMError as exc:
        logger.error("%s", exc)
        return _with_report(f"[Error]: {exc}", report)

    return _with_report("[Error]: Reached max tool iterations without a final answer.", report)


def _tool_specs() -> list[ToolSpec]:
    return [ToolSpec.from_schema(schema) for schema in REGISTRY.schemas]


def _plugin_notice(events: list[PluginEvent]) -> str:
    lines = "\n".join(f"- {event.describe()}" for event in events)
    return f"[Plugins reloaded]: your tool list was updated:\n{lines}"


def _with_report(text: str, report: PluginReport) -> str:
    summary = report.summary(PLUGINS.failures)
    return f"{text}\n\n{summary}" if summary else text
