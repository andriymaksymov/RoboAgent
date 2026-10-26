"""Tests for the '@agent' root: tools reaching the agent's own repository via agent_dir."""

from pathlib import Path

import pytest
from git import Repo

import agent.runner  # noqa: F401  registers built-in and plugin tools
from agent.branch_guard import find_protected_branch_repos
from agent.config import AgentConfig, load_config
from agent.core.registry import REGISTRY, ToolError
from agent.core.utils import resolve_in_workdir
from agent.llm.base import LLMSettings


@pytest.fixture
def roots(tmp_path):
    workdir = tmp_path / "workspace"
    agent_dir = tmp_path / "agent"
    workdir.mkdir()
    agent_dir.mkdir()
    return workdir, agent_dir


@pytest.fixture
def config(roots):
    workdir, agent_dir = roots
    return load_config_for(workdir, agent_dir)


def load_config_for(workdir: Path, agent_dir: Path | None):
    return AgentConfig(
        llm=LLMSettings(provider="anthropic", model="test", api_key="", base_url=None),
        workdir=workdir,
        system_prompt=workdir / "system.md",
        max_iterations=1,
        protected_branches=("main",),
        allowed_commands=("pytest",),
        agent_dir=agent_dir,
    )


class TestResolve:
    def test_plain_path_stays_in_workdir(self, roots):
        workdir, agent_dir = roots
        assert resolve_in_workdir(workdir, "a.py", agent_dir) == (workdir / "a.py").resolve()

    @pytest.mark.parametrize("path", ["@agent/agent/x.py", "@agent\\agent\\x.py"])
    def test_prefix_maps_to_agent_dir(self, roots, path):
        workdir, agent_dir = roots
        assert resolve_in_workdir(workdir, path, agent_dir) == (agent_dir / "agent/x.py").resolve()

    def test_bare_prefix_is_agent_root(self, roots):
        workdir, agent_dir = roots
        assert resolve_in_workdir(workdir, "@agent", agent_dir) == agent_dir.resolve()

    def test_prefix_without_agent_dir_fails(self, roots):
        workdir, _ = roots
        with pytest.raises(ToolError, match="not configured"):
            resolve_in_workdir(workdir, "@agent/x.py")

    def test_escape_from_agent_dir_fails(self, roots):
        workdir, agent_dir = roots
        with pytest.raises(ToolError, match="outside"):
            resolve_in_workdir(workdir, "@agent/../workspace/x.py", agent_dir)

    def test_absolute_path_in_agent_dir_allowed(self, roots):
        workdir, agent_dir = roots
        target = agent_dir / "x.py"
        assert resolve_in_workdir(workdir, str(target), agent_dir) == target.resolve()

    def test_absolute_path_elsewhere_fails(self, roots, tmp_path):
        workdir, agent_dir = roots
        with pytest.raises(ToolError, match="outside"):
            resolve_in_workdir(workdir, str(tmp_path / "other.py"), agent_dir)

    def test_agent_like_name_is_not_a_prefix(self, roots):
        workdir, agent_dir = roots
        assert resolve_in_workdir(workdir, "@agentx/a.py", agent_dir).parent.name == "@agentx"


class TestTools:
    def test_agent_dir_is_injected_not_exposed(self):
        tool = REGISTRY.get("read_file")
        assert "agent_dir" in tool.injected
        assert "agent_dir" not in tool.properties

    def test_write_and_read_in_agent_dir(self, config, roots):
        _, agent_dir = roots
        REGISTRY.invoke("write_file", {"path": "@agent/agent/plugin/x.py", "content": "y"}, config)
        assert (agent_dir / "agent/plugin/x.py").read_text(encoding="utf-8") == "y"
        assert REGISTRY.invoke("read_file", {"path": "@agent/agent/plugin/x.py"}, config) == "y"

    def test_disabled_agent_dir_returns_error(self, roots):
        workdir, _ = roots
        config = load_config_for(workdir, None)
        result = REGISTRY.invoke("read_file", {"path": "@agent/README.md"}, config)
        assert result.startswith("[Error]") and "not configured" in result

    def test_git_status_in_agent_dir(self, config, roots):
        _, agent_dir = roots
        Repo.init(agent_dir).close()
        assert not REGISTRY.invoke("git_status", {"repo_path": "@agent"}, config).startswith("[Error]")

    def test_run_command_cwd_in_agent_dir(self, config, roots):
        _, agent_dir = roots
        (agent_dir / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
        result = REGISTRY.invoke("run_command", {"command": ["pytest", "-q"], "cwd": "@agent"}, config)
        assert result.startswith("[Exit code]: 0")


class TestConfig:
    def test_agent_dir_resolved_against_config_file(self, tmp_path):
        (tmp_path / "self").mkdir()
        config_file = tmp_path / "run.toml"
        config_file.write_text('workdir = "./ws"\nagent_dir = "./self"\n', encoding="utf-8")
        assert load_config(config_file).agent_dir == (tmp_path / "self").resolve()

    def test_agent_dir_defaults_to_none(self, tmp_path):
        config_file = tmp_path / "run.toml"
        config_file.write_text('workdir = "./ws"\n', encoding="utf-8")
        assert load_config(config_file).agent_dir is None

    def test_missing_agent_dir_rejected(self, tmp_path):
        config_file = tmp_path / "run.toml"
        config_file.write_text('agent_dir = "./missing"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="agent_dir"):
            load_config(config_file)

    def test_default_provider_is_a_known_preset(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert load_config().provider == "anthropic"


class TestBranchGuard:
    def _repo_on(self, path: Path, branch: str) -> None:
        repo = Repo.init(path, initial_branch=branch)
        repo.index.commit("init")
        repo.close()

    def test_agent_dir_on_protected_branch_is_reported(self, roots):
        workdir, agent_dir = roots
        self._repo_on(agent_dir, "main")
        assert find_protected_branch_repos(workdir, ["main"]) == []
        assert find_protected_branch_repos(workdir, ["main"], [agent_dir]) == [f"{agent_dir}: main"]

    def test_workdir_inside_agent_dir_reported_once(self, roots):
        workdir, _ = roots
        self._repo_on(workdir, "main")
        assert len(find_protected_branch_repos(workdir, ["main"], [workdir])) == 1
