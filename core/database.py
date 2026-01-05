"""
Database Manager für KI-CLI Workspace.

SQLite mit FTS5 für Volltextsuche.
"""

import contextlib
import json
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Project:
    """Projekt-Datenmodell."""

    id: int | None = None
    name: str = ""
    path: str = ""
    git_remote: str = ""
    codacy_provider: str = "gh"  # gh, gl, bb
    codacy_org: str = ""
    github_owner: str = ""  # GitHub Owner/Org
    has_codacy: bool = True  # Hat Codacy-Integration
    is_archived: bool = False  # Archiviert (soft delete)
    phase_id: int | None = None  # Aktuelle Projekt-Phase (FK zu project_phases)
    last_sync: datetime | None = None
    # Cached Dashboard Stats (aktualisiert bei Sync/Check)
    cache_issues_critical: int = 0
    cache_issues_high: int = 0
    cache_issues_medium: int = 0
    cache_issues_low: int = 0
    cache_issues_fp: int = 0
    cache_release_passed: int = 0
    cache_release_total: int = 0
    cache_release_ready: bool = False
    cache_updated_at: datetime | None = None


@dataclass
class Issue:
    """Issue-Datenmodell."""

    id: int | None = None
    project_id: int = 0
    external_id: str = ""  # Codacy ID (UUID)
    codacy_result_id: str = ""  # Codacy itemSourceId für API-Aufrufe
    priority: str = ""  # Critical, High, Medium, Low
    status: str = "open"  # open, ignored, fixed
    scan_type: str = ""  # SAST, SCA, IaC, Secrets, CICD
    title: str = ""
    message: str = ""
    file_path: str = ""
    line_number: int = 0
    tool: str = ""
    rule: str = ""
    category: str = ""
    cve: str | None = None
    affected_version: str | None = None
    fixed_version: str | None = None
    # Unsere Erweiterungen
    is_false_positive: bool = False
    fp_reason: str | None = None
    fp_marked_at: datetime | None = None
    assessment: str | None = None  # Eigene Bewertung
    target_release: str | None = None  # Geplante Release-Version
    notes: str | None = None
    created_at: datetime | None = None
    synced_at: datetime | None = None
    # KI-Empfehlungen (lokal, wird nicht zu Codacy synchronisiert)
    ki_recommendation_category: str | None = (
        None  # accepted_use, false_positive, not_exploitable, test_code, external_code
    )
    ki_recommendation: str | None = None  # Begründung der KI
    ki_reviewed_by: str | None = None  # claude, codex, gemini
    ki_reviewed_at: datetime | None = None


@dataclass
class Handoff:
    """KI-Session Übergabe."""

    id: int | None = None
    project_id: int | None = None
    from_ai: str = ""  # claude, gemini, codex
    to_ai: str | None = None
    summary: str = ""
    open_tasks: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class Setting:
    """Einstellungs-Datenmodell."""

    key: str = ""
    value: str = ""
    is_encrypted: bool = False
    description: str = ""
    updated_at: datetime | None = None


@dataclass
class ProjectPhase:
    """Projekt-Phase (z.B. Development, Refactoring, Testing, Final)."""

    id: int | None = None
    name: str = ""  # Interner Name (development, refactoring, testing, final)
    display_name: str = ""  # Anzeigename (Entwicklung, Refactoring, Testing, Final)
    description: str = ""
    sort_order: int = 0
    is_default: bool = False  # Wird bei neuen Projekten automatisch gesetzt


@dataclass
class CheckMatrixEntry:
    """Eintrag in der Check-Matrix: Welche Checks in welcher Phase aktiv sind."""

    id: int | None = None
    phase_id: int = 0
    check_name: str = ""  # z.B. "LICENSE", "README", "Critical Issues"
    enabled: bool = True
    severity: str = "error"  # error (blocker), warning (empfohlen), info
    description: str = ""  # Optionale Beschreibung für UI


@dataclass
class FaqEntry:
    """FAQ-Eintrag für KI-Assistenten."""

    id: int | None = None
    key: str = ""  # Kurzer Schlüssel (z.B. "sync_process", "issue_workflow")
    category: str = ""  # Kategorie (process, command, workflow, concept)
    question: str = ""  # Frage/Titel
    answer: str = ""  # Kompakte Antwort (JSON-kompatibel)
    tags: list[str] = field(default_factory=list)  # Für Suche
    updated_at: datetime | None = None


