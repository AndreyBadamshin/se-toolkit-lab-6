# Task 3: The System Agent — Implementation Plan

## Overview

This task extends the agent from Task 2 by adding a `query_api` tool that allows the agent to query the deployed backend API. The agent will answer both static system questions (framework, ports, status codes) and data-dependent queries (item count, scores).

---

## 1. Tool Schema Definition for `query_api`

### Schema Structure

The `query_api` tool will be defined as a function-calling schema following the OpenAI format:

```python
{
    "name": "query_api",
    "description": "Call the backend API to query data or check system status. Use for questions about database contents, API responses, or system configuration.",
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]
            },
            "path": {
                "type": "string",
                "description": "API endpoint path (e.g., '/items/', '/analytics/scores')"
            },
            "body": {
                "type": "string",
                "description": "Optional JSON request body for POST/PUT/PATCH requests"
            }
        },
        "required": ["method", "path"]
    }
}
```

### Tool Registration

The tool will be added to the `TOOLS` list alongside `read_file` and `list_files`:

```python
TOOLS = [
    {...},  # read_file
    {...},  # list_files
    {...},  # query_api (new)
]
```

---

## 2. Authentication Handling

### Environment Variables

The agent needs to read two distinct API keys:

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider authentication | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API authentication | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Backend API base URL | Environment (default: `http://localhost:42002`) |

### Settings Class Update

Add a separate settings class for backend API configuration:

```python
class BackendApiSettings(BaseSettings):
    """Backend API configuration from environment variables."""
    
    lms_api_key: str
    agent_api_base_url: str = "http://localhost:42002"
    
    class Config:
        env_file = ".env.docker.secret"
        env_prefix = ""  # No prefix for LMS_API_KEY
```

### Authentication in `query_api`

The tool will include the `LMS_API_KEY` in the `Authorization` header:

```python
def query_api(method: str, path: str, body: str | None = None) -> str:
    """Call the backend API with authentication."""
    settings = get_backend_settings()
    url = f"{settings.agent_api_base_url}{path}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.lms_api_key}",
    }
    
    with httpx.Client() as client:
        if method == "GET":
            response = client.get(url, headers=headers)
        elif method in ("POST", "PUT", "PATCH"):
            data = json.loads(body) if body else None
            response = client.request(method, url, headers=headers, json=data)
        else:
            response = client.request(method, url, headers=headers)
    
    return json.dumps({
        "status_code": response.status_code,
        "body": response.text,
    })
```

---

## 3. System Prompt Update

### Strategy

The system prompt must guide the LLM to choose the right tool for each question type:

| Question Type | Tool to Use | Examples |
|--------------|-------------|----------|
| Wiki documentation | `read_file`, `list_files` | "How to resolve merge conflict?" |
| Source code inspection | `read_file` | "What framework does the backend use?" |
| Data queries | `query_api` | "How many items in database?" |
| System facts | `query_api` | "What status code for unauthenticated request?" |

### Updated System Prompt

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

---

## 4. Environment Variable Handling

### Configuration Sources

The agent must read all configuration from environment variables, not hardcoded values:

```python
import os

# LLM configuration (from .env.agent.secret or environment)
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_API_BASE = os.getenv("LLM_API_BASE")
LLM_MODEL = os.getenv("LLM_MODEL")

# Backend API configuration (from .env.docker.secret or environment)
LMS_API_KEY = os.getenv("LMS_API_KEY")
AGENT_API_BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")
```

### Autochecker Compatibility

The autochecker injects its own values at runtime. The agent must:
1. Not hardcode any API keys or URLs
2. Use environment variables exclusively
3. Provide sensible defaults (e.g., `AGENT_API_BASE_URL` defaults to localhost)

---

## 5. Agentic Loop Updates

The loop structure remains the same — only the available tools expand:

