# RoboAgent

An AI agent powered by Google Gemini with local Python execution tools.

## Features

- Integration with Google Gemini API
- Local Python code execution
- Calculator utilities
- Rich terminal output

## Setup

### Prerequisites

- Python 3.11 or higher
- Google Gemini API key

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
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.0-flash
```

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
├── agent.py           # Main agent implementation
├── calculator.py      # Calculator utilities
├── requirements.txt   # Project dependencies
├── pyproject.toml     # Project configuration
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## License

MIT