@dataclass
class AiPrompt:
    """KI-Prompt-Template fuer Delegation an andere KIs."""

    id: int | None = None
    name: str = ""  # Eindeutiger Name (z.B. "code_review", "security_audit")
    description: str = ""  # Kurze Beschreibung
    prompt: str = ""  # Prompt-Template mit {variablen}
    default_ai: str = "codex"  # Default-KI (codex, gemini, claude)
    category: str = "general"  # Kategorie (review, security, testing, etc.)
    is_builtin: bool = False  # True = mitgeliefert, nicht loeschbar
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatabaseManager:
    """SQLite Database Manager mit FTS5 Support."""

    def __init__(self, db_path: str | Path | None = None):
        """
        Initialisiert den Database Manager.

        Args:
            db_path: Pfad zur Datenbank (default: ~/.ai-workspace/workspace.db)
        """
        if db_path is None:
            db_path = Path.home() / ".ai-workspace" / "workspace.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Erstellt eine neue Datenbankverbindung."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self) -> None:
        """Initialisiert das Datenbankschema."""
        with self._get_connection() as conn:
            # Projekte (normale Tabelle)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    path TEXT,
                    git_remote TEXT,
                    codacy_provider TEXT DEFAULT 'gh',
                    codacy_org TEXT,
                    github_owner TEXT,
                    has_codacy INTEGER DEFAULT 1,
                    is_archived INTEGER DEFAULT 0,
                    last_sync TIMESTAMP
                )
            """)

            # Migration: Neue Spalten hinzufügen falls nicht vorhanden
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN github_owner TEXT")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN has_codacy INTEGER DEFAULT 1")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN is_archived INTEGER DEFAULT 0")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN phase_id INTEGER")
            # Dashboard Cache Spalten
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN cache_issues_critical INTEGER DEFAULT 0"
                )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN cache_issues_high INTEGER DEFAULT 0")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN cache_issues_medium INTEGER DEFAULT 0"
                )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN cache_issues_low INTEGER DEFAULT 0")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN cache_issues_fp INTEGER DEFAULT 0")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN cache_release_passed INTEGER DEFAULT 0"
                )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN cache_release_total INTEGER DEFAULT 0"
                )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN cache_release_ready INTEGER DEFAULT 0"
                )
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN cache_updated_at TIMESTAMP")

            # Issues (FTS5 für Volltextsuche)
            # Prüfen ob Tabelle existiert
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='issues'"
            )
            if not cursor.fetchone():
                conn.execute("""
                    CREATE VIRTUAL TABLE issues USING fts5(
                        id,
                        project_id,
                        external_id,
                        priority,
                        status,
                        scan_type,
                        title,
                        message,
                        file_path,
                        line_number,
                        tool,
                        rule,
                        category,
                        cve,
                        affected_version,
                        fixed_version,
                        is_false_positive,
                        fp_reason,
                        fp_marked_at,
                        assessment,
                        target_release,
                        notes,
                        created_at,
                        synced_at,
                        content='',
                        tokenize='porter'
                    )
                """)

            # Issue-Metadaten (für nicht-FTS Felder)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS issue_meta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    external_id TEXT UNIQUE NOT NULL,
                    codacy_result_id TEXT,
                    priority TEXT,
                    status TEXT DEFAULT 'open',
                    scan_type TEXT,
                    title TEXT,
                    message TEXT,
                    file_path TEXT,
                    line_number INTEGER,
                    tool TEXT,
                    rule TEXT,
                    category TEXT,
                    cve TEXT,
                    affected_version TEXT,
                    fixed_version TEXT,
                    is_false_positive INTEGER DEFAULT 0,
                    fp_reason TEXT,
                    fp_marked_at TIMESTAMP,
                    assessment TEXT,
                    target_release TEXT,
                    notes TEXT,
                    created_at TIMESTAMP,
                    synced_at TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # FTS Index für Issues
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS issues_fts USING fts5(
                    title,
                    message,
                    file_path,
                    tool,
                    rule,
                    category,
                    fp_reason,
                    notes,
                    content='issue_meta',
                    content_rowid='id',
                    tokenize='porter'
                )
            """)

            # Trigger für FTS-Sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS issues_ai AFTER INSERT ON issue_meta BEGIN
                    INSERT INTO issues_fts(rowid, title, message, file_path, tool, rule, category, fp_reason, notes)
                    VALUES (new.id, new.title, new.message, new.file_path, new.tool, new.rule, new.category, new.fp_reason, new.notes);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS issues_ad AFTER DELETE ON issue_meta BEGIN
                    INSERT INTO issues_fts(issues_fts, rowid, title, message, file_path, tool, rule, category, fp_reason, notes)
                    VALUES ('delete', old.id, old.title, old.message, old.file_path, old.tool, old.rule, old.category, old.fp_reason, old.notes);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS issues_au AFTER UPDATE ON issue_meta BEGIN
                    INSERT INTO issues_fts(issues_fts, rowid, title, message, file_path, tool, rule, category, fp_reason, notes)
                    VALUES ('delete', old.id, old.title, old.message, old.file_path, old.tool, old.rule, old.category, old.fp_reason, old.notes);
                    INSERT INTO issues_fts(rowid, title, message, file_path, tool, rule, category, fp_reason, notes)
                    VALUES (new.id, new.title, new.message, new.file_path, new.tool, new.rule, new.category, new.fp_reason, new.notes);
                END
            """)

            # Migration: codacy_result_id hinzufügen falls nicht vorhanden
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE issue_meta ADD COLUMN codacy_result_id TEXT")

            # Migration: KI-Empfehlungsfelder hinzufügen
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE issue_meta ADD COLUMN ki_recommendation_category TEXT")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE issue_meta ADD COLUMN ki_recommendation TEXT")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE issue_meta ADD COLUMN ki_reviewed_by TEXT")
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE issue_meta ADD COLUMN ki_reviewed_at TIMESTAMP")

            # Handoffs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS handoffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER,
                    from_ai TEXT NOT NULL,
                    to_ai TEXT,
                    summary TEXT,
                    open_tasks TEXT,
                    context TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # Settings (für API-Keys, Konfiguration etc.)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    is_encrypted INTEGER DEFAULT 0,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Projekt-Phasen (flexibel konfigurierbar)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_phases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_default INTEGER DEFAULT 0
                )
            """)

            # Check-Matrix (welche Checks in welcher Phase)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS check_matrix (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase_id INTEGER NOT NULL,
                    check_name TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    severity TEXT DEFAULT 'error',
                    description TEXT,
                    FOREIGN KEY (phase_id) REFERENCES project_phases(id),
                    UNIQUE (phase_id, check_name)
                )
            """)

            # Migration: phase_id zu projects hinzufügen
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE projects ADD COLUMN phase_id INTEGER")

            # Default-Phasen initialisieren (falls leer)
            cursor = conn.execute("SELECT COUNT(*) FROM project_phases")
            if cursor.fetchone()[0] == 0:
                self._init_default_phases(conn)

            # Default-Settings initialisieren (falls leer)
            cursor = conn.execute("SELECT COUNT(*) FROM settings WHERE key LIKE 'project_%'")
            if cursor.fetchone()[0] == 0:
                self._init_default_settings(conn)

            # Migration: Initial-Phase hinzufügen falls nicht vorhanden
            cursor = conn.execute("SELECT id FROM project_phases WHERE name = 'initial'")
            if not cursor.fetchone():
                conn.execute(
                    """INSERT INTO project_phases
                       (name, display_name, description, sort_order, is_default)
                       VALUES ('initial', 'Initial', 'Projekt-Erstellung und Setup', 0, 0)"""
                )

            # Migration: Ruff-Check zu check_matrix hinzufügen falls nicht vorhanden
            cursor = conn.execute("SELECT COUNT(*) FROM check_matrix WHERE check_name = 'Ruff'")
            if cursor.fetchone()[0] == 0:
                # Phase-IDs holen
                cursor = conn.execute("SELECT id, name FROM project_phases")
                phase_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
                # Ruff für alle Phasen eintragen
                ruff_configs = [
                    ("development", True, "warning"),
                    ("refactoring", True, "error"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ]
                for phase_name, enabled, severity in ruff_configs:
                    phase_id = phase_ids.get(phase_name)
                    if phase_id:
                        conn.execute(
                            """INSERT INTO check_matrix
                               (phase_id, check_name, enabled, severity, description)
                               VALUES (?, 'Ruff', ?, ?, 'Keine Linting-Fehler (ruff check)')""",
                            (phase_id, 1 if enabled else 0, severity),
                        )

            # Migration: README Status zu check_matrix hinzufügen falls nicht vorhanden
            cursor = conn.execute(
                "SELECT COUNT(*) FROM check_matrix WHERE check_name = 'README Status'"
            )
            if cursor.fetchone()[0] == 0:
                cursor = conn.execute("SELECT id, name FROM project_phases")
                phase_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
                status_configs = [
                    ("development", True, "warning"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ]
                for phase_name, enabled, severity in status_configs:
                    phase_id = phase_ids.get(phase_name)
                    if phase_id:
                        conn.execute(
                            """INSERT INTO check_matrix
                               (phase_id, check_name, enabled, severity, description)
                               VALUES (?, 'README Status', ?, ?, 'README-Status synchron mit Phase')""",
                            (phase_id, 1 if enabled else 0, severity),
                        )

            # Migration: Gitignore Patterns zu check_matrix hinzufügen falls nicht vorhanden
            cursor = conn.execute(
                "SELECT COUNT(*) FROM check_matrix WHERE check_name = 'Gitignore Patterns'"
            )
            if cursor.fetchone()[0] == 0:
                cursor = conn.execute("SELECT id, name FROM project_phases")
                phase_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
                gitignore_configs = [
                    ("development", True, "warning"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ]
                for phase_name, enabled, severity in gitignore_configs:
                    phase_id = phase_ids.get(phase_name)
                    if phase_id:
                        conn.execute(
                            """INSERT INTO check_matrix
                               (phase_id, check_name, enabled, severity, description)
                               VALUES (?, 'Gitignore Patterns', ?, ?, 'Erforderliche Patterns in .gitignore')""",
                            (phase_id, 1 if enabled else 0, severity),
                        )

            # Migration: Gradio Share Check zu check_matrix hinzufuegen falls nicht vorhanden
            cursor = conn.execute(
                "SELECT COUNT(*) FROM check_matrix WHERE check_name = 'Gradio Share'"
            )
            if cursor.fetchone()[0] == 0:
                cursor = conn.execute("SELECT id, name FROM project_phases")
                phase_ids = {row["name"]: row["id"] for row in cursor.fetchall()}
                gradio_configs = [
                    ("initial", False, "info"),
                    ("development", True, "warning"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "error"),
                    ("final", True, "error"),
                ]
                for phase_name, enabled, severity in gradio_configs:
                    phase_id = phase_ids.get(phase_name)
                    if phase_id:
                        conn.execute(
                            """INSERT INTO check_matrix
                               (phase_id, check_name, enabled, severity, description)
                               VALUES (?, 'Gradio Share', ?, ?, 'Gradio share=False (kein Public Sharing)')""",
                            (phase_id, 1 if enabled else 0, severity),
                        )

            # Migration: Backup/Clone-Pfad Settings hinzufuegen falls nicht vorhanden
            cursor = conn.execute("SELECT COUNT(*) FROM settings WHERE key = 'backup_base_path'")
            if cursor.fetchone()[0] == 0:
                home = os.path.expanduser("~")
                default_backup_path = os.path.join(home, "projekte_backup")
                default_test_path = os.path.join(home, "projekte_test")
                conn.execute(
                    """INSERT INTO settings (key, value, is_encrypted, description)
                       VALUES ('backup_base_path', ?, 0, 'Basis-Pfad fuer Projekt-Backups')""",
                    (default_backup_path,),
                )
                conn.execute(
                    """INSERT INTO settings (key, value, is_encrypted, description)
                       VALUES ('test_clone_base_path', ?, 0, 'Basis-Pfad fuer Test-Clones')""",
                    (default_test_path,),
                )

            # KI-FAQ Tabelle
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ki_faq (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    tags TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # FTS5 Index für FAQ-Suche
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS ki_faq_fts USING fts5(
                    key,
                    category,
                    question,
                    answer,
                    tags,
                    content='ki_faq',
                    content_rowid='id',
                    tokenize='porter'
                )
            """)

            # Trigger für FTS-Sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS ki_faq_ai AFTER INSERT ON ki_faq BEGIN
                    INSERT INTO ki_faq_fts(rowid, key, category, question, answer, tags)
                    VALUES (new.id, new.key, new.category, new.question, new.answer, new.tags);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS ki_faq_ad AFTER DELETE ON ki_faq BEGIN
                    INSERT INTO ki_faq_fts(ki_faq_fts, rowid, key, category, question, answer, tags)
                    VALUES ('delete', old.id, old.key, old.category, old.question, old.answer, old.tags);
                END
            """)

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS ki_faq_au AFTER UPDATE ON ki_faq BEGIN
                    INSERT INTO ki_faq_fts(ki_faq_fts, rowid, key, category, question, answer, tags)
                    VALUES ('delete', old.id, old.key, old.category, old.question, old.answer, old.tags);
                    INSERT INTO ki_faq_fts(rowid, key, category, question, answer, tags)
                    VALUES (new.id, new.key, new.category, new.question, new.answer, new.tags);
                END
            """)

            # Default-FAQ initialisieren (falls leer)
            cursor = conn.execute("SELECT COUNT(*) FROM ki_faq")
            if cursor.fetchone()[0] == 0:
                self._init_default_faq(conn)

            # AI Prompts Tabelle (fuer KI-Delegation)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL,
                    default_ai TEXT NOT NULL DEFAULT 'codex',
                    category TEXT NOT NULL DEFAULT 'general',
                    is_builtin INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Default-Prompts initialisieren (falls leer)
            cursor = conn.execute("SELECT COUNT(*) FROM ai_prompts")
            if cursor.fetchone()[0] == 0:
                self._init_default_prompts(conn)

            conn.commit()

    def _init_default_phases(self, conn: sqlite3.Connection) -> None:
        """Initialisiert die Default-Phasen und Check-Matrix."""
        # Phasen definieren
        phases = [
            ("development", "Entwicklung", "Aktive Feature-Entwicklung", 1, True),
            ("refactoring", "Refactoring", "Code-Verbesserung und Aufräumen", 2, False),
            ("testing", "Testing", "Fokus auf Testabdeckung und QA", 3, False),
            ("final", "Final", "Release-Vorbereitung, alle Checks", 4, False),
        ]

        for name, display, desc, order, is_default in phases:
            conn.execute(
                """
                INSERT INTO project_phases (name, display_name, description, sort_order, is_default)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, display, desc, order, 1 if is_default else 0),
            )

        # Phase-IDs holen
        cursor = conn.execute("SELECT id, name FROM project_phases")
        phase_ids = {row["name"]: row["id"] for row in cursor.fetchall()}

        # Check-Matrix definieren
        # Format: (check_name, description, [(phase, enabled, severity), ...])
        checks = [
            (
                "LICENSE",
                "LICENSE-Datei vorhanden",
                [
                    ("development", True, "error"),
                    ("refactoring", True, "error"),
                    ("testing", True, "error"),
                    ("final", True, "error"),
                ],
            ),
            (
                "README",
                "README mit Mindestinhalt",
                [
                    ("development", True, "error"),
                    ("refactoring", True, "error"),
                    ("testing", True, "error"),
                    ("final", True, "error"),
                ],
            ),
            (
                "CHANGELOG",
                "CHANGELOG vorhanden",
                [
                    ("development", False, "info"),
                    ("refactoring", False, "info"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ],
            ),
            (
                "Critical Issues",
                "Keine offenen Critical Issues",
                [
                    ("development", True, "error"),
                    ("refactoring", True, "error"),
                    ("testing", True, "error"),
                    ("final", True, "error"),
                ],
            ),
            (
                "High Issues",
                "Keine offenen High Issues",
                [
                    ("development", False, "info"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ],
            ),
            (
                "Radon Complexity",
                "Code-Komplexität akzeptabel",
                [
                    ("development", False, "info"),
                    ("refactoring", True, "error"),
                    ("testing", True, "warning"),
                    ("final", True, "warning"),
                ],
            ),
            (
                "Ruff",
                "Keine Linting-Fehler (ruff check)",
                [
                    ("development", True, "warning"),
                    ("refactoring", True, "error"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ],
            ),
            (
                "Tests",
                "Tests vorhanden und bestanden",
                [
                    ("development", True, "warning"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "error"),
                    ("final", True, "error"),
                ],
            ),
            (
                "Git Status",
                "Keine uncommitted Änderungen",
                [
                    ("development", False, "info"),
                    ("refactoring", False, "info"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ],
            ),
            (
                "README Status",
                "README-Status synchron mit Phase",
                [
                    ("development", True, "warning"),
                    ("refactoring", True, "warning"),
                    ("testing", True, "warning"),
                    ("final", True, "error"),
                ],
            ),
        ]

        for check_name, check_desc, phase_configs in checks:
            for phase_name, enabled, severity in phase_configs:
                phase_id = phase_ids.get(phase_name)
                if phase_id:
                    conn.execute(
                        """
                        INSERT INTO check_matrix (phase_id, check_name, enabled, severity, description)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (phase_id, check_name, 1 if enabled else 0, severity, check_desc),
                    )

    def _init_default_settings(self, conn: sqlite3.Connection) -> None:
        """Initialisiert die Default-Settings für Projekt-Verwaltung."""
        import os

        # Standard-Pfade basierend auf Home-Verzeichnis
        home = os.path.expanduser("~")
        default_projects_path = os.path.join(home, "projekte")
        default_archive_path = os.path.join(home, "projekte", "archiv")

        default_backup_path = os.path.join(home, "projekte_backup")
        default_test_path = os.path.join(home, "projekte_test")

        settings = [
            ("project_base_path", default_projects_path, "Basis-Pfad für neue Projekte"),
            ("project_archive_path", default_archive_path, "Pfad für archivierte Projekte"),
            ("backup_base_path", default_backup_path, "Basis-Pfad für Projekt-Backups"),
            ("test_clone_base_path", default_test_path, "Basis-Pfad für Test-Clones"),
            ("github_org", "goettemar", "GitHub Organisation/Username"),
            ("github_provider", "gh", "Git Provider (gh=GitHub, gl=GitLab, bb=BitBucket)"),
            ("default_license", "polyform-nc", "Standard-Lizenz für neue Projekte"),
            ("default_gitignore", "python", "Standard .gitignore Template"),
            (
                "gitignore_required_patterns",
                '["/temp", "*.log", ".env.local", ".env", ".venv", "*.pem", "*.key", "*.db", "state.json", "credentials.json", "*_cache.json"]',
                "JSON-Array mit Patterns die in .gitignore sein muessen",
            ),
            (
                "openrouter_model",
                "x-ai/grok-3-mini-beta",
                "OpenRouter Model fuer AI Commit Messages",
            ),
        ]

        for key, value, desc in settings:
            conn.execute(
                """INSERT OR IGNORE INTO settings (key, value, is_encrypted, description)
                   VALUES (?, ?, 0, ?)""",
                (key, value, desc),
            )

    # === Project CRUD ===

    def create_project(self, project: Project) -> Project:
        """Erstellt ein neues Projekt."""
        with self._get_connection() as conn:
            # Default-Phase holen wenn nicht gesetzt
            if project.phase_id is None:
                cursor = conn.execute("SELECT id FROM project_phases WHERE is_default = 1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    project.phase_id = row["id"]

            cursor = conn.execute(
                """
                INSERT INTO projects (name, path, git_remote, codacy_provider, codacy_org,
                                      github_owner, has_codacy, is_archived, phase_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.name,
                    project.path,
                    project.git_remote,
                    project.codacy_provider,
                    project.codacy_org,
                    project.github_owner,
                    1 if project.has_codacy else 0,
                    1 if project.is_archived else 0,
                    project.phase_id,
                ),
            )
            project.id = cursor.lastrowid
            conn.commit()
        return project

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        """Konvertiert eine DB-Row zu einem Project-Objekt."""
        data = dict(row)
        # Boolean-Felder konvertieren
        data["has_codacy"] = bool(data.get("has_codacy", 1))
        data["is_archived"] = bool(data.get("is_archived", 0))
        data["cache_release_ready"] = bool(data.get("cache_release_ready", 0))
        # Cache-Felder mit Defaults
        data.setdefault("cache_issues_critical", 0)
        data.setdefault("cache_issues_high", 0)
        data.setdefault("cache_issues_medium", 0)
        data.setdefault("cache_issues_low", 0)
        data.setdefault("cache_issues_fp", 0)
        data.setdefault("cache_release_passed", 0)
        data.setdefault("cache_release_total", 0)
        return Project(**data)

    def get_project(self, project_id: int) -> Project | None:
        """Lädt ein Projekt nach ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_project(row)
        return None

    def get_project_by_name(self, name: str) -> Project | None:
        """Lädt ein Projekt nach Name."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM projects WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_project(row)
        return None

    def get_all_projects(self, include_archived: bool = False) -> list[Project]:
        """
        Lädt alle Projekte.

        Args:
            include_archived: Auch archivierte Projekte einbeziehen
        """
        with self._get_connection() as conn:
            if include_archived:
                cursor = conn.execute("SELECT * FROM projects ORDER BY is_archived, name")
            else:
                cursor = conn.execute("SELECT * FROM projects WHERE is_archived = 0 ORDER BY name")
            return [self._row_to_project(row) for row in cursor.fetchall()]

    def update_project_sync_time(self, project_id: int) -> None:
        """Aktualisiert den letzten Sync-Zeitpunkt."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE projects SET last_sync = ? WHERE id = ?",
                (datetime.now().isoformat(), project_id),
            )
            conn.commit()

    def update_issue_details_by_result_id(
        self,
        project_id: int,
        codacy_result_id: str,
        file_path: str,
        line_number: int,
        tool: str,
        rule: str,
    ) -> bool:
        """
        Update issue details (file_path, line_number, tool, rule) by codacy_result_id.

        Used for deduplication: when a Quality issue matches an existing SRM issue,
        we update the SRM issue with the additional details instead of creating a duplicate.

        Returns:
            True if an issue was updated, False otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE issue_meta SET
                    file_path = COALESCE(NULLIF(?, ''), file_path),
                    line_number = CASE WHEN ? > 0 THEN ? ELSE line_number END,
                    tool = COALESCE(NULLIF(?, ''), tool),
                    rule = COALESCE(NULLIF(?, ''), rule),
                    synced_at = ?
                WHERE project_id = ? AND codacy_result_id = ?
                """,
                (
                    file_path,
                    line_number,
                    line_number,
                    tool,
                    rule,
                    datetime.now().isoformat(),
                    project_id,
                    codacy_result_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_issues_by_external_ids(self, project_id: int, external_ids: list[str]) -> int:
        """
        Delete issues by their external IDs (Codacy UUIDs).

        Used during sync to remove issues that have been closed in Codacy.

        Returns:
            Number of deleted issues.
        """
        if not external_ids:
            return 0

        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(external_ids))
            cursor = conn.execute(
                f"""
                DELETE FROM issue_meta
                WHERE project_id = ? AND external_id IN ({placeholders})
                """,
                [project_id, *external_ids],
            )
            conn.commit()
            return cursor.rowcount

    def clean_pending_ignores_by_external_ids(
        self, project_id: int, external_ids: list[str]
    ) -> int:
        """
        Clear KI recommendations for issues that have been closed in Codacy.

        This removes the pending ignore status so they don't show up in
        the Pending Ignores tab anymore.

        Returns:
            Number of cleaned recommendations.
        """
        if not external_ids:
            return 0

        with self._get_connection() as conn:
            placeholders = ",".join("?" * len(external_ids))
            cursor = conn.execute(
                f"""
                UPDATE issue_meta SET
                    ki_recommendation_category = NULL,
                    ki_recommendation = NULL,
                    ki_reviewed_by = NULL,
                    ki_reviewed_at = NULL
                WHERE project_id = ? AND external_id IN ({placeholders})
                    AND ki_recommendation IS NOT NULL
                """,
                [project_id, *external_ids],
            )
            conn.commit()
            return cursor.rowcount

    def update_project_cache(self, project_id: int) -> dict[str, int]:
        """
        Aktualisiert den Dashboard-Cache für ein Projekt.

        Zählt Issues nach Priority und False Positives.

        Returns:
            Dict mit den gecachten Werten
        """
        with self._get_connection() as conn:
            # Issues nach Priority zählen (nur offene, nicht-FP)
            cursor = conn.execute(
                """
                SELECT priority, COUNT(*) as cnt
                FROM issue_meta
                WHERE project_id = ? AND status = 'open' AND is_false_positive = 0
                GROUP BY priority
                """,
                (project_id,),
            )
            counts = {row["priority"]: row["cnt"] for row in cursor.fetchall()}

            # False Positives zählen (inkl. KI-Empfehlungen)
            cursor = conn.execute(
                """
                SELECT COUNT(*) FROM issue_meta
                WHERE project_id = ? AND (is_false_positive = 1 OR ki_recommendation IS NOT NULL)
                """,
                (project_id,),
            )
            fp_count = cursor.fetchone()[0]

            cache = {
                "cache_issues_critical": counts.get("Critical", 0),
                "cache_issues_high": counts.get("High", 0),
                "cache_issues_medium": counts.get("Medium", 0),
                "cache_issues_low": counts.get("Low", 0),
                "cache_issues_fp": fp_count,
            }

            # Cache speichern
            conn.execute(
                """
                UPDATE projects SET
                    cache_issues_critical = ?,
                    cache_issues_high = ?,
                    cache_issues_medium = ?,
                    cache_issues_low = ?,
                    cache_issues_fp = ?,
                    cache_updated_at = ?
                WHERE id = ?
                """,
                (
                    cache["cache_issues_critical"],
                    cache["cache_issues_high"],
                    cache["cache_issues_medium"],
                    cache["cache_issues_low"],
                    cache["cache_issues_fp"],
                    datetime.now().isoformat(),
                    project_id,
                ),
            )
            conn.commit()

            return cache

    def update_release_cache(self, project_id: int, passed: int, total: int, ready: bool) -> None:
        """
        Aktualisiert den Release-Check Cache für ein Projekt.

        Args:
            project_id: Projekt-ID
            passed: Anzahl bestandener Checks
            total: Gesamtzahl Checks
            ready: True wenn alle Checks bestanden
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE projects SET
                    cache_release_passed = ?,
                    cache_release_total = ?,
                    cache_release_ready = ?,
                    cache_updated_at = ?
                WHERE id = ?
                """,
                (passed, total, 1 if ready else 0, datetime.now().isoformat(), project_id),
            )
            conn.commit()

    # === Issue CRUD ===

    def upsert_issue(self, issue: Issue) -> Issue:
        """Erstellt oder aktualisiert ein Issue."""
        with self._get_connection() as conn:
            # Prüfen ob Issue existiert
            cursor = conn.execute(
                "SELECT id FROM issue_meta WHERE external_id = ?", (issue.external_id,)
            )
            existing = cursor.fetchone()

            now = datetime.now().isoformat()

            if existing:
                # Update - FP-Felder werden aktualisiert wenn von Codacy gesetzt
                if issue.is_false_positive:
                    # Von Codacy als Ignored markiert - FP-Status übernehmen
                    conn.execute(
                        """
                        UPDATE issue_meta SET
                            codacy_result_id = COALESCE(?, codacy_result_id),
                            priority = ?, status = ?, scan_type = ?, title = ?,
                            message = ?, file_path = ?, line_number = ?, tool = ?,
                            rule = ?, category = ?, cve = ?, affected_version = ?,
                            fixed_version = ?, synced_at = ?,
                            is_false_positive = 1, fp_reason = COALESCE(fp_reason, ?)
                        WHERE external_id = ?
                        """,
                        (
                            issue.codacy_result_id,
                            issue.priority,
                            issue.status,
                            issue.scan_type,
                            issue.title,
                            issue.message,
                            issue.file_path,
                            issue.line_number,
                            issue.tool,
                            issue.rule,
                            issue.category,
                            issue.cve,
                            issue.affected_version,
                            issue.fixed_version,
                            now,
                            issue.fp_reason,
                            issue.external_id,
                        ),
                    )
                else:
                    # Normale Update ohne FP-Felder zu überschreiben
                    conn.execute(
                        """
                        UPDATE issue_meta SET
                            codacy_result_id = COALESCE(?, codacy_result_id),
                            priority = ?, status = ?, scan_type = ?, title = ?,
                            message = ?, file_path = ?, line_number = ?, tool = ?,
                            rule = ?, category = ?, cve = ?, affected_version = ?,
                            fixed_version = ?, synced_at = ?
                        WHERE external_id = ?
                        """,
                        (
                            issue.codacy_result_id,
                            issue.priority,
                            issue.status,
                            issue.scan_type,
                            issue.title,
                            issue.message,
                            issue.file_path,
                            issue.line_number,
                            issue.tool,
                            issue.rule,
                            issue.category,
                            issue.cve,
                            issue.affected_version,
                            issue.fixed_version,
                            now,
                            issue.external_id,
                        ),
                    )
                issue.id = existing["id"]
            else:
                # Insert - inkl. FP-Felder für Codacy Ignored Items
                cursor = conn.execute(
                    """
                    INSERT INTO issue_meta (
                        project_id, external_id, codacy_result_id,
                        priority, status, scan_type,
                        title, message, file_path, line_number, tool, rule,
                        category, cve, affected_version, fixed_version,
                        is_false_positive, fp_reason,
                        created_at, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue.project_id,
                        issue.external_id,
                        issue.codacy_result_id,
                        issue.priority,
                        issue.status,
                        issue.scan_type,
                        issue.title,
                        issue.message,
                        issue.file_path,
                        issue.line_number,
                        issue.tool,
                        issue.rule,
                        issue.category,
                        issue.cve,
                        issue.affected_version,
                        issue.fixed_version,
                        1 if issue.is_false_positive else 0,
                        issue.fp_reason,
                        now,
                        now,
                    ),
                )
                issue.id = cursor.lastrowid

            conn.commit()
        return issue

    def get_issues(
        self,
        project_id: int | None = None,
        priority: str | None = None,
        status: str | None = None,
        scan_type: str | None = None,
        is_false_positive: bool | None = None,
        search: str | None = None,
    ) -> list[Issue]:
        """
        Lädt Issues mit optionalen Filtern.

        Args:
            project_id: Filter nach Projekt
            priority: Filter nach Priorität (Critical, High, Medium, Low)
            status: Filter nach Status (open, ignored, fixed)
            scan_type: Filter nach Scan-Typ (SAST, SCA, IaC, etc.)
            is_false_positive: Filter nach False Positive Status
            search: Volltextsuche
        """
        with self._get_connection() as conn:
            if search:
                # FTS5 Suche
                query = """
                    SELECT m.* FROM issue_meta m
                    JOIN issues_fts f ON m.id = f.rowid
                    WHERE issues_fts MATCH ?
                """
                params: list[Any] = [search]
            else:
                query = "SELECT * FROM issue_meta m WHERE 1=1"
                params = []

            if project_id is not None:
                query += " AND m.project_id = ?"
                params.append(project_id)
            if priority:
                query += " AND m.priority = ?"
                params.append(priority)
            if status:
                query += " AND m.status = ?"
                params.append(status)
            if scan_type:
                query += " AND m.scan_type = ?"
                params.append(scan_type)
            if is_false_positive is not None:
                query += " AND m.is_false_positive = ?"
                params.append(1 if is_false_positive else 0)

            query += " ORDER BY m.priority, m.created_at DESC"

            cursor = conn.execute(query, params)
            issues = []
            for row in cursor.fetchall():
                data = dict(row)
                data["is_false_positive"] = bool(data.get("is_false_positive"))
                issues.append(Issue(**data))
            return issues

    def mark_false_positive(
        self, issue_id: int, reason: str, assessment: str | None = None
    ) -> None:
        """Markiert ein Issue als False Positive."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE issue_meta SET
                    is_false_positive = 1,
                    fp_reason = ?,
                    fp_marked_at = ?,
                    assessment = ?
                WHERE id = ?
                """,
                (reason, datetime.now().isoformat(), assessment, issue_id),
            )
            conn.commit()

    def set_target_release(self, issue_id: int, release: str) -> None:
        """Setzt die Ziel-Release-Version für ein Issue."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE issue_meta SET target_release = ? WHERE id = ?",
                (release, issue_id),
            )
            conn.commit()

    def recommend_ignore(
        self,
        issue_id: int,
        category: str,
        reason: str,
        reviewer: str,
    ) -> None:
        """
        KI empfiehlt ein Issue zum Ignorieren.

        Args:
            issue_id: Issue ID
            category: Kategorie (accepted_use, false_positive, not_exploitable, test_code, external_code)
            reason: Begründung
            reviewer: KI-Name (claude, codex, gemini)
        """
        valid_categories = {
            "accepted_use",
            "false_positive",
            "not_exploitable",
            "test_code",
            "external_code",
        }
        if category not in valid_categories:
            raise ValueError(f"Ungültige Kategorie: {category}. Erlaubt: {valid_categories}")

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE issue_meta SET
                    ki_recommendation_category = ?,
                    ki_recommendation = ?,
                    ki_reviewed_by = ?,
                    ki_reviewed_at = ?
                WHERE id = ?
                """,
                (category, reason, reviewer, datetime.now().isoformat(), issue_id),
            )
            conn.commit()

    def get_pending_ignores(self, project_id: int | None = None) -> list[Issue]:
        """
        Lädt Issues die eine KI-Empfehlung haben, aber noch nicht in Codacy ignoriert sind.

        Args:
            project_id: Optional - Filter nach Projekt
        """
        with self._get_connection() as conn:
            query = """
                SELECT * FROM issue_meta
                WHERE ki_recommendation IS NOT NULL
                AND is_false_positive = 0
            """
            params: list = []

            if project_id is not None:
                query += " AND project_id = ?"
                params.append(project_id)

            query += " ORDER BY ki_reviewed_at DESC"

            cursor = conn.execute(query, params)
            issues = []
            for row in cursor.fetchall():
                data = dict(row)
                data["is_false_positive"] = bool(data.get("is_false_positive"))
                issues.append(Issue(**data))
            return issues

    def get_issue_stats(self, project_id: int | None = None) -> dict[str, Any]:
        """Gibt Statistiken über Issues zurück."""
        with self._get_connection() as conn:
            where = "WHERE project_id = ?" if project_id else ""
            params = (project_id,) if project_id else ()

            stats = {
                "total": 0,
                "by_priority": {},
                "by_status": {},
                "by_scan_type": {},
                "false_positives": 0,
            }

            # Total - where ist intern aufgebaut (project_id), nicht User-Input
            cursor = conn.execute(f"SELECT COUNT(*) FROM issue_meta {where}", params)  # nosec B608 # nosemgrep
            stats["total"] = cursor.fetchone()[0]

            # By Priority
            cursor = conn.execute(
                f"SELECT priority, COUNT(*) FROM issue_meta {where} GROUP BY priority",
                params,  # nosec B608 # nosemgrep
            )
            stats["by_priority"] = {row[0]: row[1] for row in cursor.fetchall()}

            # By Status
            cursor = conn.execute(
                f"SELECT status, COUNT(*) FROM issue_meta {where} GROUP BY status",
                params,  # nosec B608 # nosemgrep
            )
            stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

            # By Scan Type
            cursor = conn.execute(
                f"SELECT scan_type, COUNT(*) FROM issue_meta {where} GROUP BY scan_type",
                params,  # nosec B608 # nosemgrep
            )
            stats["by_scan_type"] = {row[0]: row[1] for row in cursor.fetchall()}

            # False Positives
            fp_where = f"{where} AND" if where else "WHERE"
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM issue_meta {fp_where} is_false_positive = 1",
                params,  # nosec B608 # nosemgrep
            )
            stats["false_positives"] = cursor.fetchone()[0]

            return stats

    # === Handoff CRUD ===

    def create_handoff(self, handoff: Handoff) -> Handoff:
        """Erstellt einen neuen Handoff-Eintrag."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO handoffs (project_id, from_ai, to_ai, summary, open_tasks, context)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff.project_id,
                    handoff.from_ai,
                    handoff.to_ai,
                    handoff.summary,
                    json.dumps(handoff.open_tasks),
                    json.dumps(handoff.context),
                ),
            )
            handoff.id = cursor.lastrowid
            handoff.created_at = datetime.now()
            conn.commit()
        return handoff

    def get_latest_handoff(self, project_id: int | None = None) -> Handoff | None:
        """Lädt den letzten Handoff."""
        with self._get_connection() as conn:
            if project_id:
                cursor = conn.execute(
                    "SELECT * FROM handoffs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                    (project_id,),
                )
            else:
                cursor = conn.execute("SELECT * FROM handoffs ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                data = dict(row)
                data["open_tasks"] = json.loads(data.get("open_tasks") or "[]")
                data["context"] = json.loads(data.get("context") or "{}")
                return Handoff(**data)
        return None

    # === Settings CRUD ===

    def set_setting(
        self,
        key: str,
        value: str,
        encrypt: bool = False,
        description: str = "",
    ) -> None:
        """
        Speichert eine Einstellung.

        Args:
            key: Einstellungsschlüssel
            value: Wert (wird bei encrypt=True verschlüsselt)
            encrypt: Ob der Wert verschlüsselt werden soll
            description: Beschreibung der Einstellung
        """
        from core.crypto import get_crypto

        stored_value = value
        if encrypt and value:
            stored_value = get_crypto().encrypt(value)

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, is_encrypted, description, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    is_encrypted = excluded.is_encrypted,
                    description = COALESCE(excluded.description, settings.description),
                    updated_at = excluded.updated_at
                """,
                (key, stored_value, 1 if encrypt else 0, description, datetime.now().isoformat()),
            )
            conn.commit()

    def get_setting(self, key: str, decrypt: bool = True) -> str | None:
        """
        Lädt eine Einstellung.

        Args:
            key: Einstellungsschlüssel
            decrypt: Ob verschlüsselte Werte entschlüsselt werden sollen

        Returns:
            Wert der Einstellung oder None
        """
        from core.crypto import get_crypto

        with self._get_connection() as conn:
            cursor = conn.execute("SELECT value, is_encrypted FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                value, is_encrypted = row["value"], row["is_encrypted"]
                if is_encrypted and decrypt and value:
                    return get_crypto().decrypt(value)
                return value
        return None

    def get_all_settings(self) -> list[Setting]:
        """Lädt alle Einstellungen (Werte bleiben verschlüsselt)."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM settings ORDER BY key")
            settings = []
            for row in cursor.fetchall():
                settings.append(
                    Setting(
                        key=row["key"],
                        value=row["value"],
                        is_encrypted=bool(row["is_encrypted"]),
                        description=row["description"] or "",
                        updated_at=row["updated_at"],
                    )
                )
            return settings

    def delete_setting(self, key: str) -> None:
        """Löscht eine Einstellung."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()

    # === Project erweitert ===

    def update_project(self, project: Project) -> None:
        """Aktualisiert ein bestehendes Projekt."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE projects SET
                    name = ?, path = ?, git_remote = ?,
                    codacy_provider = ?, codacy_org = ?,
                    github_owner = ?, has_codacy = ?, is_archived = ?, phase_id = ?
                WHERE id = ?
                """,
                (
                    project.name,
                    project.path,
                    project.git_remote,
                    project.codacy_provider,
                    project.codacy_org,
                    project.github_owner,
                    1 if project.has_codacy else 0,
                    1 if project.is_archived else 0,
                    project.phase_id,
                    project.id,
                ),
            )
            conn.commit()

    def archive_project(self, project_id: int) -> None:
        """Archiviert ein Projekt (soft delete)."""
        with self._get_connection() as conn:
            conn.execute("UPDATE projects SET is_archived = 1 WHERE id = ?", (project_id,))
            conn.commit()

    def unarchive_project(self, project_id: int) -> None:
        """Stellt ein archiviertes Projekt wieder her."""
        with self._get_connection() as conn:
            conn.execute("UPDATE projects SET is_archived = 0 WHERE id = ?", (project_id,))
            conn.commit()

    def set_project_phase(
        self, project_id: int, phase_id: int, update_readme: bool = True
    ) -> tuple[bool, str]:
        """
        Setzt die Phase eines Projekts und aktualisiert optional die README.

        Args:
            project_id: Projekt-ID
            phase_id: Neue Phase-ID
            update_readme: Wenn True, wird der README-Status automatisch aktualisiert

        Returns:
            (success, message)
        """
        # Phase holen
        phase = self.get_phase(phase_id)
        if not phase:
            return False, f"Phase {phase_id} nicht gefunden"

        # Projekt holen
        project = self.get_project(project_id)
        if not project:
            return False, f"Projekt {project_id} nicht gefunden"

        # Phase in DB setzen
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE projects SET phase_id = ? WHERE id = ?",
                (phase_id, project_id),
            )
            conn.commit()

        # README aktualisieren wenn gewünscht und Pfad vorhanden
        readme_msg = ""
        if update_readme and project.path:
            from core.project_tools import update_readme_status

            success, readme_msg = update_readme_status(project.path, phase.display_name)
            readme_msg = f" (README: {readme_msg})" if not success else " + README aktualisiert"

        return True, f"Phase auf '{phase.display_name}' gesetzt{readme_msg}"

    def delete_project(self, project_id: int) -> None:
        """Löscht ein Projekt und alle zugehörigen Issues (permanent)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM issue_meta WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM handoffs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    # === Project Phases CRUD ===

    def get_all_phases(self) -> list[ProjectPhase]:
        """Lädt alle Projekt-Phasen sortiert nach sort_order."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM project_phases ORDER BY sort_order")
            phases = []
            for row in cursor.fetchall():
                phases.append(
                    ProjectPhase(
                        id=row["id"],
                        name=row["name"],
                        display_name=row["display_name"],
                        description=row["description"] or "",
                        sort_order=row["sort_order"],
                        is_default=bool(row["is_default"]),
                    )
                )
            return phases

    def get_phase(self, phase_id: int) -> ProjectPhase | None:
        """Lädt eine Phase nach ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM project_phases WHERE id = ?", (phase_id,))
            row = cursor.fetchone()
            if row:
                return ProjectPhase(
                    id=row["id"],
                    name=row["name"],
                    display_name=row["display_name"],
                    description=row["description"] or "",
                    sort_order=row["sort_order"],
                    is_default=bool(row["is_default"]),
                )
        return None

    def get_phase_by_name(self, name: str) -> ProjectPhase | None:
        """Lädt eine Phase nach Name."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM project_phases WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return ProjectPhase(
                    id=row["id"],
                    name=row["name"],
                    display_name=row["display_name"],
                    description=row["description"] or "",
                    sort_order=row["sort_order"],
                    is_default=bool(row["is_default"]),
                )
        return None

    # === Check Matrix CRUD ===

    def get_check_matrix_for_phase(self, phase_id: int) -> list[CheckMatrixEntry]:
        """Lädt alle Check-Einträge für eine Phase."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM check_matrix WHERE phase_id = ? ORDER BY check_name",
                (phase_id,),
            )
            entries = []
            for row in cursor.fetchall():
                entries.append(
                    CheckMatrixEntry(
                        id=row["id"],
                        phase_id=row["phase_id"],
                        check_name=row["check_name"],
                        enabled=bool(row["enabled"]),
                        severity=row["severity"],
                        description=row["description"] or "",
                    )
                )
            return entries

    def get_full_check_matrix(self) -> dict[str, list[CheckMatrixEntry]]:
        """Lädt die komplette Check-Matrix gruppiert nach Phase."""
        phases = self.get_all_phases()
        matrix = {}
        for phase in phases:
            matrix[phase.name] = self.get_check_matrix_for_phase(phase.id)
        return matrix

    def update_check_matrix_entry(
        self, phase_id: int, check_name: str, enabled: bool, severity: str
    ) -> None:
        """Aktualisiert oder erstellt einen Eintrag in der Check-Matrix."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO check_matrix (phase_id, check_name, enabled, severity)
                VALUES (?, ?, ?, ?)
                """,
                (phase_id, check_name, 1 if enabled else 0, severity),
            )
            conn.commit()

    def get_enabled_checks_for_phase(self, phase_id: int) -> dict[str, str]:
        """
        Gibt aktivierte Checks mit Severity für eine Phase zurück.

        Returns:
            Dict {check_name: severity} für aktivierte Checks
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT check_name, severity FROM check_matrix WHERE phase_id = ? AND enabled = 1",
                (phase_id,),
            )
            return {row["check_name"]: row["severity"] for row in cursor.fetchall()}

    # === KI-FAQ CRUD ===

    def _init_default_faq(self, conn: sqlite3.Connection) -> None:
        """Initialisiert die Default-FAQ-Einträge für KI-Assistenten."""
        faqs = [
            # Prozesse
            (
                "sync_process",
                "process",
                "Was passiert bei ki-workspace sync?",
                "1. Codacy API aufrufen (SRM+Quality Issues), 2. issue_meta upsert, 3. FTS-Index aktualisieren, 4. Cache updaten, 5. Sync-Zeit speichern. FP-Status von Codacy wird übernommen.",
                "sync,codacy,api,issues",
            ),
            (
                "init_process",
                "process",
                "Was passiert bei ki-workspace init?",
                "1. Ordner erstellen unter project_base_path, 2. Struktur anlegen (src/,tests/,README,LICENSE,CHANGELOG,pyproject.toml,.gitignore), 3. git init, 4. gh repo create --public, 5. Initial commit+push, 6. DB-Eintrag mit Phase=Initial",
                "init,projekt,github,struktur",
            ),
            (
                "archive_process",
                "process",
                "Was passiert bei ki-workspace archive?",
                "1. Ordner nach project_archive_path verschieben, 2. DB: is_archived=1. GitHub Repo muss MANUELL gelöscht werden (2FA erforderlich) - Link wird angezeigt.",
                "archive,löschen,github,2fa",
            ),
            (
                "github_2fa_limitation",
                "concept",
                "Warum kann CLI keine GitHub Repos löschen?",
                "GitHub CLI (gh) kann mit 2FA keine Repos löschen - 2FA-Code wird interaktiv abgefragt. Repos müssen manuell über GitHub Settings gelöscht werden.",
                "github,2fa,delete,limitation",
            ),
            (
                "check_process",
                "process",
                "Wie funktioniert der Release-Check?",
                "Prüft: LICENSE, README (min 50 Zeichen), CHANGELOG, Critical/High Issues, Radon Complexity (optional), Tests (pytest), Git Status. Checks sind phasenabhängig (check_matrix Tabelle).",
                "check,release,quality",
            ),
            # Workflows
            (
                "issue_review_workflow",
                "workflow",
                "Wie reviewe ich Issues als KI?",
                "1. ki-workspace ki-info lesen, 2. issues --json laden, 3. Prüfen: ki_recommendation gesetzt? → SKIP, 4. Code-Kontext analysieren, 5. recommend-ignore mit Kategorie+Begründung, 6. User informieren: 'Bitte in Codacy als Ignored markieren'",
                "review,issues,workflow,ki",
            ),
            (
                "fp_categories",
                "workflow",
                "Welche Ignore-Kategorien gibt es?",
                "accepted_use (bewusst so), false_positive (Tool-Fehlalarm), not_exploitable (theoretisch, praktisch nicht), test_code (nur Tests), external_code (Fremdcode/Vendor)",
                "ignore,kategorie,fp,false_positive",
            ),
            # Befehle
            (
                "cmd_status",
                "command",
                "Was zeigt 'ki-workspace status' an?",
                "Projekt-Infos: Pfad, Git Remote, Codacy-Config, Issue-Counts (Critical/High/Medium/Low/FP), Release-Check Status, letzter Sync. --json für maschinenlesbar.",
                "status,befehl,cli",
            ),
            (
                "cmd_issues",
                "command",
                "Wie liste ich Issues?",
                "ki-workspace issues <PROJECT> [--priority Critical|High|Medium|Low] [--limit N] [--json]. Zeigt nur offene, nicht-FP Issues. Für alle: direkt DB abfragen.",
                "issues,befehl,cli,filter",
            ),
            (
                "cmd_recommend",
                "command",
                "Wie empfehle ich ein Issue zum Ignorieren?",
                "ki-workspace recommend-ignore <ID> -c <CATEGORY> -r 'Begründung' --reviewer <KI>. Kategorien: accepted_use, false_positive, not_exploitable, test_code, external_code",
                "recommend,ignore,befehl,cli",
            ),
            # Konzepte
            (
                "db_location",
                "concept",
                "Wo ist die Datenbank?",
                "~/.ai-workspace/workspace.db (SQLite mit FTS5). Tabellen: projects, issue_meta, issues_fts, settings, project_phases, check_matrix, handoffs, ki_faq",
                "datenbank,sqlite,pfad",
            ),
            (
                "ki_recommendation_fields",
                "concept",
                "Welche KI-Felder gibt es in issue_meta?",
                "ki_recommendation_category (Kategorie), ki_recommendation (Begründung), ki_reviewed_by (claude/codex/gemini), ki_reviewed_at (Timestamp). Werden NICHT zu Codacy synchronisiert - nur lokal.",
                "ki,felder,datenbank,issue",
            ),
            (
                "project_phases",
                "concept",
                "Welche Projekt-Phasen gibt es?",
                "Initial (Setup), Development (Default, aktive Entwicklung), Refactoring, Testing, Final. Jede Phase hat eigene Check-Matrix (welche Checks aktiv, welche Severity).",
                "phase,projekt,status",
            ),
            (
                "codacy_integration",
                "concept",
                "Wie funktioniert die Codacy-Integration?",
                "API-Token in settings (verschlüsselt). Sync holt SRM-Items (Security) und Quality-Issues. Provider: gh/gl/bb. Org ist GitHub-Username. Projekt muss public sein für Codacy Free.",
                "codacy,api,integration",
            ),
        ]

        for key, category, question, answer, tags in faqs:
            conn.execute(
                """INSERT INTO ki_faq (key, category, question, answer, tags)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, category, question, answer, tags),
            )

    def upsert_faq(self, faq: FaqEntry) -> FaqEntry:
        """Erstellt oder aktualisiert einen FAQ-Eintrag."""
        with self._get_connection() as conn:
            tags_str = ",".join(faq.tags) if faq.tags else ""
            now = datetime.now().isoformat()

            conn.execute(
                """
                INSERT INTO ki_faq (key, category, question, answer, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    category = excluded.category,
                    question = excluded.question,
                    answer = excluded.answer,
                    tags = excluded.tags,
                    updated_at = excluded.updated_at
                """,
                (faq.key, faq.category, faq.question, faq.answer, tags_str, now),
            )

            cursor = conn.execute("SELECT id FROM ki_faq WHERE key = ?", (faq.key,))
            faq.id = cursor.fetchone()[0]
            faq.updated_at = datetime.fromisoformat(now)
            conn.commit()
        return faq

    def get_faq(self, key: str) -> FaqEntry | None:
        """Lädt einen FAQ-Eintrag nach Key."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ki_faq WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return self._row_to_faq(row)
        return None

    def get_all_faq(self, category: str | None = None) -> list[FaqEntry]:
        """Lädt alle FAQ-Einträge, optional gefiltert nach Kategorie."""
        with self._get_connection() as conn:
            if category:
                cursor = conn.execute(
                    "SELECT * FROM ki_faq WHERE category = ? ORDER BY key",
                    (category,),
                )
            else:
                cursor = conn.execute("SELECT * FROM ki_faq ORDER BY category, key")
            return [self._row_to_faq(row) for row in cursor.fetchall()]

    def search_faq(self, query: str) -> list[FaqEntry]:
        """Durchsucht FAQ mit FTS5."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT f.* FROM ki_faq f
                JOIN ki_faq_fts fts ON f.id = fts.rowid
                WHERE ki_faq_fts MATCH ?
                ORDER BY rank
                """,
                (query,),
            )
            return [self._row_to_faq(row) for row in cursor.fetchall()]

    def delete_faq(self, key: str) -> bool:
        """Löscht einen FAQ-Eintrag."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM ki_faq WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_faq(self, row: sqlite3.Row) -> FaqEntry:
        """Konvertiert eine DB-Row zu einem FaqEntry."""
        tags_str = row["tags"] or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]
        return FaqEntry(
            id=row["id"],
            key=row["key"],
            category=row["category"],
            question=row["question"],
            answer=row["answer"],
            tags=tags,
            updated_at=row["updated_at"],
        )

    def get_faq_as_json(self, category: str | None = None) -> dict:
        """
        Gibt FAQ als kompaktes JSON-Dict zurück (für KI-Konsum).

        Returns:
            Dict mit Struktur: {category: {key: {q, a, tags}}}
        """
        faqs = self.get_all_faq(category)
        result: dict[str, dict] = {}
        for faq in faqs:
            if faq.category not in result:
                result[faq.category] = {}
            result[faq.category][faq.key] = {
                "q": faq.question,
                "a": faq.answer,
                "tags": faq.tags,
            }
        return result

    # === AI PROMPTS CRUD ===

    def _init_default_prompts(self, conn: sqlite3.Connection) -> None:
        """Initialisiert die Default-Prompts fuer KI-Delegation."""
        from core.ai_delegation import DEFAULT_PROMPTS

        for prompt_data in DEFAULT_PROMPTS:
            conn.execute(
                """INSERT INTO ai_prompts (name, description, prompt, default_ai, category, is_builtin)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (
                    prompt_data["name"],
                    prompt_data["description"],
                    prompt_data["prompt"],
                    prompt_data["default_ai"],
                    prompt_data["category"],
                ),
            )

    def get_prompt(self, name: str) -> AiPrompt | None:
        """Laedt einen Prompt nach Name."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM ai_prompts WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_prompt(row)
        return None

    def get_all_prompts(self, category: str | None = None) -> list[AiPrompt]:
        """Laedt alle Prompts, optional gefiltert nach Kategorie."""
        with self._get_connection() as conn:
            if category:
                cursor = conn.execute(
                    "SELECT * FROM ai_prompts WHERE category = ? ORDER BY name",
                    (category,),
                )
            else:
                cursor = conn.execute("SELECT * FROM ai_prompts ORDER BY category, name")
            return [self._row_to_prompt(row) for row in cursor.fetchall()]

    def upsert_prompt(self, prompt: AiPrompt) -> AiPrompt:
        """Erstellt oder aktualisiert einen Prompt."""
        with self._get_connection() as conn:
            now = datetime.now().isoformat()

            conn.execute(
                """
                INSERT INTO ai_prompts (name, description, prompt, default_ai, category, is_builtin, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    prompt = excluded.prompt,
                    default_ai = excluded.default_ai,
                    category = excluded.category,
                    updated_at = excluded.updated_at
                WHERE is_builtin = 0 OR excluded.is_builtin = 1
                """,
                (
                    prompt.name,
                    prompt.description,
                    prompt.prompt,
                    prompt.default_ai,
                    prompt.category,
                    1 if prompt.is_builtin else 0,
                    now,
                ),
            )

            cursor = conn.execute("SELECT id FROM ai_prompts WHERE name = ?", (prompt.name,))
            prompt.id = cursor.fetchone()[0]
            prompt.updated_at = datetime.fromisoformat(now)
            conn.commit()
        return prompt

    def delete_prompt(self, name: str) -> bool:
        """Loescht einen Prompt (nur nicht-builtin)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM ai_prompts WHERE name = ? AND is_builtin = 0",
                (name,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_prompt(self, row: sqlite3.Row) -> AiPrompt:
        """Konvertiert eine DB-Row zu einem AiPrompt."""
        return AiPrompt(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            prompt=row["prompt"],
            default_ai=row["default_ai"],
            category=row["category"],
            is_builtin=bool(row["is_builtin"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
