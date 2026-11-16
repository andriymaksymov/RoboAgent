import logging

from . import plugin as _plugin  # noqa: F401  side-effect: registers all plugin tools
from .branch_guard import find_protected_branch_repos
from .config import AgentConfig, load_config
from .console_log import llm_text
from .core import REGISTRY
from .llm import LLMClient, LLMError, ToolResult, create_client
from .plugin_loader import PLUGINS, PluginEvent

logger = logging.getLogger(__name__)


class PluginReport:
    """Collects the plugin events of one agent run for its final summary."""

    def __init__(self, failures_at_start: dict[str, str] | None = None) -> None:
        self._startup_failures = dict(failures_at_start or {})
        self._events: list[PluginEvent] = []

    def add(self, events: list[PluginEvent]) -> None:
        self._events.extend(events)

    def summary(self, current_failures: dict[str, str]) -> str:
        """One line per plugin touched in this run, with its final state."""
        last: dict[str, PluginEvent] = {}
        failed_attempts: dict[str, int] = {}
        for event in self._events:
            last[event.module] = event
            if event.status == "failed":
                failed_attempts[event.module] = failed_attempts.get(event.module, 0) + 1

        lines = []
        for module, event in last.items():
            line = f"- {event.describe()}"
            attempts = failed_attempts.get(module, 0)
            if event.status != "failed" and attempts:
                line += f" (after {attempts} failed attempt(s))"
            lines.append(line)
        for module, error in self._startup_failures.items():
            if module not in last and module in current_failures:
                lines.append(f"- '{module}' failed to load at startup (not loaded): {error}")

        if not lines:
            return ""
        header = "[Self-improvement]: plugin tools changed during this run"
        if current_failures:
            header += f"; {len(current_failures)} plugin(s) are still broken"
        return header + ":\n" + "\n".join(lines)


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

    if not config.system_prompt.exists():
        raise FileNotFoundError(f"System prompt file not found: {config.system_prompt}")
    system_prompt = config.system_prompt.read_text(encoding="utf-8")
    report = PluginReport(PLUGINS.failures)
    report.add(PLUGINS.refresh())  # plugins changed since import, e.g. between two runs

    try:
        client = client or create_client(config.llm)
        client.context_warning_tokens = config.context_warning_tokens
        client.start(system_prompt, user_prompt, REGISTRY.schemas_for(config))

        for iteration in range(config.max_iterations):
            logger.info("Iteration %s", iteration + 1)
            response = client.complete()
            if not response.tool_calls:
                return _with_report(response.text, report)

            if response.text:
                text = response.text.strip()
                logger.info("Model: %s", text, extra=llm_text(text))
            results = [
                ToolResult(call, REGISTRY.invoke(call.name, call.arguments, config))
                for call in response.tool_calls
            ]

            # Hot-reload plugins the model just wrote, so it can use them on its next turn.
            events = PLUGINS.refresh()
            if events:
                report.add(events)
                client.set_tools(REGISTRY.schemas_for(config))
                last = results[-1]
                results[-1] = ToolResult(last.call, f"{last.output}\n\n{_plugin_notice(events)}")
            client.add_tool_results(results)
    except LLMError as exc:
        logger.error("%s", exc)
        return _with_report(f"[Error]: {exc}", report)

    return _with_report("[Error]: Reached max tool iterations without a final answer.", report)


def _plugin_notice(events: list[PluginEvent]) -> str:
    lines = "\n".join(f"- {event.describe()}" for event in events)
    return f"[Plugins reloaded]: your tool list was updated:\n{lines}"


def _with_report(text: str, report: PluginReport) -> str:
    summary = report.summary(PLUGINS.failures)
    return f"{text}\n\n{summary}" if summary else text
