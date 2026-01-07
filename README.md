# KI-CLI Workspace

> **Note:** This repository is a hobby/experimental project. It is not a commercial product (no contracts, no guarantees, no support promise).

A cross-AI workspace tool for issue management, release readiness checks, and AI collaboration.

## Features

- **Issue Management** - Sync issues from Codacy, filter, search with full-text (SQLite FTS5)
- **False Positive Handling** - Mark issues with AI recommendations, sync back to Codacy
- **Project Phases** - Track project lifecycle (Initial, Development, Testing, Final)
- **Release Readiness** - Automated checks for LICENSE, README, CHANGELOG, open issues, tests
- **AI Delegation** - Delegate tasks to Codex, Gemini, or Claude via CLI
- **AI Commit Messages** - Generate commit messages using OpenRouter API
- **KI-FAQ System** - Quick access to workspace knowledge for AI assistants
- **Secure API Storage** - Keys stored in OS Keyring (Windows, macOS, Linux)

## Installation

```bash
cd cindergrace_ki-cli_workspace
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -e .
```

## Quick Start

```bash
# Set up API keys (stored securely in OS keyring)
ki-workspace set-key codacy <YOUR_CODACY_TOKEN>
ki-workspace set-key github <YOUR_GITHUB_TOKEN>
ki-workspace set-key openrouter <YOUR_OPENROUTER_KEY>

# Start Web UI
python app.py
# Opens http://127.0.0.1:7870
```

## CLI Commands

### Project Management

```bash
ki-workspace projects              # List all projects
ki-workspace status <PROJECT>      # Show project status with issue counts
ki-workspace init <NAME>           # Create new project with full structure
ki-workspace archive <PROJECT>     # Archive a project
```

### Issue Management

```bash
ki-workspace sync <PROJECT>        # Sync issues from Codacy
ki-workspace issues <PROJECT>      # List project issues
ki-workspace issues <P> -p High    # Filter by priority
ki-workspace issues <P> --json     # JSON output for scripting
```

### Release Readiness

```bash
ki-workspace check <PROJECT>       # Run all release checks
ki-workspace phases                # Show available phases
ki-workspace set-phase <P> <PHASE> # Set project phase
```

### KI-FAQ System

```bash
ki-workspace faq                   # Show all FAQ entries
ki-workspace faq <KEY>             # Get specific entry
ki-workspace faq <QUERY> -s        # Full-text search
ki-workspace faq --json            # Compact JSON for AI consumption
ki-workspace faq --category workflow  # Filter by category
```

### AI Features

```bash
ki-workspace commit                # Generate AI commit message
ki-workspace commit --auto         # Auto-commit without confirmation
ki-workspace delegate <PROMPT> -f <FILE>  # Delegate task to AI
ki-workspace ai-status             # Show available AI CLIs
ki-workspace prompts               # List prompt templates
```

### API Key Management

```bash
ki-workspace set-key codacy <TOKEN>     # Codacy API token
ki-workspace set-key github <TOKEN>     # GitHub token
ki-workspace set-key openrouter <KEY>   # OpenRouter API key
```

## Architecture

```
cindergrace_ki-cli_workspace/
├── app.py                  # Gradio Web UI (Port 7870)
├── cli.py                  # Typer CLI entry point
├── core/
│   ├── database.py         # SQLite + FTS5 manager
│   ├── codacy_sync.py      # Codacy REST API client
│   ├── checks.py           # Release readiness checks
│   ├── project_init.py     # Project creation/archiving
│   ├── ai_commit.py        # AI commit message generation
│   ├── ai_delegation.py    # Delegate tasks to AI CLIs
│   └── secrets.py          # OS Keyring integration
└── tests/
```

## Database

SQLite database stored at `~/.ai-workspace/workspace.db` (global for all projects).

### Tables

| Table | Purpose |
|-------|---------|
| `projects` | Project list with Codacy config and cache |
| `issue_meta` | Issues with AI recommendations |
| `issues_fts` | FTS5 index for issue search |
| `ki_faq` | Global KI-FAQ entries |
| `project_phases` | Project lifecycle phases |
| `check_matrix` | Which checks run in which phase |
| `settings` | Configuration (non-secret) |
| `ai_prompts` | Prompt templates for AI delegation |

## AI Collaboration Workflow

This tool enables multiple AI assistants (Claude, Codex, Gemini) to collaborate:

1. **Read FAQ first**: `ki-workspace faq --json` for context
2. **Check issues**: `ki-workspace issues <PROJECT> --json`
3. **Skip reviewed**: If `ki_recommendation` is set, don't re-review
4. **Recommend ignores**: Use categories like `false_positive`, `accepted_use`
5. **Delegate tasks**: Use prompt templates to delegate work

### Ignore Categories

| Category | Meaning |
|----------|---------|
| `accepted_use` | Intentionally implemented this way, no risk |
| `false_positive` | Tool false alarm, not a real issue |
| `not_exploitable` | Theoretically vulnerable, practically not exploitable |
| `test_code` | Only in tests, not in production |
| `external_code` | Third-party/vendor code, not maintainable by us |

## Release Checks

The release readiness system verifies:

- LICENSE file exists
- README exists (min. 50 characters)
- CHANGELOG exists
- No Critical issues (open)
- No High issues (open)
- Radon complexity (optional)
- Tests pass
- Git status clean

Checks are phase-dependent - early phases have fewer requirements.

## Technologies

- Python 3.10+
- Gradio 5.x (Web UI)
- Typer + Rich (CLI)
- SQLite with FTS5
- OS Keyring (secure API key storage)
- OpenRouter API (AI commit messages)

## Roadmap

- [x] Phase 1: Issue Management + Codacy Sync
- [x] Phase 2: Release Management (Project Phases, Phase-dependent Checks)
- [x] Phase 3: AI Delegation + Prompt Templates
- [ ] Phase 4: Document Management

## License

MIT License - See LICENSE file for details.
