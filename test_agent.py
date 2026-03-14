"""Regression tests for agent.py CLI.

These tests run agent.py as a subprocess and verify the JSON output structure.
Run with: uv run poe test-unit
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def agent_script() -> Path:
    """Return the path to agent.py."""
    root = Path(__file__).parent.parent.parent.parent
    return root / "agent.py"


@pytest.fixture
def env_with_llm_config(monkeypatch: pytest.MonkeyPatch) -> dict:
    """
    Set up minimal LLM configuration for agent.

    Note: This test only validates the JSON output structure.
    The actual LLM call may fail if credentials are not configured.
    """
    env = {
        "LLM_API_KEY": "test-key",
        "LLM_API_BASE": "http://localhost:8000/v1",
        "LLM_MODEL": "test-model",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


# ---------------------------------------------------------------------------
# Tests: Agent output structure
# ---------------------------------------------------------------------------


class TestAgentOutputStructure:
    """Test that agent.py produces valid JSON output with required fields."""

    @pytest.mark.skip(
        reason="Requires a running LLM API. "
        "Unskip when .env.agent.secret is configured with valid credentials."
    )
    def test_agent_returns_json_with_answer_and_tool_calls(
        self,
        agent_script: Path,
        env_with_llm_config: dict,
    ) -> None:
        """
        Test that agent.py returns JSON with 'answer' and 'tool_calls' fields.

        This test runs the agent as a subprocess and parses stdout.
        """
        result = subprocess.run(
            [
                sys.executable,
                str(agent_script),
                "--question",
                "What is the project structure?",
            ],
            capture_output=True,
            text=True,
            env=env_with_llm_config,
            timeout=30,
        )

        # Parse JSON output from stdout
        output = json.loads(result.stdout)

        # Check that required fields are present
        assert "answer" in output, "Output must contain 'answer' field"
        assert "tool_calls" in output, "Output must contain 'tool_calls' field"

        # Validate field types
        assert isinstance(output["answer"], str), "'answer' must be a string"
        assert isinstance(output["tool_calls"], list), "'tool_calls' must be a list"

    def test_agent_returns_401_with_invalid_credentials(
        self,
        agent_script: Path,
    ) -> None:
        """
        Test that agent.py fails gracefully with invalid credentials.

        This validates error handling when the LLM API is unreachable.
        """
        env = {
            "LLM_API_KEY": "invalid-key",
            "LLM_API_BASE": "http://localhost:9999/v1",
            "LLM_MODEL": "test-model",
        }

        result = subprocess.run(
            [
                sys.executable,
                str(agent_script),
                "--question",
                "Test question",
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        # Should fail with connection error or 401
        assert result.returncode != 0 or "error" in result.stderr.lower()
