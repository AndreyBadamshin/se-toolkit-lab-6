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
# Tests: Agent output structure (Task 1)
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


# ---------------------------------------------------------------------------
# Tests: Documentation Agent (Task 2)
# ---------------------------------------------------------------------------


class TestDocumentationAgent:
    """Test the documentation agent with tool-calling scenarios."""

    @pytest.mark.skip(
        reason="Requires a running LLM API. "
        "Unskip when .env.agent.secret is configured with valid credentials."
    )
    def test_merge_conflict_question_uses_read_file(
        self,
        agent_script: Path,
        env_with_llm_config: dict,
    ) -> None:
        """
        Test that asking about merge conflicts uses read_file tool.

        Expected: tool_calls contains 'read_file', source contains 'wiki/git-workflow.md'
        """
        result = subprocess.run(
            [
                sys.executable,
                str(agent_script),
                "--question",
                "How do you resolve a merge conflict?",
            ],
            capture_output=True,
            text=True,
            env=env_with_llm_config,
            timeout=60,
        )

        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output
        assert "source" in output
        assert "tool_calls" in output

        # Check that read_file was used
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "read_file" in tools_used, "Should use read_file tool"

        # Check source references wiki/git-workflow.md
        assert "wiki/git-workflow.md" in output["source"], (
            f"Source should reference wiki/git-workflow.md, got: {output['source']}"
        )

    @pytest.mark.skip(
        reason="Requires a running LLM API. "
        "Unskip when .env.agent.secret is configured with valid credentials."
    )
    def test_wiki_listing_question_uses_list_files(
        self,
        agent_script: Path,
        env_with_llm_config: dict,
    ) -> None:
        """
        Test that asking about wiki files uses list_files tool.

        Expected: tool_calls contains 'list_files'
        """
        result = subprocess.run(
            [
                sys.executable,
                str(agent_script),
                "--question",
                "What files are in the wiki?",
            ],
            capture_output=True,
            text=True,
            env=env_with_llm_config,
            timeout=60,
        )

        output = json.loads(result.stdout)

        # Check required fields
        assert "answer" in output
        assert "tool_calls" in output

        # Check that list_files was used
        tools_used = [tc.get("tool") for tc in output["tool_calls"]]
        assert "list_files" in tools_used, "Should use list_files tool"

    def test_agent_output_has_source_field(
        self,
        agent_script: Path,
    ) -> None:
        """
        Test that agent output structure includes 'source' field.

        This validates the JSON schema even when LLM call fails.
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

        # May fail, but if it produces output, check structure
        if result.stdout.strip():
            output = json.loads(result.stdout)
            assert "source" in output, "Output must contain 'source' field"
            assert isinstance(output["source"], str), "'source' must be a string"
