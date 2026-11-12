"""Dedicated developer tools: tests (pytest), lint and format (ruff), and pip.

Each tool exposes typed parameters instead of a free-form argument list, so the model
cannot pass arbitrary flags. All of them run as ``python -m <tool>`` with the agent's
interpreter via :func:`agent.core.process.run_module`, which also handles verbose
logging and auto-saving successful commands to memory.

pip is deliberately limited: read-only queries plus installing from a requirements file
or the project itself. Installing an arbitrary package by name is not offered; add it to
the project's requirements file (a reviewable, committed change) instead.
"""

import re
from pathlib import Path

from .process import format_result, run_module
from .registry import ToolError, tool
from .utils import resolve_dir, resolve_in_workdir

_PYTEST_STATUS = {
    0: "all tests passed",
    1: "some tests failed",
    2: "test run was interrupted",
    3: "internal pytest error",
    4: "pytest usage error",
    5: "no tests were collected",
}
_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _relative_paths(run_cwd: Path, paths: list[str] | None, *, node_ids: bool = False) -> list[str]:
    """Validate paths (or pytest node ids) against the run directory and return them relative to it."""
    result = []
    for raw in paths or []:
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("Paths must be non-empty strings.")
        if raw.startswith("-"):
            raise ToolError(f"Invalid path '{raw}': options are not accepted here.")
        file_part, sep, node = raw.partition("::") if node_ids else (raw, "", "")
        resolved = resolve_in_workdir(run_cwd, file_part)
        relative = resolved.relative_to(run_cwd.resolve()).as_posix() if resolved != run_cwd.resolve() else "."
        result.append(f"{relative}{sep}{node}")
    return result


def _run_dir(workdir: Path, cwd: str, agent_dir: Path | None) -> Path:
    return resolve_dir(workdir, cwd or ".", agent_dir)


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
    run_cwd = _run_dir(workdir, cwd, agent_dir)
    command = ["pytest", "-q", "-rfE", "--tb=short", "--no-header"]
    if keyword:
        command += ["-k", keyword]
    if last_failed:
        command.append("--last-failed")
    command += _relative_paths(run_cwd, paths, node_ids=True)

    result = run_module(
        "run_tests", command, run_cwd=run_cwd, cwd_label=cwd, timeout=timeout,
        verbose=verbose, agent_dir=agent_dir,
    )
    return format_result(result, _PYTEST_STATUS.get(result.returncode, "unknown pytest exit code"))


@tool
def lint(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    paths: list[str] | None = None,
    fix: bool = False,
    cwd: str = ".",
) -> str:
    """Lint Python code with ruff (ruff check) and return one line per issue: file:line:col code message.

    Args:
        paths: Files or directories relative to cwd (default: the whole cwd).
        fix: Apply ruff's safe automatic fixes and report the remaining issues.
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
    """
    run_cwd = _run_dir(workdir, cwd, agent_dir)
    command = ["ruff", "check", "--output-format", "concise", "--no-cache"]
    if fix:
        command.append("--fix")
    command += _relative_paths(run_cwd, paths) or ["."]

    result = run_module(
        "lint", command, run_cwd=run_cwd, cwd_label=cwd, timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    status = {0: "no issues", 1: "issues found"}.get(result.returncode, "ruff error")
    return format_result(result, status)


@tool
def format_code(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    paths: list[str] | None = None,
    check: bool = False,
    cwd: str = ".",
) -> str:
    """Format Python code with ruff (ruff format). With check=true, change nothing and show the diff that formatting would apply.

    Args:
        paths: Files or directories relative to cwd (default: the whole cwd).
        check: Only report (as a diff) what would be reformatted; do not modify files.
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
    """
    run_cwd = _run_dir(workdir, cwd, agent_dir)
    command = ["ruff", "format", "--no-cache"]
    if check:
        command.append("--diff")
    command += _relative_paths(run_cwd, paths) or ["."]

    result = run_module(
        "format_code", command, run_cwd=run_cwd, cwd_label=cwd, timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    if check:
        status = {0: "already formatted", 1: "files would be reformatted"}.get(result.returncode, "ruff error")
    else:
        status = "formatted" if result.returncode == 0 else "ruff error"
    return format_result(result, status)


@tool
def pip_list(workdir: Path, verbose: bool, agent_dir: Path | None, outdated: bool = False) -> str:
    """List the packages installed in the agent's Python environment.

    Args:
        outdated: Only list packages with a newer version available (queries the package index).
    """
    command = ["pip", "list", "--format", "columns", "--disable-pip-version-check"]
    if outdated:
        command.append("--outdated")
    result = run_module(
        "pip_list", command, run_cwd=workdir, cwd_label=".", timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    return format_result(result)


@tool
def pip_show(package: str, workdir: Path, verbose: bool, agent_dir: Path | None) -> str:
    """Show an installed package's version, location and dependencies.

    Args:
        package: Distribution name, e.g. 'requests'.
    """
    if not _PACKAGE_NAME.match(package or ""):
        raise ToolError(f"Invalid package name: '{package}'.")
    result = run_module(
        "pip_show", ["pip", "show", "--disable-pip-version-check", package],
        run_cwd=workdir, cwd_label=".", timeout=None,
        verbose=verbose, agent_dir=agent_dir, save_to_memory=False,
    )
    return format_result(result)


@tool
def pip_install(
    workdir: Path,
    agent_dir: Path | None,
    verbose: bool,
    requirements_file: str | None = None,
    cwd: str = ".",
    timeout: int | None = None,
) -> str:
    """Install the project's dependencies into the agent's environment: from a requirements file, or (without one) the project in cwd itself in editable mode (pip install -e .). Installing an arbitrary package by name is not supported: add it to the requirements file or pyproject.toml first.

    Args:
        requirements_file: Requirements file relative to cwd, e.g. 'requirements.txt'. Omit to install the project in cwd (needs pyproject.toml or setup.py).
        cwd: Directory to run in, relative to the workdir ('@agent' for the agent's own repository).
        timeout: Timeout in seconds (default 300, max 600).
    """
    run_cwd = _run_dir(workdir, cwd, agent_dir)
    command = ["pip", "install", "--disable-pip-version-check"]
    if requirements_file:
        (relative,) = _relative_paths(run_cwd, [requirements_file])
        if not (run_cwd / relative).is_file():
            raise ToolError(f"Requirements file not found: '{requirements_file}'.")
        command += ["-r", relative]
    else:
        if not any((run_cwd / name).is_file() for name in ("pyproject.toml", "setup.py")):
            raise ToolError(
                f"No pyproject.toml or setup.py in '{cwd}'; pass requirements_file instead."
            )
        command += ["-e", "."]

    result = run_module(
        "pip_install", command, run_cwd=run_cwd, cwd_label=cwd, timeout=timeout or 300,
        verbose=verbose, agent_dir=agent_dir,
    )
    return format_result(result, "installed" if result.returncode == 0 else "install failed")
