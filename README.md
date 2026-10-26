# RoboAgent

RoboAgent is a lightweight AI coding and build agent for Python projects. It connects to a switchable LLM provider (OpenAI, Anthropic Claude, Google Gemini or a local OpenAI-compatible server), exposes a focused set of local tools to the model, and lets the model inspect files, edit code, run Python, search project trees, and perform basic Git operations inside a controlled working directory.

## Purpose

The project is a minimal foundation for an AI-assisted build agent that can:

- accept a natural-language task
- inspect project files and folders
- search for files and matching content across subfolders
- modify code and documentation
- execute Python for validation
- review and create Git changes
- iterate until it produces a final response

The provider is selected with one setting in the run config. Each provider uses its native API, so features such as reasoning, thinking and prompt caching work as intended.

## Repository Structure

```text
RoboAgent/
├── agent/
│   ├── __init__.py              # Exposes run_agent
│   ├── branch_guard.py          # Refuses to start on protected branches
│   ├── config.py                # Loads .env (LLM_* settings) and the TOML run config
│   ├── runner.py                # Main agent loop and tool dispatch
│   ├── system_prompt.py         # Loads the system prompt file
│   ├── llm/
│   │   ├── __init__.py          # create_client(): picks the backend for the provider
│   │   ├── base.py              # LLMClient interface, ToolSpec/ToolCall/ToolResult/LLMResponse
│   │   ├── presets.py           # Provider presets (model, endpoint) and env variable resolution
│   │   ├── openai_client.py     # OpenAI Responses API
│   │   ├── claude_client.py     # Anthropic Messages API
│   │   ├── gemini_client.py     # Google Gemini (google-genai)
│   │   └── local_client.py      # OpenAI-compatible Chat Completions (vLLM, Ollama, ...)
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
│       ├── git_ls_files.py      # Lists files tracked by git
│       ├── git_pull.py          # Pulls remote changes
│       ├── git_restore.py       # Discards or unstages uncommitted changes
│       ├── git_status.py        # Shows repository status
│       ├── registry.py          # @tool decorator, Tool, ToolRegistry, central error handling/logging
│       ├── run_command.py       # Runs allowed tools (pytest, pip, ruff)
│       └── utils.py             # Shared path resolution and git repository helpers
│   └── plugin/
│       ├── __init__.py          # Auto-discovers and imports every plugin module
│       └── echo.py              # Example plugin tool and template
├── prompts/
│   └── system.md                # System prompt used by the agent
├── cli.py                       # Command-line entrypoint
├── roboagent.toml.example       # Example run configuration
├── pyproject.toml               # Package metadata and tool configuration
├── requirements.txt             # Runtime dependencies
├── test/                        # pytest suite
└── README.md
```

## Key Components

### Configuration

Configuration is split in two:

- **`.env`**: LLM API settings, loaded with `python-dotenv` (see [`.env.example`](.env.example)). Each setting is looked up as `<PROVIDER>_<KEY>` (e.g. `ANTHROPIC_API_KEY`), then `LLM_<KEY>`, then the provider preset:
  - `<PROVIDER>_API_KEY` / `LLM_API_KEY`. If neither is set, the provider SDK falls back to its own variable.
  - `<PROVIDER>_BASE_URL` / `LLM_BASE_URL`
  - `<PROVIDER>_MODEL` / `LLM_MODEL`
- **TOML run config** (passed with `--config`, see [`roboagent.toml.example`](roboagent.toml.example)): per-run settings. Relative paths are resolved against the config file's directory. Without a config file, the defaults apply relative to the current directory. Unknown keys are rejected.
  - `provider` (default: `anthropic`): `openai`, `anthropic`, `gemini` or `local`, see [LLM Providers](#llm-providers)
  - `workdir` (default: `./workspace`): the only directory the tools may access; it is created if missing
  - `system_prompt` (default: `./prompts/system.md`)
  - `max_iterations` (default: `20`)
  - `protected_branches` (default: `["main"]`): the agent refuses to start if a repository in the workdir (the workdir itself or a direct subfolder) is on one of these branches
  - `allowed_commands` (default: `["pytest", "pip", "ruff"]`): tools `run_command` may execute; each runs as `python -m <tool>` with the agent's interpreter
  - `model` (optional): overrides the provider's model (`<PROVIDER>_MODEL`, `LLM_MODEL` or preset) for this run

### LLM Providers

`agent/llm/` hides the provider behind one small interface, `LLMClient`:

- `start(system_prompt, user_prompt, tools)` begins a conversation
- `complete()` returns an `LLMResponse` (text plus `ToolCall`s)
- `add_tool_results(results)` sends the tool outputs back

Each backend keeps the conversation in its provider's native format. Provider-specific state (reasoning items, thinking blocks, thought signatures) is returned to the model unchanged.

| `provider` | API | Preset model | Preset endpoint | Notes |
|---|---|---|---|---|
| `openai` | Responses API | `gpt-5.4` | SDK default | stateless (`store=False`), encrypted reasoning passed back between turns, `reasoning.effort="medium"` |
| `anthropic` | Messages API | `claude-sonnet-4-6` | SDK default | adaptive thinking, automatic prompt caching, `is_error` on failed tool results |
| `gemini` | `google-genai` | `gemini-2.5-pro` | SDK default | `system_instruction`, raw JSON schemas, automatic function calling disabled, thought signatures preserved |
| `local` | Chat Completions | none (set `LOCAL_MODEL` or `model`) | `http://localhost:8000/v1` | any OpenAI-compatible server (vLLM, Ollama, llama.cpp, LM Studio), `temperature=0.1` |

Tuning knobs such as `reasoning_effort`, `max_tokens`, `thinking` or `temperature` are class attributes of each backend. To add a provider, implement `LLMClient` in a new module and register a `ProviderPreset` in `agent/llm/presets.py`. Provider SDKs are imported only when their provider is selected.

### Agent Runner

`agent/runner.py` contains the orchestration loop. It:

1. loads configuration and the system prompt
2. refuses to start if a repository in the workdir is on a protected branch (see `protected_branches`)
3. creates the `LLMClient` for the configured provider (`agent.llm.create_client`)
4. sends the conversation and tool definitions to the model
5. executes requested tools locally
6. appends tool results back into the conversation
7. repeats until the model returns a final answer or the iteration limit is reached

The runner is provider-neutral. API failures are returned as `[Error]: ...` (CLI exit code `1`).

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

To add a tool, drop a module with the decorated function into `agent/plugin/`; it is imported automatically at startup (a plugin that fails to import is logged and skipped). Built-in tools live in `agent/core/` and are imported in `agent/core/__init__.py`.

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
- `git_ls_files(repo_path, pathspec=None)`
- `echo(message, repeat=1)` (example plugin)

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
- an API key for OpenAI, Anthropic or Google Gemini, or a local OpenAI-compatible server

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
ANTHROPIC_API_KEY=your_anthropic_key_here
OPENAI_API_KEY=your_openai_key_here
GEMINI_API_KEY=your_gemini_key_here
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL=your-local-model
```

Run settings go in a TOML file. Copy [`roboagent.toml.example`](roboagent.toml.example) to `roboagent.toml` and adjust it:

```toml
provider = "anthropic"   # "openai" | "anthropic" | "gemini" | "local"
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
