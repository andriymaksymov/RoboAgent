# RoboAgent

An AI coding agent powered by an OpenAI-compatible API (including on-prem AI servers) with local Python execution tools.

## Features

- Integration with OpenAI-compatible chat API
- Local Python code execution
- Tool calling for file read/write/replace operations
- Rich terminal output

## Setup

### Prerequisites

- Python 3.11 or higher
- OpenAI-compatible API endpoint

### Installation

1. Create a virtual environment:

```bash
python -m venv venv
```

2. Activate the virtual environment:

**On Windows:**
```bash
venv\Scripts\activate
```

**On macOS/Linux:**
```bash
source venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root with your API key:

```
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=gpt-4o-mini
AGENT_WORKDIR=./workspace
AGENT_SYSTEM_PROMPT_DIR=./prompts
AGENT_SYSTEM_PROMPT_FILE=system.txt
```

`AGENT_WORKDIR` controls where generated code files are created and edited.

`AGENT_SYSTEM_PROMPT_DIR` and `AGENT_SYSTEM_PROMPT_FILE` define where the system prompt is loaded from.

## Usage

Run the agent:

```bash
python agent.py
```

## Development

Install development dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run linting:

```bash
ruff check .
black . --check
```

## Project Structure

```
RoboAgent/
├── agent.py                   # Main entrypoint
├── agent_core/                # Agent package
│   ├── __init__.py
│   ├── config.py
│   ├── runner.py
│   ├── execute_python.py
│   ├── file_reader.py
│   ├── file_writer.py
│   ├── file_replacer.py
│   ├── paths.py
│   └── system_prompt.py
├── prompts/
│   └── system.txt             # System prompt content
├── requirements.txt
├── pyproject.toml
└── README.md
```

## License

MIT
