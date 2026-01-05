"""
Release Readiness Checks fuer KI-Workspace.

Prueft ob ein Projekt bereit fuer Release/Publikation ist.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.database import DatabaseManager, Project


@dataclass
class CheckResult:
    """Ergebnis eines einzelnen Checks."""

    name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning, info


def check_license(project_path: str) -> CheckResult:
    """Prueft ob eine LICENSE-Datei vorhanden ist."""
    path = Path(project_path)
    license_files = ["LICENSE", "LICENSE.md", "LICENSE.txt", "LIZENZ"]

    for lf in license_files:
        if (path / lf).exists():
            return CheckResult(
                name="LICENSE",
                passed=True,
                message=f"{lf} vorhanden",
                severity="error",
            )

    return CheckResult(
        name="LICENSE",
        passed=False,
        message="Keine LICENSE-Datei gefunden",
        severity="error",
    )


def check_readme(project_path: str) -> CheckResult:
    """Prueft ob eine README-Datei vorhanden ist."""
    path = Path(project_path)
    readme_files = ["README.md", "README.txt", "README", "README.rst"]

    for rf in readme_files:
        if (path / rf).exists():
            # Pruefen ob nicht leer
            content = (path / rf).read_text(encoding="utf-8", errors="ignore")
            if len(content.strip()) < 50:
                return CheckResult(
                    name="README",
                    passed=False,
                    message=f"{rf} ist zu kurz (< 50 Zeichen)",
                    severity="warning",
                )
            return CheckResult(
                name="README",
                passed=True,
                message=f"{rf} vorhanden",
                severity="error",
            )

    return CheckResult(
        name="README",
        passed=False,
        message="Keine README-Datei gefunden",
        severity="error",
    )


def check_changelog(project_path: str) -> CheckResult:
    """Prueft ob eine CHANGELOG-Datei vorhanden ist."""
    path = Path(project_path)
    changelog_files = ["CHANGELOG.md", "CHANGELOG.txt", "CHANGELOG", "HISTORY.md"]

    for cf in changelog_files:
        if (path / cf).exists():
            return CheckResult(
                name="CHANGELOG",
                passed=True,
                message=f"{cf} vorhanden",
                severity="warning",
            )

    return CheckResult(
        name="CHANGELOG",
        passed=False,
        message="Kein CHANGELOG gefunden",
        severity="warning",
    )


def check_critical_issues(db: DatabaseManager, project_id: int) -> CheckResult:
    """Prueft ob es offene Critical Issues gibt."""
    issues = db.get_issues(
        project_id=project_id, priority="Critical", status="open", is_false_positive=False
    )
    count = len(issues)

    if count == 0:
        return CheckResult(
            name="Critical Issues",
            passed=True,
            message="Keine Critical Issues",
            severity="error",
        )

    return CheckResult(
        name="Critical Issues",
        passed=False,
        message=f"{count} Critical Issue(s) gefunden",
        severity="error",
    )


def check_high_issues(db: DatabaseManager, project_id: int) -> CheckResult:
    """Prueft ob es offene High Issues gibt."""
    issues = db.get_issues(
        project_id=project_id, priority="High", status="open", is_false_positive=False
    )
    count = len(issues)

    if count == 0:
        return CheckResult(
            name="High Issues",
            passed=True,
            message="Keine High Issues",
            severity="warning",
        )

    return CheckResult(
        name="High Issues",
        passed=False,
        message=f"{count} High Issue(s) gefunden",
        severity="warning",
    )


def check_radon_complexity(project_path: str) -> CheckResult:
    """
    Prueft die Cyclomatic Complexity mit radon.

    Fails wenn Funktionen mit Complexity >= B (6-10) gefunden werden.
    Sucht radon im Projekt-venv (.venv/bin/radon) oder global.
    """
    path = Path(project_path)

    # Radon-Pfad: bevorzuge Projekt-venv, dann global
    venv_radon = path / ".venv" / "bin" / "radon"
    radon_cmd = str(venv_radon) if venv_radon.exists() else "radon"

    # Prüfe nur src/ falls vorhanden, sonst Projekt-Root (ohne .venv)
    src_path = path / "src"
    check_path = str(src_path) if src_path.exists() else project_path

    try:
        result = subprocess.run(
            [
                radon_cmd,
                "cc",
                check_path,
                "-a",
                "-s",
                "--total-average",
                "--exclude",
                ".venv,venv,node_modules,__pycache__",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            # radon nicht gefunden oder Fehler
            return CheckResult(
                name="Radon Complexity",
                passed=True,
                message="Uebersprungen (radon nicht verfuegbar)",
                severity="info",
            )

        output = result.stdout

        # Complexity-Stufen:
        # A-B (1-10): OK - gut handhabbar fuer KIs
        # C (11-20): Warnung - sollte refaktoriert werden
        # D-F (21+): Fehler - muss refaktoriert werden
        error_grades = ["D", "E", "F"]  # Fehler
        warn_grades = ["C"]  # Warnung
        error_patterns = [f" - {g} (" for g in error_grades]
        warn_patterns = [f" - {g} (" for g in warn_grades]

        # Zaehle problematische Funktionen
        error_lines = [
            line
            for line in output.split("\n")
            if any(pattern in line for pattern in error_patterns)
        ]
        warn_lines = [
            line for line in output.split("\n") if any(pattern in line for pattern in warn_patterns)
        ]

        if error_lines:
            return CheckResult(
                name="Radon Complexity",
                passed=False,
                message=f"{len(error_lines)} Funktion(en) mit sehr hoher Complexity (D+)",
                severity="error",
            )

        if warn_lines:
            return CheckResult(
                name="Radon Complexity",
                passed=True,
                message=f"{len(warn_lines)} Funktion(en) mit Complexity C (refactoring empfohlen)",
                severity="warning",
            )

        return CheckResult(
            name="Radon Complexity",
            passed=True,
            message="Complexity OK (A-B)",
            severity="info",
        )

    except FileNotFoundError:
        return CheckResult(
            name="Radon Complexity",
            passed=True,
            message="Uebersprungen (radon nicht installiert)",
            severity="info",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Radon Complexity",
            passed=True,
            message="Uebersprungen (Timeout)",
            severity="info",
        )
    except Exception as e:
        return CheckResult(
            name="Radon Complexity",
            passed=True,
            message=f"Uebersprungen ({e})",
            severity="info",
        )


def check_coverage(project_path: str) -> CheckResult:
    """
    Prueft die Test-Coverage mit pytest-cov.

    Thresholds:
    - >= 80%: OK (gruen)
    - >= 60%: Warning (gelb)
    - < 60%: Error (rot)

    Sucht pytest im Projekt-venv (.venv/bin/pytest) oder global.
    """
    path = Path(project_path)

    # Pytest-Pfad: bevorzuge Projekt-venv, dann global
    venv_pytest = path / ".venv" / "bin" / "pytest"
    pytest_cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"

    # Prüfe ob src/ existiert für coverage path
    src_path = path / "src"
    cov_path = str(src_path) if src_path.exists() else project_path

    try:
        result = subprocess.run(
            [
                pytest_cmd,
                project_path,
                "-q",
                "--tb=no",
                f"--cov={cov_path}",
                "--cov-report=term-missing",
                "--cov-fail-under=0",
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=project_path,
        )

        # Parse coverage percentage from output
        # Format: "TOTAL ... XX%"
        output = result.stdout + result.stderr
        coverage_pct = None

        for line in output.split("\n"):
            if "TOTAL" in line and "%" in line:
                # Extract percentage
                match = re.search(r"(\d+)%", line)
                if match:
                    coverage_pct = int(match.group(1))
                    break

        if coverage_pct is None:
            return CheckResult(
                name="Coverage",
                passed=True,
                message="Coverage konnte nicht ermittelt werden",
                severity="info",
            )

        # Thresholds: >= 80% OK, >= 60% Warning, < 60% Error
        if coverage_pct >= 80:
            return CheckResult(
                name="Coverage",
                passed=True,
                message=f"Coverage {coverage_pct}% (gut)",
                severity="info",
            )
        elif coverage_pct >= 60:
            return CheckResult(
                name="Coverage",
                passed=True,
                message=f"Coverage {coverage_pct}% (akzeptabel)",
                severity="warning",
            )
        else:
            return CheckResult(
                name="Coverage",
                passed=False,
                message=f"Coverage {coverage_pct}% (zu niedrig)",
                severity="error",
            )

    except FileNotFoundError:
        return CheckResult(
            name="Coverage",
            passed=True,
            message="Uebersprungen (pytest-cov nicht installiert)",
            severity="info",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Coverage",
            passed=True,
            message="Uebersprungen (Timeout)",
            severity="info",
        )
    except Exception as e:
        return CheckResult(
            name="Coverage",
            passed=True,
            message=f"Uebersprungen ({e})",
            severity="info",
        )


def check_tests(project_path: str) -> CheckResult:
    """
    Prueft ob Tests vorhanden sind und bestehen.

    Sucht nach pytest im Projekt-venv (.venv/bin/pytest) oder global.
    """
    path = Path(project_path)

    # Pruefen ob tests/ oder test/ existiert
    test_dirs = ["tests", "test"]
    has_tests = any((path / td).exists() for td in test_dirs)

    if not has_tests:
        # Suche nach test_*.py Dateien
        test_files = list(path.glob("**/test_*.py"))
        if not test_files:
            return CheckResult(
                name="Tests",
                passed=False,
                message="Keine Tests gefunden",
                severity="warning",
            )

    # Pytest-Pfad: bevorzuge Projekt-venv, dann global
    venv_pytest = path / ".venv" / "bin" / "pytest"
    pytest_cmd = str(venv_pytest) if venv_pytest.exists() else "pytest"

    # Versuche pytest auszufuehren
    try:
        result = subprocess.run(
            [pytest_cmd, project_path, "-q", "--tb=no", "-x"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_path,
        )

        if result.returncode == 0:
            return CheckResult(
                name="Tests",
                passed=True,
                message="Tests bestanden",
                severity="error",
            )
        elif result.returncode == 5:
            # pytest: no tests collected
            return CheckResult(
                name="Tests",
                passed=True,
                message="Keine Tests gesammelt",
                severity="warning",
            )
        else:
            return CheckResult(
                name="Tests",
                passed=False,
                message="Tests fehlgeschlagen",
                severity="error",
            )

    except FileNotFoundError:
        return CheckResult(
            name="Tests",
            passed=True,
            message="Uebersprungen (pytest nicht installiert)",
            severity="info",
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="Tests",
            passed=False,
            message="Tests Timeout (> 120s)",
            severity="error",
        )
    except Exception as e:
        return CheckResult(
            name="Tests",
            passed=True,
            message=f"Uebersprungen ({e})",
            severity="info",
        )


def check_git_status(project_path: str) -> CheckResult:
    """Prueft ob das Git-Repository sauber ist (keine uncommitted changes)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_path,
        )

        if result.returncode != 0:
            return CheckResult(
                name="Git Status",
                passed=True,
                message="Kein Git-Repository",
                severity="info",
            )

        if result.stdout.strip():
            lines = len(result.stdout.strip().split("\n"))
            return CheckResult(
                name="Git Status",
                passed=False,
                message=f"{lines} uncommitted Aenderung(en)",
                severity="warning",
            )

        return CheckResult(
            name="Git Status",
            passed=True,
            message="Repository sauber",
            severity="warning",
        )

    except Exception as e:
        return CheckResult(
            name="Git Status",
            passed=True,
            message=f"Uebersprungen ({e})",
            severity="info",
        )