```
User Question
      │
      ▼
┌─────────────────┐
│ Send to LLM     │
│ + tool schemas  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Parse response  │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
  tools?    no tools
    │         │
    ▼         ▼
┌─────────┐ ┌──────────┐
│ Execute │ │ Extract  │
│ tool:   │ │ answer   │
│ - read  │ │ + source │
│ - list  │ │ Output   │
│ - query │ │ JSON     │
└────┬────┘ └──────────┘
     │
     ▼
┌─────────────────┐
│ Append result   │
│ Loop back       │
└─────────────────┘
```

---

## 6. Benchmark Iteration Strategy

### Initial Run

Run the benchmark to establish a baseline:

```bash
uv run run_eval.py
```

### Expected First Failures

| Question | Likely Issue | Fix |
|----------|--------------|-----|
| Q4 (items count) | query_api not implemented | Implement tool |
| Q5 (status code) | Missing auth header | Add LMS_API_KEY |
| Q6 (division error) | Can't read source after API error | Multi-step tool chaining |
| Q7 (NoneType error) | Same as Q6 | Improve error analysis |
| Q8 (request lifecycle) | Incomplete source reading | Better system prompt |
| Q9 (idempotency) | Can't find ETL code | Add file discovery strategy |

### Iteration Process

1. **Run benchmark** → identify failing questions
2. **Check tool_calls** → verify correct tools were used
3. **Check answer** → verify answer contains expected keywords
4. **Fix one issue at a time**:
   - Tool not called → improve tool description in schema
   - Wrong arguments → clarify parameter descriptions
   - Wrong answer → improve system prompt or tool implementation
5. **Re-run benchmark** → verify improvement
6. **Repeat** until all 10 questions pass

---

## 7. Testing Strategy

### New Test Cases

| Test | Question | Expected Tool | Expected Result |
|------|----------|---------------|-----------------|
| 1 | "What framework does the backend use?" | `read_file` | Answer contains "FastAPI" |
| 2 | "How many items are in the database?" | `query_api` | Answer contains a number > 0 |

### Test Implementation

Tests will:
1. Run `agent.py` as subprocess with test question
2. Parse JSON output
3. Assert correct tool was used
4. Assert answer contains expected keywords

---

## 8. File Changes Summary

| File | Changes |
|------|---------|
| `agent.py` | Add `query_api` tool, update settings, update system prompt |
| `.env.docker.secret` | Source for `LMS_API_KEY` |
| `AGENT.md` | Document `query_api`, authentication, lessons learned |
| `backend/tests/unit/test_agent.py` | Add 2 regression tests |
| `plans/task-3.md` | This plan file |

---

## 9. Acceptance Criteria Checklist

- [ ] Plan written before code implementation
- [ ] `query_api` defined as function-calling schema with `method`, `path`, `body`
- [ ] `query_api` authenticates with `LMS_API_KEY`
- [ ] Agent reads `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` from environment
- [ ] Agent reads `AGENT_API_BASE_URL` from environment (default: localhost)
- [ ] System prompt updated with tool selection strategy
- [ ] `run_eval.py` passes all 10 questions
- [ ] `AGENT.md` updated with documentation (200+ words)
- [ ] 2 regression tests added and passing

---

## 10. Initial Benchmark Score (to be filled after first run)

**Score:** _/10 (run `uv run run_eval.py` after setting up backend)

**First Failures:**
- Q#: [description]
- Q#: [description]

**Iteration Strategy:**
1. [First fix to implement]
2. [Second fix to implement]
3. [etc.]

---

## 11. Implementation Notes

### Completed Changes

1. **`query_api` tool schema** — Defined with `method`, `path`, `body` parameters
2. **Authentication** — Uses `LMS_API_KEY` from `.env.docker.secret`
3. **Environment variables** — All config read from env vars:
   - `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL` from `.env.agent.secret`
   - `LMS_API_KEY`, `AGENT_API_BASE_URL` from `.env.docker.secret` or defaults
4. **System prompt** — Updated with tool selection strategy for 3 tools
5. **Error handling** — Network errors, JSON errors gracefully handled
