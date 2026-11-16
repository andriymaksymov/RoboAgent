"""Format of the prompt file after a run.

``cli.py`` rewrites the prompt file with the task, the agent's final answer and its token
usage; ``delegate_tasks`` reads a sub-agent's answer and usage back from that file, so
the parent sees only the summary, not the sub-agent's conversation.
"""

import re

RESPONSE_HEADER = "# Agent Response"
TOKEN_USAGE_HEADER = "# Token usage"

_RESPONSE_MARKER = f"\n---\n{RESPONSE_HEADER}\n\n"
_USAGE_MARKER = f"\n\n---\n{TOKEN_USAGE_HEADER}\n\n"
_USAGE = re.compile(r"input=(\d+),\s*output=(\d+)")


def format_task_file(
    prompt: str, final_response: str, input_tokens: int, output_tokens: int
) -> str:
    """Render the prompt file after a run: the task, the final answer and the token usage."""
    return (
        f"# User Prompt\n\n{prompt}\n{_RESPONSE_MARKER}{final_response}"
        f"{_USAGE_MARKER}input={input_tokens}, output={output_tokens}\n"
    )


def parse_task_file(text: str) -> tuple[str | None, int, int]:
    """Return ``(final_answer, input_tokens, output_tokens)``; the answer is None if the run
    never wrote one (e.g. the process was killed)."""
    _, found, rest = text.partition(_RESPONSE_MARKER)
    if not found:
        return None, 0, 0
    answer, found, usage = rest.rpartition(_USAGE_MARKER)
    if not found:
        return rest.strip(), 0, 0
    match = _USAGE.search(usage)
    if not match:
        return answer.strip(), 0, 0
    return answer.strip(), int(match.group(1)), int(match.group(2))
