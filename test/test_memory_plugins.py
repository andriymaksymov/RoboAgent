"""Tests for the memory_save and memory_search plugin tools.

All tests use an ephemeral (in-memory) CodeMemory so **no files are written to
disk**.  The shared ``agent.memory_backend.get_memory`` factory is monkeypatched
for every test that exercises the plugin functions at runtime, ensuring full
isolation between test cases.

Test categories
---------------
* ``TestMemoryPluginRegistration`` – both tools appear in the REGISTRY & schemas.
* ``TestMemorySaveSchema``         – JSON schema derived from memory_save is correct.
* ``TestMemorySearchSchema``       – JSON schema derived from memory_search is correct.
* ``TestMemoryRoundTrip``          – save-then-search integration (quick dummy test).
* ``TestMemorySaveRuntime``        – memory_save return value & error handling.
* ``TestMemorySearchRuntime``      – memory_search return value & error handling.
"""

from __future__ import annotations

import re
import uuid

import pytest

import agent.runner  # noqa: F401 – side-effect: registers all plugins
from agent.code_memory import CodeMemory
from agent.core.registry import REGISTRY, ToolError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ephemeral() -> CodeMemory:
    """Return a fresh, isolated in-memory CodeMemory (no files written to disk)."""
    return CodeMemory(path=None, collection_name=f"test_{uuid.uuid4().hex}")


# ---------------------------------------------------------------------------
# Plugin registration / schema tests
# ---------------------------------------------------------------------------


class TestMemoryPluginRegistration:
    """Both tools must be auto-registered when agent.runner is imported."""

    def test_memory_save_is_registered(self):
        assert "memory_save" in REGISTRY, "memory_save tool must be in REGISTRY"

    def test_memory_search_is_registered(self):
        assert "memory_search" in REGISTRY, "memory_search tool must be in REGISTRY"

    def test_memory_save_appears_in_schemas(self):
        names = {s["function"]["name"] for s in REGISTRY.schemas}
        assert "memory_save" in names

    def test_memory_search_appears_in_schemas(self):
        names = {s["function"]["name"] for s in REGISTRY.schemas}
        assert "memory_search" in names


class TestMemorySaveSchema:
    """The JSON schema for memory_save must expose the right parameters."""

    @pytest.fixture
    def save_tool(self):
        return REGISTRY.get("memory_save")

    def test_tool_exists(self, save_tool):
        assert save_tool is not None

    def test_required_params_are_title_description_code(self, save_tool):
        assert set(save_tool.required) == {"title", "description", "code"}

    def test_tags_is_optional(self, save_tool):
        assert "tags" in save_tool.properties
        assert "tags" not in save_tool.required

    def test_title_is_string(self, save_tool):
        assert save_tool.properties["title"]["type"] == "string"

    def test_description_is_string(self, save_tool):
        assert save_tool.properties["description"]["type"] == "string"

    def test_code_is_string(self, save_tool):
        assert save_tool.properties["code"]["type"] == "string"

    def test_tags_is_array_of_strings(self, save_tool):
        prop = save_tool.properties["tags"]
        assert prop["type"] == "array"
        assert prop.get("items", {}).get("type") == "string"

    def test_no_injectable_params_exposed(self, save_tool):
        """workdir and other AgentConfig fields must not leak into the LLM schema."""
        injectable_names = {"workdir", "config", "llm", "max_iterations",
                            "allowed_commands", "protected_branches", "agent_dir"}
        exposed = set(save_tool.properties)
        assert exposed.isdisjoint(injectable_names)

    def test_description_is_non_empty(self, save_tool):
        assert save_tool.description, "Tool must have a non-empty description for the LLM"


class TestMemorySearchSchema:
    """The JSON schema for memory_search must expose the right parameters."""

    @pytest.fixture
    def search_tool(self):
        return REGISTRY.get("memory_search")

    def test_tool_exists(self, search_tool):
        assert search_tool is not None

    def test_required_params_is_only_query(self, search_tool):
        assert list(search_tool.required) == ["query"]

    def test_n_results_is_optional(self, search_tool):
        assert "n_results" in search_tool.properties
        assert "n_results" not in search_tool.required

    def test_query_is_string(self, search_tool):
        assert search_tool.properties["query"]["type"] == "string"

    def test_n_results_is_integer(self, search_tool):
        assert search_tool.properties["n_results"]["type"] == "integer"

    def test_description_is_non_empty(self, search_tool):
        assert search_tool.description, "Tool must have a non-empty description for the LLM"


# ---------------------------------------------------------------------------
# Round-trip integration test (the "quick dummy test" requested by the task)
# ---------------------------------------------------------------------------