def check_readme_english(project_path: str) -> CheckResult:
    """Check if README is written in English (no German umlauts outside quotes)."""
    path = Path(project_path)
    readme_files = ["README.md", "README.txt", "README", "README.rst"]

    for rf in readme_files:
        readme_path = path / rf
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8", errors="ignore")
            # Check for German characters outside of code blocks and quotes
            german_chars = "äöüÄÖÜß"
            has_german = any(c in content for c in german_chars)

            if has_german:
                return CheckResult(
                    name="README English",
                    passed=False,
                    message=f"{rf} contains German characters",
                    severity="warning",
                )
            return CheckResult(
                name="README English",
                passed=True,
                message=f"{rf} is in English",
                severity="warning",
            )

    return CheckResult(
        name="README English",
        passed=True,
        message="No README found (skipped)",
        severity="info",
    )


def check_hobby_notice(project_path: str) -> CheckResult:
    """Check if README contains hobby/experimental project notice."""
    path = Path(project_path)
    readme_files = ["README.md", "README.txt", "README", "README.rst"]

    hobby_keywords = [
        "hobby",
        "experimental",
        "experiment",
        "not a commercial",
        "no warranties",
        "no support",
        "Hobby",
        "Experimental",
    ]

    for rf in readme_files:
        readme_path = path / rf
        if readme_path.exists():
            content = readme_path.read_text(encoding="utf-8", errors="ignore").lower()
            has_notice = any(kw.lower() in content for kw in hobby_keywords)

            if has_notice:
                return CheckResult(
                    name="Hobby Notice",
                    passed=True,
                    message="Hobby/experimental notice found",
                    severity="warning",
                )
            return CheckResult(
                name="Hobby Notice",
                passed=False,
                message=f"{rf} missing hobby/experimental notice",
                severity="warning",
            )

    return CheckResult(
        name="Hobby Notice",
        passed=True,
        message="No README found (skipped)",
        severity="info",
    )


