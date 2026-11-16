"""The large-context warning threshold comes from the run config (TOML)."""

import dataclasses
import logging
from collections.abc import Sequence
from pathlib import Path

import pytest

import agent.runner
from agent.config import AgentConfig, load_config
from agent.llm.base import (
    DEFAULT_CONTEXT_WARNING_TOKENS,
    LLMClient,
    LLMResponse,
    LLMSettings,
    ToolResult,
    ToolSpec,
)


class UsageClient(LLMClient):
    """Answers at once, reporting a fixed prompt size."""

    def __init__(self, context_tokens: int) -> None:
        super().__init__(LLMSettings(provider="test", model="test"))
        self.context_tokens = context_tokens

    def start(self, system_prompt: str, user_prompt: str, tools: Sequence[ToolSpec]) -> None:
        pass

    def set_tools(self, tools: Sequence[ToolSpec]) -> None:
        pass

    def _complete(self) -> LLMResponse:
        self._add_token_usage(self.context_tokens, 1)
        return LLMResponse(text="done")

    def add_tool_results(self, results: Sequence[ToolResult]) -> None:
        pass


def write_config(tmp_path, extra: str = "") -> Path:
    path = tmp_path / "run.toml"
    path.write_text(f'workdir = "./ws"\n{extra}', encoding="utf-8")
    return path


class TestConfig:
    def test_default(self, tmp_path):
        assert load_config(write_config(tmp_path)).context_warning_tokens == DEFAULT_CONTEXT_WARNING_TOKENS

    def test_toml_overrides(self, tmp_path):
        config = load_config(write_config(tmp_path, "context_warning_tokens = 100000\n"))
        assert config.context_warning_tokens == 100_000

    @pytest.mark.parametrize("value", ["0", "-5", '"big"', "true", "1.5"])
    def test_rejects_invalid(self, tmp_path, value):
        with pytest.raises(ValueError, match="context_warning_tokens"):
            load_config(write_config(tmp_path, f"context_warning_tokens = {value}\n"))


class TestRunnerAppliesThreshold:
    @pytest.fixture
    def run_config(self, tmp_path):
        system_prompt = tmp_path / "system.md"
        system_prompt.write_text("test", encoding="utf-8")
        return AgentConfig(
            llm=LLMSettings(provider="test", model="test"),
            workdir=tmp_path,
            system_prompt=system_prompt,
            max_iterations=1,
            protected_branches=(),
            allowed_commands=(),
        )

    def test_warns_above_configured_threshold(self, run_config, caplog):
        client = UsageClient(context_tokens=600)
        config = dataclasses.replace(run_config, context_warning_tokens=500)
        with caplog.at_level(logging.WARNING, logger="agent.llm.base"):
            agent.runner.run_agent("task", config, client)
        assert client.context_warning_tokens == 500
        assert "LARGE CONTEXT" in caplog.text

    def test_quiet_below_configured_threshold(self, run_config, caplog):
        client = UsageClient(context_tokens=40_000)  # above the default, below the config
        config = dataclasses.replace(run_config, context_warning_tokens=50_000)
        with caplog.at_level(logging.WARNING, logger="agent.llm.base"):
            agent.runner.run_agent("task", config, client)
        assert "LARGE CONTEXT" not in caplog.text
