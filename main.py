import logging

from agent import run_agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

#    prompt = (
#        "Create a Python script named 'enlist_folder_content.py' with a function 'folder_content(path: str, workdir: Path)'. "
#        "The function should return a list of all files and directories in the specified path with their names, sizes, and types. "
#        "Ignore hidden files and directories. "
#        "Run a short test using execute_python for relative path './workspace'. "
#    )

#    prompt = (
#        "Analyse the code. "
#        "Add verbose functionality to log detailed information about the analysis. "
#        "Ensure that all steps and decisions made during the analysis are clearly logged. "
#        "Provide a summary of used tokens. "
#        "Provide a proposed plan for further actions based on the analysis."
#    )

#    prompt = (
#        "Create a Python script named 'calc.py' with a function 'add(a, b)', mul(a, b). "
#        "The function 'add' should return the sum of 'a' and 'b', "
#        "and the function 'mul' should return the product of 'a' and 'b'. "
#        "Run a short test using available tools. "
#    )

    prompt = (
        "It is a python project for an AI build agent. Analyse this project. "
        "Read README.md and other relevant documentation files in the project. "
        "Provide a summary of the project's purpose, structure, and key components. "
        "Refresh README.md content to ensure the latest information is considered. "
        "Provide any necessary updates or corrections to the documentation based on the analysis."
    )

    logger.info("---\nStarting task:\n%s\n---", prompt)
    final_response = run_agent(prompt)
    logger.info("[Agent Final Response]:\n%s", final_response)

