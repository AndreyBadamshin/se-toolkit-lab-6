# Task 2: The Documentation Agent — Implementation Plan

## Overview

This task extends the agent from Task 1 by adding two tools (`read_file`, `list_files`) and implementing an agentic loop that allows the LLM to iteratively call tools until it can produce a final answer.

---

## 1. Tool Schemas Definition

### Approach

Tool schemas will be defined as Python dictionaries following the OpenAI function-calling format. Each tool will have:
- `name`: The tool identifier
- `description`: What the tool does and when to use it
- `parameters`: JSON Schema defining required arguments

### Schema Structure

```python
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the project repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root (e.g., 'wiki/git.md')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_files",
        "description": "List files and directories at a given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from project root (e.g., 'wiki/')"
                }
            },
            "required": ["path"]
        }
    }
]
```

### Tool Registration

Tools will be passed to the LLM API in the `tools` parameter of the chat completions request:

```python
response = client.post(
    f"{settings.llm_api_base}/chat/completions",
    json={
        "model": settings.llm_model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto"  # Let LLM decide when to call tools
    }
)
```

---

## 2. Agentic Loop Implementation

### Loop Structure

```
┌─────────────────────────────────────────────────────────────┐
│  1. Send user question + tool schemas to LLM                │
│                          │                                  │
│                          ▼                                  │
│  2. Parse response: has tool_calls?                         │
│                    │           │                            │
│                   yes         no                            │
│                    │           │                            │
│                    ▼           ▼                            │
│  3. Execute tools   │    4. Final answer                    │
│     - read_file     │       - Extract answer                │
│     - list_files    │       - Extract source                │
│                    │       - Output JSON & exit             │
│                    │                                        │
│  5. Append results │                                        │
│     as tool messages│                                        │
│                    │                                        │
│  6. Check limit: < 10 calls?                                │
│       │                      │                              │
│      yes                    no                              │
│       │                      │                              │
│       └──────► back to 1     ▼                              │
│                         Stop with partial answer            │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Steps

1. **Initialize message history** with system prompt and user question
2. **Loop** (max 10 iterations):
   - Call LLM with current messages + tool schemas
   - Parse response for `tool_calls`
   - If no tool calls: extract final answer and break
   - If tool calls: execute each tool, append results as `tool` role messages
3. **Build output** with `answer`, `source`, and `tool_calls` history

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {
        "role": "assistant",
        "tool_calls": [{"id": "call_1", "function": {...}}]
    },
    {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "Tool execution result"
    }
]
```

### Output Structure

```json
{
  "answer": "The final answer from the LLM",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "File contents..."
    }
  ]
}
```

---

## 3. Path Security

### Threat Model

Prevent directory traversal attacks where a user or malicious LLM could attempt to read files outside the project directory using paths like:
- `../../etc/passwd`
- `wiki/../../../.env`
- Absolute paths like `/etc/passwd`

### Security Strategy

1. **Resolve to absolute path**: Use `Path.resolve()` to get the canonical absolute path
2. **Check prefix**: Verify the resolved path starts with the project root
3. **Reject invalid paths**: Return an error message if the path is outside bounds

### Implementation

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()

def is_safe_path(path: str) -> bool:
    """Check if a path is within the project directory."""
    try:
        # Resolve to absolute path (resolves .., symlinks, etc.)
        resolved = (PROJECT_ROOT / path).resolve()
        # Check if resolved path is within project root
        return str(resolved).startswith(str(PROJECT_ROOT))
    except (ValueError, OSError):
        return False

def read_file(path: str) -> str:
    """Read a file from the project repository."""
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is outside project directory"
    
    file_path = PROJECT_ROOT / path
    if not file_path.exists():
        return f"Error: File not found - {path}"
    if not file_path.is_file():
        return f"Error: Not a file - {path}"
    
    return file_path.read_text()

def list_files(path: str) -> str:
    """List files and directories at a given path."""
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is outside project directory"
    
    dir_path = PROJECT_ROOT / path
    if not dir_path.exists():
        return f"Error: Directory not found - {path}"
    if not dir_path.is_dir():
        return f"Error: Not a directory - {path}"
    
    entries = [entry.name for entry in dir_path.iterdir()]
    return "\n".join(sorted(entries))
```

### Edge Cases Handled

| Case | Handling |
|------|----------|
| `../` traversal | Resolved path checked against project root |
| Absolute paths | Joined with project root, then resolved and checked |
| Symlinks | `resolve()` follows symlinks, then checked |
| Non-existent paths | Return error message (not exception) |
| Empty path | Treated as project root |

---

## 4. System Prompt Strategy

The system prompt will guide the LLM to:

1. Use `list_files` to discover wiki files when the question is about documentation
2. Use `read_file` to read relevant files and find the answer
3. Include the source reference (file path + section anchor) in the final answer
4. Stop after finding the answer (don't call unnecessary tools)

### Minimal System Prompt (Task 2)

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

---

## 5. Testing Strategy

### Test Cases

| Test | Question | Expected Tool | Expected Source |
|------|----------|---------------|-----------------|
| 1 | "How do you resolve a merge conflict?" | `read_file` | `wiki/git-workflow.md` |
| 2 | "What files are in the wiki?" | `list_files` | N/A (listing) |

### Test Implementation

Tests will:
1. Run `agent.py` as a subprocess with a test question
2. Parse JSON output from stdout
3. Assert `tool_calls` contains expected tool names
4. Assert `source` field contains expected file path

---

## 6. File Changes Summary

| File | Changes |
|------|---------|
| `agent.py` | Add tool definitions, implement agentic loop, add path security |
| `AGENT.md` | Document tools, loop, and system prompt |
| `backend/tests/unit/test_agent.py` | Add 2 regression tests |
| `plans/task-2.md` | This plan file |

---

## 7. Acceptance Criteria Checklist

- [ ] Plan written before code implementation
- [ ] Tool schemas defined for `read_file` and `list_files`
- [ ] Agentic loop implemented with max 10 iterations
- [ ] Path security prevents directory traversal
- [ ] Output includes `answer`, `source`, and `tool_calls`
- [ ] `AGENT.md` updated with documentation
- [ ] 2 regression tests added and passing
