"""Tests für DatabaseManager."""

import tempfile
from pathlib import Path

import pytest

from core.database import DatabaseManager, Issue, Project


class TestDatabaseManager:
    """Tests für Datenbank-Operationen."""

    @pytest.fixture
    def db(self):
        """Erstellt temporäre Test-Datenbank."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            yield DatabaseManager(db_path=db_path)

    def test_create_project(self, db):
        """Projekt anlegen funktioniert."""
        project = Project(
            name="test-project",
            path="/home/user/test",
            git_remote="git@github.com:user/test.git",
            codacy_provider="gh",
            codacy_org="user",
        )
        created = db.create_project(project)

        assert created.id is not None
        assert created.id > 0

        # Wieder laden
        loaded = db.get_project(created.id)
        assert loaded is not None
        assert loaded.name == "test-project"
        assert loaded.codacy_org == "user"

    def test_get_all_projects(self, db):
        """Alle Projekte laden."""
        # Zwei Projekte anlegen
        db.create_project(Project(name="project1", codacy_org="org1"))
        db.create_project(Project(name="project2", codacy_org="org2"))

        projects = db.get_all_projects()
        assert len(projects) == 2
        assert projects[0].name == "project1"
        assert projects[1].name == "project2"

    def test_archive_project(self, db):
        """Projekt archivieren und wiederherstellen."""
        created = db.create_project(Project(name="to-archive"))
        project_id = created.id

        # Archivieren
        db.archive_project(project_id)

        # Nicht in normaler Liste
        projects = db.get_all_projects(include_archived=False)
        assert len(projects) == 0

        # Aber in Liste mit Archivierten
        projects = db.get_all_projects(include_archived=True)
        assert len(projects) == 1
        assert projects[0].is_archived is True

        # Wiederherstellen
        db.unarchive_project(project_id)
        projects = db.get_all_projects(include_archived=False)
        assert len(projects) == 1
        assert projects[0].is_archived is False

    def test_settings_encrypted(self, db):
        """Settings werden verschlüsselt gespeichert."""
        db.set_setting("api_token", "secret123", encrypt=True)

        # Laden gibt entschlüsselten Wert zurück
        loaded = db.get_setting("api_token")
        assert loaded == "secret123"

    def test_settings_unencrypted(self, db):
        """Unverschlüsselte Settings."""
        db.set_setting("theme", "dark", encrypt=False)

        loaded = db.get_setting("theme")
        assert loaded == "dark"

    def test_upsert_issue(self, db):
        """Issue anlegen und aktualisieren (Upsert)."""
        created = db.create_project(Project(name="issue-test"))
        project_id = created.id

        issue = Issue(
            project_id=project_id,
            external_id="ext-123",
            priority="High",
            status="open",
            title="Test Issue",
        )
        db.upsert_issue(issue)

        # Nochmal mit Update
        issue.status = "fixed"
        db.upsert_issue(issue)

        # Laden und prüfen
        issues = db.get_issues(project_id=project_id)
        assert len(issues) == 1
        assert issues[0].status == "fixed"

    def test_mark_false_positive(self, db):
        """Issue als False Positive markieren."""
        created = db.create_project(Project(name="fp-test"))
        project_id = created.id

        issue = Issue(
            project_id=project_id,
            external_id="fp-issue",
            priority="Medium",
            title="False Positive Test",
        )
        db.upsert_issue(issue)

        issues = db.get_issues(project_id=project_id)
        issue_id = issues[0].id

        db.mark_false_positive(issue_id, "Not applicable in test code")

        # Prüfen
        issues = db.get_issues(project_id=project_id, is_false_positive=True)
        assert len(issues) == 1
        assert issues[0].is_false_positive is True

    def test_delete_project(self, db):
        """Projekt löschen."""
        created = db.create_project(Project(name="to-delete"))
        project_id = created.id

        db.delete_project(project_id)

        assert db.get_project(project_id) is None

    def test_project_has_codacy_field(self, db):
        """has_codacy Feld funktioniert."""
        project = Project(name="no-codacy", has_codacy=False)
        created = db.create_project(project)
        project_id = created.id

        loaded = db.get_project(project_id)
        assert loaded.has_codacy is False

        # Update
        loaded.has_codacy = True
        db.update_project(loaded)

        reloaded = db.get_project(project_id)
        assert reloaded.has_codacy is True
