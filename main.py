import logging

from agent import run_agent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger(__name__)

#    prompt = (
#        "Create a Python script named 'calc.py' with a function 'add(a, b)', mul(a, b). "
#        "The function 'add' should return the sum of 'a' and 'b', "
#        "and the function 'mul' should return the product of 'a' and 'b'. "
#        "Run a short test using available tools. "
#    )

#    prompt = (
#        "Create a Python script named 'enlist_folder_content.py' with a function 'folder_content(path: str, workdir: Path)'. "
#        "The function should return a list of all files and directories in the specified path with their names, sizes, and types. "
#        "Ignore hidden files and directories. "
#        "Run a short test using execute_python for relative path './workspace'. "
#    )

    prompt = (
        "Add `git pull` tool to the workflow. Enrich the git functionality with this new tool."
        "Ensure that the new tool is properly integrated and tested."
        "Update documentation to reflect the addition of the new tool."
    )


#    prompt = (
#        "It is a Python project for a lightweight AI build agent. "
#        "Read README.md and other relevant documentation files in the project. "
##        "Enrich tools with git functionality. Use GitPython for interacting with git repositories. "
##        "Each git operation should be placed in a separate python file for better modularity and maintainability. "
##        "Place common function as 'resolve_in_workdir' or used to open repo in the same file 'utils.py'. "
##        "Ensure that all git operations are logged and any errors are properly handled. "
#        
#        "Provide a summary of the project's purpose, structure, and key components. "
#        "Refresh README.md content to ensure the latest information is considered. "
#        "Provide any necessary updates or corrections to the documentation based on the analysis."
#    )

    logger.info("---\nStarting task:\n%s\n---", prompt)
    final_response = run_agent(prompt)
    logger.info("[Agent Final Response]:\n%s", final_response)

