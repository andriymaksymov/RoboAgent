import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from agent import run_agent
from agent.config import agent_depth, load_config
from agent.console_log import console_handler
from agent.llm import LLMError, create_client
from agent.task_file import format_task_file

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_LOGS_DIR = Path(__file__).parent / "logs"


def _setup_file_logger(prompt_file: Path, verbose: bool) -> Path:
    """Attach a FileHandler to the root logger with the full, timestamped log.

    The log file is placed in ``<agent_root>/logs/`` and named
    ``<prompt_stem>_<YYYYMMDD_HHMMSS>.log``.  Sub-agents (``ROBOAGENT_DEPTH`` > 0) all use
    a ``task.md`` in their own folder, so their name is prefixed with that folder's name
    to keep concurrent runs in separate files.  Returns the resolved log path.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = prompt_file.stem
    if agent_depth() > 0:
        stem = f"sub_{prompt_file.resolve().parent.name}_{stem}"
    log_path = _LOGS_DIR / f"{stem}_{timestamp}.log"

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
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Console shows only warnings and errors (the log file is unchanged). "
        "Always on for sub-agents (ROBOAGENT_DEPTH > 0).",
    )
    parser.add_argument("--workdir", type=Path, help="Override the config's workdir.")
    parser.add_argument("--agent-dir", type=Path, help="Override the config's agent_dir.")
    parser.add_argument("--max-iterations", type=int, help="Override the config's max_iterations.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    # Console: compact view (no timestamp/module, "Iteration N" + highlighted model text,
    # tool calls with their arguments, "!" for problems), the same in verbose mode. The log
    # file keeps the full detail, including tool outcomes and DEBUG records when verbose.
    # Quiet (sub-agents): only warnings and errors, so parallel runs don't flood the console.
    quiet = args.quiet or agent_depth() > 0
    root.addHandler(console_handler(logging.WARNING if quiet else logging.INFO))
    # Keep third-party debug noise (HTTP, git) out of verbose agent logs.
    for noisy in ("httpx", "httpcore", "openai", "anthropic", "google_genai", "git"):
        logging.getLogger(noisy).setLevel(logging.INFO if args.verbose else logging.WARNING)
    logger = logging.getLogger("roboagent")

    log_path = _setup_file_logger(args.prompt_file, args.verbose)
    logger.info("Logging to file: %s", log_path)

    try:
        prompt = args.prompt_file.read_text(encoding="utf-8")
        config = load_config(
            args.config,
            verbose=args.verbose,
            workdir=args.workdir,
            agent_dir=args.agent_dir,
            max_iterations=args.max_iterations,
        )
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
        content = format_task_file(
            prompt, final_response, token_usage.input_tokens, token_usage.output_tokens
        )
        args.prompt_file.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Could not write final output to prompt file '%s': %s", args.prompt_file, exc)
        return 1

    return 1 if final_response.startswith("[Error]") else 0


if __name__ == "__main__":
    sys.exit(main())
