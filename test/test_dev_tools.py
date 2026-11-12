"""Tests for the dedicated developer tools, the run_command gate, the execute_python guard,
and git_checkout / git_clone."""

import dataclasses
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

import agent.runner  # noqa: F401  registers built-in and plugin tools
from agent.config import AgentConfig, load_config
from agent.core.registry import REGISTRY, ToolRegistry, build_tool, tool
from agent.llm.base import LLMSettings

# The module object; 'agent.core.execute_python' as an attribute is the re-exported function.
execute_python_module = importlib.import_module("agent.core.execute_python")


@pytest.fixture(autouse=True)
def mock_memory():
    mem = MagicMock()
    with patch("agent.memory_backend.get_memory", return_value=mem):
        yield mem


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
    return AgentConfig(
        llm=LLMSettings(provider="anthropic", model="test", api_key="", base_url=None),
        workdir=workdir,
        system_prompt=workdir / "system.md",
        max_iterations=1,
        protected_branches=("main",),
        allowed_commands=("pytest",),
        agent_dir=agent_dir,
    )


def invoke(name, config, **arguments):
    return REGISTRY.invoke(name, arguments, config)


# ---------------------------------------------------------------------------
# run_command gate
# ---------------------------------------------------------------------------


class TestRunCommandGate:
    def test_disabled_by_default(self, config):
        assert config.enable_run_command is False
        names = {schema["function"]["name"] for schema in REGISTRY.schemas_for(config)}
        assert "run_command" not in names
        assert {"run_tests", "lint", "format_code", "pip_install", "git_checkout", "git_clone"} <= names

    def test_disabled_call_is_refused(self, config):
        result = invoke("run_command", config, command=["pytest", "-q"])
        assert result.startswith("[Error]") and "enable_run_command" in result

    def test_enabled_tool_runs(self, config, roots):
        workdir, _ = roots
        (workdir / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
        enabled = dataclasses.replace(config, enable_run_command=True)
        assert "run_command" in {s["function"]["name"] for s in REGISTRY.schemas_for(enabled)}
        assert invoke("run_command", enabled, command=["pytest", "-q"]).startswith("[Exit code]: 0")

    def test_config_file_flag(self, tmp_path):
        (tmp_path / "run.toml").write_text('workdir = "./ws"\nenable_run_command = true\n', encoding="utf-8")
        assert load_config(tmp_path / "run.toml").enable_run_command is True

    def test_config_file_flag_must_be_bool(self, tmp_path):
        (tmp_path / "run.toml").write_text('workdir = "./ws"\nenable_run_command = "yes"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="enable_run_command"):
            load_config(tmp_path / "run.toml")

    def test_enabled_by_must_name_config_field(self):
        def sample() -> str:
            """Sample."""
            return ""

        with pytest.raises(ValueError, match="enabled_by"):
            build_tool(sample, enabled_by="no_such_field")

    def test_custom_registry_gate(self, config):
        registry = ToolRegistry()

        @tool(registry=registry, enabled_by="verbose")
        def only_verbose() -> str:
            """Only in verbose runs."""
            return "ok"

        assert registry.schemas_for(config) == []
        assert registry.invoke("only_verbose", {}, config).startswith("[Error]")
        verbose = dataclasses.replace(config, verbose=True)
        assert registry.invoke("only_verbose", {}, verbose) == "ok"


# ---------------------------------------------------------------------------
# run_tests / lint / format_code
# ---------------------------------------------------------------------------


class TestRunTests:
    def test_pass_and_fail(self, config, roots):
        workdir, _ = roots
        (workdir / "test_a.py").write_text(
            "def test_ok():\n    pass\n\ndef test_bad():\n    assert 1 == 2\n", encoding="utf-8"
        )
        result = invoke("run_tests", config)
        assert result.startswith("[Exit code]: 1")
        assert "[Status]: some tests failed" in result
        assert "test_bad" in result

        result = invoke("run_tests", config, paths=["test_a.py::test_ok"])
        assert "[Status]: all tests passed" in result

        result = invoke("run_tests", config, keyword="ok")
        assert result.startswith("[Exit code]: 0")

    def test_no_tests(self, config):
        assert "[Status]: no tests were collected" in invoke("run_tests", config)

    def test_successful_run_saved_to_memory(self, config, roots, mock_memory):
        workdir, _ = roots
        (workdir / "test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
        invoke("run_tests", config)
        mock_memory.save_snippet.assert_called_once()
        assert "run_tests" in mock_memory.save_snippet.call_args.kwargs["tags"]

    @pytest.mark.parametrize("path", ["-p", "--rootdir=/", "../outside.py"])
    def test_rejects_options_and_escapes(self, config, path):
        assert invoke("run_tests", config, paths=[path]).startswith("[Error]")


class TestRuff:
    def test_lint_reports_issues_and_fixes(self, config, roots):
        workdir, _ = roots
        (workdir / "bad.py").write_text("import os\n", encoding="utf-8")
        result = invoke("lint", config)
        assert "[Status]: issues found" in result and "F401" in result

        result = invoke("lint", config, fix=True)
        assert "[Status]: no issues" in result
        assert (workdir / "bad.py").read_text(encoding="utf-8") == ""

    def test_format_check_then_format(self, config, roots):
        workdir, _ = roots
        source = workdir / "ugly.py"
        source.write_text("x = {  'a':1 }\n", encoding="utf-8")

        result = invoke("format_code", config, paths=["ugly.py"], check=True)
        assert "[Status]: files would be reformatted" in result
        assert source.read_text(encoding="utf-8") == "x = {  'a':1 }\n"

        assert "[Status]: formatted" in invoke("format_code", config, paths=["ugly.py"])
        assert source.read_text(encoding="utf-8") == 'x = {"a": 1}\n'


# ---------------------------------------------------------------------------
# pip
# ---------------------------------------------------------------------------


class TestPip:
    def test_list_and_show(self, config):
        assert "pytest" in invoke("pip_list", config).lower()
        assert "Name: pytest" in invoke("pip_show", config, package="pytest")

    @pytest.mark.parametrize("package", ["", "-r", "x; rm", "pkg==1.0"])
    def test_show_rejects_bad_names(self, config, package):
        assert invoke("pip_show", config, package=package).startswith("[Error]")

    def test_install_needs_requirements_or_project(self, config):
        assert "pyproject.toml" in invoke("pip_install", config)
        assert "not found" in invoke("pip_install", config, requirements_file="requirements.txt")

    def test_install_requirements_file(self, config, roots):
        workdir, _ = roots
        (workdir / "requirements.txt").write_text("pytest\n", encoding="utf-8")
        result = invoke("pip_install", config, requirements_file="requirements.txt")
        assert result.startswith("[Exit code]: 0"), result

    def test_install_rejects_paths_outside(self, config):
        assert invoke("pip_install", config, requirements_file="../r.txt").startswith("[Error]")


# ---------------------------------------------------------------------------
# execute_python guard
# ---------------------------------------------------------------------------


class TestExecutePythonGuard:
    @pytest.mark.parametrize(
        "code",
        [
            "import subprocess",
            "import multiprocessing.pool",
            "from subprocess import run",
            "import os\nos.system('dir')",
            "import os\nos.popen('dir')",
            "from os import execv",
            "import os\nos.spawnl(0, 'x')",
            "__import__('subprocess')",
            "import importlib\nimportlib.import_module('subprocess')",
        ],
    )
    def test_static_check_rejects(self, config, code):
        result = invoke("execute_python", config, code=code)
        assert result.startswith("[Error]") and "pure computation" in result

    def test_runtime_hook_blocks_indirect_process_creation(self, config):
        code = (
            "import asyncio, sys\n"
            "asyncio.run(asyncio.create_subprocess_exec(sys.executable, '-V'))\n"
        )
        assert execute_python_module.find_forbidden_calls(code) == []
        result = invoke("execute_python", config, code=code)
        assert "PermissionError" in result and "subprocess.Popen" in result

    def test_pure_computation_still_works(self, config):
        code = "import os, json\nprint(json.dumps({'n': sum(range(5)), 'sep': os.sep != ''}))"
        assert invoke("execute_python", config, code=code).strip() == '{"n": 10, "sep": true}'

    def test_unicode_and_main_guard(self, config):
        code = "if __name__ == '__main__':\n    print('héllo ✓')"
        assert invoke("execute_python", config, code=code).strip() == "héllo ✓"

    def test_syntax_error_reported_by_python(self, config):
        assert "SyntaxError" in invoke("execute_python", config, code="def (:")


# ---------------------------------------------------------------------------
# git_checkout / git_clone
# ---------------------------------------------------------------------------


def make_repo(path: Path, branch: str = "feature/x") -> Repo:
    repo = Repo.init(path, initial_branch="main")
    with repo.config_writer() as writer:
        writer.set_value("user", "name", "Test")
        writer.set_value("user", "email", "test@example.com")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    repo.index.add(["a.txt"])
    repo.index.commit("init")
    repo.git.switch("-c", branch)
    return repo


class TestGitCheckout:
    def test_create_and_switch(self, config, roots):
        workdir, _ = roots
        repo = make_repo(workdir)
        result = invoke("git_checkout", config, repo_path=".", branch="feature/y", create=True)
        assert result.startswith("[Success]") and repo.active_branch.name == "feature/y"

        assert invoke("git_checkout", config, repo_path=".", branch="feature/x").startswith("[Success]")
        assert repo.active_branch.name == "feature/x"
        repo.close()

    def test_protected_branch_refused(self, config, roots):
        workdir, _ = roots
        make_repo(workdir).close()
        result = invoke("git_checkout", config, repo_path=".", branch="main")
        assert result.startswith("[Error]") and "protected" in result

    @pytest.mark.parametrize("branch", ["-f", "bad..name", ""])
    def test_invalid_branch(self, config, roots, branch):
        workdir, _ = roots
        make_repo(workdir).close()
        assert invoke("git_checkout", config, repo_path=".", branch=branch, create=True).startswith("[Error]")

    def test_start_point_requires_create(self, config, roots):
        workdir, _ = roots
        make_repo(workdir).close()
        result = invoke("git_checkout", config, repo_path=".", branch="feature/z", start_point="HEAD")
        assert result.startswith("[Error]")

    def test_agent_repo(self, config, roots):
        _, agent_dir = roots
        make_repo(agent_dir).close()
        result = invoke("git_checkout", config, repo_path="@agent", branch="feature/self", create=True)
        assert result.startswith("[Success]")


class TestGitClone:
    def test_clone_agent_into_workdir(self, config, roots):
        workdir, agent_dir = roots
        make_repo(agent_dir).close()
        result = invoke("git_clone", config, source="@agent", destination="agent-copy")
        assert result.startswith("[Success]") and "feature/x" in result
        assert (workdir / "agent-copy" / "a.txt").is_file()

    def test_clone_workdir_subrepo_on_protected_branch_warns(self, config, roots):
        workdir, _ = roots
        repo = make_repo(workdir / "proj")
        repo.git.switch("main")
        repo.close()
        result = invoke("git_clone", config, source="proj", destination="proj-copy")
        assert result.startswith("[Success]") and "protected" in result

    def test_clone_protected_branch_refused(self, config, roots):
        workdir, _ = roots
        make_repo(workdir / "proj").close()
        result = invoke("git_clone", config, source="proj", destination="copy", branch="main")
        assert result.startswith("[Error]")

    def test_destination_must_be_empty_and_inside(self, config, roots):
        workdir, _ = roots
        make_repo(workdir / "proj").close()
        (workdir / "taken").mkdir()
        (workdir / "taken" / "f").write_text("x", encoding="utf-8")
        assert invoke("git_clone", config, source="proj", destination="taken").startswith("[Error]")
        assert invoke("git_clone", config, source="proj", destination="../out").startswith("[Error]")

    @pytest.mark.parametrize("source", ["https://example.com/r.git", "git@example.com:r.git"])
    def test_remote_urls_refused(self, config, source):
        assert "remote URLs" in invoke("git_clone", config, source=source, destination="c")
