# RoboAgent

RoboAgent is a lightweight AI coding and build agent for Python projects. It connects to an OpenAI-compatible chat API, exposes a focused set of local tools to the model, and lets the model inspect files, edit code, run Python, search project trees, and perform basic Git operations inside a controlled working directory.

## Purpose

The project is a minimal foundation for an AI-assisted build agent that can:

- accept a natural-language task
- inspect project files and folders
- search for files and matching content across subfolders
- modify code and documentation
- execute Python for validation
- review and create Git changes
- iterate until it produces a final response

Because the API base URL is configurable, RoboAgent can work with hosted APIs as well as local or self-hosted OpenAI-compatible endpoints.

## Repository Structure

```text
RoboAgent/
├── agent/
│   ├── __init__.py              # Exposes run_agent
│   ├── branch_guard.py          # Refuses to start on protected branches
│   ├── config.py                # Loads .env (API settings) and the TOML run config
│   ├── runner.py                # Main agent loop and tool dispatch
│   ├── system_prompt.py         # Loads the system prompt file
│   └── core/
│       ├── __init__.py          # Imports the built-in tool modules (registers them)
│       ├── content_search.py    # Grep-like content search in folders/subfolders
│       ├── execute_python.py    # Executes Python in a subprocess
│       ├── file_reader.py       # Reads files from the workdir
│       ├── file_replacer.py     # Replaces text in files
│       ├── file_search.py       # Searches files by glob pattern
│       ├── file_writer.py       # Writes files in the workdir
│       ├── folder_content.py    # Lists directory contents as JSON
│       ├── git_add.py           # Stages files in a git repository
│       ├── git_commit.py        # Creates git commits
│       ├── git_diff.py          # Shows repository diffs
│       ├── git_log.py           # Shows recent commit history
│       ├── git_pull.py          # Pulls remote changes
│       ├── git_restore.py       # Discards or unstages uncommitted changes
│       ├── git_status.py        # Shows repository status
│       ├── registry.py          # @tool decorator, Tool, ToolRegistry, central error handling/logging
│       ├── run_command.py       # Runs allowed tools (pytest, pip, ruff)
│       └── utils.py             # Shared path resolution and git repository helpers
├── prompts/
│   └── system.md                # System prompt used by the agent
├── cli.py                       # Command-line entrypoint
├── roboagent.toml               # Example run configuration
├── pyproject.toml               # Package metadata and tool configuration
├── requirements.txt             # Runtime dependencies
└── README.md
```

## Key Components

### Configuration

Configuration is split in two:

- **`.env`**: general settings only, loaded with `python-dotenv`:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL` (default: `http://localhost:8000/v1`)
  - `OPENAI_MODEL` (default: `gpt-5.4`)
- **TOML run config** (passed with `--config`, see [`roboagent.toml`](roboagent.toml)): per-run settings. Relative paths are resolved against the config file's directory. Without a config file, the defaults apply relative to the current directory. Unknown keys are rejected.
  - `workdir` (default: `./workspace`): the only directory the tools may access; it is created if missing
  - `system_prompt` (default: `./prompts/system.md`)
  - `max_iterations` (default: `20`)
  - `protected_branches` (default: `["main"]`): the agent refuses to start if a repository in the workdir (the workdir itself or a direct subfolder) is on one of these branches
  - `allowed_commands` (default: `["pytest", "pip", "ruff"]`): tools `run_command` may execute; each runs as `python -m <tool>` with the agent's interpreter
  - `model` (optional): overrides `OPENAI_MODEL` for this run

### Agent Runner

`agent/runner.py` contains the orchestration loop. It:

1. loads configuration and the system prompt
2. refuses to start if a repository in the workdir is on a protected branch (see `protected_branches`)
3. creates an `OpenAI` client
4. sends the conversation and tool definitions to the model
5. executes requested tools locally
6. appends tool results back into the conversation
7. repeats until the model returns a final answer or the iteration limit is reached

The runner currently uses the Chat Completions API and keeps the interaction loop intentionally small and easy to inspect.

### Tool Registry and Local Tools

A tool is a plain function decorated with `@tool` (`agent/core/registry.py`). The decorator builds the JSON schema from the function signature and its Google-style docstring, then registers the tool in `REGISTRY`:

