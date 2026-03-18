#!/usr/bin/env python3
"""
Agent CLI - answers questions by calling an LLM with tools.

Usage:
    python agent.py --question "Your question here"
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


PROJECT_ROOT = Path(__file__).parent.resolve()
MAX_TOOL_CALLS = 10


class AgentSettings(BaseSettings):
    """LLM configuration from environment variables."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str

    model_config = {
        "env_file": ".env.agent.secret",
        "env_prefix": "",
        "case_sensitive": False,
    }


class BackendSettings(BaseSettings):
    """Backend API configuration from environment variables."""

    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"

    model_config = {
        "env_file": ".env.docker.secret",
        "env_prefix": "",
        "extra": "ignore",
    }


# ---------------------------------------------------------------------------
# Tool Schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------


TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the project repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from project root (e.g., 'wiki/git.md')",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories at a given path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative directory path from project root (e.g., 'wiki/')",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "query_api",
        "description": "Call the backend API and return the response. Use this for questions about system state, data counts, API responses, or runtime behavior.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                },
                "path": {
                    "type": "string",
                    "description": "API endpoint path WITHOUT /api prefix. Examples: '/items/', '/analytics/completion-rate?lab=lab-01', '/interactions/', '/learners/', '/pipeline/'",
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body for POST/PUT requests",
                },
                "use_auth": {
                    "type": "boolean",
                    "description": "Whether to include authentication header. Default is true. Set to false to test unauthenticated access.",
                    "default": True,
                },
            },
            "required": ["method", "path"],
        },
    },
]


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def get_settings() -> AgentSettings:
    """Load agent settings from environment."""
    return AgentSettings()  # type: ignore[call-arg]


def get_backend_settings() -> BackendSettings:
    """Load backend settings from environment."""
    return BackendSettings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Path Security
# ---------------------------------------------------------------------------


def is_safe_path(path: str) -> bool:
    """
    Check if a path is within the project directory.

    Prevents directory traversal attacks by resolving the path and
    verifying it starts with the project root.
    """
    try:
        resolved = (PROJECT_ROOT / path).resolve()
        return str(resolved).startswith(str(PROJECT_ROOT))
    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root.

    Returns:
        File contents as a string, or an error message.
    """
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is outside project directory"

    file_path = PROJECT_ROOT / path
    if not file_path.exists():
        return f"Error: File not found - {path}"
    if not file_path.is_file():
        return f"Error: Not a file - {path}"

    return file_path.read_text()


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root.

    Returns:
        Newline-separated listing of entries, or an error message.
    """
    if not is_safe_path(path):
        return f"Error: Access denied - path '{path}' is outside project directory"

    dir_path = PROJECT_ROOT / path
    if not dir_path.exists():
        return f"Error: Directory not found - {path}"
    if not dir_path.is_dir():
        return f"Error: Not a directory - {path}"

    entries = [entry.name for entry in dir_path.iterdir()]
    return "\n".join(sorted(entries))


def query_api(method: str, path: str, body: str | None = None, use_auth: bool = True) -> str:
    """
    Call the backend API and return the response.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: API endpoint path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        use_auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or an error message.
    """
    backend_settings = get_backend_settings()

    # Convert use_auth to boolean - handle string "False" from LLM
    if isinstance(use_auth, str):
        use_auth = use_auth.lower() not in ('false', 'no', '0', '')
    
    # Construct the full URL
    base_url = backend_settings.agent_api_base_url.rstrip("/")
    url = f"{base_url}{path}"

    # Build headers - only include Authorization if use_auth is True and LMS_API_KEY is configured
    headers = {}
    if use_auth and backend_settings.lms_api_key:
        headers["Authorization"] = f"Bearer {backend_settings.lms_api_key}"
    headers["Content-Type"] = "application/json"

    try:
        with httpx.Client() as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers, timeout=30.0)
            elif method.upper() == "POST":
                response = client.post(url, headers=headers, json=json.loads(body) if body else None, timeout=30.0)
            elif method.upper() == "PUT":
                response = client.put(url, headers=headers, json=json.loads(body) if body else None, timeout=30.0)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers, timeout=30.0)
            else:
                return f"Error: Unsupported HTTP method '{method}'"

            result = {
                "status_code": response.status_code,
                "body": response.text,
            }
            return json.dumps(result)

    except httpx.ConnectError as e:
        return f"Error: Cannot connect to API at {url} - {e}"
    except httpx.TimeoutException as e:
        return f"Error: API request timed out - {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON in request body - {e}"
    except Exception as e:
        return f"Error: {type(e).__name__} - {e}"


