# KI-CLI Workspace - Architektur v2.0

## Übersicht

Refactoring des KI-CLI Workspace für:
- Keine hardcoded Konfiguration
- Windows-Kompatibilität
- Multi-User Support (max 5 User, lokal)
- Online-Sync (self-hosted Backend)
- Offline-first mit späterem Sync

## Zielarchitektur

```
┌─────────────────────────────────────────────────────────────┐
│                    KI-CLI Workspace Client                   │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Gradio UI  │  │   CLI       │  │  MCP Server         │  │
│  │  (Tabs)     │  │   Commands  │  │  (IDE Integration)  │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   Service Layer                        │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │  │
│  │  │ ProjectSvc  │ │ IssueSvc    │ │ SyncSvc         │  │  │
│  │  │ - add       │ │ - list      │ │ - pull          │  │  │
│  │  │ - archive   │ │ - update    │ │ - push          │  │  │
│  │  │ - list      │ │ - recommend │ │ - resolve       │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                   Data Layer                           │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              Local SQLite                        │  │  │
│  │  │  - projects, issues, faq, settings, sync_state  │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS (optional)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 KI-CLI Workspace Server (Optional)           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  FastAPI Backend                     │    │
│  │  - /api/sync      (pull/push changes)               │    │
│  │  - /api/projects  (shared project registry)         │    │
│  │  - /api/issues    (issue sync)                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                          │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              PostgreSQL (encrypted at rest)          │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Datenmodell

### Lokale Tabellen (SQLite)

```sql
-- Benutzer (lokal, max 5)
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    email TEXT,
    is_active BOOLEAN DEFAULT FALSE,  -- Aktuell aktiver User
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Projekte (erweitert)
CREATE TABLE projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT,                        -- Lokaler Pfad (kann pro Client unterschiedlich sein)
    git_remote TEXT,                  -- Canonical identifier
    codacy_provider TEXT,
    codacy_org TEXT,
    phase TEXT DEFAULT 'development',
    is_archived BOOLEAN DEFAULT FALSE,
    sync_enabled BOOLEAN DEFAULT TRUE, -- Für selektiven Sync
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    remote_id TEXT                    -- ID auf dem Server (für Sync)
);

-- Issues (erweitert um User-Tracking)
CREATE TABLE issues (
    id INTEGER PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    external_id TEXT,
    -- ... existing fields ...
    assigned_to INTEGER REFERENCES users(id),
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMP,
    remote_id TEXT,
    sync_state TEXT DEFAULT 'local'   -- local, synced, conflict
);

-- Sync-Status
CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY,
    entity_type TEXT,                 -- 'project', 'issue', 'faq'
    entity_id INTEGER,
    local_version INTEGER,
    remote_version INTEGER,
    last_sync TIMESTAMP,
    sync_status TEXT                  -- pending, synced, conflict
);

-- Settings (ersetzt hardcoded config)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    category TEXT,                    -- 'server', 'ui', 'codacy', 'github'
    updated_at TIMESTAMP
);
```

### Server-Tabellen (PostgreSQL)

```sql
-- Workspace (Mandant/Team)
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    api_key TEXT NOT NULL UNIQUE,     -- Für Client-Auth
    created_at TIMESTAMP DEFAULT NOW()
);

-- Projects (zentral)
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    git_remote TEXT NOT NULL,         -- Canonical identifier
    name TEXT,
    codacy_provider TEXT,
    codacy_org TEXT,
    phase TEXT,
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    version INTEGER DEFAULT 1         -- Für Conflict Detection
);

-- Issues (zentral)
CREATE TABLE issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    project_id UUID REFERENCES projects(id),
    external_id TEXT,
    -- ... fields ...
    version INTEGER DEFAULT 1
);

