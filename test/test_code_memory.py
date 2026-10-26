"""
test/test_code_memory.py
========================
Standalone unit tests for :class:`CodeMemory` and :class:`Snippet`.

All tests use ``path=None`` (ChromaDB ``EphemeralClient``) so **no files are
written to disk** and each test fixture gets a completely isolated, blank store.

Test categories
---------------
* ``TestSnippetDataclass``   – :class:`Snippet` properties and helper.
* ``TestSaveSnippet``        – :meth:`save_snippet` return value and count tracking.
* ``TestSearchSnippets``     – semantic search relevance, result structure, edge cases.
* ``TestDeleteSnippet``      – :meth:`delete_snippet` removes data from store.
* ``TestValidation``         – :meth:`save_snippet` rejects invalid input.
"""

from __future__ import annotations

import uuid

import pytest

from code_memory import CodeMemory, Snippet


def _unique_mem() -> CodeMemory:
    """Return a fresh, empty in-memory CodeMemory with a collision-proof collection name."""
    return CodeMemory(path=None, collection_name=f"test_{uuid.uuid4().hex}")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mem() -> CodeMemory:
    """Fresh, empty in-memory CodeMemory instance with an isolated collection."""
    return _unique_mem()


# A realistic set of Python snippets that span several domains so semantic
# distinctions between them are meaningful.
SNIPPETS: list[tuple[str, str, str, list[str]]] = [
    (
        "Binary search",
        "Efficient O(log n) search in a sorted list",
        (
            "def binary_search(arr, target):\n"
            "    lo, hi = 0, len(arr) - 1\n"
            "    while lo <= hi:\n"
            "        mid = (lo + hi) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            lo = mid + 1\n"
            "        else:\n"
            "            hi = mid - 1\n"
            "    return -1"
        ),
        ["python", "algorithms", "search"],
    ),
    (
        "Bubble sort",
        "Simple O(n²) comparison-based sorting algorithm",
        (
            "def bubble_sort(arr):\n"
            "    n = len(arr)\n"
            "    for i in range(n):\n"
            "        for j in range(n - i - 1):\n"
            "            if arr[j] > arr[j + 1]:\n"
            "                arr[j], arr[j + 1] = arr[j + 1], arr[j]"
        ),
        ["python", "algorithms", "sorting"],
    ),
    (
        "Read text file",
        "Read all lines from a text file into a list",
        (
            "def read_lines(path: str) -> list[str]:\n"
            "    with open(path, encoding='utf-8') as fh:\n"
            "        return fh.readlines()"
        ),
        ["python", "io", "files"],
    ),
    (
        "HTTP GET request",
        "Perform an HTTP GET request and return the parsed JSON body",
        (
            "import requests\n\n"
            "def get_json(url: str) -> dict:\n"
            "    response = requests.get(url, timeout=10)\n"
            "    response.raise_for_status()\n"
            "    return response.json()"
        ),
        ["python", "http", "networking"],
    ),
    (
        "Parse JSON string",
        "Deserialize a JSON-encoded string into a Python object",
        (
            "import json\n\n"
            "def parse_json(text: str):\n"
            "    return json.loads(text)"
        ),
        ["python", "json", "parsing"],
    ),
]


@pytest.fixture()
def populated_mem() -> CodeMemory:
    """In-memory store pre-loaded with :data:`SNIPPETS`, using an isolated collection."""
    m = _unique_mem()
    for title, desc, code, tags in SNIPPETS:
        m.save_snippet(title, desc, code, tags)
    return m


# ---------------------------------------------------------------------------
# Snippet data-class tests
# ---------------------------------------------------------------------------


class TestSnippetDataclass:
    def test_similarity_is_one_minus_distance(self) -> None:
        s = Snippet(id="x", title="T", description="D", code="c", tags=[], distance=0.3)
        assert s.similarity == pytest.approx(0.7)

    def test_similarity_never_negative(self) -> None:
        # distance > 1 is possible in cosine space when vectors point away from each other
        s = Snippet(id="x", title="T", description="D", code="c", tags=[], distance=1.5)
        assert s.similarity == 0.0

    def test_perfect_match_has_zero_distance(self) -> None:
        s = Snippet(id="x", title="T", description="D", code="c", tags=[], distance=0.0)
        assert s.similarity == pytest.approx(1.0)

    def test_tags_is_a_list(self) -> None:
        s = Snippet(id="x", title="T", description="D", code="c", tags=["a", "b"], distance=0.1)
        assert isinstance(s.tags, list)
        assert s.tags == ["a", "b"]


# ---------------------------------------------------------------------------
# save_snippet tests
# ---------------------------------------------------------------------------


