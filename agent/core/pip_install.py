"""pip_install – install the project's dependencies into the agent's environment.

Deliberately limited: installing from a requirements file or the project itself only.
Installing an arbitrary package by name is not offered; add it to the project's
requirements file (a reviewable, committed change) instead.
"""

from pathlib import Path

from .process import format_result, run_module
from .registry import ToolError, tool
from .utils import relative_paths, run_dir


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
    run_cwd = run_dir(workdir, cwd, agent_dir)
    command = ["pip", "install", "--disable-pip-version-check"]
    if requirements_file:
        (relative,) = relative_paths(run_cwd, [requirements_file])
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
