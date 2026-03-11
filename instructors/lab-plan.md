# Lab plan — Building an Observability CLI Agent

**Topic:** Agentic loops with observability using the VictoriaMetrics stack
**Date:** 2026-03-11

## Learning outcomes

By the end of this lab, students should be able to:

- [Remember] Identify the three pillars of observability — metrics, logs, and traces — and the role each plays in understanding a running system.
- [Understand] Explain how an agentic loop works: the LLM receives context, decides whether to call a tool, receives the tool result, and repeats until it produces a final answer.
- [Apply] Query the VictoriaMetrics and VictoriaLogs HTTP APIs from a Python CLI to retrieve metrics and log entries.
- [Apply] Implement a minimal agentic loop in Python that gives an LLM access to observability tools and iterates until the LLM stops calling tools.
- [Analyze] Interpret telemetry signals — high error rates, slow response times, spike in log errors — to diagnose a simulated system anomaly.
- [Evaluate] Assess how the set of tools exposed to an agent affects the completeness of its diagnosis by comparing outputs with different tool configurations.

In simple words:

> 1. I can name the three pillars of observability and say what each one is for.
> 2. I can explain what happens in an agentic loop step by step.
> 3. I can write Python code that queries VictoriaMetrics and VictoriaLogs and displays the results in the terminal.
> 4. I can build a loop that lets an LLM call my observability tools and stop when it has an answer.
> 5. I can read metrics and logs from the stack and explain what they reveal about the system's health.
> 6. I can compare what the agent produces with different tools enabled and explain why wider tool access leads to a better diagnosis.

## Lab story

You joined the SRE team at a company that runs a set of microservices. The team already deploys a VictoriaMetrics stack via Docker Compose — it collects metrics and logs from every service — but no one has built a tool that pulls it all together. The team lead wants a small command-line agent that can autonomously investigate a system anomaly by querying the observability stack and report its findings in plain language. The agent will use the Qwen3-Coder model through the free Qwen API, which provides 1000 requests per day — enough for development and testing.

A senior engineer explains the assignment:

> 1. Explore the observability stack running in Docker Compose — understand what metrics and logs are available and how to query them through the HTTP APIs.
> 2. Build a Python CLI using `rich` that can fetch and display metrics and log entries from VictoriaMetrics and VictoriaLogs.
> 3. Extend the CLI with an agentic loop: give an LLM access to your observability tools and let it autonomously investigate a simulated anomaly and produce a diagnosis report.

## Required tasks

### Task 1 — Explore the Observability Stack

**Purpose:** Build a mental model of the VictoriaMetrics stack and learn what observability data is available before writing any code.

Students start the provided Docker Compose environment, which runs VictoriaMetrics (metrics), VictoriaLogs (logs), and a simulated service that emits realistic metrics and log entries. They open the VictoriaMetrics UI and run several MetricsQL queries by hand to see what series exist. They also query the VictoriaLogs HTTP API to retrieve recent log entries. Students fill in a structured questionnaire file with answers extracted directly from the UI and API responses — metric names, label cardinality, log stream selectors, and the difference between a counter and a gauge. The questionnaire is committed to the repository and verified by the autochecker.

**Acceptance criteria:**

- The Docker Compose environment starts successfully and all containers pass their health checks.
- The questionnaire file exists at the required path and every field contains a value matching the expected format.
- The questionnaire answer for "what data source stores logs" is `victorialogs`.
- The questionnaire answer for the MetricsQL query that returns the HTTP request rate uses `rate()`.
- The autochecker confirms all questionnaire answers are correct.

---

### Task 2 — Build the Observability CLI

**Purpose:** Implement a Python CLI using `rich` that queries VictoriaMetrics and VictoriaLogs and presents results in a readable format, forming the tool layer the agent will use in Task 3.

Building on the API knowledge from Task 1, students implement a Python CLI with two subcommands: `metrics` (queries VictoriaMetrics via its HTTP query API and renders results as a `rich` table) and `logs` (queries VictoriaLogs via its HTTP query API and streams results as a `rich` live log panel). The CLI accepts arguments for the query string and a time range. Students write unit tests for the query-building and response-parsing logic using `pytest`. The seed project provides the project scaffold and a working `rich` table example as a reference; students implement the two query functions and their CLI wrappers by following the reference pattern.

**Acceptance criteria:**

- `uv run poe cli metrics --query 'rate(http_requests_total[1m])'` prints a `rich` table with at least one row.
- `uv run poe cli logs --query '{service="api"}' --limit 20` prints at least one log line in a `rich` panel.
- All unit tests pass (`uv run poe test`).
- A PR with the implementation is approved and merged.

---

### Task 3 — Implement the Agentic Loop

**Purpose:** Build the simplest possible agentic loop — an LLM that calls the observability tools from Task 2 iteratively until it can produce a diagnosis — and observe how tool availability and context accumulation drive autonomous reasoning.

Students extend the CLI with an `investigate` subcommand. The command implements a minimal agentic loop: (1) send the user's question and a tool schema to the LLM; (2) if the LLM returns a tool call, execute the matching Python function and append the result to the message history; (3) repeat until the LLM returns a text response with no tool calls; (4) display the final diagnosis using `rich`. The available tools are the metric and log query functions from Task 2. The seed project provides the message-history accumulation skeleton with `# UNCOMMENT AND FILL IN` placeholders; students implement the tool-dispatch loop and the tool schema definitions. A Docker Compose service runs a simulated anomaly (a spike in HTTP 500 errors) that the agent must identify. Students observe the full loop in action, note how many iterations the agent takes, and record the finding in a comment on their issue. As a final step, students disable one of the two tools and re-run the agent to observe how the narrower tool set produces a less complete diagnosis — making visible that an agent's debugging ability is defined by the tools it can access.

**Acceptance criteria:**

- `uv run poe cli investigate "Is the API healthy?"` completes without error and prints a `rich` diagnosis panel.
- The agent executes at least two tool calls before producing its final answer (visible in the loop debug output).
- The agent correctly identifies the simulated anomaly (elevated HTTP 500 rate) in its diagnosis text.
- A PR with the implementation is approved and merged.
- The issue contains a comment with the agent's diagnosis from the full-tool run and the single-tool run, each pasted as a code block.

---

## Optional task

### Task 1 — Add a Traces Tool Using the Tempo API

**Purpose:** Extend the agent with a third observability pillar — distributed traces — and observe how richer tool coverage changes the quality of the agent's diagnosis.

Students add a third tool, `get_traces`, that queries a Grafana Tempo instance (added to the Docker Compose file) for recent trace summaries for a given service and time window. They register the tool in the agent's tool schema alongside the metrics and logs tools. The simulated anomaly is updated to also produce a slow trace (high latency on a specific span) that only the trace tool can reveal. Students run the agent again and compare the diagnosis with and without the traces tool, recording the difference in a structured comparison file that the autochecker verifies. The Docker Compose update and the tool implementation must each be a separate commit.

**Acceptance criteria:**

- A Tempo service is added to `docker-compose.yml` and starts successfully.
- `uv run poe cli investigate "What is causing slow responses in the API?"` uses the `get_traces` tool at least once.
- The agent's diagnosis mentions span latency or a specific slow operation visible only in traces.
- The comparison file exists at the required path with answers for both the "without traces" and "with traces" scenarios.
- The Docker Compose change and the tool implementation are separate commits.
