import subprocess
from pathlib import Path

def execute_python(code: str, executable: Path, cwd: Path) -> str:
    python_executable = str(executable)

    """Execute Python code in a subprocess and return stdout/stderr."""
    try:
        result = subprocess.run(
            [python_executable, "-c", code],
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
