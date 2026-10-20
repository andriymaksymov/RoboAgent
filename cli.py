import logging
from pathlib import Path
from agent import run_agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

    prompt = Path("./prompt.md").read_text(encoding="utf-8")

    logger.info("---\nStarting task:\n%s\n---", prompt)
    final_response = run_agent(prompt)
    logger.info("[Agent Final Response]:\n%s", final_response)

