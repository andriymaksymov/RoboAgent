from pathlib import Path


def load_system_prompt(prompt_dir: Path, prompt_file: str) -> str:
    candidate = (prompt_dir / prompt_file).resolve()

    if candidate.exists():
        return candidate.read_text(encoding="utf-8")

    raise FileNotFoundError(f"System prompt file not found: {candidate}")

