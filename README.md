# RoboAgent

RoboAgent is a lightweight AI coding/build agent for Python projects. It connects to an OpenAI-compatible chat API, exposes a small set of local tools to the model, and lets the model inspect files, edit code, and execute Python inside a controlled working directory.

## Purpose

The project is designed as a minimal foundation for an AI-assisted build agent that can:

- receive a natural-language task
- call local tools to inspect and modify files
- run Python code for validation
- iterate until it produces a final response

It is especially suited for local or self-hosted OpenAI-compatible endpoints because the API base URL is configurable.

## Current Architecture

The repository currently contains:

- a CLI-style entrypoint in `main.py`
- the main package in `agent/`
- prompt files in `prompts/`
- packaging/configuration files in `pyproject.toml` and `requirements.txt`

### Project structure

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
│       └── utils.py             # Shared path resolution and repository opening helpers
├── prompts/
│   └── system.md                # System prompt used by the agent
├── main.py                      # Example/manual entrypoint
├── pyproject.toml               # Package metadata and dev tool config
├── requirements.txt             # Runtime dependencies
└── README.md
```

## Key Components

### 1. Configuration

`agent/config.py` loads environment variables via `python-dotenv` and builds an `AgentConfig` object.

Supported settings:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL` (default: `http://localhost:8000/v1`)
- `OPENAI_MODEL` (default in code: `gpt-5.4`)
- `AGENT_WORKDIR` (default: `./workspace`)
- `AGENT_SYSTEM_PROMPT_DIR` (default: `./prompts`)
- `AGENT_SYSTEM_PROMPT_FILE` (default: `system.md`)
- `AGENT_MAX_ITERATIONS` (default: `20`)

The work directory and prompt directory are created automatically if they do not exist.

### 2. Agent loop

`agent/runner.py` contains the main orchestration logic:

- loads config and system prompt
- creates an `OpenAI` client
- sends the conversation and tool definitions to the model
- executes requested tools locally
- appends tool results back into the conversation
- repeats until the model returns a final answer or the iteration limit is reached

### 3. Tooling layer

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

### 4. Path safety and git helpers

`agent/core/utils.py` provides the shared `resolve_in_workdir` helper used to keep file and repository access inside `AGENT_WORKDIR`. The same module also centralizes repository opening with GitPython so git tools share consistent validation and error handling.

### 5. Git tooling

Git operations are implemented as separate modules for modularity and maintainability. Each operation logs its activity and handles repository or command failures gracefully.

### 6. Prompting

The system prompt is stored in `prompts/system.md`. It instructs the model to use tools, validate changes with Python execution when useful, keep edits focused, and provide a concise summary.

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

Alternatively, install as a package:

```bash
pip install -e .
pip install -e ".[dev]"  # optional development tools
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

Run the project with:

```bash
python main.py
```

`main.py` currently contains a hard-coded sample prompt plus commented examples for other tasks. It is best understood as a development/demo entrypoint rather than a polished CLI.

## Documentation corrections from analysis

The previous README did not match the current repository layout. The following items were outdated and have been corrected:

- the entrypoint is `main.py`, not `agent.py`
- the package directory is `agent/`, not `agent_core/`
- the system prompt file is `prompts/system.md`, not `system.txt`
- the default model in code is `gpt-5.4`, not `gpt-4o-mini`
- `AGENT_MAX_ITERATIONS` is supported and should be documented

## Observations and improvement opportunities

- `main.py` is currently a manual test harness with hard-coded prompts; a real CLI interface would improve usability.
- There are no tests in the repository yet, although the development instructions mention `pytest`.
- `runner.py` uses `from .core import *`; explicit imports would be clearer and easier to maintain.
- `folder_content.py` has minor style issues (unused import ordering/formatting), but functionality is straightforward.
- The package name in `pyproject.toml` is `agent-core`, while the repository name is `RoboAgent`; this may be intentional, but it is worth confirming.

## Development

Useful commands:

```bash
ruff check .
black .
pytest
```

## License

MIT