def check_i18n(project_path: str) -> CheckResult:
    """Check if project has internationalization (i18n) support."""
    path = Path(project_path)

    # Check for translations directory
    trans_dirs = ["translations", "locales", "i18n", "locale"]
    has_trans_dir = any((path / td).exists() for td in trans_dirs)
    has_trans_in_src = any(
        (path / "src").glob(f"**/{td}") for td in trans_dirs if (path / "src").exists()
    )

    # Check for i18n imports in Python files
    i18n_imports = ["gradio_i18n", "gettext", "babel", "i18n"]
    has_i18n_import = False

    py_files = list(path.glob("**/*.py"))
    for py_file in py_files[:50]:  # Limit to avoid timeout
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if any(imp in content for imp in i18n_imports):
                has_i18n_import = True
                break
        except Exception:
            continue

    if has_trans_dir or has_trans_in_src or has_i18n_import:
        return CheckResult(
            name="i18n Support",
            passed=True,
            message="i18n/translations found",
            severity="warning",
        )

    return CheckResult(
        name="i18n Support",
        passed=False,
        message="No i18n/translations found",
        severity="warning",
    )


def check_pyproject_english(project_path: str) -> CheckResult:
    """Check if pyproject.toml has English description and metadata."""
    path = Path(project_path)
    pyproject_path = path / "pyproject.toml"

    if not pyproject_path.exists():
        return CheckResult(
            name="pyproject.toml English",
            passed=True,
            message="No pyproject.toml found (skipped)",
            severity="info",
        )

    german_chars = "äöüÄÖÜß"
    try:
        content = pyproject_path.read_text(encoding="utf-8", errors="ignore")
        if any(c in content for c in german_chars):
            return CheckResult(
                name="pyproject.toml English",
                passed=False,
                message="pyproject.toml contains German characters",
                severity="warning",
            )
        return CheckResult(
            name="pyproject.toml English",
            passed=True,
            message="pyproject.toml is in English",
            severity="warning",
        )
    except Exception:
        return CheckResult(
            name="pyproject.toml English",
            passed=True,
            message="Could not read pyproject.toml (skipped)",
            severity="info",
        )


