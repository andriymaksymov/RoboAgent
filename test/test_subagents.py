"""Tests for sub-agents: delegate_tasks, git_merge_from, depth/memory limits, config and CLI options."""

import dataclasses
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from git import Repo

import agent.runner  # noqa: F401  registers built-in and plugin tools
from agent.config import AgentConfig, agent_depth, load_config
from agent.core.registry import REGISTRY
from agent.llm.base import LLMSettings
from agent.task_file import format_task_file, parse_task_file

delegate_module = sys.modules["agent.plugin.delegate_tasks"]
AGENT_ROOT = Path(__file__).resolve().parents[1]


def make_repo(path: Path, branch: str = "feature/x") -> Repo:
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(path, initial_branch="main")
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "Test")
        writer.set_value("user", "email", "test@example.com")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("init")
    repo.git.switch("-c", branch)
    return repo


@pytest.fixture(autouse=True)
def top_level(monkeypatch):
    monkeypatch.delenv("ROBOAGENT_DEPTH", raising=False)


@pytest.fixture
def config(tmp_path):
    workdir = tmp_path / "workspace"
    workdir.mkdir()
    return AgentConfig(
        llm=LLMSettings(provider="anthropic", model="test-model", api_key="", base_url=None),
        workdir=workdir,
        system_prompt=tmp_path / "system.md",
        max_iterations=5,
        protected_branches=("main",),
        allowed_commands=("pytest",),
        enable_subagents=True,
        max_subagents=2,
    )


def invoke(name, config, **arguments):
    return REGISTRY.invoke(name, arguments, config)


# A stand-in for cli.py: records what it was given, commits a file named after the task's
# first word and writes the answer and token usage back to task.md like the real CLI.
FAKE_CLI = """
import argparse, os, sys, time, tomllib
from pathlib import Path
sys.path.insert(0, {root!r})
from git import Repo
from agent.task_file import format_task_file

parser = argparse.ArgumentParser()
parser.add_argument("-p")
parser.add_argument("-c")
parser.add_argument("--quiet", action="store_true")
args = parser.parse_args()
cfg = tomllib.loads(Path(args.c).read_text(encoding="utf-8"))
task = Path(args.p).read_text(encoding="utf-8")
work = Path(cfg["workdir"])
(work / "env.txt").write_text(
    f"{{os.environ.get('ROBOAGENT_DEPTH')}}|{{cfg['max_iterations']}}|{{cfg['enable_subagents']}}|"
    f"{{args.quiet}}|{{cfg['model']}}",
    encoding="utf-8",
)
if "SLEEP" in task:
    time.sleep(60)
if "CRASH" in task:
    print("boom")
    sys.exit(3)
name = task.split()[0]
(work / f"{{name}}.txt").write_text(name, encoding="utf-8")
repo = Repo(work)
repo.index.add([f"{{name}}.txt"])
repo.index.commit(f"add {{name}}")
repo.close()
tokens = int(task.split()[1]) if task.split()[1].isdigit() else 100
Path(args.p).write_text(format_task_file(task, f"done {{name}}", tokens, 20), encoding="utf-8")
"""


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    script = tmp_path / "fake_cli.py"
    script.write_text(FAKE_CLI.format(root=str(AGENT_ROOT)), encoding="utf-8")
    monkeypatch.setattr(delegate_module, "CLI_PATH", script)
    return script


