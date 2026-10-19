# RoboAgent

RoboAgent is a lightweight AI coding and build agent for Python projects. It connects to an OpenAI-compatible chat API, exposes a focused set of local tools to the model, and allows the model to inspect files, edit code, run Python, and perform basic Git operations inside a controlled working directory.

## Purpose

The project is intended as a minimal foundation for an AI-assisted build agent that can:

- accept a natural-language task
- inspect project files and folders
- modify code and documentation
- execute Python for validation
- review and create Git changes
- iterate until it produces a final response

Because the API base URL is configurable, RoboAgent works well with local or self-hosted OpenAI-compatible endpoints in addition to hosted APIs.

## Repository Structure

```text
RoboAgent/
├── agent/
│   ├── __init__.py              # Exposes run_agent
│   ├── config.py                # Environment-based configuration loading
│   ├── runner.py                # Main agent loop and tool dispatch
│   ├── system_prompt.py         # Loads the system prompt file
│   └── core/
│       ├── __init__.py          # Tool registry and tool schemas
│       ├── execute_python.py    # Executes Python in a subprocess
│       ├── file_reader.py       # Reads files from AGENT_WORKDIR
│       ├── file_writer.py       # Writes files in AGENT_WORKDIR
│       ├── file_replacer.py     # Replaces text in files
│       ├── folder_content.py    # Lists directory contents as JSON
│       ├── git_add.py           # Stages files in a git repository
│       ├── git_commit.py        # Creates git commits
│       ├── git_diff.py          # Shows repository diffs
│       ├── git_log.py           # Shows recent commit history
│       ├── git_status.py        # Shows repository status
│       ├── paths.py             # Legacy path helper module
│       └── utils.py             # Shared path resolution and git repository helpers
├── prompts/
│   └── system.md                # System prompt used by the agent
├── main.py                      # Example/manual entrypoint
├── pyproject.toml               # Package metadata and tool configuration
├── requirements.txt             # Runtime dependencies
└── README.md
```

## Key Components

### Configuration

`agent/config.py` loads environment variables with `python-dotenv` and builds an `AgentConfig` object.

Supported settings:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (default: `http://localhost:8000/v1`)
- `OPENAI_MODEL` (default: `gpt-5.4`)
- `AGENT_WORKDIR` (default: `./workspace`)
- `AGENT_SYSTEM_PROMPT_DIR` (default: `./prompts`)
- `AGENT_SYSTEM_PROMPT_FILE` (default: `system.md`)
- `AGENT_MAX_ITERATIONS` (default: `20`)

The configured work directory and prompt directory are created automatically if they do not already exist.

### Agent Runner

`agent/runner.py` contains the orchestration loop. It:

1. loads configuration and the system prompt
2. creates an `OpenAI` client
3. sends the conversation and tool definitions to the model
4. executes requested tools locally
5. appends tool results back into the conversation
6. repeats until the model returns a final answer or the iteration limit is reached

### Tool Registry and Local Tools

`agent/core/__init__.py` defines the tool schemas exposed to the model and exports the implementations.

Available tools:

- `execute_python(code)`
- `read_file(path)`
- `write_file(path, content)`
- `replace_in_file(path, target_text, replacement_text)`
- `folder_content(path)`
- `git_status(repo_path)`
- `git_diff(repo_path, rev=None)`
- `git_add(repo_path, pathspec)`
- `git_commit(repo_path, message)`
- `git_log(repo_path, max_count=10)`

### Path Safety and Git Helpers

`agent/core/utils.py` centralizes path resolution and Git repository access. File and repository operations are constrained to `AGENT_WORKDIR` through `resolve_in_workdir`, which helps prevent accidental access outside the configured workspace.

There is also a `paths.py` module that contains a duplicate path helper. Based on the current code, `utils.py` is the active shared helper and `paths.py` appears to be leftover compatibility or legacy code.

### Prompting

The system prompt lives in `prompts/system.md`. It instructs the model to use tools, keep edits focused, validate changes when useful, and return a concise summary.

### Entrypoint

`main.py` is currently a simple manual entrypoint rather than a full CLI. It sets up logging, defines a hard-coded prompt, runs `run_agent`, and logs the final response.

## Setup

### Prerequisites

- Python 3.11+
- access to an OpenAI-compatible API endpoint

### Installation

```bash
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# or .venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Alternatively:

```bash
pip install -e .
pip install -e ".[dev]"
```

## Configuration

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=gpt-5.4
AGENT_WORKDIR=./workspace
AGENT_SYSTEM_PROMPT_DIR=./prompts
AGENT_SYSTEM_PROMPT_FILE=system.md
AGENT_MAX_ITERATIONS=20
```

## Usage

Run the example entrypoint with:

```bash
python main.py
```

At present, `main.py` is best treated as a development/demo harness. If you want a reusable command-line workflow, the next logical improvement would be adding a real CLI that accepts a prompt and optional configuration overrides.

## Documentation Updates Made

This README was refreshed to match the current repository state. Key corrections include:

- confirming the package name is `RoboAgent` in `pyproject.toml`
- documenting the current default model as `gpt-5.4`
- documenting `AGENT_MAX_ITERATIONS`
- reflecting the current `agent/` package layout and Git tool modules
- noting the presence of `agent/core/paths.py`, which is not part of the main documented flow
- clarifying that `main.py` is a manual/demo entrypoint rather than a polished CLI

## Observations

- The project is intentionally lightweight and easy to inspect.
- Git support is already integrated through dedicated tool modules.
- There are no tests in the repository yet, although development dependencies include `pytest`.
- `agent/runner.py` uses explicit imports from `agent.core`, which is clearer than wildcard imports.
- `agent/core/folder_content.py` includes an unused `Path` import and could be cleaned up in a future refactor.

## Development

Useful commands:

```bash
ruff check .
black .
pytest
```

## License

MIT
