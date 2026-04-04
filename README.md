# AI Scrum Master

An AI-powered scrum master that automates GitHub project management — triaging issues, decomposing stories into tickets, detecting duplicates, and running security checks on pull requests.

## What it does

- **Story decomposition** — submit a plain-text feature description and the crew breaks it down into epics, stories, and tasks, creates GitHub issues with labels, and links sub-issues automatically
- **Deduplication** — before creating tickets, existing open issues are checked for overlap so the same story can be submitted multiple times safely
- **Triage** — incoming GitHub webhook events are classified and routed to the appropriate handler
- **DevSecOps** — pull requests and issues are scanned for secrets, CVEs in dependency files, OWASP categories, and branch naming policy violations

## Architecture

```
POST /stories      →  story decomposer agent  →  GitHub issues (with sub-issue linking)
POST /webhook      →  triage agent  →  dedup + devsecops + action agents
POST /scan         →  devsecops agent
```

Agents are built with [CrewAI](https://github.com/crewai-ai/crewai) and run against a local [Ollama](https://ollama.com) instance. GitHub interactions use the REST API and an MCP server.

## Requirements

- Docker and Docker Compose
- A GitHub personal access token with `repo` scope
- Ollama running `qwen2.5:7b` (or configure a different model)

## Setup

Copy `.env.example` to `.env` and fill in the values:

```
GITHUB_TOKEN=ghp_...
GITHUB_WEBHOOK_SECRET=your-webhook-secret
API_KEY=your-api-key
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:7b
MCP_SERVER_URL=http://github-mcp:3000
```

Start the stack:

```bash
docker compose up -d
```

## Usage

### Decompose a story into tickets

```bash
curl -X POST http://localhost:8000/stories \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-api-key" \
  -d '{"repo":"owner/repo","story":"As a user I want to log in with email and password."}'
```

### Trigger a manual security scan

```bash
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-api-key" \
  -d '{"repo":"owner/repo"}'
```

### GitHub webhook

Point your repository webhook at `POST /webhook` with a `application/json` content type and the same secret as `GITHUB_WEBHOOK_SECRET`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