def copies(workdir: Path) -> list[Path]:
    return sorted(p for p in (workdir / ".subagents").iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Gate, depth and validation
# ---------------------------------------------------------------------------


class TestDelegateGate:
    def test_disabled_by_default(self, config):
        disabled = dataclasses.replace(config, enable_subagents=False)
        assert "delegate_tasks" not in {s.name for s in REGISTRY.schemas_for(disabled)}
        assert "delegate_tasks" in {s.name for s in REGISTRY.schemas_for(config)}
        result = invoke("delegate_tasks", disabled, tasks=["x"])
        assert result.startswith("[Error]") and "enable_subagents" in result

    def test_plugins_load_and_schema(self, config):
        from agent.plugin_loader import PLUGINS

        assert not {"delegate_tasks", "git_merge_from"} & set(PLUGINS.failures)
        spec = next(s for s in REGISTRY.schemas_for(config) if s.name == "delegate_tasks")
        assert set(spec.parameters["properties"]) == {
            "tasks",
            "source",
            "iteration_limit",
            "timeout",
        }
        assert spec.parameters["required"] == ["tasks"]

    def test_refused_in_subagent(self, config, monkeypatch):
        monkeypatch.setenv("ROBOAGENT_DEPTH", "1")
        result = invoke("delegate_tasks", config, tasks=["x"])
        assert result.startswith("[Error]") and "depth" in result

    @pytest.mark.parametrize(
        "arguments",
        [
            {"tasks": []},
            {"tasks": ["ok", " "]},
            {"tasks": ["t"] * 9},
            {"tasks": ["t"], "iteration_limit": 0},
            {"tasks": ["t"], "iteration_limit": 51},
            {"tasks": ["t"], "timeout": 0},
        ],
    )
    def test_invalid_arguments(self, config, arguments):
        assert invoke("delegate_tasks", config, **arguments).startswith("[Error]")

    def test_source_must_be_repo(self, config):
        assert "Invalid git repository" in invoke("delegate_tasks", config, tasks=["t"])

    def test_agent_depth(self, monkeypatch):
        assert agent_depth() == 0
        monkeypatch.setenv("ROBOAGENT_DEPTH", "1")
        assert agent_depth() == 1
        monkeypatch.setenv("ROBOAGENT_DEPTH", "junk")
        assert agent_depth() == 0


# ---------------------------------------------------------------------------
# Running sub-agents (with a fake cli.py in separate processes)
# ---------------------------------------------------------------------------


class TestDelegateRun:
    def test_parallel_tasks_and_merge(self, config, fake_cli):
        workdir = config.workdir
        make_repo(workdir).close()
        result = invoke(
            "delegate_tasks", config, tasks=["alpha do it", "beta do it"], iteration_limit=7
        )
        assert result.startswith("[delegate_tasks]: 2 task(s): 2 ok"), result
        assert "done alpha" in result and "done beta" in result
        assert "input=200, output=40" in result
        # The conversation of the sub-agent never reaches the parent: only the answer.
        assert "Sub-agent instructions" not in result

        alpha, beta = copies(workdir)
        assert f"branch: sub/{alpha.name}" in result and "exit code: 0" in result
        depth, iterations, nested, quiet, model = (
            (alpha / "env.txt").read_text(encoding="utf-8").split("|")
        )
        assert (depth, iterations, nested, quiet, model) == (
            "1",
            "7",
            "False",
            "True",
            "test-model",
        )
        clone = Repo(alpha)
        assert clone.active_branch.name == f"sub/{alpha.name}"
        assert not {"task.md", "sub.toml", "console.log"} & set(clone.untracked_files)
        clone.close()
        assert ".subagents/" in (workdir / ".git" / "info" / "exclude").read_text(encoding="utf-8")

        for copy in (alpha, beta):
            merged = invoke(
                "git_merge_from",
                config,
                repo_path=".",
                source_repo=f".subagents/{copy.name}",
                branch=f"sub/{copy.name}",
            )
            assert merged.startswith("[Success]: Merged"), merged
        assert (workdir / "alpha.txt").is_file() and (workdir / "beta.txt").is_file()
        repo = Repo(workdir)
        assert not repo.is_dirty() and repo.active_branch.name == "feature/x"
        repo.close()

    def test_timeout_kills_subagent(self, config, fake_cli):
        make_repo(config.workdir).close()
        result = invoke("delegate_tasks", config, tasks=["slow SLEEP"], timeout=3)
        assert "killed: timeout" in result and "exit code: none" in result
        assert "(no final answer)" in result

    def test_failed_subagent_reports_console_tail(self, config, fake_cli):
        make_repo(config.workdir).close()
        result = invoke("delegate_tasks", config, tasks=["bad CRASH"])
        assert "1 failed" in result and "exit code: 3" in result and "boom" in result

    def test_token_budget_skips_remaining_tasks(self, config, fake_cli):
        make_repo(config.workdir).close()
        limited = dataclasses.replace(config, max_subagents=1, subagent_token_budget=100)
        result = invoke("delegate_tasks", limited, tasks=["one 500", "two 10"])
        assert "1 ok, 1 skipped" in result and "token budget" in result
        assert len(copies(config.workdir)) == 1

    def test_agent_repo_as_source(self, config, fake_cli, tmp_path):
        agent_dir = tmp_path / "agent"
        make_repo(agent_dir).close()
        with_agent = dataclasses.replace(config, agent_dir=agent_dir)
        result = invoke("delegate_tasks", with_agent, tasks=["gamma"], source="@agent")
        assert "1 ok" in result and 'repo_path="@agent"' in result


# ---------------------------------------------------------------------------
# git_merge_from
# ---------------------------------------------------------------------------


@pytest.fixture
def conflict(config):
    """Workdir repo and a clone on branch 'sub/1' that change a.txt differently."""
    workdir = config.workdir
    repo = make_repo(workdir)
    clone = Repo.clone_from(str(workdir), str(workdir / ".copy"), branch="feature/x")
    clone.git.switch("-c", "sub/1")
    with clone.config_writer() as writer:
        writer.set_value("user", "name", "Test")
        writer.set_value("user", "email", "test@example.com")
    (workdir / ".copy" / "a.txt").write_text("from copy\n", encoding="utf-8")
    clone.index.add(["a.txt"])
    clone.index.commit("copy change")
    clone.close()
    (workdir / "a.txt").write_text("from parent\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("parent change")
    yield repo
    repo.close()


class TestGitMergeFrom:
    def test_conflict_aborted(self, config, conflict):
        head = conflict.head.commit.hexsha
        result = invoke(
            "git_merge_from",
            config,
            repo_path=".",
            source_repo=".copy",
            branch="sub/1",
            abort_on_conflict=True,
        )
        assert result.startswith("[Conflict]") and "a.txt" in result and "aborted" in result
        assert conflict.head.commit.hexsha == head and not conflict.is_dirty()

    def test_conflict_kept_then_aborted(self, config, conflict):
        result = invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch="sub/1"
        )
        assert result.startswith("[Conflict]") and "a.txt" in result and "git_commit" in result
        again = invoke("git_merge_from", config, repo_path=".", source_repo=".copy", branch="sub/1")
        assert again.startswith("[Error]") and "in progress" in again
        aborted = invoke(
            "git_merge_from",
            config,
            repo_path=".",
            source_repo=".copy",
            branch="sub/1",
            abort_on_conflict=True,
        )
        assert aborted.startswith("[Success]: Aborted") and not conflict.is_dirty()

    def test_protected_and_dirty_refused(self, config, conflict):
        (config.workdir / "a.txt").write_text("dirty\n", encoding="utf-8")
        assert "uncommitted" in invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch="sub/1"
        )
        conflict.git.checkout("--", "a.txt")
        conflict.git.switch("main")
        assert "protected" in invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch="sub/1"
        )

    @pytest.mark.parametrize("branch", ["", "-x", "no such"])
    def test_invalid_branch(self, config, conflict, branch):
        assert invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch=branch
        ).startswith("[Error]")

    def test_unknown_branch(self, config, conflict):
        result = invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch="sub/none"
        )
        assert result.startswith("[Error]") and "fetch" in result

    def test_already_up_to_date(self, config, conflict):
        result = invoke(
            "git_merge_from", config, repo_path=".", source_repo=".copy", branch="feature/x"
        )
        assert "up to date" in result