# Map tool names to implementations
TOOL_FUNCTIONS = {
    "read_file": read_file,
    "list_files": list_files,
    "query_api": query_api,
}


# ---------------------------------------------------------------------------
# LLM Communication
# ---------------------------------------------------------------------------


def call_llm(
    messages: list[dict[str, Any]],
    settings: AgentSettings,
) -> dict[str, Any]:
    """
    Call the LLM API with the given messages and tool schemas.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        settings: Agent configuration.

    Returns:
        The LLM response as a dict.
    """
    url = f"{settings.llm_api_base}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }

    with httpx.Client(timeout=60.0) as client:
        try:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {
                "choices": [{
                    "message": {
                        "content": f"LLM API error: {e.response.status_code} - {e.response.text[:200]}",
                        "tool_calls": []
                    }
                }]
            }
        except httpx.ConnectError as e:
            return {
                "choices": [{
                    "message": {
                        "content": f"Cannot connect to LLM API: {e}",
                        "tool_calls": []
                    }
                }]
            }
        except httpx.TimeoutException as e:
            return {
                "choices": [{
                    "message": {
                        "content": "LLM API request timed out (60s)",
                        "tool_calls": []
                    }
                }]
            }


def build_system_prompt() -> str:
    """
    Build the system prompt for the agent.

    Guides the LLM to use tools effectively and provide source references.
    """
    return """You are a helpful assistant that answers questions by reading project documentation and querying the backend API.

You have three tools:
- list_files(path): List files in a directory
- read_file(path): Read contents of a file
- query_api(method, path, body, use_auth): Call the backend API

API Endpoints (use WITHOUT /api prefix):
- /items/ - Get all items
- /items/{id} - Get specific item
- /analytics/scores?lab=lab-01 - Score distribution
- /analytics/pass-rates?lab=lab-01 - Pass rates
- /analytics/completion-rate?lab=lab-01 - Completion rate
- /analytics/top-learners?lab=lab-01 - Top learners
- /interactions/ - Interactions
- /learners/ - Learners
- /pipeline/ - Pipeline status

Strategy:
1. For questions about documentation or source code:
   - Use list_files MAX ONCE, then use read_file
   - Be efficient - you know the path is backend/app/routers/
2. For questions about system state, data counts, or API behavior:
   - Use query_api ONCE to get the data, then answer
3. For questions about unauthenticated access or error status codes:
   - Use query_api with use_auth=false to test without authentication
4. For bug diagnosis questions:
   - Query the API ONCE to see the error or behavior
   - Then IMMEDIATELY read backend/app/routers/analytics.py to find the bug
   - Do NOT make multiple API queries with different parameters
   - Do NOT explore directories - go directly to the source file
5. Include the source reference (file path + section anchor) in your answer when using wiki files
6. Maximum 10 tool calls per question - BE EFFICIENT

Always provide the source file path in your final answer when reading documentation. For API queries, describe what you found.

CRITICAL for bug diagnosis:
- Make ONE API call to see the error/behavior
- Read backend/app/routers/analytics.py directly (you know the path)
- Find the bug in the code and explain it
- Total: 2-3 tool calls maximum for bug questions

IMPORTANT: API paths do NOT have /api prefix. Use '/items/' not '/api/items/'."""


