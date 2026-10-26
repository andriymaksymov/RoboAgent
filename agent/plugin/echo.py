"""Echo tool — minimal example and template for plugin authors.

Copy this file, rename it, and replace the function body.  The only rules are:

1. Import ``tool`` (and ``ToolError`` when needed) from ``agent.core.registry``.
2. Decorate exactly one function per logical tool with ``@tool``.
3. Return a plain ``str`` on success.
4. Raise ``ToolError("<human-readable message>")`` for expected failures so the
   model receives a clean error instead of a traceback.
5. Declare any ``AgentConfig`` field by name (e.g. ``workdir``, ``allowed_commands``)
   as a parameter to receive the value automatically — the model never sees it.
6. Write a Google-style docstring with an ``Args:`` section; the registry uses it
   to build the JSON schema that is sent to the model.
"""

from pathlib import Path

from agent.core.registry import ToolError, tool


@tool
def echo(message: str, workdir: Path, repeat: int = 1) -> str:
    """Return the given message repeated one or more times.

    Demonstrates the minimal structure of a plugin tool:
    - ``message`` is a required parameter exposed to the model.
    - ``repeat`` is an optional parameter with a default value.
    - ``workdir`` is injected automatically from ``AgentConfig``; the model
      never sees it in the JSON schema.
    - A ``ToolError`` is raised for invalid input so the model receives a
      clean, actionable error message instead of a raw Python traceback.

    Args:
        message: The text to echo back.
        repeat: How many times to repeat the message (1–10, default 1).
    """
    if not isinstance(repeat, int) or not (1 <= repeat <= 10):
        raise ToolError("'repeat' must be an integer between 1 and 10.")

    lines = "\n".join([message] * repeat)
    return f"[Echo] (workdir={workdir.name}):\n{lines}"
