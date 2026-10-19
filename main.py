from agent_core import run_agent


if __name__ == "__main__":
    prompt = (
        "Create a Python script named 'enlist_folder_content.py' with a function 'folder_content(path: str, workdir: Path)'. "
        "The function should return a list of all files and directories in the specified path with their names, sizes, and types. "
        "Ignore hidden files and directories. "
        "Run a short test using execute_python for relative path './workspace'. "
    )
    print(f"--- Starting task: {prompt} ---\n")
    final_response = run_agent(prompt)
    print("\n[Agent Final Response]:")
    print(final_response)

