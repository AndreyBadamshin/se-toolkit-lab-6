# Agent Documentation

## Overview

This agent is a CLI tool that answers questions by reading the lab documentation and querying the backend API. It uses an **agentic loop**: user input → LLM → tool call → execute → feed result → repeat until final answer.

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
│         ├──────────▶ query_api(method, path) ──▶ backend    │
│         │                                                   │
│         ▼                                                   │
│  Structured JSON Output                                     │
└─────────────────────────────────────────────────────────────┘
```

### Agentic Loop

The agent loop executes up to 10 tool calls per question:

1. **Send user question + tool schemas to LLM** — Include system prompt and available tools
2. **Parse response for `tool_calls`** — Check if LLM wants to use tools
3. **If tool calls exist:**
   - Execute each tool (`read_file`, `list_files`)
   - Append results as `tool` role messages
   - Loop back to step 1
4. **If no tool calls:** — LLM produced final answer
   - Extract `answer` from message content
   - Extract `source` from answer (wiki file reference)
   - Output JSON and exit
5. **If max iterations reached:** — Stop with partial answer

### Message Flow

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After LLM responds with tool calls:
    {
        "role": "assistant",
        "tool_calls": [{"id": "call_1", "function": {"name": "read_file", ...}}]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "File contents..."
    },
    # Loop continues...
]
```

## Available Tools

### `read_file`

Read the contents of a file from the project repository.

**Parameters:**
- `path` (string, required) — Relative path from project root (e.g., `wiki/git.md`)

**Returns:** File contents as a string, or an error message.

**Example:**
```json
{"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "# Git Workflow\n..."}
```

### `list_files`

List files and directories at a given path.

**Parameters:**
- `path` (string, required) — Relative directory path from project root (e.g., `wiki/`)

**Returns:** Newline-separated listing of entries, or an error message.

**Example:**
```json
{"tool": "list_files", "args": {"path": "wiki"}, "result": "git.md\ngit-workflow.md\n..."}
```

### `query_api`

Call the backend API to query data or check system status.

**Parameters:**
- `method` (string, required) — HTTP method (GET, POST, PUT, DELETE, PATCH)
- `path` (string, required) — API endpoint path (e.g., `/items/`, `/analytics/scores`)
- `body` (string, optional) — JSON request body for POST/PUT/PATCH requests

**Returns:** JSON string with `status_code` and `body`, or an error message.

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` (backend API key, not LLM key).

**Example:**
```json
{
  "tool": "query_api",
  "args": {"method": "GET", "path": "/items/"},
  "result": "{\"status_code\": 200, \"body\": \"[{\\\"id\\\": 1, ...}]\"}"
}
```

**Error Handling:**
- Network errors return `{"status_code": 0, "body": "Request error: ..."}`
- Invalid JSON body returns `{"status_code": 0, "body": "Invalid JSON body: ..."}`

## Path Security

Tools implement path traversal protection:

1. **Resolve to absolute path** — Uses `Path.resolve()` to get canonical path
2. **Check prefix** — Verifies resolved path starts with `PROJECT_ROOT`
3. **Reject invalid paths** — Returns error message for paths outside project

**Protected against:**
- `../` traversal (e.g., `../../etc/passwd`)
- Absolute paths (e.g., `/etc/passwd`)
- Symlinks pointing outside project

## System Prompt Strategy

The system prompt guides the LLM to choose the right tool for each question type:

```
You are a helpful assistant that answers questions by reading project documentation, source code, and querying the backend API.

You have three tools:
- list_files(path): List files in a directory
- read_file(path): Read contents of a file
- query_api(method, path, body): Call the backend API

Tool Selection Strategy:
1. For wiki documentation questions → use list_files to discover files, then read_file
2. For source code questions → use read_file on relevant source files
3. For data queries (database contents, counts) → use query_api with GET
4. For system facts (status codes, framework info) → use query_api or read_file on source

When using query_api:
- Use GET for reading data
- Use POST/PUT/PATCH for creating/updating
- Include body only for POST/PUT/PATCH requests

Always provide the source reference (file path or API endpoint) in your answer.
Maximum 10 tool calls per question.
```

### Tool Selection Table

| Question Type | Tool to Use | Examples |
|--------------|-------------|----------|
| Wiki documentation | `read_file`, `list_files` | "How to resolve merge conflict?" |
| Source code inspection | `read_file` | "What framework does the backend use?" |
| Data queries | `query_api` | "How many items in database?" |
| System facts | `query_api` | "What status code for unauthenticated request?" |

## How to Run

### Prerequisites

1. **Set up LLM credentials:**
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit .env.agent.secret with your LLM_API_KEY and LLM_API_BASE
   ```

