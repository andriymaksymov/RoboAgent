"""memory_search — query the agent's persistent code-memory vector store.

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
def memory_search(
    query: str,
    n_results: int = 3,
) -> str:
    """Search the agent's persistent memory for code snippets relevant to a query.

    Use this tool before attempting to solve a problem you may have encountered
    before.  Results are ranked by semantic similarity so natural-language queries
    work well alongside code fragments.

    Args:
        query: Natural-language description or code fragment to search for
            (e.g. "retry HTTP request with exponential back-off").
        n_results: Maximum number of results to return (1–10, default 3).
    """
    if not query:
        raise ToolError("'query' must not be empty.")
    if not isinstance(n_results, int) or not (1 <= n_results <= 10):
        raise ToolError("'n_results' must be an integer between 1 and 10.")

    try:
        mem = _backend.get_memory()
        results = mem.search_snippets(query, n_results=n_results)
    except Exception as exc:
        raise ToolError(f"Memory search failed: {exc}") from exc

    if not results:
        return "No matching snippets found in memory."

    lines: list[str] = [f"Found {len(results)} snippet(s) for query: {query!r}\n"]
    for i, snippet in enumerate(results, start=1):
        tag_str = ", ".join(snippet.tags) if snippet.tags else "(none)"
        lines.append(
            f"--- Result {i} (similarity={snippet.similarity:.2f}) ---\n"
            f"Title       : {snippet.title}\n"
            f"Description : {snippet.description}\n"
            f"Tags        : {tag_str}\n"
            f"ID          : {snippet.id}\n"
            f"Code:\n{snippet.code}\n"
        )
    return "\n".join(lines)
