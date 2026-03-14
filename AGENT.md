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

The system prompt guides the LLM to:

```
You are a helpful assistant that answers questions by reading project documentation.

You have two tools:
- list_files(path): List files in a directory
- read_file(path): Read contents of a file

Strategy:
1. Use list_files to discover wiki files
2. Use read_file to find the answer
3. Include the source reference (file path + section anchor) in your answer
4. Maximum 10 tool calls per question

Always provide the source file path in your final answer.
```

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
- `source` (string) — Wiki section reference (e.g., `wiki/git-workflow.md#section`)
- `tool_calls` (array) — All tool calls made during execution

## Project Structure

```
se-toolkit-lab-6/
├── agent.py                  # Main agent CLI
├── AGENT.md                  # This file — agent architecture documentation
├── .env.agent.secret         # LLM credentials (gitignored)
├── .env.agent.example        # Example LLM configuration
├── plans/                    # Implementation plans for each task
│   ├── task-1.md             # LLM provider and agent structure
│   └── task-2.md             # Tool schemas and agentic loop plan
├── wiki/                     # Documentation the agent can read
├── backend/                  # FastAPI backend (for query_api tool in Task 3)
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

**Run tests:**
```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

## Development Status

| Task | Status | Description |
|------|--------|-------------|
| Task 1 | ✅ Complete | Call an LLM from code |
| Task 2 | ✅ Complete | The documentation agent (read_file, list_files, agentic loop) |
| Task 3 | ⏳ Pending | The system agent (query_api tool) |
