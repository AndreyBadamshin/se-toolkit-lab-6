# Agent Documentation

## Overview

This agent is a CLI tool that answers questions by reading the lab documentation and querying the backend API. It uses an agentic loop: user input → LLM → tool call → execute → feed result → repeat until final answer.

## LLM Provider and Model

**Provider:** Qwen Code API (OpenAI-compatible endpoint)  
**Model:** `coder-model` (Qwen 3.5 Plus)

The agent uses the Qwen Code API exposed via `qwen-code-oai-proxy` running on a VM. The API follows the OpenAI-compatible chat completions format with tool/function calling support.

### Configuration

LLM settings are stored in `.env.agent.secret` (gitignored):

```env
LLM_API_KEY=<your-qwen-api-key>
LLM_API_BASE=http://<vm-ip>:<port>/v1
LLM_MODEL=coder-model
```

## How the Agent Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  User Input                                                 │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────┐     ┌──────────────────────────────────┐  │
│  │  agent.py    │────▶│  Qwen Code API                   │  │
│  │  (CLI)       │◀────│  (coder-model via OpenAI API)    │  │
│  └──────┬───────┘     └──────────────────────────────────┘  │
│         │                                                   │
│         │ tool calls                                        │
│         ├──────────▶ read_file(path) ──▶ wiki/, source code │
│         ├──────────▶ list_files(dir)  ──▶ directory listing │
│         ├──────────▶ query_api(path)  ──▶ backend API       │
│         │                                                   │
│         ▼                                                   │
│  Structured JSON Output                                     │
└─────────────────────────────────────────────────────────────┘
```

### Agent Loop

1. **Receive user input** — a question or task from the command line
2. **Send to LLM** — format as a message and call the Qwen Code API
3. **Process tool calls** — if the LLM requests tool execution:
   - `read_file(path)` — read a file from the filesystem
   - `list_files(dir)` — list directory contents
   - `query_api(path)` — query the backend FastAPI
4. **Feed results back** — return tool outputs to the LLM
5. **Repeat** — continue until the LLM produces a final answer
6. **Output** — return structured JSON response

### Available Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read contents of a file by path |
| `list_files` | List files and directories in a directory |
| `query_api` | Send HTTP requests to the backend API |

## How to Run

### Prerequisites

1. **Set up LLM credentials:**
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit .env.agent.secret with your LLM_API_KEY and LLM_API_BASE
   ```

2. **Ensure the Qwen Code API is running** on your VM (see `wiki/qwen.md`)

### Run the Agent

```bash
python agent.py --question "Your question here"
```

Or for interactive mode (to be implemented):

```bash
python agent.py
```

### Output Format

The agent produces structured JSON output:

```json
{
  "answer": "The final answer",
  "tool_calls": [...],
  "model": "coder-model"
}
```

## Project Structure

```
se-toolkit-lab-6/
├── agent.py              # Main agent CLI (to be implemented)
├── AGENT.md              # This file — agent architecture documentation
├── .env.agent.secret     # LLM credentials (gitignored)
├── plans/                # Implementation plans for each task
├── wiki/                 # Documentation the agent can read
├── backend/              # FastAPI backend for query_api tool
└── lab/tasks/required/   # Task descriptions with acceptance criteria
```

## Development Status

- [ ] Task 1: Call an LLM from code
- [ ] Task 2: The documentation agent
- [ ] Task 3: The system agent