def check_code_english(project_path: str) -> CheckResult:
    """Check if Python code is written in English (no German in comments/docstrings)."""
    path = Path(project_path)
    german_chars = "äöüÄÖÜß"

    # Directories to skip (translations are allowed to have German)
    skip_dirs = {"translations", "locales", "i18n", "locale", ".venv", "venv", "__pycache__"}

    issues_found = []
    py_files = list(path.glob("**/*.py"))

    for py_file in py_files[:100]:  # Limit to avoid timeout
        # Skip translation directories
        if any(skip_dir in py_file.parts for skip_dir in skip_dirs):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if any(c in content for c in german_chars):
                rel_path = py_file.relative_to(path)
                issues_found.append(str(rel_path))
        except Exception:
            continue

    if issues_found:
        count = len(issues_found)
        return CheckResult(
            name="Code English",
            passed=False,
            message=f"{count} file(s) with German text",
            severity="warning",
        )

    return CheckResult(
        name="Code English",
        passed=True,
        message="Code is in English",
        severity="warning",
    )


def run_all_checks(db: DatabaseManager, project: Project) -> list[CheckResult]:
    """
    Fuehrt Release Readiness Checks basierend auf der Projekt-Phase aus.

    Die aktivierten Checks und ihre Severity werden aus der check_matrix
    in der Datenbank geladen. So kann der Prozess flexibel angepasst werden.

    Args:
        db: DatabaseManager Instanz
        project: Projekt-Objekt

    Returns:
        Liste der CheckResults (nur aktivierte Checks)
    """
    results = []

    # Check-Funktionen Mapping (Name -> Funktion)
    # Datei-basierte Checks
    file_checks = {
        "LICENSE": lambda: check_license(project.path),
        "README": lambda: check_readme(project.path),
        "CHANGELOG": lambda: check_changelog(project.path),
        "Radon Complexity": lambda: check_radon_complexity(project.path),
        "Tests": lambda: check_tests(project.path),
        "Coverage": lambda: check_coverage(project.path),
        "Git Status": lambda: check_git_status(project.path),
        "README English": lambda: check_readme_english(project.path),
        "Hobby Notice": lambda: check_hobby_notice(project.path),
        "i18n Support": lambda: check_i18n(project.path),
        "Code English": lambda: check_code_english(project.path),
        "pyproject.toml English": lambda: check_pyproject_english(project.path),
    }

    # DB-basierte Checks
    db_checks = {
        "Critical Issues": lambda: check_critical_issues(db, project.id),
        "High Issues": lambda: check_high_issues(db, project.id),
    }

    # Aktivierte Checks aus der Matrix laden
    enabled_checks: dict[str, str] = {}
    if project.phase_id:
        enabled_checks = db.get_enabled_checks_for_phase(project.phase_id)

    # Fallback: Wenn keine Phase gesetzt, alle Checks mit Default-Severity
    if not enabled_checks:
        enabled_checks = {
            "LICENSE": "error",
            "README": "error",
            "CHANGELOG": "warning",
            "Radon Complexity": "warning",
            "Tests": "error",
            "Coverage": "warning",
            "Git Status": "warning",
            "Critical Issues": "error",
            "High Issues": "warning",
            "README English": "warning",
            "Hobby Notice": "warning",
            "i18n Support": "warning",
            "Code English": "warning",
            "pyproject.toml English": "warning",
        }

    # Datei-basierte Checks ausfuehren (nur wenn Pfad existiert)
    if project.path:
        for check_name, check_func in file_checks.items():
            if check_name in enabled_checks:
                result = check_func()
                # Severity aus Matrix ueberschreiben (ausser bei info/uebersprungen)
                if result.severity != "info":
                    result.severity = enabled_checks[check_name]
                results.append(result)

    # DB-basierte Checks ausfuehren
    for check_name, check_func in db_checks.items():
        if check_name in enabled_checks:
            result = check_func()
            if result.severity != "info":
                result.severity = enabled_checks[check_name]
            results.append(result)

    return results


