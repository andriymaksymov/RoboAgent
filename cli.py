import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from agent import run_agent
from agent.config import load_config
from agent.llm import LLMError, create_client

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOGS_DIR = Path(__file__).parent / "logs"


def _setup_file_logger(prompt_file: Path, verbose: bool) -> Path:
    """Attach a FileHandler to the root logger that mirrors all console output.

    The log file is placed in ``<agent_root>/logs/`` and named
    ``<prompt_stem>_<YYYYMMDD_HHMMSS>.log``.  Returns the resolved log path.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _LOGS_DIR / f"{prompt_file.stem}_{timestamp}.log"

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    logging.getLogger().addHandler(handler)
    return log_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="roboagent",
        description="Run the RoboAgent build agent on a task. "
        "The LLM provider is selected in the config file; API key, endpoint and model "
        "come from the provider preset and LLM_* variables in the environment / .env.",
    )
    parser.add_argument(
        "-p",
        "--prompt-file",
        type=Path,
        required=True,
        help="Markdown/text file with the task for the agent.",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help="TOML config file with run settings (provider, workdir, system prompt, ...). "
        "Defaults are used if omitted.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging: full tool arguments and outputs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=_LOG_FORMAT,
    )
    # Keep third-party debug noise (HTTP, git) out of verbose agent logs.
    for noisy in ("httpx", "httpcore", "openai", "anthropic", "google_genai", "git"):
        logging.getLogger(noisy).setLevel(logging.INFO if args.verbose else logging.WARNING)
    logger = logging.getLogger("roboagent")

    log_path = _setup_file_logger(args.prompt_file, args.verbose)
    logger.info("Logging to file: %s", log_path)

    try:
        prompt = args.prompt_file.read_text(encoding="utf-8")
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        logger.error("%s", exc)
        return 2

    logger.info(
        "Config: %s | workdir: %s | provider: %s | model: %s",
        args.config or "defaults",
        config.workdir,
        config.provider,
        config.model,
    )
    logger.info("---\nStarting task:\n%s\n---", prompt)
    try:
        client = create_client(config.llm)
    except (LLMError, ValueError) as exc:
        logger.error("%s", exc)
        return 1

    final_response = run_agent(prompt, config, client=client)
    token_usage = client.token_usage
    
    logger.info("---")
    logger.info("[Agent Final Response]:\n%s", final_response)
    
    logger.info(
        "[Token usage]:\ninput=%d, output=%d",
        token_usage.input_tokens,
        token_usage.output_tokens,
    )

    try:
        prompt = f"# User Prompt\n\n{prompt}\n\n---\n# Agent Response\n\n{final_response}"
        args.prompt_file.write_text(prompt, encoding="utf-8")
    except OSError as exc:
        logger.error("Could not write final output to prompt file '%s': %s", args.prompt_file, exc)
        return 1

    return 1 if final_response.startswith("[Error]") else 0


if __name__ == "__main__":
    sys.exit(main())
