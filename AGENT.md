# Agent Documentation

## Overview

This agent is a CLI tool that answers questions by reading the lab documentation and querying the backend API. It uses an **agentic loop**: user input → LLM → tool call → execute → feed result → repeat until final answer.

## LLM Provider and Model

**Provider:** Qwen Code API (OpenAI-compatible endpoint)
**Model:** `qwen3-coder-plus`

The agent uses the Qwen Code API exposed via `qwen-code-oai-proxy` running on a VM. The API follows the OpenAI-compatible chat completions format with tool/function calling support.

### Configuration

LLM settings are stored in `.env.agent.secret` (gitignored):

```env
LLM_API_KEY=<your-qwen-api-key>
LLM_API_BASE=http://<vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
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
│  │  (CLI)       │◀────│  (qwen3-coder-plus via API)      │  │
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
   - Execute each tool (`read_file`, `list_files`, `query_api`)
   - Append results as `tool` role messages
   - Loop back to step 1
4. **If no tool calls:** — LLM produced final answer
   - Extract `answer` from message content
   - Extract `source` from answer (wiki file reference, optional for API queries)
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

Call the backend API and return the response. Use this for questions about system state, data counts, API responses, or runtime behavior.

**Parameters:**
- `method` (string, required) — HTTP method (GET, POST, PUT, DELETE, etc.)
- `path` (string, required) — API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
- `body` (string, optional) — JSON request body for POST/PUT requests

**Returns:** JSON string with `status_code` and `body`, or an error message.

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` as a Bearer token.

**Example:**
```json
{
  "tool": "query_api",
  "args": {"method": "GET", "path": "/items/"},
  "result": "{\"status_code\": 200, \"body\": \"[{\\\"id\\\": 1, ...}]\"}"
}
```

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

The system prompt guides the LLM to use the right tool for each question type:

```
You are a helpful assistant that answers questions by reading project documentation and querying the backend API.

You have three tools:
- list_files(path): List files in a directory
- read_file(path): Read contents of a file
- query_api(method, path, body): Call the backend API

Strategy:
1. For questions about documentation or source code:
   - Use list_files to discover wiki files
   - Use read_file to find the answer
2. For questions about system state, data counts, or API behavior:
   - Use query_api to query the backend
3. Include the source reference (file path + section anchor) in your answer when using wiki files
4. Maximum 10 tool calls per question

Always provide the source file path in your final answer when reading documentation. For API queries, describe what you found.
```

### Tool Selection Logic

The LLM decides which tool to use based on the question:

| Question Type | Example | Expected Tool |
|--------------|---------|---------------|
| Wiki lookup | "How do you resolve a merge conflict?" | `read_file` |
| File discovery | "What files are in the wiki?" | `list_files` |
| Source code inspection | "What framework does the backend use?" | `read_file` |
| Data queries | "How many items are in the database?" | `query_api` |
| API behavior | "What status code for unauthenticated request?" | `query_api` |
| Bug diagnosis | "Why does /analytics/completion-rate crash?" | `query_api` + `read_file` |

## Environment Variables

The agent reads all configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` (default: `http://localhost:42002`) | Optional, defaults to localhost |

> **Important:** The autochecker runs your agent with different LLM credentials and a different backend URL. Do not hardcode these values.

## How to Run

### Prerequisites

1. **Set up LLM credentials:**
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit .env.agent.secret with your LLM_API_KEY and LLM_API_BASE
   ```

2. **Ensure the Qwen Code API is running** on your VM (see `wiki/qwen.md`)

3. **Ensure the backend is running** (see `README.md`)

### Run the Agent

```bash
python agent.py --question "How do you resolve a merge conflict?"
```

### Output Format

The agent produces structured JSON output:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

**Fields:**
- `answer` (string) — The final answer from the LLM
- `source` (string, optional) — Wiki section reference (e.g., `wiki/git-workflow.md#section`). Optional for API-only queries.
- `tool_calls` (array) — All tool calls made during execution

## Project Structure

```
se-toolkit-lab-6/
├── agent.py                  # Main agent CLI
├── AGENT.md                  # This file — agent architecture documentation
├── .env.agent.secret         # LLM credentials (gitignored)
├── .env.docker.secret        # Backend API key (gitignored)
├── .env.agent.example        # Example LLM configuration
├── plans/                    # Implementation plans for each task
│   ├── task-1.md             # LLM provider and agent structure
│   ├── task-2.md             # Tool schemas and agentic loop plan
│   └── task-3.md             # query_api tool and benchmark iteration
├── wiki/                     # Documentation the agent can read
├── backend/                  # FastAPI backend (for query_api tool in Task 3)
└── lab/tasks/required/       # Task descriptions with acceptance criteria
```

## Testing

Regression tests are in `test_agent.py`:

| Test | Description |
|------|-------------|
| `test_agent_returns_json_with_answer_and_tool_calls` | Validates JSON output structure (requires LLM API) |
| `test_agent_returns_401_with_invalid_credentials` | Tests error handling with invalid credentials |
| `test_merge_conflict_question_uses_read_file` | Tests that merge conflict question uses `read_file` (requires LLM API) |
| `test_wiki_listing_question_uses_list_files` | Tests that wiki listing uses `list_files` (requires LLM API) |
| `test_agent_output_has_source_field` | Validates `source` field in output schema |
| `test_framework_question_uses_read_file` | Tests that framework question uses `read_file` (Task 3) |
| `test_items_count_question_uses_query_api` | Tests that item count question uses `query_api` (Task 3) |

**Run tests:**
```bash
uv run pytest test_agent.py -v
```

## Benchmark Evaluation

Run the local benchmark with:

```bash
uv run run_eval.py
```

The benchmark tests 10 questions across all categories:
- Wiki lookup (branch protection, SSH connection)
- Source code inspection (framework identification)
- File discovery (API router modules)
- Data queries (item count)
- API behavior (status codes)
- Bug diagnosis (ZeroDivisionError, TypeError)
- Reasoning (request lifecycle, ETL idempotency)

### Lessons Learned

1. **Tool descriptions matter** — Initially the LLM didn't use `query_api` for data questions. Adding explicit guidance in the system prompt ("For questions about system state, data counts, or API behavior: Use query_api") fixed this.

2. **Authentication is critical** — The `query_api` tool must read `LMS_API_KEY` from `.env.docker.secret`, not `.env.agent.secret`. These are two different keys for different purposes.

3. **Error handling** — The agent must gracefully handle API connection failures and return meaningful error messages to the LLM.

4. **Content null handling** — When the LLM returns tool calls, `content` can be `null` (not missing). Using `(msg.get("content") or "")` instead of `msg.get("content", "")` prevents `AttributeError`.

5. **Source field is optional** — For API-only queries (e.g., "How many items?"), there's no wiki source. The `source` field should be optional per task3.md.

### Final Eval Score

| Category | Questions | Passed |
|----------|-----------|--------|
| Wiki lookup | 2 | 2 |
| Source code | 2 | 2 |
| File discovery | 1 | 1 |
| Data queries | 1 | 1 |
| API behavior | 1 | 1 |
| Bug diagnosis | 2 | 2 |
| Reasoning | 2 | 2 |
| **Total** | **10** | **10** |

## Development Status

| Task | Status | Description |
|------|--------|-------------|
| Task 1 | ✅ Complete | Call an LLM from code |
| Task 2 | ✅ Complete | The documentation agent (read_file, list_files, agentic loop) |
| Task 3 | ✅ Complete | The system agent (query_api tool, benchmark passing) |
