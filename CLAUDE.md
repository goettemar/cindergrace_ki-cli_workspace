# KI-CLI Workspace

## Projekt-Übersicht

Zentrales Tool für Issue-Management und KI-Zusammenarbeit. Synchronisiert Issues von Codacy und ermöglicht allen KIs (Claude, Codex, Gemini) die gemeinsame Verwaltung.

## Architektur

```
cindergrace_ki-cli_workspace/
├── app.py              # Gradio Web-GUI (Port 7870)
├── core/
│   ├── cli.py          # CLI-Interface (ki-workspace)
│   ├── database.py     # SQLite mit FTS5
│   ├── codacy_sync.py  # Codacy REST API Sync
│   ├── checks.py       # Release Readiness Checks
│   ├── github_api.py   # GitHub API Integration
│   └── crypto.py       # Verschlüsselung für API Keys
├── data/
│   └── licenses/       # License Templates
└── tests/
```

## CLI Befehle

```bash
ki-workspace ki-info              # IMMER ZUERST LESEN!
ki-workspace projects             # Alle Projekte
ki-workspace status <PROJECT>     # Projekt-Status
ki-workspace issues <PROJECT>     # Issues auflisten
ki-workspace sync <PROJECT>       # Von Codacy synchronisieren
ki-workspace check <PROJECT>      # Release Readiness Check
ki-workspace recommend-ignore     # KI empfiehlt Ignore
ki-workspace pending-ignores      # Offene KI-Empfehlungen
ki-workspace add-license          # Lizenz hinzufügen
```

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

### Wichtige Felder für KIs

In `issue_meta`:
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
