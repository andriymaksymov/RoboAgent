import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AgentConfig:
    api_key: str
    base_url: str
    model: str
    workdir: Path
    system_prompt_dir: Path
    system_prompt_file: str
    python_executable: Path
    max_iterations: int


def _parse_positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return parsed if parsed > 0 else default


def load_config() -> AgentConfig:
    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    workdir = Path(os.getenv("AGENT_WORKDIR", "./workspace")).resolve()
    system_prompt_dir = Path(os.getenv("AGENT_SYSTEM_PROMPT_DIR", "./prompts")).resolve()
    system_prompt_file = os.getenv("AGENT_SYSTEM_PROMPT_FILE", "system.md")
    python_executable = Path(os.getenv("AGENT_PYTHON_EXECUTABLE", ".venv/Scripts/python.exe")).resolve()
    max_iterations = _parse_positive_int(os.getenv("AGENT_MAX_ITERATIONS", "20"), 20)

    workdir.mkdir(parents=True, exist_ok=True)
    system_prompt_dir.mkdir(parents=True, exist_ok=True)

    return AgentConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        workdir=workdir,
        system_prompt_dir=system_prompt_dir,
        system_prompt_file=system_prompt_file,
        python_executable=python_executable,
        max_iterations=max_iterations,
    )