# ---------------------------------------------------------------------------
# Agentic Loop
# ---------------------------------------------------------------------------


def execute_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a single tool call and return the result.

    Args:
        tool_call: Tool call dict with 'function' containing 'name' and 'arguments'.

    Returns:
        Dict with 'tool', 'args', and 'result' keys.
    """
    function = tool_call.get("function", {})
    tool_name = function.get("name", "unknown")
    args_str = function.get("arguments", "{}")

    try:
        args: dict[str, str] = json.loads(args_str)
    except json.JSONDecodeError:
        args = {}

    tool_func = TOOL_FUNCTIONS.get(tool_name)
    if tool_func is None:
        result = f"Error: Unknown tool '{tool_name}'"
    else:
        try:
            result = tool_func(**args)
        except Exception as e:
            result = f"Error: {type(e).__name__} - {e}"

    return {
        "tool": tool_name,
        "args": args,
        "result": result,
    }


def run_agent(question: str) -> dict[str, Any]:
    """
    Run the agent with the given question using an agentic loop.

    Args:
        question: The user's question.

    Returns:
        A dict with 'answer', 'source', and 'tool_calls' keys.
    """
    settings = get_settings()

    system_prompt = build_system_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    all_tool_calls = []
    answer = ""
    source = ""

    for _ in range(MAX_TOOL_CALLS):
        # Call LLM with current message history
        response = call_llm(messages, settings)

        # Extract the assistant's response
        choices = response.get("choices", [])
        if not choices:
            break

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        # Check if LLM returned a final answer (no tool calls)
        if not tool_calls:
            answer = content or ""
            # Extract source from answer if not already set
            if not source and answer:
                source = extract_source_from_answer(answer)
            break

        # Execute tool calls
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_message)  # pyright: ignore

        for tool_call in tool_calls:
            # Execute the tool
            result = execute_tool_call(tool_call)
            all_tool_calls.append(result)

            # Append tool result to messages
            tool_message = {
                "role": "tool",
                "tool_call_id": tool_call.get("id", ""),
                "content": result["result"],
            }
            messages.append(tool_message)

    # If we exited without a final answer, use the last content or indicate incomplete
    if not answer and all_tool_calls:
        answer = "I was unable to complete the answer within the tool call limit."

    return {
        "answer": answer,
        "source": source,
        "tool_calls": all_tool_calls,
    }


def extract_source_from_answer(answer: str) -> str:
    """
    Extract a source reference from the answer text.

    Looks for patterns like 'wiki/file.md', 'wiki/file.md#section',
    or source code paths like 'backend/app/routers/analytics.py'.
    """
    import re

    # Match wiki file paths with optional section anchors
    pattern = r"(wiki/[\w\-/]+\.md(?:#[\w\-]+)?)"
    match = re.search(pattern, answer)
    if match:
        return match.group(1)

    # Match backend source code paths
    pattern = r"(backend/[\w\-/]+\.py)"
    match = re.search(pattern, answer)
    if match:
        return match.group(1)

    # Match any .py file paths
    pattern = r"([\w\-/]+\.py)"
    match = re.search(pattern, answer)
    if match:
        return match.group(1)

    return ""


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point for the agent CLI."""
    parser = argparse.ArgumentParser(
        description="Agent CLI - answers questions by calling an LLM with tools."
    )
    parser.add_argument(
        "question",
        nargs="?",
        default=None,
        help="The question to ask the agent.",
    )
    parser.add_argument(
        "--question",
        "-q",
        dest="question_flag",
        type=str,
        default=None,
        help="The question to ask the agent.",
    )

    args = parser.parse_args()

    # Support both positional and --question argument
    question = args.question or args.question_flag
    if not question:
        parser.print_help()
        sys.exit(1)

    result = run_agent(question)

    # Output structured JSON to stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
