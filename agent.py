#!/usr/bin/env python3
"""
Agent CLI - answers questions by calling an LLM.

Usage:
    python agent.py --question "Your question here"
"""

import argparse
import json
import os
import sys
from typing import Any

import httpx
from pydantic_settings import BaseSettings


class AgentSettings(BaseSettings):
    """LLM configuration from environment variables."""

    llm_api_key: str
    llm_api_base: str
    llm_model: str

    class Config:
        env_file = ".env.agent.secret"
        env_prefix = "LLM_"


def get_settings() -> AgentSettings:
    """Load agent settings from environment."""
    return AgentSettings()


def call_lllm(
    messages: list[dict[str, str]],
    settings: AgentSettings,
) -> dict[str, Any]:
    """
    Call the LLM API with the given messages.

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
    }

    with httpx.Client() as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def build_system_prompt() -> str:
    """
    Build the system prompt for the agent.

    Currently minimal — will be expanded in later tasks when adding
    tools and domain knowledge.
    """
    return "You are a helpful assistant."


def run_agent(question: str) -> dict[str, Any]:
    """
    Run the agent with the given question.

    Args:
        question: The user's question.

    Returns:
        A dict with 'answer' and 'tool_calls' keys.
    """
    settings = get_settings()

    system_prompt = build_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    response = call_lllm(messages, settings)

    # Extract the assistant's response
    choices = response.get("choices", [])
    if not choices:
        return {"answer": "", "tool_calls": []}

    message = choices[0].get("message", {})
    answer = message.get("content", "")
    tool_calls = message.get("tool_calls", [])

    return {
        "answer": answer,
        "tool_calls": tool_calls,
    }


def main() -> None:
    """Main entry point for the agent CLI."""
    parser = argparse.ArgumentParser(
        description="Agent CLI - answers questions by calling an LLM."
    )
    parser.add_argument(
        "--question",
        "-q",
        type=str,
        required=True,
        help="The question to ask the agent.",
    )

    args = parser.parse_args()

    result = run_agent(args.question)

    # Output structured JSON to stdout
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
