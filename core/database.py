"""
Database Manager für KI-CLI Workspace.

SQLite mit FTS5 für Volltextsuche.
"""

import contextlib
import json
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
    last_sync: datetime | None = None


@dataclass
class Issue:
    """Issue-Datenmodell."""

    id: int | None = None
    project_id: int = 0
    external_id: str = ""  # Codacy ID
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

            conn.commit()

    # === Project CRUD ===

    def create_project(self, project: Project) -> Project:
        """Erstellt ein neues Projekt."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, path, git_remote, codacy_provider, codacy_org,
                                      github_owner, has_codacy, is_archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                            priority = ?, status = ?, scan_type = ?, title = ?,
                            message = ?, file_path = ?, line_number = ?, tool = ?,
                            rule = ?, category = ?, cve = ?, affected_version = ?,
                            fixed_version = ?, synced_at = ?,
                            is_false_positive = 1, fp_reason = COALESCE(fp_reason, ?)
                        WHERE external_id = ?
                        """,
                        (
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
                            priority = ?, status = ?, scan_type = ?, title = ?,
                            message = ?, file_path = ?, line_number = ?, tool = ?,
                            rule = ?, category = ?, cve = ?, affected_version = ?,
                            fixed_version = ?, synced_at = ?
                        WHERE external_id = ?
                        """,
                        (
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
                # Insert
                cursor = conn.execute(
                    """
                    INSERT INTO issue_meta (
                        project_id, external_id, priority, status, scan_type,
                        title, message, file_path, line_number, tool, rule,
                        category, cve, affected_version, fixed_version,
                        created_at, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue.project_id,
                        issue.external_id,
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

            # Total
            cursor = conn.execute(f"SELECT COUNT(*) FROM issue_meta {where}", params)
            stats["total"] = cursor.fetchone()[0]

            # By Priority
            cursor = conn.execute(
                f"SELECT priority, COUNT(*) FROM issue_meta {where} GROUP BY priority", params
            )
            stats["by_priority"] = {row[0]: row[1] for row in cursor.fetchall()}

            # By Status
            cursor = conn.execute(
                f"SELECT status, COUNT(*) FROM issue_meta {where} GROUP BY status", params
            )
            stats["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}

            # By Scan Type
            cursor = conn.execute(
                f"SELECT scan_type, COUNT(*) FROM issue_meta {where} GROUP BY scan_type", params
            )
            stats["by_scan_type"] = {row[0]: row[1] for row in cursor.fetchall()}

            # False Positives
            fp_where = f"{where} AND" if where else "WHERE"
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM issue_meta {fp_where} is_false_positive = 1", params
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
                    github_owner = ?, has_codacy = ?, is_archived = ?
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

    def delete_project(self, project_id: int) -> None:
        """Löscht ein Projekt und alle zugehörigen Issues (permanent)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM issue_meta WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM handoffs WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()
