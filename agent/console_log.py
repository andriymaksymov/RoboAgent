"""Compact, colored console logging.

The log file keeps the full record (timestamp, level, logger, message). The console shows
a condensed view instead, driven by an optional ``kind`` attribute on the log record
(pass it with ``extra=``):

- ``KIND_LLM_TEXT``: text produced by the model, shown in full and highlighted.
- ``KIND_TOOL_CALL``: a tool invocation with its (shortened) arguments, e.g.
  ``-> read_file(path='a.txt')``.

Records marked with ``file_only()`` are detail for the log file and never reach the
console. Below WARNING, only the agent's own loggers (``agent.*``, ``roboagent``) reach the
console, so library chatter such as "HTTP Request: POST ..." (logged by httpx, or httpx2
inside the Anthropic SDK) stays in the log file. Records without a ``kind`` are shown as their plain
message. Warnings and errors are prefixed with ``!`` and colored. DEBUG records (verbose
mode) are dimmed.
"""

import logging
import os
import sys
from typing import TextIO

KIND_LLM_TEXT = "llm_text"
KIND_TOOL_CALL = "tool_call"

# The agent's own loggers; any other logger reaches the console only from WARNING up.
_OWN_LOGGERS = ("agent", "roboagent")

_RESET = "\x1b[0m"
_BRIGHT_CYAN = "\x1b[1;96m"
_GREEN = "\x1b[32m"
_BRIGHT_RED = "\x1b[1;91m"
_YELLOW = "\x1b[93m"
_DIM = "\x1b[2m"


def file_only() -> dict:
    return {"file_only": True}


class _ConsoleFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "file_only", False):
            return False
        return record.levelno >= logging.WARNING or _is_own(record.name)


def _is_own(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in _OWN_LOGGERS)


def llm_text(text: str) -> dict:
    return {"kind": KIND_LLM_TEXT, "llm_text": text}


def tool_call(name: str) -> dict:
    return {"kind": KIND_TOOL_CALL, "tool": name}


class ConsoleFormatter(logging.Formatter):
    def __init__(self, color: bool = True) -> None:
        super().__init__()
        self.color = color

    def _paint(self, text: str, code: str) -> str:
        return f"{code}{text}{_RESET}" if self.color else text

    def format(self, record: logging.LogRecord) -> str:
        kind = getattr(record, "kind", None)

        if kind == KIND_LLM_TEXT:
            return self._paint(getattr(record, "llm_text", record.getMessage()), _BRIGHT_CYAN)
        if kind == KIND_TOOL_CALL:
            return self._paint(record.getMessage(), _GREEN)

        message = record.getMessage()
        if record.exc_info and record.levelno >= logging.ERROR:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if record.levelno >= logging.ERROR:
            return self._paint(f"! {message}", _BRIGHT_RED)
        if record.levelno >= logging.WARNING:
            return self._paint(f"! {message}", _YELLOW)
        if record.levelno <= logging.DEBUG:
            return self._paint(message, _DIM)
        return message


def _supports_color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if not hasattr(stream, "isatty") or not stream.isatty():
        return False
    if sys.platform == "win32":
        return _enable_windows_ansi()
    return True


def _enable_windows_ansi() -> bool:
    """Turn on ANSI escape processing for the Windows console (no-op on modern terminals)."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        enabled = False
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
                enabled = True
        return enabled
    except Exception:
        return False


def console_handler(level: int, stream: TextIO | None = None) -> logging.Handler:
    stream = stream or sys.stderr
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(ConsoleFormatter(color=_supports_color(stream)))
    handler.addFilter(_ConsoleFilter())
    return handler
