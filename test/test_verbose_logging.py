"""Tests for verbose-mode file logging in execute_python / run_command.

Coverage goals
--------------
* execute_python writes a .py log file when verbose=True and agent_dir is set.
* execute_python does NOT write a log file when verbose=False.
* execute_python does NOT write a log file when agent_dir is None (even if verbose=True).
* Neither tool saves anything to vector memory automatically.
* run_command writes a .txt log file when verbose=True and agent_dir is set.
* run_command does NOT write a log file when verbose=False.
* AgentConfig.verbose propagates correctly from load_config(verbose=True).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_dir(tmp_path: Path) -> Path:
    d = tmp_path / "agent"
    d.mkdir()
    return d


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "work"
    d.mkdir()
    return d


@pytest.fixture()
def mock_memory():
    """Return a mock CodeMemory instance; patch code_memory.get_memory."""
    mem = MagicMock()
    mem.save_snippet.return_value = "fake-uuid"
    with patch("agent.code_memory.get_memory", return_value=mem):
        yield mem


# ---------------------------------------------------------------------------
# execute_python – verbose file logging
# ---------------------------------------------------------------------------


class TestExecutePythonVerboseLogging:
    def test_log_file_created_when_verbose(self, workdir, agent_dir, mock_memory):
        from agent.core.execute_python import execute_python

        code = "x = 1\ny = 2\nprint(x + y)\n"
        execute_python(code=code, workdir=workdir, verbose=True, agent_dir=agent_dir)

        log_files = list((agent_dir / "logs").glob("exec_python_*.py"))
        assert len(log_files) == 1, "Exactly one log file should be created"
        content = log_files[0].read_text(encoding="utf-8")
        assert "x = 1" in content
        assert "=== execute_python ===" in content

    def test_no_log_file_when_not_verbose(self, workdir, agent_dir, mock_memory):
        from agent.core.execute_python import execute_python

        execute_python(
            code="print('hello')\n",
            workdir=workdir,
            verbose=False,
            agent_dir=agent_dir,
        )
        logs_dir = agent_dir / "logs"
        files = list(logs_dir.glob("exec_python_*.py")) if logs_dir.exists() else []
        assert files == [], "No log file should be created when verbose=False"

    def test_no_log_file_when_agent_dir_is_none(self, workdir, mock_memory):
        from agent.core.execute_python import execute_python

        # verbose=True but no agent_dir – should not raise, should not write anything
        execute_python(
            code="print('x')\n",
            workdir=workdir,
            verbose=True,
            agent_dir=None,
        )
        # Nothing to assert file-wise; just verify no exception was raised.

    def test_log_file_contains_header(self, workdir, agent_dir, mock_memory):
        from agent.core.execute_python import execute_python

        execute_python(
            code="# My title\nimport os\nprint(os.getcwd())\n",
            workdir=workdir,
            verbose=True,
            agent_dir=agent_dir,
        )
        log_file = next((agent_dir / "logs").glob("exec_python_*.py"))
        content = log_file.read_text(encoding="utf-8")
        assert "Timestamp" in content
        assert "Sequence" in content

    def test_multiple_calls_produce_separate_files(self, workdir, agent_dir, mock_memory):
        from agent.core.execute_python import execute_python

        for i in range(3):
            execute_python(
                code=f"print({i})\nx={i}\ny={i*2}\n",
                workdir=workdir,
                verbose=True,
                agent_dir=agent_dir,
            )
        log_files = list((agent_dir / "logs").glob("exec_python_*.py"))
        assert len(log_files) == 3


# ---------------------------------------------------------------------------
# run_command – verbose file logging
# ---------------------------------------------------------------------------


class TestRunCommandVerboseLogging:
    @pytest.fixture()
    def allowed(self) -> Iterable[str]:
        return ["pytest", "ruff", "pip"]

    def test_log_file_created_when_verbose(self, workdir, agent_dir, mock_memory, allowed):
        from agent.core.run_command import run_command

        # Use python -c to echo something that always succeeds
        run_command(
            command=["pytest", "--version"],
            workdir=workdir,
            agent_dir=agent_dir,
            allowed_commands=allowed,
            verbose=True,
            cwd=".",
        )
        log_files = list((agent_dir / "logs").glob("run_cmd_*.txt"))
        assert len(log_files) == 1
        content = log_files[0].read_text(encoding="utf-8")
        assert "pytest" in content
        assert "=== run_command ===" in content

    def test_no_log_file_when_not_verbose(self, workdir, agent_dir, mock_memory, allowed):
        from agent.core.run_command import run_command

        run_command(
            command=["pytest", "--version"],
            workdir=workdir,
            agent_dir=agent_dir,
            allowed_commands=allowed,
            verbose=False,
            cwd=".",
        )
        logs_dir = agent_dir / "logs"
        files = list(logs_dir.glob("run_cmd_*.txt")) if logs_dir.exists() else []
        assert files == []

    def test_no_log_file_when_agent_dir_is_none(self, workdir, mock_memory, allowed):
        from agent.core.run_command import run_command

        # verbose=True but agent_dir=None – must not raise
        run_command(
            command=["pytest", "--version"],
            workdir=workdir,
            agent_dir=None,
            allowed_commands=allowed,
            verbose=True,
            cwd=".",
        )

    def test_log_file_contains_cwd_and_timeout(self, workdir, agent_dir, mock_memory, allowed):
        from agent.core.run_command import run_command

        run_command(
            command=["ruff", "--version"],
            workdir=workdir,
            agent_dir=agent_dir,
            allowed_commands=allowed,
            verbose=True,
            cwd=".",
            timeout=30,
        )
        log_file = next((agent_dir / "logs").glob("run_cmd_*.txt"))
        content = log_file.read_text(encoding="utf-8")
        assert "CWD" in content
        assert "30s" in content

    def test_multiple_calls_produce_separate_files(self, workdir, agent_dir, mock_memory, allowed):
        from agent.core.run_command import run_command

        for _ in range(3):
            run_command(
                command=["pytest", "--version"],
                workdir=workdir,
                agent_dir=agent_dir,
                allowed_commands=allowed,
                verbose=True,
                cwd=".",
            )
        log_files = list((agent_dir / "logs").glob("run_cmd_*.txt"))
        assert len(log_files) == 3


# ---------------------------------------------------------------------------
# No automatic saves to vector memory
# ---------------------------------------------------------------------------


class TestNoAutoSave:
    def test_execute_python_success_is_not_saved(self, workdir, mock_memory):
        from agent.core.execute_python import execute_python

        code = "# A snippet\nimport math\nresult = math.sqrt(16)\nprint(result)\n"
        assert "4.0" in execute_python(code=code, workdir=workdir, verbose=False, agent_dir=None)
        mock_memory.save_snippet.assert_not_called()

    def test_run_command_success_is_not_saved(self, workdir, agent_dir, mock_memory):
        from agent.core.run_command import run_command

        result = run_command(
            command=["pytest", "--version"],
            workdir=workdir,
            agent_dir=agent_dir,
            allowed_commands=["pytest"],
            verbose=False,
            cwd=".",
        )
        assert "[Exit code]: 0" in result
        mock_memory.save_snippet.assert_not_called()


# ---------------------------------------------------------------------------
# AgentConfig.verbose – propagation
# ---------------------------------------------------------------------------


class TestAgentConfigVerbose:
    def test_verbose_defaults_to_false(self, tmp_path):
        from agent.config import AgentConfig
        from agent.llm.presets import resolve_settings

        cfg = AgentConfig(
            llm=resolve_settings("openai", None),
            workdir=tmp_path,
            system_prompt=tmp_path / "sys.md",
            max_iterations=5,
            protected_branches=("main",),
            allowed_commands=("pytest",),
        )
        assert cfg.verbose is False

    def test_load_config_passes_verbose_true(self, tmp_path, monkeypatch):
        """load_config(verbose=True) must set AgentConfig.verbose = True."""
        import agent.config as cfg_mod

        # Monkeypatch resolve_settings so we don't need a real API key
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(cfg_mod, "DEFAULTS", {**cfg_mod.DEFAULTS, "workdir": str(tmp_path)})

        config = cfg_mod.load_config(verbose=True)
        assert config.verbose is True

    def test_load_config_verbose_false_by_default(self, tmp_path, monkeypatch):
        import agent.config as cfg_mod

        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(cfg_mod, "DEFAULTS", {**cfg_mod.DEFAULTS, "workdir": str(tmp_path)})

        config = cfg_mod.load_config()
        assert config.verbose is False
