"""delegate_tasks — run small, independent subtasks in parallel sub-agents.

Each task gets its own git clone of the source repository in
``<workdir>/.subagents/<id>`` on a new branch ``sub/<id>``, a ``task.md`` and a
``sub.toml``, and runs as a separate process: ``python cli.py -p task.md -c sub.toml``
with this agent's interpreter. Processes, not threads: the tool registry, plugin loader,
logging setup and counters are process-wide globals that two agents in one process would
share.

Only each sub-agent's short final answer (read back from its ``task.md``), branch, exit
code and token usage are returned, so the parent's context grows by a summary per task,
not by the sub-agent's whole conversation. The parent reviews and merges the branches with
``git_merge_from``.

Limits against runaway recursion and cost:

- off unless ``enable_subagents = true`` in the config;
- ``ROBOAGENT_DEPTH``: sub-agents run with depth 1 and cannot delegate again;
- at most ``max_subagents`` processes at once, each killed after its timeout;
- a total token budget (``subagent_token_budget``, checked before each start) and a
  total time budget (``subagent_time_budget``, caps every timeout) per call.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from git import Repo

from agent.config import DEPTH_ENV, MAX_DEPTH, AgentConfig, agent_depth
from agent.core.registry import ToolError, tool
from agent.core.utils import open_repo
from agent.task_file import parse_task_file

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = AGENT_ROOT / "cli.py"
SUBAGENTS_DIR = ".subagents"
TASK_FILE = "task.md"
CONFIG_FILE = "sub.toml"
CONSOLE_FILE = "console.log"
MAX_TASKS = 8
MAX_ITERATIONS = 50
MAX_ANSWER_CHARS = 2_000
CONSOLE_TAIL_CHARS = 800


@dataclass
class _Outcome:
    task: str
    task_id: str = ""
    status: str = "not started"
    exit_code: int | None = None
    answer: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed: float = 0.0


class _Budget:
    """Shared token and time budget of one delegate_tasks call (thread-safe)."""

    def __init__(self, tokens: int, seconds: int) -> None:
        self.tokens = tokens
        self.deadline = time.monotonic() + seconds
        self._spent = 0
        self._lock = threading.Lock()

    @property
    def spent(self) -> int:
        with self._lock:
            return self._spent

    def add(self, tokens: int) -> None:
        with self._lock:
            self._spent += tokens

    def remaining_seconds(self) -> float:
        return self.deadline - time.monotonic()

    def exhausted(self) -> str | None:
        if self.spent >= self.tokens:
            return f"token budget of {self.tokens} used up"
        if self.remaining_seconds() < 1:
            return "time budget used up"
        return None


def _clip(text: str, limit: int) -> str:
    return (
        text
        if len(text) <= limit
        else f"{text[:limit]}\n[... {len(text) - limit} more chars in task.md]"
    )


def _first_line(text: str, limit: int = 80) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= limit else line[: limit - 3] + "..."


def _task_prompt(task: str, branch: str) -> str:
    return (
        f"{task.strip()}\n\n"
        "---\n"
        "# Sub-agent instructions\n"
        "You are a sub-agent started by another RoboAgent with `delegate_tasks`. Your workdir is "
        f"a git clone made for this task alone, on branch `{branch}`.\n"
        f"- Work only on this task, in this copy. Stay on `{branch}`; do not pull or switch branches.\n"
        f"- Validate your changes (run_tests, lint) and commit them on `{branch}`: the parent "
        "merges committed work only.\n"
        "- The memory is read-only for you (`memory_search` works, `memory_save` does not), and "
        "you cannot delegate further.\n"
        "- Your final answer is all the parent sees. Keep it short: what you changed (files), "
        "the test/lint result, your commit(s), and anything left undone or worth saving to memory.\n"
    )


def _sub_config(config: AgentConfig, copy_dir: Path, max_iterations: int) -> str:
    settings: dict[str, object] = {"provider": config.provider}
    if config.model:
        settings["model"] = config.model
    settings.update(
        workdir=copy_dir.as_posix(),
        system_prompt=config.system_prompt.as_posix(),
        max_iterations=max_iterations,
        protected_branches=list(config.protected_branches),
        allowed_commands=list(config.allowed_commands),
        enable_run_command=config.enable_run_command,
        context_warning_tokens=config.context_warning_tokens,
        enable_subagents=False,
    )
    # JSON scalars and arrays are valid TOML values (strings, booleans, integers, lists).
    lines = [f"{key} = {json.dumps(value)}" for key, value in settings.items()]
    return "# Generated by delegate_tasks for one sub-agent run.\n" + "\n".join(lines) + "\n"


def _exclude(git_dir: Path, patterns: list[str]) -> None:
    """Add *patterns* to ``.git/info/exclude`` (local ignore, never committed)."""
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    missing = [pattern for pattern in patterns if pattern not in existing]
    if missing:
        with exclude.open("a", encoding="utf-8") as handle:
            if existing and existing[-1].strip():
                handle.write("\n")
            handle.write("\n".join(missing) + "\n")


def _new_ids(root: Path, count: int) -> list[str]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    ids = []
    for index in range(1, count + 1):
        task_id, suffix = f"{stamp}-{index}", 0
        while (root / task_id).exists():
            suffix += 1
            task_id = f"{stamp}-{index}-{suffix}"
        ids.append(task_id)
    return ids


def _prepare_copy(
    source_dir: Path,
    source_branch: str | None,
    identity: dict[str, str],
    copy_dir: Path,
    branch: str,
) -> None:
    options = {"branch": source_branch} if source_branch else {}
    clone = Repo.clone_from(str(source_dir), str(copy_dir), **options)
    try:
        clone.git.switch("-c", branch)
        if identity:
            with clone.config_writer() as writer:
                for key, value in identity.items():
                    writer.set_value("user", key, value)
        _exclude(Path(clone.git_dir), [TASK_FILE, CONFIG_FILE, CONSOLE_FILE])
    finally:
        clone.close()


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill the sub-agent and the processes it started (pytest, pip, ...)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=30,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Could not kill process tree %s: %s", process.pid, exc)
    if process.poll() is None:
        process.kill()


def _run_process(
    command: list[str], env: dict[str, str], console: Path, timeout: float
) -> tuple[int | None, bool]:
    """Run *command* with output to *console*; return ``(exit_code, timed_out)``."""
    options: dict[str, object] = {} if os.name == "nt" else {"start_new_session": True}
    with console.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(  # fixed argv: this interpreter + cli.py
            command,
            cwd=str(AGENT_ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            **options,
        )
        try:
            return process.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            _kill_tree(process)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
            return None, True


def _console_tail(console: Path) -> str:
    try:
        text = console.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-CONSOLE_TAIL_CHARS:]


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env[DEPTH_ENV] = str(agent_depth() + 1)
    env["PYTHONIOENCODING"] = "utf-8"
    env["NO_COLOR"] = "1"
    env.pop("FORCE_COLOR", None)
    return env


def _format_report(outcomes: list[_Outcome], source: str, budget: _Budget, elapsed: float) -> str:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        key = outcome.status.split(":")[0].split(" ")[0]
        counts[key] = counts.get(key, 0) + 1
    total_in = sum(o.input_tokens for o in outcomes)
    total_out = sum(o.output_tokens for o in outcomes)
    summary = ", ".join(f"{count} {status}" for status, count in counts.items())
    header = (
        f"[delegate_tasks]: {len(outcomes)} task(s): {summary} | tokens: input={total_in}, "
        f"output={total_out} (budget {budget.tokens}) | {elapsed:.0f}s"
    )
    hint = (
        f'Review each branch, then merge with git_merge_from(repo_path="{source}", '
        'source_repo=".subagents/<id>", branch="sub/<id>"), run the tests and commit.'
    )
    lines = [header, hint]
    for number, outcome in enumerate(outcomes, start=1):
        lines.append(f"\n## Task {number}: {_first_line(outcome.task)}")
        details = [f"status: {outcome.status}"]
        if outcome.task_id:
            exit_code = "none (killed)" if outcome.exit_code is None else str(outcome.exit_code)
            details += [
                f"exit code: {exit_code}",
                f"branch: sub/{outcome.task_id}",
                f"copy: {SUBAGENTS_DIR}/{outcome.task_id}",
                f"tokens: input={outcome.input_tokens}, output={outcome.output_tokens}",
                f"{outcome.elapsed:.0f}s",
            ]
        lines.append(" | ".join(details))
        if outcome.answer:
            lines.append(outcome.answer)
    return "\n".join(lines)


@tool(enabled_by="enable_subagents")
def delegate_tasks(
    tasks: list[str],
    workdir: Path,
    agent_dir: Path | None,
    config: AgentConfig,
    source: str = ".",
    iteration_limit: int = 15,
    timeout: int = 900,
) -> str:
    """Run small, independent subtasks in parallel sub-agents, each in its own git clone of the source repository ('.subagents/<id>', branch 'sub/<id>'). Returns only each sub-agent's short final answer, branch, exit code and token usage. Use it only for subtasks that touch different files; then review and merge the branches with git_merge_from, run the tests and commit. Sub-agents cannot delegate further and only read the memory.

    Args:
        tasks: Self-contained task prompts, one per sub-agent (at most 8). Each must say exactly what to change and how to validate it; the sub-agent sees nothing of your conversation.
        source: Repository to clone, relative to the workdir ('.' for the workdir itself, '@agent' for the agent's own repository). Only committed changes are cloned.
        iteration_limit: Maximum iterations of each sub-agent (1-50, default 15).
        timeout: Seconds after which a sub-agent is killed (default 900; capped by the total time budget).
    """
    depth = agent_depth()
    if depth >= MAX_DEPTH:
        raise ToolError(
            f"Delegation refused: this agent already runs at depth {depth} ({DEPTH_ENV}); "
            f"sub-agents cannot start further sub-agents. Do the task yourself."
        )
    if not isinstance(tasks, list) or not tasks:
        raise ToolError("'tasks' must be a non-empty list of task prompts.")
    if not all(isinstance(task, str) and task.strip() for task in tasks):
        raise ToolError("Every task must be a non-empty string.")
    if len(tasks) > MAX_TASKS:
        raise ToolError(f"At most {MAX_TASKS} tasks per call; got {len(tasks)}.")
    if (
        isinstance(iteration_limit, bool)
        or not isinstance(iteration_limit, int)
        or not 1 <= iteration_limit <= MAX_ITERATIONS
    ):
        raise ToolError(f"'iteration_limit' must be an integer between 1 and {MAX_ITERATIONS}.")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ToolError("'timeout' must be a positive number of seconds.")
    if not CLI_PATH.is_file():
        raise ToolError(f"Agent entry point not found: {CLI_PATH}")

    source_repo = open_repo(workdir, source, agent_dir)
    try:
        source_dir = Path(source_repo.working_tree_dir or source_repo.git_dir)
        source_branch = None if source_repo.head.is_detached else source_repo.active_branch.name
        dirty = source_repo.is_dirty(untracked_files=False)
        reader = source_repo.config_reader()
        identity = {
            key: str(reader.get_value("user", key, ""))
            for key in ("name", "email")
            if reader.get_value("user", key, "")
        }
    finally:
        source_repo.close()

    root = workdir / SUBAGENTS_DIR
    root.mkdir(parents=True, exist_ok=True)
    if (workdir / ".git").is_dir():
        _exclude(workdir / ".git", [f"{SUBAGENTS_DIR}/"])

    budget = _Budget(config.subagent_token_budget, config.subagent_time_budget)
    outcomes = [_Outcome(task=task) for task in tasks]
    ids = _new_ids(root, len(tasks))
    env = _child_env()
    started = time.monotonic()

    def work(index: int) -> None:
        outcome = outcomes[index]
        reason = budget.exhausted()
        if reason:
            outcome.status = f"skipped: {reason}"
            return
        task_id = ids[index]
        branch = f"sub/{task_id}"
        copy_dir = root / task_id
        task_file = copy_dir / TASK_FILE
        console = copy_dir / CONSOLE_FILE
        try:
            _prepare_copy(source_dir, source_branch, identity, copy_dir, branch)
            task_file.write_text(_task_prompt(outcome.task, branch), encoding="utf-8")
            (copy_dir / CONFIG_FILE).write_text(
                _sub_config(config, copy_dir, iteration_limit), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001 - reported per task
            outcome.status = f"failed: could not prepare the copy: {exc}"
            return
        outcome.task_id = task_id

        seconds = max(min(float(timeout), budget.remaining_seconds()), 1.0)
        command = [
            sys.executable,
            str(CLI_PATH),
            "-p",
            str(task_file),
            "-c",
            str(copy_dir / CONFIG_FILE),
            "--quiet",
        ]
        logger.info("Sub-agent %s started (timeout %.0fs)", task_id, seconds)
        begin = time.monotonic()
        try:
            exit_code, timed_out = _run_process(command, env, console, seconds)
        except OSError as exc:
            outcome.status = f"failed: could not start: {exc}"
            return
        outcome.elapsed = time.monotonic() - begin
        outcome.exit_code = exit_code

        try:
            answer, tokens_in, tokens_out = parse_task_file(task_file.read_text(encoding="utf-8"))
        except OSError:
            answer, tokens_in, tokens_out = None, 0, 0
        outcome.input_tokens, outcome.output_tokens = tokens_in, tokens_out
        budget.add(tokens_in + tokens_out)

        if timed_out:
            outcome.status = f"killed: timeout after {seconds:.0f}s"
        else:
            outcome.status = "ok" if exit_code == 0 else "failed"
        if answer is None:
            tail = _console_tail(console)
            answer = "(no final answer)" + (f"\nConsole tail:\n{tail}" if tail else "")
        outcome.answer = _clip(answer, MAX_ANSWER_CHARS)
        logger.info("Sub-agent %s finished: %s", task_id, outcome.status)

    workers = max(1, min(config.max_subagents, len(tasks)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="subagent") as pool:
        list(pool.map(work, range(len(tasks))))

    report = _format_report(outcomes, source, budget, time.monotonic() - started)
    if dirty:
        report = f"Note: '{source}' had uncommitted changes; the copies contain only committed work.\n{report}"
    return report
