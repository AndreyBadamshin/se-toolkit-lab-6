#!/usr/bin/env python3
"""
Agent CLI - answers questions by calling an LLM with tools.

Usage:
    python agent.py --question "Your question here"
"""

import argparse
import json
import os
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

    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""

    model_config = {
        "env_file": str(Path(__file__).parent / ".env.agent.secret"),
        "env_prefix": "",
    }


class BackendApiSettings(BaseSettings):
    """Backend API configuration from environment variables."""

    lms_api_key: str = ""
    agent_api_base_url: str = "http://localhost:42002"

    model_config = {
        "env_file": str(Path(__file__).parent / ".env.docker.secret"),
        "env_prefix": "",
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
        "description": "Call the backend API to query data or check system status. Use for questions about database contents, API responses, or system configuration.",
        "parameters": {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                },
                "path": {
                    "type": "string",
                    "description": "API endpoint path (e.g., '/items/', '/analytics/scores')",
                },
                "body": {
                    "type": "string",
                    "description": "Optional JSON request body for POST/PUT/PATCH requests",
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


def get_backend_settings() -> BackendApiSettings:
    """Load backend API settings from environment."""
    return BackendApiSettings()  # type: ignore[call-arg]


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


def query_api(method: str, path: str, body: str | None = None) -> str:
    """
    Call the backend API with authentication.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH).
        path: API endpoint path (e.g., '/items/').
        body: Optional JSON request body for POST/PUT/PATCH.

    Returns:
        JSON string with status_code and body, or an error message.
    """
    settings = get_backend_settings()
    url = f"{settings.agent_api_base_url}{path}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.lms_api_key}",
    }

    try:
        with httpx.Client() as client:
            if method == "GET":
                response = client.get(url, headers=headers, timeout=10.0)
            elif method in ("POST", "PUT", "PATCH"):
                data = json.loads(body) if body else None
                response = client.request(
                    method, url, headers=headers, json=data, timeout=10.0
                )
            else:
                response = client.request(method, url, headers=headers, timeout=10.0)

        return json.dumps(
            {
                "status_code": response.status_code,
                "body": response.text,
            }
        )
    except httpx.RequestError as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": f"Request error: {str(e)}",
            }
        )
    except json.JSONDecodeError as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": f"Invalid JSON body: {str(e)}",
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "status_code": 0,
                "body": f"Error: {type(e).__name__} - {str(e)}",
            }
        )


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

    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def build_system_prompt() -> str:
    """
    Build the system prompt for the agent.

    Guides the LLM to use tools effectively and provide source references.
    """
    return """You are a helpful assistant that answers questions by reading project documentation, source code, and querying the backend API.

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
Maximum 10 tool calls per question."""


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
        content = message.get("content") or ""

        # Check if LLM returned a final answer (no tool calls)
        if not tool_calls:
            answer = content
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

    Looks for patterns like 'wiki/file.md' or 'wiki/file.md#section'.
    """
    import re

    # Match wiki file paths with optional section anchors
    pattern = r"(wiki/[\w\-/]+\.md(?:#[\w\-]+)?)"
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
        type=str,
        help="The question to ask the agent.",
    )

    args = parser.parse_args()

    result = run_agent(args.question)

    # Output structured JSON to stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
