from pathlib import Path

from .registry import ToolError, tool
from .utils import MAX_TEXT_CHARS, clip_line, resolve_in_workdir

DEFAULT_LINES = 300


@tool
def read_file(
    path: str,
    workdir: Path,
    agent_dir: Path | None,
    offset: int = 1,
    limit: int = DEFAULT_LINES,
) -> str:
    """Read a text file from the workdir. Returns at most `limit` lines (and about 16,000 characters) starting at line `offset`; a header then shows the line range and how to read on. Use content_search first to find the relevant lines of large files.

    Args:
        path: File path relative to the workdir.
        offset: First line to return, 1-based (default 1).
        limit: Maximum number of lines to return (default 300).
    """
    if offset < 1 or limit < 1:
        raise ToolError("'offset' and 'limit' must be positive.")
    lines = resolve_in_workdir(workdir, path, agent_dir).read_text(encoding="utf-8").splitlines(
        keepends=True
    )
    total = len(lines)
    if offset == 1 and limit >= total and sum(map(len, lines)) <= MAX_TEXT_CHARS:
        return "".join(lines)  # the whole file fits: return it unchanged
    if offset > max(total, 1):
        raise ToolError(f"'offset' {offset} is past the end of the file ({total} lines).")

    start = offset - 1
    page: list[str] = []
    size = 0
    for line in lines[start : start + limit]:
        if page and size + len(line) > MAX_TEXT_CHARS:
            break
        if not page and len(line) > MAX_TEXT_CHARS:  # one huge line (e.g. minified code)
            line = clip_line(line, MAX_TEXT_CHARS) + "\n"
        page.append(line)
        size += len(line)

    end = start + len(page)
    header = f"[Lines {offset}-{end} of {total}"
    header += f"; next: read_file(path, offset={end + 1})]" if end < total else "; end of file]"
    return header + "\n" + "".join(page)