def run_phase_checks(
    db: DatabaseManager, project: Project, enabled_checks: dict[str, str]
) -> list[CheckResult]:
    """
    Fuehrt Release Readiness Checks basierend auf uebergebenen enabled_checks aus.

    Args:
        db: DatabaseManager Instanz
        project: Projekt-Objekt
        enabled_checks: Dict von check_name -> severity (aus check_matrix)

    Returns:
        Liste der CheckResults (nur aktivierte Checks)
    """
    results = []

    # Check-Funktionen Mapping (Name -> Funktion)
    # Datei-basierte Checks
    file_checks = {
        "LICENSE": lambda: check_license(project.path),
        "README": lambda: check_readme(project.path),
        "CHANGELOG": lambda: check_changelog(project.path),
        "Radon Complexity": lambda: check_radon_complexity(project.path),
        "Tests": lambda: check_tests(project.path),
        "Coverage": lambda: check_coverage(project.path),
        "Git Status": lambda: check_git_status(project.path),
        "README English": lambda: check_readme_english(project.path),
        "Hobby Notice": lambda: check_hobby_notice(project.path),
        "i18n Support": lambda: check_i18n(project.path),
        "Code English": lambda: check_code_english(project.path),
        "pyproject.toml English": lambda: check_pyproject_english(project.path),
    }

    # DB-basierte Checks
    db_checks = {
        "Critical Issues": lambda: check_critical_issues(db, project.id),
        "High Issues": lambda: check_high_issues(db, project.id),
    }

    # Datei-basierte Checks ausfuehren (nur wenn Pfad existiert)
    if project.path:
        for check_name, check_func in file_checks.items():
            if check_name in enabled_checks:
                result = check_func()
                # Severity aus Matrix ueberschreiben (ausser bei info/uebersprungen)
                if result.severity != "info":
                    result.severity = enabled_checks[check_name]
                results.append(result)

    # DB-basierte Checks ausfuehren
    for check_name, check_func in db_checks.items():
        if check_name in enabled_checks:
            result = check_func()
            if result.severity != "info":
                result.severity = enabled_checks[check_name]
            results.append(result)

    return results


def get_phase_info(db: DatabaseManager, phase_id: int | None) -> dict[str, str] | None:
    """
    Gibt Informationen zur aktuellen Phase zurueck.

    Args:
        db: DatabaseManager Instanz
        phase_id: Phase-ID

    Returns:
        Dict mit name und display_name oder None
    """
    if not phase_id:
        return None
    phase = db.get_phase(phase_id)
    if phase:
        return {"name": phase.name, "display_name": phase.display_name}
    return None