-- Sync-Log (Audit Trail)
CREATE TABLE sync_log (
    id SERIAL PRIMARY KEY,
    workspace_id UUID,
    client_id TEXT,
    user_name TEXT,
    action TEXT,                      -- push, pull, resolve
    entity_type TEXT,
    entity_id UUID,
    timestamp TIMESTAMP DEFAULT NOW()
);
```

## Konfigurationsmanagement

### Settings-Kategorien

```python
SETTINGS_SCHEMA = {
    "server": {
        "sync_url": "",               # https://your-server.com/api
        "api_key": "",                # Workspace API Key
        "auto_sync": False,           # Automatischer Sync beim Start
    },
    "codacy": {
        "api_token": "",              # Via SecretStore
        "default_provider": "gh",
    },
    "github": {
        "api_token": "",              # Via SecretStore
        "sync_issues": True,
    },
    "ui": {
        "theme": "default",
        "language": "de",
        "projects_per_page": 20,
    }
}
```

### Migration von Hardcoded → Settings

```python
# Alt (hardcoded)
CODACY_ORG = "goettemar"
CODACY_PROVIDER = "gh"

# Neu (Settings-based)
class Config:
    @classmethod
    def get(cls, key: str, default=None):
        return settings_service.get(key, default)

    @property
    def codacy_org(self):
        return self.get("codacy.default_org")
```

## Sync-Strategie

### Offline-First Prinzip

1. **Alle Operationen lokal zuerst**
   - Änderungen werden in lokaler SQLite gespeichert
   - `sync_state` wird auf `pending` gesetzt

2. **Sync bei Verbindung**
   - Pull: Remote-Änderungen holen
   - Push: Lokale Änderungen hochladen
   - Conflict Resolution bei Bedarf

### Conflict Resolution

```python
class ConflictStrategy:
    LAST_WRITE_WINS = "last_write"    # Einfachste Strategie
    LOCAL_WINS = "local"               # Lokale Änderung bevorzugen
    REMOTE_WINS = "remote"             # Server-Version bevorzugen
    MANUAL = "manual"                  # User entscheidet

# Bei Issues: LAST_WRITE_WINS (basierend auf updated_at)
# Bei Projects: MANUAL (selten, wichtige Entscheidung)
```

### Sync-Protokoll

```
Client                              Server
   │                                   │
   │──── GET /api/sync/changes ───────>│
   │<─── {changes since last_sync} ────│
   │                                   │
   │  [Apply remote changes locally]   │
   │                                   │
   │──── POST /api/sync/push ─────────>│
   │     {local pending changes}       │
   │<─── {accepted, conflicts} ────────│
   │                                   │
   │  [Resolve conflicts if any]       │
   │                                   │
```

## API-Design (Server)

### Endpoints

```
POST   /api/workspace/register     # Neuen Workspace erstellen
GET    /api/workspace/info         # Workspace-Info abrufen

GET    /api/sync/changes           # Änderungen seit last_sync
POST   /api/sync/push              # Lokale Änderungen pushen
POST   /api/sync/resolve           # Konflikt auflösen

GET    /api/projects               # Alle Projekte
POST   /api/projects               # Projekt erstellen
PUT    /api/projects/{id}          # Projekt updaten
DELETE /api/projects/{id}          # Projekt archivieren

GET    /api/issues                 # Issues (mit Filter)
POST   /api/issues/bulk            # Bulk-Update
```

### Authentifizierung

```
Header: X-API-Key: <workspace_api_key>
Header: X-Client-ID: <unique_client_identifier>
Header: X-User-Name: <current_user_name>
```

Keine komplexe Auth - API-Key pro Workspace reicht für kleine Teams.

## Windows-Kompatibilität

### Problembereiche

1. **Pfade**: `\` vs `/`
   ```python
   from pathlib import Path  # Immer Path verwenden, nie string concat
   ```

2. **XDG-Pfade**: Nicht verfügbar auf Windows
   ```python
   # platformdirs verwenden statt xdg
   from platformdirs import user_data_dir, user_config_dir

   data_dir = user_data_dir("ki-workspace", "cindergrace")
   # Linux: ~/.local/share/ki-workspace
   # Windows: C:\Users\<user>\AppData\Local\cindergrace\ki-workspace
   ```

3. **Keyring**: Funktioniert auf beiden, aber Backend unterschiedlich
   ```python
   # SecretStore aus cindergrace_common abstrahiert das bereits
   ```

4. **Shell-Commands**: Verschiedene Shells
   ```python
   # subprocess mit shell=False und Liste statt String
   subprocess.run(["git", "status"], shell=False)
   ```

## UI-Änderungen (Dashboard)

### Projekt-Auswahl für Batch-Operationen

```python
# Dashboard Tab - Projekt-Liste mit Checkboxen
with gr.Row():
    project_table = gr.Dataframe(
        headers=["✓", "Projekt", "Phase", "Issues", "Letzter Sync"],
        # Erste Spalte: Checkbox
    )