class TestMemoryRoundTrip:
    """Save a dummy snippet and retrieve it via the tool interface."""

    @pytest.fixture(autouse=True)
    def _isolated_store(self, monkeypatch):
        """Route both tools to the same ephemeral store for the duration of the test."""
        mem = _ephemeral()
        monkeypatch.setattr("agent.memory_backend.get_memory", lambda: mem)
        self.mem = mem

    def test_full_round_trip(self):
        """Core integration: save → search → result contains the saved snippet."""
        from agent.plugin.memory_save import memory_save
        from agent.plugin.memory_search import memory_search

        # --- SAVE ---
        save_result = memory_save(
            title="Exponential back-off retry",
            description="Retry a failing call with exponential back-off and jitter.",
            code=(
                "import time, random\n"
                "def retry(fn, retries=5):\n"
                "    for i in range(retries):\n"
                "        try: return fn()\n"
                "        except Exception:\n"
                "            time.sleep((2 ** i) + random.random())\n"
                "    raise RuntimeError('max retries exceeded')"
            ),
            tags=["python", "retry", "networking"],
        )

        assert "saved" in save_result.lower(), "save must confirm success"
        assert "Exponential back-off retry" in save_result, "save must echo the title"

        # UUID4 pattern must appear in the output
        assert re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            save_result,
        ), "save output must contain the UUID4 snippet ID"

        # --- SEARCH ---
        search_result = memory_search(query="retry a function call with back-off")

        assert "Exponential back-off retry" in search_result, (
            "search must surface the saved snippet by its title"
        )
        assert "similarity=" in search_result, "search output must include similarity score"
        assert "python" in search_result, "tags must appear in search output"

    def test_save_without_optional_tags(self):
        from agent.plugin.memory_save import memory_save

        result = memory_save(
            title="No-tag snippet",
            description="A snippet stored without any tags.",
            code="pass",
        )
        assert "saved" in result.lower()
        assert "(none)" in result  # tag_str fallback

    def test_search_empty_store_reports_no_matches(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="anything at all")
        assert "no matching" in result.lower()

    def test_multiple_snippets_n_results_respected(self):
        from agent.plugin.memory_save import memory_save
        from agent.plugin.memory_search import memory_search

        titles = ["Alpha snippet", "Beta snippet", "Gamma snippet", "Delta snippet"]
        for t in titles:
            memory_save(title=t, description="placeholder", code="x = 1", tags=[])

        result = memory_search(query="snippet", n_results=2)
        # Exactly 2 "Result N" blocks
        assert result.count("--- Result") == 2


# ---------------------------------------------------------------------------
# memory_save runtime behaviour
# ---------------------------------------------------------------------------


class TestMemorySaveRuntime:
    @pytest.fixture(autouse=True)
    def _isolated_store(self, monkeypatch):
        monkeypatch.setattr("agent.memory_backend.get_memory", lambda: _ephemeral())

    def test_returns_string(self):
        from agent.plugin.memory_save import memory_save

        result = memory_save(title="T", description="D", code="x=1")
        assert isinstance(result, str)

    def test_output_contains_snippet_id(self):
        from agent.plugin.memory_save import memory_save

        result = memory_save(title="T", description="D", code="x=1")
        assert re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            result,
        )

    def test_output_contains_title(self):
        from agent.plugin.memory_save import memory_save

        result = memory_save(title="My cool snippet", description="D", code="x=1")
        assert "My cool snippet" in result

    def test_output_contains_tags(self):
        from agent.plugin.memory_save import memory_save

        result = memory_save(title="T", description="D", code="x=1", tags=["alpha", "beta"])
        assert "alpha" in result
        assert "beta" in result

    def test_empty_title_raises_tool_error(self):
        from agent.plugin.memory_save import memory_save

        with pytest.raises(ToolError, match="title"):
            memory_save(title="", description="D", code="x=1")

    def test_empty_code_raises_tool_error(self):
        from agent.plugin.memory_save import memory_save

        with pytest.raises(ToolError, match="code"):
            memory_save(title="T", description="D", code="")

    def test_none_tags_treated_as_empty(self):
        from agent.plugin.memory_save import memory_save

        # Passing None explicitly (as the LLM might omit the field) must not crash.
        result = memory_save(title="T", description="D", code="x=1", tags=None)
        assert "saved" in result.lower()


# ---------------------------------------------------------------------------
# memory_search runtime behaviour
# ---------------------------------------------------------------------------


class TestMemorySearchRuntime:
    @pytest.fixture(autouse=True)
    def _isolated_store(self, monkeypatch):
        mem = _ephemeral()
        # Pre-populate with one snippet so search has something to find.
        mem.save_snippet(
            "HTTP GET helper",
            "Perform an HTTP GET and return JSON",
            "import requests\ndef get(url): return requests.get(url).json()",
            ["python", "http"],
        )
        monkeypatch.setattr("agent.memory_backend.get_memory", lambda: mem)

    def test_returns_string(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="http request")
        assert isinstance(result, str)

    def test_result_contains_title(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="HTTP GET request")
        assert "HTTP GET helper" in result

    def test_result_contains_similarity(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="get json from url")
        assert "similarity=" in result

    def test_result_contains_code(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="http")
        assert "import requests" in result

    def test_result_contains_tags(self):
        from agent.plugin.memory_search import memory_search

        result = memory_search(query="http")
        assert "python" in result or "http" in result

    def test_empty_query_raises_tool_error(self):
        from agent.plugin.memory_search import memory_search

        with pytest.raises(ToolError, match="query"):
            memory_search(query="")

    def test_n_results_zero_raises_tool_error(self):
        from agent.plugin.memory_search import memory_search

        with pytest.raises(ToolError):
            memory_search(query="http", n_results=0)

    def test_n_results_eleven_raises_tool_error(self):
        from agent.plugin.memory_search import memory_search

        with pytest.raises(ToolError):
            memory_search(query="http", n_results=11)

    def test_default_n_results_is_three(self, monkeypatch):
        """Signature default means the LLM can omit n_results and get 3 back."""
        mem = _ephemeral()
        for i in range(5):
            mem.save_snippet(f"Snippet {i}", "desc", f"x = {i}", [])
        monkeypatch.setattr("agent.memory_backend.get_memory", lambda: mem)

        from agent.plugin.memory_search import memory_search

        result = memory_search(query="snippet")
        assert result.count("--- Result") == 3
