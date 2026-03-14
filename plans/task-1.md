# Task 1: AI Agent Description

## LLM Provider and Model

**Provider:** Qwen Code (Alibaba Group)  
**Model:** coder-model

The agent uses Qwen Code, an interactive CLI agent developed by Alibaba Group, specializing in software engineering tasks. The coder-model is configured for code generation, refactoring, and technical problem-solving.

## AI Agent Structure

### Core Components

1. **Main Entry Point** (`agent.py`)
   - CLI interface for user interaction
   - Orchestrates tool execution and LLM calls

2. **Skills** (`.agents/skills/`)
   - Modular capabilities for specific tasks:
     - `cleanup-file-review` — cleaning up reviewed files
     - `commit` — git commit operations
     - `find-empty-sections` / `find-incomplete-sections` — document analysis
     - `find-new-patterns` — pattern detection
     - `fix-broken-links` / `fix-file` — file corrections
     - `get-meeting-report` / `get-meeting-transcript` — meeting processing
     - `ideate-lab` — lab ideation
     - `pr` — pull request handling
     - `review-file` — file review

3. **Tools**
   - File operations: `read_file`, `write_file`, `edit`, `list_directory`
   - Code operations: `grep_search`, `glob`, `run_shell_command`
   - Web operations: `web_search`, `web_fetch`
   - Task management: `task`, `todo_write`
   - Communication: `ask_user_question`

4. **Configuration**
   - `.qwen/` — agent settings and preferences
   - `.env.agent.secret` — LLM provider credentials

### Architecture Flow

```
User Input → Agent Core → [Skills Selection] → [Tool Execution] → LLM (coder-model) → Response
```
