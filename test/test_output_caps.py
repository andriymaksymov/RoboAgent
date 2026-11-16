"""Tools return bounded output and tell the model how to get the rest."""

import subprocess

import pytest
from git import Repo

from agent.core.content_search import content_search
from agent.core.execute_python import execute_python
from agent.core.file_reader import read_file
from agent.core.file_search import file_search
from agent.core.folder_content import folder_content
from agent.core.git_diff import git_diff
from agent.core.git_ls_files import git_ls_files
from agent.core.process import MAX_OUTPUT_CHARS, format_result, split_budget
from agent.core.registry import ToolError
from agent.core.utils import MAX_ENTRIES, MAX_MATCHES, MAX_TEXT_CHARS


def numbered(count: int) -> str:
    return "".join(f"line {n}\n" for n in range(1, count + 1))


class TestReadFile:
    def test_small_file_is_returned_unchanged(self, tmp_path):
        (tmp_path / "a.txt").write_text("x\ny\n", encoding="utf-8")
        assert read_file("a.txt", tmp_path, None) == "x\ny\n"

    def test_long_file_is_paged(self, tmp_path):
        (tmp_path / "a.txt").write_text(numbered(1000), encoding="utf-8")
        first = read_file("a.txt", tmp_path, None)
        assert first.startswith("[Lines 1-300 of 1000; next: read_file(path, offset=301)]\nline 1\n")
        assert first.endswith("line 300\n")

        last = read_file("a.txt", tmp_path, None, offset=901, limit=500)
        assert last.startswith("[Lines 901-1000 of 1000; end of file]\nline 901\n")

    def test_char_budget_stops_early(self, tmp_path):
        line = "x" * 99 + "\n"
        (tmp_path / "a.txt").write_text(line * 500, encoding="utf-8")
        page = read_file("a.txt", tmp_path, None, limit=500)
        assert len(page) <= MAX_TEXT_CHARS + 100
        assert "next: read_file(path, offset=161)" in page.splitlines()[0]

    def test_huge_single_line_is_clipped(self, tmp_path):
        (tmp_path / "min.js").write_text("a" * (MAX_TEXT_CHARS * 2), encoding="utf-8")
        page = read_file("min.js", tmp_path, None)
        assert page.startswith("[Lines 1-1 of 1; end of file]")
        assert len(page) < MAX_TEXT_CHARS + 200

    @pytest.mark.parametrize(("offset", "limit"), [(0, 10), (1, 0), (50, 10)])
    def test_invalid_range(self, tmp_path, offset, limit):
        (tmp_path / "a.txt").write_text(numbered(10), encoding="utf-8")
        with pytest.raises(ToolError):
            read_file("a.txt", tmp_path, None, offset=offset, limit=limit)


class TestSearchAndListing:
    def test_content_search_format_and_cap(self, tmp_path):
        (tmp_path / "a.py").write_text("hit\n" * (MAX_MATCHES + 5), encoding="utf-8")
        result = content_search(".", "hit", tmp_path, None).splitlines()
        assert result[0] == "a.py:1: hit"
        assert len(result) == MAX_MATCHES + 1
        assert result[-1].startswith("[... 5 more not shown;")

    def test_content_search_clips_long_lines(self, tmp_path):
        (tmp_path / "a.txt").write_text("hit" + "x" * 1000 + "\n", encoding="utf-8")
        assert len(content_search(".", "hit", tmp_path, None)) < 400

    def test_content_search_no_matches(self, tmp_path):
        (tmp_path / "a.txt").write_text("nothing\n", encoding="utf-8")
        assert content_search(".", "hit", tmp_path, None) == "No matches."

    def test_file_search_cap(self, tmp_path):
        for n in range(MAX_ENTRIES + 3):
            (tmp_path / f"f{n:04d}.py").write_text("", encoding="utf-8")
        result = file_search(".", "*.py", tmp_path, None).splitlines()
        assert result[0] == "f0000.py"
        assert result[-1].startswith("[... 3 more not shown;")

    def test_folder_content_format(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.txt").write_text("abc", encoding="utf-8")
        (tmp_path / ".hidden").write_text("", encoding="utf-8")
        assert folder_content(".", tmp_path, None) == "a.txt  3\nsub/"


class TestGit:
    @pytest.fixture
    def repo(self, tmp_path):
        repo = Repo.init(tmp_path)
        for n in range(MAX_ENTRIES + 2):
            (tmp_path / f"f{n:04d}.txt").write_text("old\n", encoding="utf-8")
        repo.index.add([f"f{n:04d}.txt" for n in range(MAX_ENTRIES + 2)])
        with repo.config_writer() as cfg:
            cfg.set_value("user", "name", "t")
            cfg.set_value("user", "email", "t@example.com")
        repo.index.commit("init")
        yield repo
        repo.close()

    def test_ls_files_cap(self, repo, tmp_path):
        result = git_ls_files(".", tmp_path, None).splitlines()
        assert result[-1].startswith("[... 2 more not shown;")
        assert git_ls_files(".", tmp_path, None, pathspec="f0001.txt") == "f0001.txt"

    def test_diff_cap_stat_and_path(self, repo, tmp_path):
        assert git_diff(".", tmp_path, None) == "No differences."
        for n in range(MAX_ENTRIES + 2):
            (tmp_path / f"f{n:04d}.txt").write_text("new\n" * 20, encoding="utf-8")

        full = git_diff(".", tmp_path, None)
        assert len(full) < MAX_TEXT_CHARS + 200
        assert "use stat=true" in full.splitlines()[-1]

        assert "files changed" in git_diff(".", tmp_path, None, stat=True)
        single = git_diff(".", tmp_path, None, path="f0001.txt")
        assert "f0001.txt" in single and "f0002.txt" not in single


class TestProcessOutput:
    def test_split_budget(self):
        assert split_budget(10, 20, total=100) == (10, 20)
        assert split_budget(10, 500, total=100) == (10, 90)
        assert split_budget(500, 10, total=100) == (90, 10)
        assert split_budget(500, 500, total=100) == (50, 50)

    def test_format_result_shares_budget(self):
        result = subprocess.CompletedProcess([], 1, stdout="o" * 50_000, stderr="e" * 50_000)
        assert len(format_result(result)) < MAX_OUTPUT_CHARS + 200

    def test_execute_python_output_capped(self, tmp_path):
        output = execute_python("print('x' * 100_000)", tmp_path, False, None)
        assert output.startswith("[... truncated")
        assert len(output) < MAX_OUTPUT_CHARS + 100
