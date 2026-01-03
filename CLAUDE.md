# KI-CLI Workspace

## Projekt-Übersicht

Zentrales Tool für Issue-Management und KI-Zusammenarbeit. Synchronisiert Issues von Codacy und ermöglicht allen KIs (Claude, Codex, Gemini) die gemeinsame Verwaltung.

## Architektur

```
cindergrace_ki-cli_workspace/
├── app.py              # Gradio Web-GUI (Port 7870)
├── cli.py              # CLI Entry Point
├── core/
│   ├── database.py     # SQLite mit FTS5 + FAQ
│   ├── codacy_sync.py  # Codacy REST API Sync
│   ├── checks.py       # Release Readiness Checks
│   ├── project_init.py # Projekt-Erstellung/Archivierung
│   └── crypto.py       # Verschlüsselung für API Keys
└── tests/
```

## CLI Befehle

```bash
ki-workspace ki-info              # IMMER ZUERST LESEN!
ki-workspace projects             # Alle Projekte
ki-workspace status <PROJECT>     # Projekt-Status (inkl. Phase)
ki-workspace issues <PROJECT>     # Issues auflisten
ki-workspace sync <PROJECT>       # Von Codacy synchronisieren
ki-workspace check <PROJECT>      # Release Readiness Check (phasenabhaengig)
ki-workspace check <P> --phase final  # Check mit Phase-Override
ki-workspace phases               # Verfuegbare Phasen anzeigen
ki-workspace set-phase <P> <PHASE>    # Projekt-Phase setzen
ki-workspace recommend-ignore     # KI empfiehlt Ignore
ki-workspace pending-ignores      # Offene KI-Empfehlungen
ki-workspace init <NAME>          # Neues Projekt erstellen
ki-workspace archive <PROJECT>    # Projekt archivieren
ki-workspace faq                  # KI-FAQ anzeigen
ki-workspace faq <KEY>            # Bestimmten FAQ-Eintrag
ki-workspace faq <QUERY> -s       # FAQ durchsuchen
ki-workspace faq --json           # Kompakt für KI-Konsum
```

## KI-FAQ System

Schneller Zugriff auf Workspace-Wissen ohne Token-Verschwendung:

```bash
# Alles als kompaktes JSON (für KI-Konsum)
ki-workspace faq --json

# Bestimmtes Thema
ki-workspace faq sync_process

# Suche
ki-workspace faq issue -s

# Nach Kategorie (process, workflow, command, concept)
ki-workspace faq --category workflow
```

**Projekt-spezifisches FAQ:** Jedes neue Projekt erhält `.ki-faq.json` mit Architektur, Konventionen und TODOs.

## KI-Workflow für Issue-Review

### Wichtigste Regel

**Der lokale Status zieht zuerst!** Wenn ein Issue bereits eine KI-Empfehlung hat (`ki_recommendation` gesetzt), NICHT erneut bewerten. Der User hat es evtl. nur noch nicht in Codacy markiert.

### Ablauf

1. **Workflow-Info lesen:** `ki-workspace ki-info`
2. **Issues laden:** `ki-workspace issues <PROJECT> --json`
3. **Prüfen:** Hat Issue bereits `ki_recommendation`? → SKIP
4. **Analysieren:** Code-Kontext prüfen, ist es ein echtes Problem?
5. **Empfehlen:** `ki-workspace recommend-ignore <ID> -c <CATEGORY> -r "Begründung" --reviewer <KI>`
6. **User informieren:** "Bitte in Codacy als Ignored markieren"

### Kategorien für recommend-ignore

| Kategorie | Bedeutung |
|-----------|-----------|
| `accepted_use` | Bewusst so implementiert, kein Risiko |
| `false_positive` | Tool-Fehlalarm, kein echtes Problem |
| `not_exploitable` | Theoretisch verwundbar, praktisch nicht ausnutzbar |
| `test_code` | Nur in Tests, nicht in Produktion |
| `external_code` | Fremdcode/Vendor, nicht von uns wartbar |

### Beispiel

```bash
# SQL-Injection als False Positive markieren (parameterisierte Query)
ki-workspace recommend-ignore 42 \
    --category false_positive \
    --reason "Query ist parameterisiert, Parameter werden nicht in SQL eingebettet" \
    --reviewer claude
```

## Datenbank

SQLite unter `~/.ai-workspace/workspace.db`

### Tabellen

- `projects` - Projektliste mit Codacy-Config und Cache
- `issue_meta` - Issues mit KI-Empfehlungen
- `issues_fts` - FTS5 Index für Issue-Suche
- `ki_faq` - Globales KI-FAQ
- `ki_faq_fts` - FTS5 Index für FAQ-Suche
- `project_phases` - Projekt-Phasen (Initial, Development, Testing, Final)
- `check_matrix` - Welche Checks in welcher Phase
- `settings` - API-Keys (verschlüsselt), Pfade
- `handoffs` - KI-Session Übergaben

### KI-Felder in issue_meta

- `ki_recommendation_category` - Empfohlene Ignore-Kategorie
- `ki_recommendation` - Begründung der KI
- `ki_reviewed_by` - Welche KI (claude, codex, gemini)
- `ki_reviewed_at` - Timestamp

## API Keys

Verschlüsselt in DB gespeichert (Fernet/AES-128):
- `codacy_api_token` - Für Issue-Sync
- `github_token` - Für GitHub API

## Release Readiness Checks

Prüft automatisch:
- LICENSE vorhanden
- README vorhanden (min. 50 Zeichen)
- CHANGELOG vorhanden
- Keine Critical Issues (open)
- Keine High Issues (open)
- Radon Complexity (optional)
- Tests bestanden
- Git Status sauber

## Technologien

- Python 3.10+
- Gradio 5.x (Web-UI)
- Typer (CLI)
- SQLite mit FTS5
- Fernet (Verschlüsselung)