# ---------------------------------------------------------------------------
# Memory, config, task file and CLI
# ---------------------------------------------------------------------------


def test_memory_save_read_only_in_subagent(config, monkeypatch):
    mem = MagicMock()
    monkeypatch.setattr("agent.code_memory.get_memory", lambda: mem)
    monkeypatch.setenv("ROBOAGENT_DEPTH", "1")
    result = invoke("memory_save", config, title="t", description="d", code="x = 1")
    assert result.startswith("[Error]") and "read-only" in result
    mem.save_snippet.assert_not_called()
    mem.search_snippets.return_value = []
    assert "No matching" in invoke("memory_search", config, query="q")


class TestConfig:
    def test_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        loaded = load_config()
        assert loaded.enable_subagents is False
        assert loaded.max_subagents == 3
        assert loaded.subagent_token_budget > 0 and loaded.subagent_time_budget > 0

    def test_file_settings(self, tmp_path):
        (tmp_path / "run.toml").write_text(
            'workdir = "./ws"\nenable_subagents = true\nmax_subagents = 2\n'
            "subagent_token_budget = 1000\nsubagent_time_budget = 60\n",
            encoding="utf-8",
        )
        loaded = load_config(tmp_path / "run.toml")
        assert (loaded.enable_subagents, loaded.max_subagents) == (True, 2)
        assert (loaded.subagent_token_budget, loaded.subagent_time_budget) == (1000, 60)

    @pytest.mark.parametrize("line", ['enable_subagents = "yes"', "max_subagents = 0"])
    def test_invalid_values(self, tmp_path, line):
        (tmp_path / "run.toml").write_text(f'workdir = "./ws"\n{line}\n', encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(tmp_path / "run.toml")

    def test_overrides(self, tmp_path):
        (tmp_path / "run.toml").write_text(
            'workdir = "./ws"\nmax_iterations = 20\n', encoding="utf-8"
        )
        (tmp_path / "me").mkdir()
        loaded = load_config(
            tmp_path / "run.toml",
            workdir=tmp_path / "other",
            agent_dir=tmp_path / "me",
            max_iterations=4,
        )
        assert loaded.workdir == (tmp_path / "other").resolve() and loaded.workdir.is_dir()
        assert loaded.agent_dir == (tmp_path / "me").resolve()
        assert loaded.max_iterations == 4
        with pytest.raises(ValueError, match="max_iterations"):
            load_config(tmp_path / "run.toml", max_iterations=0)


class TestTaskFile:
    def test_round_trip(self):
        text = format_task_file("do X", "Done: changed a.py\n\n---\nnotes", 1234, 56)
        assert parse_task_file(text) == ("Done: changed a.py\n\n---\nnotes", 1234, 56)

    def test_unanswered(self):
        assert parse_task_file("just the task") == (None, 0, 0)


def test_cli_options(monkeypatch):
    monkeypatch.syspath_prepend(str(AGENT_ROOT))
    import cli

    args = cli.parse_args(
        ["-p", "t.md", "--workdir", "w", "--agent-dir", "a", "--max-iterations", "3", "--quiet"]
    )
    assert (args.workdir, args.agent_dir, args.max_iterations, args.quiet) == (
        Path("w"),
        Path("a"),
        3,
        True,
    )
    defaults = cli.parse_args(["-p", "t.md"])
    assert (defaults.workdir, defaults.agent_dir, defaults.max_iterations, defaults.quiet) == (
        None,
        None,
        None,
        False,
    )
