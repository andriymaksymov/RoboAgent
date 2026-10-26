"""Shared persistent-store configuration for the memory_save / memory_search plugins.

Both plugin modules import ``get_memory`` from here so that tests and future
configuration changes only need to touch a single place.

The store lives at ``~/.roboagent/chroma_store`` by default.  Point
``MEMORY_STORE_PATH`` to ``None`` to use an in-memory (ephemeral) store, or
monkeypatch ``get_memory`` in tests to return a pre-built ``CodeMemory``.
"""

from __future__ import annotations

from pathlib import Path

from .code_memory import CodeMemory

# Default location for the persistent vector database.
# Override in tests by monkeypatching ``agent.memory_backend.get_memory``.
MEMORY_STORE_PATH: str = str(Path.home() / ".roboagent" / "chroma_store")


def get_memory() -> CodeMemory:
    """Return a :class:`~agent.code_memory.CodeMemory` instance for the shared store.

    A new client object is created on every call; ChromaDB's ``PersistentClient``
    is thread-safe and re-opens the same on-disk database automatically.
    """
    return CodeMemory(path=MEMORY_STORE_PATH)
