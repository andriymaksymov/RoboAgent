"""run_tests – run the test suite with pytest (``python -m pytest`` via :func:`run_module`)."""

from pathlib import Path

from .process import format_result, run_module
from .registry import tool
from .utils import relative_paths, run_dir

_PYTEST_STATUS = {
    0: "all tests passed",
    1: "some tests failed",
    2: "test run was interrupted",
    3: "internal pytest error",
    4: "pytest usage error",
    5: "no tests were collected",
}


@tool
def run_tests(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    paths: list[str] | None = None,
    keyword: str | None = None,
    last_failed: bool = False,
    cwd: str = ".",
    timeout: int | None = None,
) -> str:
    """Run the test suite with pytest (quiet, short tracebacks, summary of failures and errors). Returns the exit code, a status line and pytest's output.

    Args:
        paths: Test files, directories or node ids relative to cwd, e.g. ["test/test_x.py::test_y"]. Default: pytest's configured test paths.
        keyword: Only run tests matching this pytest -k expression.
        last_failed: Re-run only the tests that failed in the previous run.
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
        timeout: Timeout in seconds (default 120, max 600).
    """
    run_cwd = run_dir(workdir, cwd, agent_dir)
    command = ["pytest", "-q", "-rfE", "--tb=short", "--no-header"]
    if keyword:
        command += ["-k", keyword]
    if last_failed:
        command.append("--last-failed")
    command += relative_paths(run_cwd, paths, node_ids=True)

    result = run_module(
        "run_tests", command, run_cwd=run_cwd, cwd_label=cwd, timeout=timeout,
        verbose=verbose, agent_dir=agent_dir,
    )
    return format_result(result, _PYTEST_STATUS.get(result.returncode, "unknown pytest exit code"))
