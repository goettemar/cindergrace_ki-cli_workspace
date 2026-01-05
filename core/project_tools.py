"""
Projekt-Tools fuer KI-Workspace.

Backup, Test-Clone, Ruff-Fix und Final-Workflow Funktionen.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.database import DatabaseManager, Project

# Konstanten
MAX_BACKUPS_PER_PROJECT = 5
RUFF_COMMIT_MESSAGE = "style: ruff auto-fix"
README_STATUS_PATTERN = re.compile(r"\*\*Status:\*\*\s*\w+", re.IGNORECASE)
README_STATUS_FORMAT = "**Status:** {phase}"


def get_timestamp() -> str:
    """Gibt aktuellen Timestamp im Format YYYYMMDD_HHMMSS zurueck."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def expand_path(path: str) -> str:
    """Expandiert ~ und Umgebungsvariablen in Pfad."""
    return os.path.expanduser(os.path.expandvars(path))


def cleanup_old_backups(backup_dir: Path, max_count: int = MAX_BACKUPS_PER_PROJECT) -> int:
    """
    Loescht alte Backups wenn mehr als max_count vorhanden.

    Args:
        backup_dir: Verzeichnis mit Backup-Unterordnern (timestamps)
        max_count: Maximale Anzahl zu behaltender Backups

    Returns:
        Anzahl geloeschter Backups
    """
    if not backup_dir.exists():
        return 0

    # Alle Unterverzeichnisse nach Name (timestamp) sortiert
    subdirs = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir()],
        key=lambda x: x.name,
        reverse=True,  # Neueste zuerst
    )

    deleted = 0
    # Behalte die neuesten max_count
    for old_dir in subdirs[max_count:]:
        try:
            shutil.rmtree(old_dir)
            deleted += 1
        except Exception:
            pass  # Ignoriere Fehler beim Loeschen

    return deleted