with gr.Row():
    select_all_btn = gr.Button("Alle auswählen")
    deselect_all_btn = gr.Button("Keine auswählen")

with gr.Row():
    sync_selected_btn = gr.Button("Ausgewählte aktualisieren", variant="primary")
    sync_all_btn = gr.Button("Alle aktualisieren")
    archive_selected_btn = gr.Button("Ausgewählte archivieren", variant="stop")
```

### Projekt hinzufügen (ohne Hardcoding)

```python
# Neuer Dialog
with gr.Row():
    folder_path = gr.Textbox(label="Projekt-Pfad", placeholder="/home/user/projekte/...")
    browse_btn = gr.Button("📁 Durchsuchen")  # Öffnet nativen Datei-Dialog

with gr.Row():
    # Auto-detect aus git remote
    git_remote = gr.Textbox(label="Git Remote (auto-detected)")
    codacy_org = gr.Textbox(label="Codacy Organisation")
    codacy_provider = gr.Dropdown(["gh", "gl", "bb"], label="Provider")

add_project_btn = gr.Button("Projekt hinzufügen", variant="primary")
```

## Phasenplan

### Phase 1: Lokales Refactoring (ohne Server)
- [ ] Settings-System implementieren
- [ ] Hardcoded Config → Settings migrieren
- [ ] Projekt Add/Archive über UI
- [ ] Dashboard Checkboxen für Batch-Operationen
- [ ] Windows-Kompatibilität (platformdirs, Path)
- [ ] User-Auswahl beim Start (lokal, max 5)

### Phase 2: Server-Backend
- [ ] FastAPI Server Grundgerüst
- [ ] PostgreSQL Schema
- [ ] API-Endpoints (Workspace, Projects, Issues)
- [ ] Verschlüsselung at-rest
- [ ] Docker-Compose für einfaches Deployment

### Phase 3: Sync-Implementation
- [ ] Sync-State Tracking lokal
- [ ] Pull/Push Logik
- [ ] Conflict Detection & Resolution
- [ ] Offline-Queue für pending Changes

### Phase 4: Multi-User Features
- [ ] User-Tracking bei Aktionen
- [ ] Issue-Assignment
- [ ] Aktivitäts-History
- [ ] Team-Dashboard (wer arbeitet woran)

## Offene Fragen

1. **GitHub Issue Sync**: Bidirektional oder nur Import?
2. **Verschlüsselung**: Nur at-rest oder auch in-transit beyond HTTPS?
3. **Backup-Strategie**: Automatische Backups auf dem Server?
4. **Rate-Limiting**: Für API-Schutz bei public-facing Server?

## Tech-Stack

### Client
- Python 3.10+
- Gradio 6.x (UI)
- SQLite (lokal)
- httpx (HTTP Client)
- platformdirs (Cross-platform Pfade)
- cindergrace-common (Shared Utils)

### Server
- Python 3.10+
- FastAPI
- PostgreSQL 15+
- SQLAlchemy 2.0
- Alembic (Migrations)
- Docker + Docker-Compose

---

*Dokument-Version: 0.1 (Draft)*
*Erstellt: 2026-01-06*
*Review ausstehend: Codex*
