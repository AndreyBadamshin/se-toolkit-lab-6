# Task 3 Plan: The System Agent

## Overview

This task extends the documentation agent from Task 2 with a new tool `query_api` that allows the agent to query the deployed backend API. This enables the agent to answer two new kinds of questions:
1. **Static system facts** — framework, ports, status codes
2. **Data-dependent queries** — item count, scores, analytics

## Tool Schema: `query_api`

I defined the `query_api` tool with the following schema:

```json
{
  "name": "query_api",
  "description": "Call the backend API and return the response. Use this for questions about system state, data counts, API responses, or runtime behavior.",
  "parameters": {
    "type": "object",
    "properties": {
      "method": {
        "type": "string",
        "description": "HTTP method (GET, POST, etc.)"
      },
      "path": {
        "type": "string",
        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate')"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      },
      "use_auth": {
        "type": "boolean",
        "description": "Whether to include authentication header. Default is true. Set to false to test unauthenticated access.",
        "default": true
      }
    },
    "required": ["method", "path"]
  }
}
```

## Authentication

The `query_api` tool authenticates using the `LMS_API_KEY` environment variable from `.env.docker.secret`. The key is sent in the `Authorization` header as a Bearer token. If `use_auth=false`, the Authorization header is omitted.

## Environment Variables

The agent reads the following environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for `query_api` auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for `query_api` (default: `http://localhost:42002`) | Optional, defaults to localhost |

## System Prompt Update

I updated the system prompt to guide the LLM on when to use each tool:

- **`read_file`** — For questions about source code, documentation, or configuration files
- **`list_files`** — For discovering what files exist in a directory
- **`query_api`** — For questions about system state, data counts, API responses, or runtime behavior
- **`query_api` with `use_auth=false`** — For testing unauthenticated access

## Implementation Steps

1. Add `query_api` tool schema to the `TOOLS` list
2. Implement the `query_api` function with:
   - HTTP client (httpx) for making requests
   - Authentication via `LMS_API_KEY` header (optional based on `use_auth`)
   - Error handling for connection failures and HTTP errors
3. Update the system prompt to include guidance on `query_api` and `use_auth`
4. Add `AGENT_API_BASE_URL` configuration with default value
5. Update `extract_source_from_answer` to handle backend source code paths
6. Update `AGENT.md` documentation
7. Create 2 regression tests for the new tool

## Initial Benchmark Results

**First run failures:**
1. Question 4 (items count): Agent exceeded tool call limit — fixed by improving system prompt for efficiency
2. Question 5 (status code): Agent got 200 instead of 401 — fixed by adding `use_auth` parameter
3. Question 6 (ZeroDivisionError): Missing source field — fixed by updating `extract_source_from_answer`
4. Question 7 (TypeError): Agent exceeded tool call limit — fixed by improving system prompt

## Iteration Strategy

1. First run: Expect failures on API-related questions
2. Fix `query_api` authentication and URL construction
3. Add `use_auth` parameter for unauthenticated requests
4. Fix source extraction for backend paths
5. Improve system prompt for efficiency
6. Re-run until all 10 questions pass

## Final Benchmark Score

| Question | Topic | Status |
|----------|-------|--------|
| 0 | Branch protection (wiki) | ✓ PASSED |
| 1 | SSH connection (wiki) | ✓ PASSED |
| 2 | Framework (source code) | ✓ PASSED |
| 3 | API routers (list_files) | ✓ PASSED |
| 4 | Items count (query_api) | ✓ PASSED |
| 5 | Status code (query_api) | ✓ PASSED |
| 6 | ZeroDivisionError (query_api + read_file) | ✓ PASSED |
| 7 | TypeError (query_api + read_file) | ✓ PASSED |
| 8 | Request lifecycle (read_file) | ✓ PASSED |
| 9 | ETL idempotency (read_file) | ✓ PASSED |

**Total: 10/10 PASSED**

## Lessons Learned

1. **Tool descriptions matter** — Initially the LLM didn't use `query_api` for data questions. Adding explicit guidance in the system prompt fixed this.

2. **Authentication is critical** — The `query_api` tool must read `LMS_API_KEY` from `.env.docker.secret`, not `.env.agent.secret`. These are two different keys for different purposes.

3. **Flexible authentication** — Adding `use_auth` parameter allows the LLM to test unauthenticated endpoints, which is required for question 5.

4. **Source extraction** — The `extract_source_from_answer` function needs to handle both wiki paths (`wiki/file.md`) and backend source paths (`backend/app/routers/analytics.py`).

5. **Efficiency matters** — The LLM can exceed the 10 tool call limit if not guided properly. The system prompt should emphasize efficiency.

6. **String to boolean conversion** — The LLM may return `"False"` as a string instead of `false` as a boolean. The `query_api` function handles this conversion.
