from pathlib import Path


def load_system_prompt(prompt_file: Path) -> str:
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    raise FileNotFoundError(f"System prompt file not found: {prompt_file}")