2. **Set up backend API credentials:**
   ```bash
   cp .env.docker.example .env.docker.secret
   # LMS_API_KEY is already set in .env.docker.secret
   ```

3. **Ensure the Qwen Code API is running** on your VM (see `wiki/qwen.md`)

4. **Ensure the backend API is running:**
   ```bash
   docker compose up -d
   ```

### Run the Agent

```bash
python agent.py --question "How do you resolve a merge conflict?"
```

### Output Format

The agent produces structured JSON output:

```json
{
  "answer": "There are 120 items in the database.",
  "source": "",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
    }
  ]
}
```

**Fields:**
- `answer` (string) — The final answer from the LLM
- `source` (string) — Wiki section reference (e.g., `wiki/git-workflow.md#section`) or API endpoint. Empty for system questions.
- `tool_calls` (array) — All tool calls made during execution

## Project Structure

```
se-toolkit-lab-6/
├── agent.py                  # Main agent CLI
├── AGENT.md                  # This file — agent architecture documentation
├── .env.agent.secret         # LLM credentials (gitignored)
├── .env.agent.example        # Example LLM configuration
├── .env.docker.secret        # Backend API credentials (gitignored)
├── .env.docker.example       # Example backend configuration
├── plans/                    # Implementation plans for each task
│   ├── task-1.md             # LLM provider and agent structure
│   ├── task-2.md             # Tool schemas and agentic loop plan
│   └── task-3.md             # query_api tool and benchmark plan
├── wiki/                     # Documentation the agent can read
├── backend/                  # FastAPI backend (for query_api tool)
├── run_eval.py               # Benchmark evaluation script
└── lab/tasks/required/       # Task descriptions with acceptance criteria
```

## Testing

Regression tests are in `backend/tests/unit/test_agent.py`:

| Test | Description |
|------|-------------|
| `test_agent_returns_json_with_answer_and_tool_calls` | Validates JSON output structure (requires LLM API) |
| `test_agent_returns_401_with_invalid_credentials` | Tests error handling with invalid credentials |
| `test_merge_conflict_question_uses_read_file` | Tests that merge conflict question uses `read_file` (requires LLM API) |
| `test_wiki_listing_question_uses_list_files` | Tests that wiki listing uses `list_files` (requires LLM API) |
| `test_agent_output_has_source_field` | Validates `source` field in output schema |
| `test_framework_question_uses_read_file` | Tests that framework question uses `read_file` (requires LLM API) |
| `test_items_count_question_uses_query_api` | Tests that items count question uses `query_api` (requires LLM API) |

**Run tests:**
```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

## Benchmark Evaluation

The agent is evaluated against 10 benchmark questions in `run_eval.py`:

| # | Question Type | Tools Required |
|---|---------------|----------------|
| 0-1 | Wiki documentation | `read_file` |
| 2-3 | Source code inspection | `read_file`, `list_files` |
| 4-5 | Data queries / System facts | `query_api` |
| 6-7 | Bug diagnosis | `query_api`, `read_file` |
| 8-9 | Reasoning (LLM judge) | `read_file` |

**Run benchmark:**
```bash
uv run run_eval.py
```

## Lessons Learned

### Key Insights

1. **Two distinct API keys:** `LMS_API_KEY` (backend) and `LLM_API_KEY` (LLM provider) must not be confused. They come from different files (`.env.docker.secret` vs `.env.agent.secret`).

2. **Environment variable injection:** The autochecker injects its own credentials at runtime. Hardcoding values causes failure.

3. **Tool selection depends on prompt clarity:** The LLM needs explicit guidance on when to use each tool. Vague descriptions lead to wrong tool choices.

4. **Error handling matters:** Network errors, invalid JSON, and API errors must be gracefully handled and returned as structured responses.

5. **Multi-step tool chaining:** Some questions require calling `query_api` to get an error, then `read_file` to find the bug in source code.

### Benchmark Iteration

Initial score: _/10 (to be filled after first run)

Common failures and fixes:
- Agent doesn't call `query_api` for data questions → Improve tool description
- Agent calls wrong endpoint → Add endpoint examples to system prompt
- Agent can't diagnose bugs → Improve error message parsing

## Development Status

| Task | Status | Description |
|------|--------|-------------|
| Task 1 | ✅ Complete | Call an LLM from code |
| Task 2 | ✅ Complete | The documentation agent (read_file, list_files, agentic loop) |
| Task 3 | ✅ Complete | The system agent (query_api tool with authentication) |
