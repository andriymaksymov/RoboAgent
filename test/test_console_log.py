"""Tests for the compact console log view and the file-only detail records."""

import io
import logging

import pytest

from agent.console_log import console_handler, file_only, llm_text, tool_call, tool_result
from agent.core.registry import ToolError, ToolRegistry, build_tool


@pytest.fixture
def console(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    handler = console_handler(logging.INFO, stream)
    logger = logging.getLogger("test.console_log")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    yield logger, stream
    logger.removeHandler(handler)


def lines(stream: io.StringIO) -> list[str]:
    return stream.getvalue().splitlines()


def test_plain_info_has_no_timestamp_or_module(console):
    logger, stream = console
    logger.info("Iteration %s", 1)
    assert lines(stream) == ["Iteration 1"]


def test_llm_text_is_printed_in_full(console):
    logger, stream = console
    text = "first line\n" + "x" * 500
    logger.info("Model: %s", text, extra=llm_text(text))
    assert stream.getvalue() == text + "\n"


def test_tool_call_shows_name_only(console):
    logger, stream = console
    logger.info("-> read_file(path='a.txt')", extra=tool_call("read_file"))
    assert lines(stream) == ["-> read_file"]


def test_tool_result_succeeded_and_failed(console):
    logger, stream = console
    logger.info("<- t: ok", extra=tool_result("t", ok=True))
    logger.warning("<- t failed: boom", extra=tool_result("t", ok=False, error="boom"))
    assert [line.strip() for line in lines(stream)] == ["succeeded", "failed  ! boom"]


def test_warnings_and_errors_are_marked(console):
    logger, stream = console
    logger.warning("careful")
    logger.error("broken")
    assert lines(stream) == ["! careful", "! broken"]


def test_debug_and_file_only_records_stay_off_the_console(console):
    logger, stream = console
    logger.debug("debug detail")
    logger.info("file detail", extra=file_only())
    assert stream.getvalue() == ""


def _tool(func):
    return build_tool(func)


def ok(x: str) -> str:
    """ok.

    Args:
        x: x
    """
    return "fine"


def bad(x: str) -> str:
    """bad.

    Args:
        x: x
    """
    raise ToolError("nope")


def nonzero(x: str) -> str:
    """nonzero.

    Args:
        x: x
    """
    return "[Exit code]: 1\n[Status]: some tests failed\n"


def test_registry_console_view(monkeypatch, tmp_path):
    from agent.config import load_config

    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    handler = console_handler(logging.INFO, stream)
    registry_logger = logging.getLogger("agent.core.registry")
    previous = registry_logger.level
    registry_logger.setLevel(logging.INFO)
    registry_logger.addHandler(handler)
    try:
        registry = ToolRegistry([_tool(ok), _tool(bad), _tool(nonzero)])
        config = load_config()
        for name in ("ok", "bad", "nonzero"):
            registry.invoke(name, {"x": "1"}, config)
    finally:
        registry_logger.removeHandler(handler)
        registry_logger.setLevel(previous)

    assert [line.strip() for line in lines(stream)] == [
        "-> ok",
        "succeeded",
        "-> bad",
        "failed  ! nope",
        "-> nonzero",
        "failed  ! exit code 1 (some tests failed)",
    ]
