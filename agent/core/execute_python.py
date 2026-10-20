import subprocess
import sys
from pathlib import Path

from .registry import tool


@tool
def execute_python(code: str, workdir: Path) -> str:
    """Execute Python code in a subprocess.

    Args:
        code: Python source to run with the agent's interpreter in the workdir.
    """
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(workdir),
    )
    output = result.stdout
    if result.stderr:
        output += f"\n[stderr]:\n{result.stderr}"
    return output if output else "[Code executed successfully without output]"
