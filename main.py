import logging

from agent_core import run_agent


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
#        "Create a Python script named 'calc.py' with a function 'add(a, b)'. "
#        "The function should return the sum of 'a' and 'b'. "
#        "Run a short test using available tools. "
#    )

    prompt = (
        "Analyse this Python project. It is a package for AI build agent. "
        "Provide a detailed analysis of the project's structure, functionality, and potential improvements. "
        "Identify any potential issues or areas for optimization within the project. "
        "Summarize the key findings and next steps for the project. "
        "Persist your result in 'ANALYSIS.md' file"
    )
    logger.info("---\nStarting task:\n%s\n---", prompt)
    final_response = run_agent(prompt)
    logger.info("[Agent Final Response]:\n%s", final_response)

