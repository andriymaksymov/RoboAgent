"""
code_memory.py
==============
Local, fully-offline vector-based memory system for code snippets and solutions.

Architecture
------------
* **Embedding model** – ``all-MiniLM-L6-v2`` (ONNX, ~80 MB, downloaded once to
  ``~/.cache/chroma/onnx_models/`` on first use).  ChromaDB bundles the model so
  no extra dependency is required.
* **Vector store** – ChromaDB:
  - ``PersistentClient`` (default): writes an SQLite DB + HNSW index to *path*.
  - ``EphemeralClient`` (``path=None``): fully in-memory; no files written –
    ideal for unit tests and one-shot scripts.
* **Distance metric** – cosine distance (``hnsw:space = "cosine"``), stored in
  the collection's metadata so it is fixed for the lifetime of the collection.

Usage
-----
>>> mem = CodeMemory()                          # persist to ./chroma_store
>>> mem.save_snippet("Binary search",
...                  "O(log n) search in a sorted array",
...                  "def binary_search(arr, t): ...",
...                  ["python", "algorithms"])
>>> results = mem.search_snippets("how to find an element in a sorted list")
>>> for s in results:
...     print(s.title, f"(similarity={s.similarity:.2f})")
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import chromadb

# Name of the ChromaDB collection used by default.
COLLECTION_NAME: str = "code_snippets"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Snippet:
    """A single code snippet returned by :meth:`CodeMemory.search_snippets`.

    Attributes
    ----------
    id          : Unique identifier assigned at save time (UUID4 string).
    title       : Short human-readable name.
    description : Longer explanation of what the snippet does.
    code        : The actual source code text.
    tags        : Arbitrary labels (e.g. ``["python", "sorting"]``).
    distance    : Cosine distance to the query vector (0 = identical, 2 = opposite).
    """

    id: str
    title: str
    description: str
    code: str
    tags: list[str]
    distance: float

    @property
    def similarity(self) -> float:
        """Approximate cosine similarity on a **0–1** scale.

        Derived from cosine *distance* as ``max(0, 1 − distance)``.
        A value of ``1.0`` means a perfect match; ``0.0`` means unrelated.
        """
        return max(0.0, 1.0 - self.distance)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Snippet(title={self.title!r}, similarity={self.similarity:.3f}, "
            f"tags={self.tags})"
        )


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class CodeMemory:
    """Local vector memory for code snippets powered by ChromaDB.

    Parameters
    ----------
    path : str | None
        Directory where ChromaDB stores its SQLite database and HNSW index.
        Set to ``None`` to use a purely in-memory (ephemeral) client – no
        files are written and the store is discarded when the object is
        garbage-collected.  Defaults to ``"./chroma_store"``.
    collection_name : str
        Name of the ChromaDB collection.  You can maintain multiple
        independent snippet libraries by using different names.
    """

    def __init__(
        self,
        path: str | None = "./chroma_store",
        collection_name: str = COLLECTION_NAME,
    ) -> None:
        self._client: chromadb.ClientAPI
        if path is None:
            self._client = chromadb.EphemeralClient()
        else:
            self._client = chromadb.PersistentClient(path=path)

        # cosine distance is fixed at collection-creation time via metadata.
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_snippet(
        self,
        title: str,
        description: str,
        code: str,
        tags: list[str],
    ) -> str:
        """Embed and store a code snippet in the local vector store.

        The *document* passed to the embedding model is a structured
        concatenation of *title*, *description*, and *code* so that all
        three fields influence the resulting vector::

            Title: <title>
            Description: <description>
            Code:
            <code>

        All other fields (title, description, code, tags) are stored as
        ChromaDB metadata for verbatim retrieval.

        Parameters
        ----------
        title       : Short human-readable name (e.g. ``"Binary search"``).
        description : What the snippet does and when to use it.
        code        : The actual source code.
        tags        : Arbitrary string labels for filtering / bookkeeping.

        Returns
        -------
        str
            UUID4 string that uniquely identifies the stored snippet.
        """
        if not title:
            raise ValueError("title must not be empty")
        if not code:
            raise ValueError("code must not be empty")

        snippet_id = str(uuid.uuid4())

        # The full document is what gets embedded – richer context = better search.
        document = f"Title: {title}\nDescription: {description}\nCode:\n{code}"

        self._collection.add(
            ids=[snippet_id],
            documents=[document],
            metadatas=[
                {
                    "title": title,
                    "description": description,
                    "code": code,
                    # ChromaDB metadata values must be str / int / float / bool.
                    "tags": ",".join(tags),
                }
            ],
        )
        return snippet_id

    def search_snippets(
        self,
        query: str,
        n_results: int = 3,
    ) -> list[Snippet]:
        """Semantic search over all stored snippets.

        Parameters
        ----------
        query     : Natural-language description or code fragment to search for.
        n_results : Maximum number of results to return.  The actual count may
                    be lower when the store contains fewer snippets than
                    *n_results*.

        Returns
        -------
        list[Snippet]
            Snippets ordered from most to least semantically similar to *query*.
            Returns an empty list when the store is empty.
        """
        total = self._collection.count()
        if total == 0:
            return []

        # ChromaDB raises if n_results > number of documents in the collection.
        actual_n = min(n_results, total)

        raw = self._collection.query(
            query_texts=[query],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"],
        )

        snippets: list[Snippet] = []
        # ChromaDB wraps results in an outer list (one entry per query text).
        ids: list[str] = raw["ids"][0]
        metadatas: list[dict] = raw["metadatas"][0]  # type: ignore[index]
        distances: list[float] = raw["distances"][0]  # type: ignore[index]

        for sid, meta, dist in zip(ids, metadatas, distances):
            raw_tags: str = meta.get("tags", "")
            tags_list = [t for t in raw_tags.split(",") if t]
            snippets.append(
                Snippet(
                    id=sid,
                    title=meta.get("title", ""),
                    description=meta.get("description", ""),
                    code=meta.get("code", ""),
                    tags=tags_list,
                    distance=float(dist),
                )
            )

        return snippets

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return the total number of snippets currently stored."""
        return self._collection.count()

    def delete_snippet(self, snippet_id: str) -> None:
        """Permanently remove a snippet by its *snippet_id*.

        Parameters
        ----------
        snippet_id : The UUID4 string returned by :meth:`save_snippet`.
        """
        self._collection.delete(ids=[snippet_id])