```python
from pathlib import Path

from .registry import ToolError, tool


@tool
def count_lines(path: str, workdir: Path) -> str:
    """Count the lines of a file in the workdir.

    Args:
        path: File path relative to the workdir.
    """
    file = workdir / path
    if not file.is_file():
        raise ToolError(f"Not a file: '{path}'.")
    return str(len(file.read_text(encoding="utf-8").splitlines()))
```

How a tool is built from the function:

- **Description**: the docstring text above `Args:`. Each `Args:` entry becomes that parameter's description.
- **Types**: `str`, `int`, `float`, `bool`, `list[...]`, `dict` and `X | None` map to JSON schema types. Parameters without a default are required.
- **Injected parameters**: parameters named like an `AgentConfig` field (`workdir`, `allowed_commands`, ...) or `config` are filled in from the configuration and hidden from the model.
- **Errors**: raise `ToolError` (or let an `OSError` propagate) for expected failures. The model receives `[Error]: <message>`. Any other exception is also returned as an error, and its traceback is logged at debug level. Tools need no try/except of their own.
- **Logging**: each call logs one short info line with the arguments and one with the first output line and its size. Debug level (`--verbose`) adds the full arguments and output.

To add a tool, put the decorated function in a module under `agent/core/` and import it in `agent/core/__init__.py`.

Available tools:

- `execute_python(code)`
- `run_command(command, cwd=".", timeout=120)`
- `read_file(path)`
- `write_file(path, content)`
- `replace_in_file(path, target_text, replacement_text)`
- `folder_content(path)`
- `file_search(path, pattern)`
- `content_search(path, query, file_pattern=None)`
- `git_pull(repo_path)`
- `git_status(repo_path)`
- `git_diff(repo_path, rev=None)`
- `git_add(repo_path, pathspec)`
- `git_restore(repo_path, pathspec, staged=False, source=None)`
- `git_commit(repo_path, message)`
- `git_log(repo_path, max_count=10)`

These tools are intentionally narrow in scope so the agent can inspect and modify a project while staying within the configured workspace.

### Search Tools

The new search tools are split into separate modules:

- `file_search` searches for files recursively using gitignore-style glob patterns such as `*.py`, `**/*.md`, or `agent/core/*.py`.
- `content_search` performs grep-like recursive content search and returns structured matches including file path, line number, line text, and submatch offsets.

The implementation uses Python's standard library:

- `pathlib.Path.rglob` for recursive traversal
- `fnmatch` for glob-style file filtering
- `re` for grep-like content matching

This approach fits the lightweight build-agent workflow because it adds no extra runtime dependencies while still providing practical recursive file and content search.

### Path Safety and Git Helpers

`agent/core/utils.py` centralizes path resolution and Git repository access. File and repository operations are constrained to the workdir through `resolve_in_workdir`, which helps prevent accidental access outside the configured workspace.

Git operations are implemented as separate modules and use `GitPython` under the hood. The available workflow includes `git_pull`, allowing the agent to begin repository work by synchronizing with the remote before inspecting status or making changes.

### Prompting

The system prompt lives in `prompts/system.md`. It instructs the model to inspect files before editing, validate changes after modifications, keep edits focused, and return a concise summary.

### Entrypoint

`cli.py` is the command-line entrypoint. It takes the task prompt file and an optional run config file, runs the agent, and exits with `0` on success, `1` if the agent returns an error, or `2` for an invalid prompt or config file.

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

Create a `.env` file in the project root (see `.env.example`):

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=gpt-5.4
```

Run settings go in a TOML file such as [`roboagent.toml`](roboagent.toml):

```toml
workdir = "./workspace"
system_prompt = "./prompts/system.md"
max_iterations = 20
protected_branches = ["main"]
allowed_commands = ["pytest", "pip", "ruff"]
```

## Usage

```bash
python cli.py --prompt-file prompt.md --config roboagent.toml
python cli.py -p prompt.md -c roboagent.toml --verbose   # debug logging
python cli.py --help
```

Keep one config file per kind of run, for example a different workdir, system prompt or allowed commands, and pass the one you need.

## Development

Useful commands:

```bash
ruff check .
black .
pytest
```

## License

MIT