class TestSaveSnippet:
    def test_returns_non_empty_string_id(self, mem: CodeMemory) -> None:
        sid = mem.save_snippet("Hello", "Prints greeting", "print('hi')", ["python"])
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_each_save_returns_unique_id(self, mem: CodeMemory) -> None:
        ids = {mem.save_snippet("T", "D", f"x = {i}", []) for i in range(5)}
        assert len(ids) == 5, "Every saved snippet should get a distinct ID"

    def test_count_starts_at_zero(self, mem: CodeMemory) -> None:
        assert mem.count() == 0

    def test_count_increments_by_one(self, mem: CodeMemory) -> None:
        for i in range(1, 4):
            mem.save_snippet(f"Snippet {i}", "desc", "pass", [])
            assert mem.count() == i

    def test_save_without_tags(self, mem: CodeMemory) -> None:
        sid = mem.save_snippet("No tags", "A snippet with no tags", "pass", [])
        assert isinstance(sid, str)
        assert mem.count() == 1

    def test_save_with_multiple_tags(self, mem: CodeMemory) -> None:
        mem.save_snippet("Tagged", "desc", "pass", ["a", "b", "c", "d"])
        assert mem.count() == 1


# ---------------------------------------------------------------------------
# search_snippets tests
# ---------------------------------------------------------------------------


