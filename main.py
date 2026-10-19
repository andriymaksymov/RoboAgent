from agent_core import run_agent


if __name__ == "__main__":
    prompt = (
        "Create a Python script named 'calculator.py' with a function 'add(a, b)'. "
        "Run a short test using execute_python. "
        "Then use replace_in_file to add a function 'multiply(a, b)' and test again."
    )
    print(f"--- Starting task: {prompt} ---\n")
    final_response = run_agent(prompt)
    print("\n[Agent Final Response]:")
    print(final_response)

