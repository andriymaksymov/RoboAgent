import sys
import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def execute_python(code: str, cwd: Path) -> str:

    """Execute Python code in a subprocess and return stdout/stderr."""
    try:
        logger.debug("Executing Python code in cwd=%s", cwd)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(cwd),
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]:\n{result.stderr}"
        return output if output else "[Code executed successfully without output]"
    except Exception as exc:
        return f"[Execution error]: {exc}"