class TestSearchSnippets:
    # ---- return-type / structure ----------------------------------------

    def test_returns_a_list(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("sort a list")
        assert isinstance(results, list)

    def test_all_elements_are_snippet_instances(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm")
        assert all(isinstance(s, Snippet) for s in results)

    def test_snippet_title_is_non_empty_string(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm", n_results=1)
        assert len(results) == 1
        assert isinstance(results[0].title, str) and results[0].title

    def test_snippet_code_is_non_empty_string(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm", n_results=1)
        assert isinstance(results[0].code, str) and results[0].code

    def test_snippet_description_is_string(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm", n_results=1)
        assert isinstance(results[0].description, str)

    def test_snippet_tags_is_list(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm", n_results=1)
        assert isinstance(results[0].tags, list)

    def test_snippet_distance_is_float(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("algorithm", n_results=1)
        assert isinstance(results[0].distance, float)

    def test_similarity_between_zero_and_one(self, populated_mem: CodeMemory) -> None:
        for s in populated_mem.search_snippets("python", n_results=5):
            assert 0.0 <= s.similarity <= 1.0, f"Out-of-range similarity: {s.similarity}"

    # ---- n_results behaviour -------------------------------------------

    def test_default_n_results_is_three(self, populated_mem: CodeMemory) -> None:
        # SNIPPETS has 5 entries; default n_results=3 should return exactly 3.
        results = populated_mem.search_snippets("python code")
        assert len(results) == 3

    def test_custom_n_results_respected(self, populated_mem: CodeMemory) -> None:
        assert len(populated_mem.search_snippets("code", n_results=1)) == 1
        assert len(populated_mem.search_snippets("code", n_results=2)) == 2
        assert len(populated_mem.search_snippets("code", n_results=5)) == 5

    def test_n_results_capped_at_collection_size(self) -> None:
        """Requesting more results than stored snippets must not raise."""
        m = _unique_mem()
        m.save_snippet("Only one", "Just one snippet here", "x = 1", ["test"])
        results = m.search_snippets("snippet", n_results=100)
        assert len(results) == 1

    def test_empty_store_returns_empty_list(self, mem: CodeMemory) -> None:
        assert mem.search_snippets("anything") == []

    # ---- ordering -------------------------------------------------------

    def test_results_ordered_by_ascending_distance(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("search algorithm", n_results=5)
        distances = [s.distance for s in results]
        assert distances == sorted(distances), (
            f"Results not ordered by ascending distance: {distances}"
        )

    def test_top_result_has_lowest_distance(self, populated_mem: CodeMemory) -> None:
        results = populated_mem.search_snippets("sort numbers", n_results=3)
        top_dist = results[0].distance
        for other in results[1:]:
            assert top_dist <= other.distance

    # ---- semantic relevance --------------------------------------------

    def test_sort_query_returns_sort_related_snippet(self, populated_mem: CodeMemory) -> None:
        """'sorting algorithm' should surface the bubble-sort or binary-search snippet."""
        results = populated_mem.search_snippets("sorting algorithm", n_results=3)
        titles_lower = [s.title.lower() for s in results]
        assert any("sort" in t or "search" in t for t in titles_lower), (
            f"Expected a sort/search snippet in top-3, got: {titles_lower}"
        )

    def test_file_query_returns_file_snippet(self, populated_mem: CodeMemory) -> None:
        """'read lines from a text file' should surface the file-I/O snippet."""
        results = populated_mem.search_snippets("read lines from a text file", n_results=3)
        titles_lower = [s.title.lower() for s in results]
        assert any("file" in t or "read" in t for t in titles_lower), (
            f"Expected a file-related snippet in top-3, got: {titles_lower}"
        )

    def test_http_query_returns_http_snippet(self, populated_mem: CodeMemory) -> None:
        """'perform an HTTP GET request' should surface the HTTP snippet."""
        results = populated_mem.search_snippets("perform an HTTP GET request", n_results=3)
        titles_lower = [s.title.lower() for s in results]
        assert any("http" in t or "request" in t for t in titles_lower), (
            f"Expected an HTTP snippet in top-3, got: {titles_lower}"
        )

    def test_json_query_returns_json_snippet(self, populated_mem: CodeMemory) -> None:
        """'deserialize json data' should surface the JSON-parsing snippet."""
        results = populated_mem.search_snippets("deserialize json data", n_results=3)
        titles_lower = [s.title.lower() for s in results]
        assert any("json" in t or "parse" in t for t in titles_lower), (
            f"Expected a JSON snippet in top-3, got: {titles_lower}"
        )

    # ---- round-trip fidelity -------------------------------------------

    def test_title_round_trip(self, mem: CodeMemory) -> None:
        title = "My unique snippet title"
        mem.save_snippet(title, "description", "x = 1", [])
        results = mem.search_snippets(title, n_results=1)
        assert results[0].title == title

    def test_code_round_trip(self, mem: CodeMemory) -> None:
        code = "def greet(name):\n    return f'Hello, {name}!'"
        mem.save_snippet("Greeter", "Returns a greeting", code, [])
        results = mem.search_snippets("greeting function", n_results=1)
        assert results[0].code == code

    def test_description_round_trip(self, mem: CodeMemory) -> None:
        desc = "Computes the factorial of n recursively"
        mem.save_snippet("Factorial", desc, "def f(n): return 1 if n<=1 else n*f(n-1)", [])
        results = mem.search_snippets("factorial", n_results=1)
        assert results[0].description == desc

    def test_tags_round_trip(self, populated_mem: CodeMemory) -> None:
        """Tags stored as comma-separated string must come back as a proper list."""
        results = populated_mem.search_snippets("binary search", n_results=1)
        assert isinstance(results[0].tags, list)
        assert len(results[0].tags) > 0

    def test_empty_tags_stored_as_empty_list(self, mem: CodeMemory) -> None:
        mem.save_snippet("No tags", "desc", "pass", [])
        results = mem.search_snippets("no tags", n_results=1)
        assert results[0].tags == []

    def test_id_in_results_is_string(self, mem: CodeMemory) -> None:
        saved_id = mem.save_snippet("ID test", "Check IDs", "x = 42", [])
        results = mem.search_snippets("check", n_results=1)
        assert isinstance(results[0].id, str)
        assert results[0].id == saved_id


# ---------------------------------------------------------------------------
# delete_snippet tests
# ---------------------------------------------------------------------------


class TestDeleteSnippet:
    def test_delete_reduces_count_by_one(self, mem: CodeMemory) -> None:
        sid = mem.save_snippet("Temp", "Temporary snippet", "pass", [])
        assert mem.count() == 1
        mem.delete_snippet(sid)
        assert mem.count() == 0

    def test_delete_removes_from_search_results(self, mem: CodeMemory) -> None:
        sid = mem.save_snippet(
            "Unique XYZ marker",
            "A snippet with a very distinctive XYZ identifier",
            "XYZ_CONSTANT = 99",
            ["unique"],
        )
        # Confirm it is retrievable before deletion.
        before = mem.search_snippets("XYZ marker", n_results=1)
        assert len(before) == 1 and before[0].id == sid

        mem.delete_snippet(sid)
        assert mem.count() == 0
        after = mem.search_snippets("XYZ marker")
        assert after == []

    def test_delete_one_leaves_others_intact(self, populated_mem: CodeMemory) -> None:
        initial_count = populated_mem.count()
        # Retrieve one ID via search
        results = populated_mem.search_snippets("binary search", n_results=1)
        target_id = results[0].id

        populated_mem.delete_snippet(target_id)
        assert populated_mem.count() == initial_count - 1
        # The remaining snippets should still be searchable.
        remaining = populated_mem.search_snippets("python code", n_results=10)
        assert all(s.id != target_id for s in remaining)


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    def test_empty_title_raises_value_error(self, mem: CodeMemory) -> None:
        with pytest.raises(ValueError, match="title"):
            mem.save_snippet("", "desc", "pass", [])

    def test_empty_code_raises_value_error(self, mem: CodeMemory) -> None:
        with pytest.raises(ValueError, match="code"):
            mem.save_snippet("Title", "desc", "", [])
