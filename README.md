# KI-CLI Workspace

KI-übergreifendes Workspace-Tool für Issue-Management und Prozessdokumentation.

## Features

- **Issue-Management**: Codacy-Issues synchronisieren, filtern, durchsuchen
- **False Positives**: Markieren mit Begründung, sync zu Codacy
- **Volltextsuche**: SQLite FTS5 für schnelle Suche
- **KI-Übergaben**: Session-Kontext zwischen Claude, Gemini, Codex teilen

## Installation

```bash
cd cindergrace_ki-cli_workspace
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Start

```bash
python app.py
# Öffnet http://127.0.0.1:7870
```

## Architektur

```
cindergrace_ki-cli_workspace/
├── app.py                # Gradio Hauptanwendung
├── core/
│   ├── database.py       # SQLite + FTS5 Manager
│   └── codacy_sync.py    # Codacy API Client
├── addons/               # Erweiterbare Module
│   ├── issues/
│   └── security/
└── data/                 # Lokale Daten
```

## Datenbank

Die Datenbank wird in `~/.ai-workspace/workspace.db` gespeichert (global für alle Projekte).

## Roadmap

- [x] Phase 1: Issue Management + Codacy Sync
- [ ] Phase 2: Backlog + Release Management
- [ ] Phase 3: Dokumentenmanagement
