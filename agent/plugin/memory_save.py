"""memory_save — persist code snippets, bug fixes, and patterns to the agent's vector memory.

Plugin rules satisfied:
1. ``@tool`` is imported from ``agent.core.registry``.
2. The decorated function returns a plain ``str`` on success.
3. Expected failures raise ``ToolError`` with a human-readable message.
4. A Google-style docstring with an ``Args:`` section drives JSON-schema generation
   so that Gemini / Anthropic / OpenAI can invoke the tool reliably.
"""

from __future__ import annotations

import agent.memory_backend as _backend
from agent.core.registry import ToolError, tool


@tool
def memory_save(
    title: str,
    description: str,
    code: str,
    tags: list[str] | None = None,
) -> str:
    """Store a code snippet, bug fix, or pattern in the agent's persistent memory.

    Use this tool after solving a non-trivial problem so the solution can be
    recalled semantically in future tasks via ``memory_search``.  Each entry is
    embedded into a local ChromaDB vector database for efficient similarity search.

    Args:
        title: Short, human-readable name for the snippet
            (e.g. "Retry with exponential back-off").
        description: What the snippet does and when to use it.  The richer
            the description, the better the semantic search recall.
        code: The actual source code to store.  Must not be empty.
        tags: Optional list of keyword labels for categorisation
            (e.g. ["python", "error-handling", "networking"]).
    """
    if not title:
        raise ToolError("'title' must not be empty.")
    if not code:
        raise ToolError("'code' must not be empty.")

    tag_list: list[str] = tags if tags is not None else []

    try:
        mem = _backend.get_memory()
        snippet_id = mem.save_snippet(title, description, code, tag_list)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except Exception as exc:
        raise ToolError(f"Failed to save snippet: {exc}") from exc

    tag_str = ", ".join(tag_list) if tag_list else "(none)"
    return (
        f"Snippet saved successfully.\n"
        f"  id          : {snippet_id}\n"
        f"  title       : {title}\n"
        f"  tags        : {tag_str}\n"
        f"  store       : {_backend.MEMORY_STORE_PATH}"
    )
