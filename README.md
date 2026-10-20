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
│   ├── config.py                # Environment-based configuration loading
│   ├── runner.py                # Main agent loop and tool dispatch
│   ├── system_prompt.py         # Loads the system prompt file
│   └── core/
│       ├── __init__.py          # Tool registry and tool schemas
│       ├── content_search.py    # Grep-like content search in folders/subfolders
│       ├── execute_python.py    # Executes Python in a subprocess
│       ├── file_reader.py       # Reads files from AGENT_WORKDIR
│       ├── file_replacer.py     # Replaces text in files
│       ├── file_search.py       # Searches files by glob pattern
│       ├── file_writer.py       # Writes files in AGENT_WORKDIR
│       ├── folder_content.py    # Lists directory contents as JSON
│       ├── git_add.py           # Stages files in a git repository
│       ├── git_commit.py        # Creates git commits
│       ├── git_diff.py          # Shows repository diffs
│       ├── git_log.py           # Shows recent commit history
│       ├── git_pull.py          # Pulls remote changes
│       ├── git_status.py        # Shows repository status
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

The runner currently uses the Chat Completions API and keeps the interaction loop intentionally small and easy to inspect.

### Tool Registry and Local Tools

`agent/core/__init__.py` defines the tool schemas exposed to the model and exports the implementations.

Available tools:

- `execute_python(code)`
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

`agent/core/utils.py` centralizes path resolution and Git repository access. File and repository operations are constrained to `AGENT_WORKDIR` through `resolve_in_workdir`, which helps prevent accidental access outside the configured workspace.

Git operations are implemented as separate modules and use `GitPython` under the hood. The available workflow includes `git_pull`, allowing the agent to begin repository work by synchronizing with the remote before inspecting status or making changes.

### Prompting

The system prompt lives in `prompts/system.md`. It instructs the model to inspect files before editing, validate changes after modifications, keep edits focused, and return a concise summary.

### Entrypoint

`main.py` is a simple manual entrypoint rather than a full CLI. It sets up logging, defines a hard-coded prompt, runs `run_agent`, and logs the final response.

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

At present, `main.py` is best treated as a development or demo harness. A natural next step for the project would be adding a real CLI that accepts a prompt and optional configuration overrides.

## Development

Useful commands:

```bash
ruff check .
black .
pytest
```

## License

MIT