def create_backup(project: Project, backup_base: str) -> tuple[bool, str]:
    """
    Erstellt Backup mit git archive (respektiert .gitignore).

    Args:
        project: Projekt-Objekt mit path
        backup_base: Basis-Pfad fuer Backups

    Returns:
        (success, message_or_path)
    """
    if not project.path:
        return False, "Kein Projekt-Pfad definiert"

    project_path = Path(project.path)
    if not project_path.exists():
        return False, f"Projekt-Pfad existiert nicht: {project.path}"

    # Backup-Ziel erstellen
    backup_base_path = Path(expand_path(backup_base))
    timestamp = get_timestamp()
    backup_dir = backup_base_path / project.name / timestamp

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Konnte Backup-Verzeichnis nicht erstellen: {e}"

    # Pruefen ob Git-Repository
    git_dir = project_path / ".git"
    if git_dir.exists():
        # Git archive verwenden (respektiert .gitignore)
        archive_path = backup_dir / f"{project.name}.tar.gz"
        try:
            result = subprocess.run(
                ["git", "archive", "--format=tar.gz", "-o", str(archive_path), "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return False, f"Git archive fehlgeschlagen: {result.stderr}"

            # Alte Backups aufraeumen
            project_backup_dir = backup_base_path / project.name
            deleted = cleanup_old_backups(project_backup_dir)

            msg = f"Backup erstellt: {archive_path}"
            if deleted > 0:
                msg += f" ({deleted} alte Backups geloescht)"
            return True, msg

        except subprocess.TimeoutExpired:
            return False, "Git archive Timeout (> 120s)"
        except Exception as e:
            return False, f"Git archive Fehler: {e}"
    else:
        # Kein Git - rsync mit Standard-Excludes
        try:
            excludes = [
                "--exclude=.venv",
                "--exclude=venv",
                "--exclude=__pycache__",
                "--exclude=*.pyc",
                "--exclude=.git",
                "--exclude=node_modules",
                "--exclude=.pytest_cache",
                "--exclude=htmlcov",
                "--exclude=.coverage",
                "--exclude=dist",
                "--exclude=build",
                "--exclude=*.egg-info",
            ]
            result = subprocess.run(
                ["rsync", "-a", *excludes, f"{project_path}/", str(backup_dir) + "/"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                return False, f"Rsync fehlgeschlagen: {result.stderr}"

            # Alte Backups aufraeumen
            project_backup_dir = backup_base_path / project.name
            deleted = cleanup_old_backups(project_backup_dir)

            msg = f"Backup erstellt: {backup_dir}"
            if deleted > 0:
                msg += f" ({deleted} alte Backups geloescht)"
            return True, msg

        except FileNotFoundError:
            return False, "rsync nicht installiert"
        except subprocess.TimeoutExpired:
            return False, "Rsync Timeout (> 300s)"
        except Exception as e:
            return False, f"Rsync Fehler: {e}"


def create_test_clone(project: Project, test_base: str) -> tuple[bool, str]:
    """
    Klont Projekt von GitHub in Test-Verzeichnis.

    Args:
        project: Projekt-Objekt mit git_remote
        test_base: Basis-Pfad fuer Test-Clones

    Returns:
        (success, message_or_path)
    """
    if not project.git_remote:
        return False, "Kein Git-Remote definiert"

    # Test-Ziel erstellen
    test_base_path = Path(expand_path(test_base))
    timestamp = get_timestamp()
    clone_dir = test_base_path / project.name / timestamp

    try:
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Konnte Test-Verzeichnis nicht erstellen: {e}"

    # Git clone
    try:
        result = subprocess.run(
            ["git", "clone", "--depth=1", project.git_remote, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return False, f"Git clone fehlgeschlagen: {result.stderr}"

        # Alte Clones aufraeumen (gleiche Logik wie Backups)
        project_test_dir = test_base_path / project.name
        deleted = cleanup_old_backups(project_test_dir)

        msg = f"Test-Clone erstellt: {clone_dir}"
        if deleted > 0:
            msg += f" ({deleted} alte Clones geloescht)"
        return True, msg

    except subprocess.TimeoutExpired:
        return False, "Git clone Timeout (> 300s)"
    except Exception as e:
        return False, f"Git clone Fehler: {e}"


def run_ruff_fix(project_path: str) -> tuple[bool, str, int]:
    """
    Fuehrt ruff check --fix + ruff format aus.

    Args:
        project_path: Pfad zum Projekt

    Returns:
        (success, output, files_changed)
    """
    path = Path(project_path)
    if not path.exists():
        return False, f"Projekt-Pfad existiert nicht: {project_path}", 0

    # Ruff-Pfad: bevorzuge Projekt-venv, dann global
    venv_ruff = path / ".venv" / "bin" / "ruff"
    ruff_cmd = str(venv_ruff) if venv_ruff.exists() else "ruff"

    # Pruefen ob ruff verfuegbar
    try:
        result = subprocess.run(
            [ruff_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False, "Ruff nicht verfuegbar", 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, "Ruff nicht installiert", 0

    # Pfad zum Pruefen
    src_path = path / "src"
    check_path = str(src_path) if src_path.exists() else project_path

    output_lines = []
    files_changed = 0

    # 1. ruff check --fix
    try:
        result = subprocess.run(
            [
                ruff_cmd,
                "check",
                check_path,
                "--fix",
                "--exclude",
                ".venv,venv,node_modules,__pycache__,build,dist",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_path,
        )
        if result.stdout:
            output_lines.append("=== ruff check --fix ===")
            output_lines.append(result.stdout)
            # Zaehle geaenderte Dateien (grob)
            files_changed += result.stdout.count("Fixed")

    except subprocess.TimeoutExpired:
        return False, "Ruff check Timeout", 0
    except Exception as e:
        return False, f"Ruff check Fehler: {e}", 0

    # 2. ruff format
    try:
        result = subprocess.run(
            [
                ruff_cmd,
                "format",
                check_path,
                "--exclude",
                ".venv,venv,node_modules,__pycache__,build,dist",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_path,
        )
        if result.stdout:
            output_lines.append("=== ruff format ===")
            output_lines.append(result.stdout)
            # Zaehle formatierte Dateien
            files_changed += result.stdout.count("reformatted")

    except subprocess.TimeoutExpired:
        return False, "Ruff format Timeout", files_changed
    except Exception as e:
        return False, f"Ruff format Fehler: {e}", files_changed

    if files_changed == 0:
        return True, "Keine Aenderungen noetig", 0

    output = "\n".join(output_lines) if output_lines else f"{files_changed} Dateien geaendert"
    return True, output, files_changed


def git_commit_changes(project_path: str, message: str = RUFF_COMMIT_MESSAGE) -> tuple[bool, str]:
    """
    Committet alle Aenderungen im Projekt.

    Args:
        project_path: Pfad zum Projekt
        message: Commit-Message

    Returns:
        (success, message)
    """
    path = Path(project_path)

    try:
        # Pruefen ob Aenderungen vorhanden
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not result.stdout.strip():
            return True, "Keine Aenderungen zu committen"

        # Stage all
        subprocess.run(
            ["git", "add", "-A"],
            cwd=path,
            capture_output=True,
            timeout=30,
        )

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, f"Commit fehlgeschlagen: {result.stderr}"

        return True, f"Commit erstellt: {message}"

    except subprocess.TimeoutExpired:
        return False, "Git Timeout"
    except Exception as e:
        return False, f"Git Fehler: {e}"


def git_push(project_path: str) -> tuple[bool, str]:
    """
    Pusht zum Remote-Repository.

    Args:
        project_path: Pfad zum Projekt

    Returns:
        (success, message)
    """
    try:
        result = subprocess.run(
            ["git", "push"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return False, f"Push fehlgeschlagen: {result.stderr}"
        return True, "Push erfolgreich"

    except subprocess.TimeoutExpired:
        return False, "Git push Timeout (> 120s)"
    except Exception as e:
        return False, f"Git push Fehler: {e}"


def update_readme_status(project_path: str, phase_display_name: str) -> tuple[bool, str]:
    """
    Aktualisiert den Status in der README.

    Args:
        project_path: Pfad zum Projekt
        phase_display_name: Anzeigename der Phase (z.B. "Development")

    Returns:
        (success, message)
    """
    path = Path(project_path)
    readme_files = ["README.md", "README.txt", "README", "README.rst"]

    for rf in readme_files:
        readme_path = path / rf
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8")
                new_status = README_STATUS_FORMAT.format(phase=phase_display_name)

                if README_STATUS_PATTERN.search(content):
                    # Status-Zeile ersetzen
                    new_content = README_STATUS_PATTERN.sub(new_status, content)
                    if new_content != content:
                        readme_path.write_text(new_content, encoding="utf-8")
                        return True, f"README Status aktualisiert: {phase_display_name}"
                    return True, "README Status bereits aktuell"
                else:
                    # Status-Zeile am Anfang hinzufuegen (nach erstem Header)
                    lines = content.split("\n")
                    insert_idx = 0
                    for i, line in enumerate(lines):
                        if line.startswith("#"):
                            insert_idx = i + 1
                            break

                    # Leere Zeile + Status einfuegen
                    lines.insert(insert_idx, "")
                    lines.insert(insert_idx + 1, new_status)
                    lines.insert(insert_idx + 2, "")

                    readme_path.write_text("\n".join(lines), encoding="utf-8")
                    return True, f"README Status hinzugefuegt: {phase_display_name}"

            except Exception as e:
                return False, f"README Update Fehler: {e}"

    return False, "Keine README gefunden"


def get_readme_status(project_path: str) -> str | None:
    """
    Liest den aktuellen Status aus der README.

    Args:
        project_path: Pfad zum Projekt

    Returns:
        Status-String oder None wenn nicht gefunden
    """
    path = Path(project_path)
    readme_files = ["README.md", "README.txt", "README", "README.rst"]

    for rf in readme_files:
        readme_path = path / rf
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8")
                match = README_STATUS_PATTERN.search(content)
                if match:
                    # Extrahiere nur den Status-Namen
                    status_line = match.group(0)
                    # "**Status:** Development" -> "Development"
                    parts = status_line.split(":")
                    if len(parts) >= 2:
                        return parts[1].strip().strip("*").strip()
            except Exception:
                pass

    return None


def run_release_checks(db: DatabaseManager, project: Project) -> tuple[bool, list]:
    """
    Fuehrt Release-Checks aus.

    Args:
        db: DatabaseManager Instanz
        project: Projekt-Objekt

    Returns:
        (all_passed, list_of_results)
    """
    from core.checks import run_all_checks

    results = run_all_checks(db, project)
    all_passed = all(r.passed for r in results)
    return all_passed, results


def run_final_workflow(
    project: Project, db: DatabaseManager, backup_base: str
) -> list[tuple[str, bool, str]]:
    """
    Kompletter Final-Workflow:
    1. Backup erstellen
    2. Ruff fix + format
    3. git commit (wenn Aenderungen)
    4. Release Check
    5. git push (wenn alle Checks OK)

    Args:
        project: Projekt-Objekt
        db: DatabaseManager Instanz
        backup_base: Basis-Pfad fuer Backups

    Returns:
        Liste von (step_name, success, message) Tupeln
    """
    steps = []

    # 1. Backup
    success, msg = create_backup(project, backup_base)
    steps.append(("Backup", success, msg))
    if not success:
        return steps  # Abbrechen bei Backup-Fehler

    # 2. Ruff Fix
    success, msg, files_changed = run_ruff_fix(project.path)
    steps.append(("Ruff Fix", success, msg))

    # 3. Git Commit (wenn Aenderungen)
    if files_changed > 0:
        success, msg = git_commit_changes(project.path)
        steps.append(("Git Commit", success, msg))

    # 4. Release Check
    all_passed, results = run_release_checks(db, project)
    check_summary = f"{sum(1 for r in results if r.passed)}/{len(results)} Checks bestanden"
    steps.append(("Release Check", all_passed, check_summary))

    if not all_passed:
        failed_checks = [r.name for r in results if not r.passed]
        steps.append(("Abbruch", False, f"Fehlgeschlagene Checks: {', '.join(failed_checks)}"))
        return steps

    # 5. Git Push
    success, msg = git_push(project.path)
    steps.append(("Git Push", success, msg))

    if success:
        steps.append(("Fertig", True, "Final-Workflow erfolgreich abgeschlossen!"))

    return steps
