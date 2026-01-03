"""
Projekt-Initialisierung.

Erstellt neue Projekte mit Standard-Struktur, GitHub Repo und Codacy-Integration.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.database import DatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class ProjectStatus:
    """Status für README Badge."""

    ALPHA = "alpha"
    BETA = "beta"
    STABLE = "stable"

    @staticmethod
    def get_badge(status: str) -> str:
        """Gibt den Badge-Markdown für den Status zurück."""
        badges = {
            "alpha": "![Status](https://img.shields.io/badge/Status-Alpha-red)",
            "beta": "![Status](https://img.shields.io/badge/Status-Beta-yellow)",
            "stable": "![Status](https://img.shields.io/badge/Status-Stable-green)",
        }
        return badges.get(status, badges["alpha"])

    @staticmethod
    def get_warning(status: str) -> str:
        """Gibt den Warnhinweis für den Status zurück."""
        warnings = {
            "alpha": "> ⚠️ **Alpha** - In aktiver Entwicklung, nicht für Produktion geeignet.",
            "beta": "> 🔶 **Beta** - Grundfunktionen stabil, kann noch Bugs enthalten.",
            "stable": "> ✅ **Stable** - Produktionsreif und getestet.",
        }
        return warnings.get(status, warnings["alpha"])


# === Templates ===

README_TEMPLATE = """# {name}

{badge}

{warning}

{description}

## Installation

```bash
pip install {package_name}
```

## Verwendung

```python
from {module_name} import example

# TODO: Beispielcode
```

## Entwicklung

```bash
# Repository klonen
git clone https://github.com/{github_org}/{name}.git
cd {name}

# Virtual Environment erstellen
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\\Scripts\\activate  # Windows

# Dependencies installieren
pip install -e ".[dev]"
```

## Lizenz

Dieses Projekt steht unter der [PolyForm Noncommercial License 1.0.0](LICENSE).

---

Erstellt am {date} | [{github_org}](https://github.com/{github_org})
"""

CHANGELOG_TEMPLATE = """# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

## [Unreleased]

### Hinzugefügt
- Initiale Projektstruktur
- README.md mit Status-Badge
- PolyForm NC Lizenz

### Geändert
- Nichts

### Behoben
- Nichts

---

[Unreleased]: https://github.com/{github_org}/{name}/compare/v0.1.0...HEAD
"""

PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
license = {{text = "PolyForm-Noncommercial-1.0.0"}}
requires-python = ">=3.10"
authors = [
    {{name = "{github_org}"}}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
]

[project.urls]
Homepage = "https://github.com/{github_org}/{name}"
Repository = "https://github.com/{github_org}/{name}"
Issues = "https://github.com/{github_org}/{name}/issues"

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
"""

INIT_PY_TEMPLATE = '''"""
{name} - {description}
"""

__version__ = "0.1.0"
'''

# Projekt-spezifisches FAQ für KI-Assistenten
PROJECT_FAQ_TEMPLATE = """{{
  "meta": {{
    "project": "{name}",
    "version": "0.1.0",
    "updated": "{date}"
  }},
  "architecture": {{
    "type": "python_package",
    "entry": "src/{module_name}/__init__.py",
    "tests": "tests/",
    "docs": "README.md"
  }},
  "conventions": {{
    "style": "ruff (E,F,W,I,N,UP,B,C4)",
    "tests": "pytest",
    "versioning": "semantic"
  }},
  "todos": [],
  "notes": []
}}
"""

# AGENTS.md für Codex CLI und andere KI-Assistenten
AGENTS_MD_TEMPLATE = """# Repository Guidelines

## Project Structure & Module Organization
- Source code lives in `src/{module_name}/` (package entry).
- Tests live in `tests/` and follow `test_*.py` naming.
- Top-level docs are in `README.md` and `CHANGELOG.md`.

## Build, Test, and Development Commands
- `python -m venv .venv` creates a local virtualenv.
- `source .venv/bin/activate` activates it.
- `python -m pip install -e ".[dev]"` installs editable deps plus dev tools.
- `pytest` runs the test suite from `tests/`.

## Coding Style & Naming Conventions
- Python 3.10+ only; keep code ASCII unless the file already uses Unicode.
- Follow Ruff defaults defined in `pyproject.toml` (line length 100).
- Modules use `snake_case.py`; functions/vars `snake_case`; classes `PascalCase`.
- Prefer small, focused modules; add brief comments only when logic is non-obvious.

## Testing Guidelines
- Framework: `pytest` (configured in `pyproject.toml`).
- Test files: `tests/test_*.py`; test functions: `test_*`.
- Add tests for new functionality where practical.

## Commit & Pull Request Guidelines
- Use clear, imperative commit messages (e.g., "Add feature X").
- PRs should describe behavior changes and include tests for new features.

## Security & Configuration Tips
- Avoid storing secrets in the repo; configuration belongs in user config files or environment variables.

## KI-CLI Workspace Integration

Dieses Projekt ist Teil des zentralen KI-Workspaces. Nutze diese Befehle:

```bash
# FAQ für schnellen Kontext (Token-sparend!)
ki-workspace faq --json

# Projekt-Status und Issues
ki-workspace status {name}
ki-workspace issues {name} --json
ki-workspace sync {name}      # Von Codacy holen

# Issue-Review Workflow
ki-workspace faq issue_review_workflow    # Workflow lesen
ki-workspace recommend-ignore <ID> -c <CATEGORY> -r "Grund" --reviewer codex
```

**Kategorien:** `accepted_use`, `false_positive`, `not_exploitable`, `test_code`, `external_code`

**Wichtig:** Wenn `ki_recommendation` bereits gesetzt → Issue NICHT erneut bewerten!
"""

GITIGNORE_PYTHON = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# Virtual environments
.venv/
venv/
ENV/

# Distribution / packaging
dist/
build/
*.egg-info/
*.egg

# IDE
.idea/
.vscode/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Misc
*.log
.DS_Store
Thumbs.db

# Environment variables
.env
.env.local

# Jupyter
.ipynb_checkpoints/
"""

POLYFORM_NC_LICENSE = """# PolyForm Noncommercial License 1.0.0

<https://polyformproject.org/licenses/noncommercial/1.0.0>

## Acceptance

In order to get any license under these terms, you must agree
to them as both strict obligations and conditions to all
your licenses.

## Copyright License

The licensor grants you a copyright license for the
software to do everything you might do with the software
that would otherwise infringe the licensor's copyright
in it for any permitted purpose.  However, you may
only distribute the software according to [Distribution
License](#distribution-license) and make changes or new works
based on the software according to [Changes and New Works
License](#changes-and-new-works-license).

## Distribution License

The licensor grants you an additional copyright license
to distribute copies of the software.  Your license
to distribute covers distributing the software with
changes and new works permitted by [Changes and New Works
License](#changes-and-new-works-license).

## Notices

You must ensure that anyone who gets a copy of any part of
the software from you also gets a copy of these terms or the
URL for them above, as well as copies of any plain-text lines
beginning with `Required Notice:` that the licensor provided
with the software.  For example:

> Required Notice: Copyright Yoyodyne, Inc. (http://example.com)

## Changes and New Works License

The licensor grants you an additional copyright license to
make changes and new works based on the software for any
permitted purpose.

## Patent License

The licensor grants you a patent license for the software that
covers patent claims the licensor can license, or becomes able
to license, that you would infringe by using the software.

## Noncommercial Purposes

Any noncommercial purpose is a permitted purpose.

## Personal Uses

Personal use for research, experiment, and testing for
the benefit of public knowledge, personal study, private
entertainment, hobby projects, amateur pursuits, or religious
observance, without any anticipated commercial application,
is use for a permitted purpose.

## Noncommercial Organizations

Use by any charitable organization, educational institution,
public research organization, public safety or health
organization, environmental protection organization,
or government institution is use for a permitted purpose
regardless of the source of funding or obligations resulting
from the funding.

## Fair Use

You may have "fair use" rights for the software under the
law. These terms do not limit them.

## No Other Rights

These terms do not allow you to sublicense or transfer any of
your licenses to anyone else, or prevent the licensor from
granting licenses to anyone else.  These terms do not imply
any other licenses.

## Patent Defense

If you make any written claim that the software infringes or
contributes to infringement of any patent, your patent license
for the software granted under these terms ends immediately. If
your company makes such a claim, your patent license ends
immediately for work on behalf of your company.

## Violations

The first time you are notified in writing that you have
violated any of these terms, or done anything with the software
not covered by your licenses, your licenses can nonetheless
continue if you come into full compliance with these terms,
and take practical steps to correct past violations, within
32 days of receiving notice.  Otherwise, all your licenses
end immediately.

## No Liability

***As far as the law allows, the software comes as is, without
any warranty or condition, and the licensor will not be liable
to you for any damages arising out of these terms or the use
or nature of the software, under any kind of legal claim.***

## Definitions

The **licensor** is the individual or entity offering these
terms, and the **software** is the software the licensor makes
available under these terms.

**You** refers to the individual or entity agreeing to these
terms.

**Your company** is any legal entity, sole proprietorship,
or other kind of organization that you work for, plus all
organizations that have control over, are under the control of,
or are under common control with that organization.  **Control**
means ownership of substantially all the assets of an entity,
or the power to direct its management and policies by vote,
contract, or otherwise.  Control can be direct or indirect.

**Your licenses** are all the licenses granted to you for the
software under these terms.

**Use** means anything you do with the software requiring one
of your licenses.
"""


class ProjectInitializer:
    """Erstellt neue Projekte mit Standard-Struktur."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._load_settings()

    def _load_settings(self) -> None:
        """Lädt Settings aus der Datenbank."""
        self.base_path = self.db.get_setting("project_base_path") or os.path.expanduser(
            "~/projekte"
        )
        self.archive_path = self.db.get_setting("project_archive_path") or os.path.join(
            self.base_path, "archiv"
        )
        self.github_org = self.db.get_setting("github_org") or "goettemar"
        self.github_provider = self.db.get_setting("github_provider") or "gh"

    def create_project(
        self,
        name: str,
        description: str = "",
        status: str = "alpha",
        create_github: bool = True,
        connect_codacy: bool = True,
    ) -> dict:
        """
        Erstellt ein neues Projekt mit kompletter Struktur.

        Args:
            name: Projektname (z.B. cindergrace_mein_projekt)
            description: Kurze Beschreibung
            status: alpha, beta oder stable
            create_github: GitHub Repo erstellen
            connect_codacy: Codacy-Verbindung herstellen

        Returns:
            Dict mit Ergebnis und Details
        """
        result = {
            "success": False,
            "name": name,
            "path": "",
            "github_url": "",
            "errors": [],
            "steps": [],
        }

        # Validierung
        if not name:
            result["errors"].append("Projektname darf nicht leer sein")
            return result

        # Pfade
        project_path = Path(self.base_path) / name
        result["path"] = str(project_path)

        # 1. Ordner erstellen
        try:
            if project_path.exists():
                result["errors"].append(f"Ordner existiert bereits: {project_path}")
                return result

            project_path.mkdir(parents=True)
            result["steps"].append(f"✅ Ordner erstellt: {project_path}")
        except Exception as e:
            result["errors"].append(f"Ordner-Fehler: {e}")
            return result

        # 2. Projektstruktur erstellen
        try:
            self._create_structure(project_path, name, description, status)
            result["steps"].append("✅ Projektstruktur erstellt")
        except Exception as e:
            result["errors"].append(f"Struktur-Fehler: {e}")
            return result

        # 3. Git initialisieren
        try:
            self._init_git(project_path)
            result["steps"].append("✅ Git Repository initialisiert")
        except Exception as e:
            result["errors"].append(f"Git-Fehler: {e}")
            return result

        # 4. GitHub Repo erstellen
        if create_github:
            try:
                github_url = self._create_github_repo(name, description)
                result["github_url"] = github_url
                result["steps"].append(f"✅ GitHub Repo erstellt: {github_url}")
            except Exception as e:
                result["errors"].append(f"GitHub-Fehler: {e}")
                # Weitermachen, nicht abbrechen

        # 5. Erster Commit und Push
        try:
            self._initial_commit_and_push(project_path, create_github)
            result["steps"].append("✅ Erster Commit und Push")
        except Exception as e:
            result["errors"].append(f"Commit/Push-Fehler: {e}")

        # 6. In Workspace-DB eintragen
        try:
            self._add_to_workspace(name, str(project_path), description, connect_codacy)
            result["steps"].append("✅ In Workspace eingetragen")
        except Exception as e:
            result["errors"].append(f"Workspace-Fehler: {e}")

        result["success"] = len(result["errors"]) == 0
        return result

    def _create_structure(self, path: Path, name: str, description: str, status: str) -> None:
        """Erstellt die Projektstruktur."""
        # Modul-Name (Unterstriche statt Bindestriche)
        module_name = name.replace("-", "_")
        package_name = name.replace("_", "-")

        # Template-Variablen
        vars = {
            "name": name,
            "module_name": module_name,
            "package_name": package_name,
            "description": description or f"{name} - Ein Python Projekt",
            "github_org": self.github_org,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "badge": ProjectStatus.get_badge(status),
            "warning": ProjectStatus.get_warning(status),
        }

        # Ordner erstellen
        (path / "src" / module_name).mkdir(parents=True)
        (path / "tests").mkdir()

        # Dateien erstellen
        (path / "README.md").write_text(README_TEMPLATE.format(**vars), encoding="utf-8")
        (path / "CHANGELOG.md").write_text(CHANGELOG_TEMPLATE.format(**vars), encoding="utf-8")
        (path / "LICENSE").write_text(POLYFORM_NC_LICENSE, encoding="utf-8")
        (path / ".gitignore").write_text(GITIGNORE_PYTHON, encoding="utf-8")
        (path / "pyproject.toml").write_text(PYPROJECT_TEMPLATE.format(**vars), encoding="utf-8")
        (path / "src" / module_name / "__init__.py").write_text(
            INIT_PY_TEMPLATE.format(**vars), encoding="utf-8"
        )
        (path / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (path / "tests" / f"test_{module_name}.py").write_text(
            f'"""Tests für {name}."""\n\n\ndef test_import():\n    """Test ob Import funktioniert."""\n    from {module_name} import __version__\n    assert __version__ == "0.1.0"\n',
            encoding="utf-8",
        )
        # Projekt-FAQ für KI-Assistenten
        (path / ".ki-faq.json").write_text(PROJECT_FAQ_TEMPLATE.format(**vars), encoding="utf-8")
        # AGENTS.md für Codex CLI und andere KI-Assistenten
        (path / "AGENTS.md").write_text(AGENTS_MD_TEMPLATE.format(**vars), encoding="utf-8")

    def _init_git(self, path: Path) -> None:
        """Initialisiert Git Repository."""
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)

    def _create_github_repo(self, name: str, description: str) -> str:
        """Erstellt GitHub Repository."""
        cmd = [
            "gh",
            "repo",
            "create",
            name,
            "--public",
            "--description",
            description or f"{name} - Ein Python Projekt",
            "--source",
            ".",
            "--remote",
            "origin",
        ]

        # Muss im Projektverzeichnis ausgeführt werden
        project_path = Path(self.base_path) / name
        subprocess.run(cmd, cwd=project_path, check=True, capture_output=True)

        return f"https://github.com/{self.github_org}/{name}"

    def _initial_commit_and_push(self, path: Path, push: bool = True) -> None:
        """Erster Commit und Push."""
        subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit - Projektstruktur"],
            cwd=path,
            check=True,
            capture_output=True,
        )

        if push:
            # Aktuellen Branch-Namen ermitteln (master oder main)
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=path,
                capture_output=True,
                text=True,
            )
            branch = result.stdout.strip() or "master"

            subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=path,
                check=True,
                capture_output=True,
            )

    def _add_to_workspace(
        self, name: str, path: str, description: str, connect_codacy: bool
    ) -> None:
        """Fügt Projekt zur Workspace-DB hinzu."""
        from core.database import Project

        # Initial-Phase holen
        phases = self.db.get_all_phases()
        next((p for p in phases if p.name == "initial"), None)
        dev_phase = next((p for p in phases if p.name == "development"), None)

        # Entwicklungs-Phase als Standard (Initial ist abgeschlossen)
        phase_id = dev_phase.id if dev_phase else None

        project = Project(
            name=name,
            path=path,
            git_remote=f"https://github.com/{self.github_org}/{name}.git",
            codacy_provider=self.github_provider if connect_codacy else None,
            codacy_org=self.github_org if connect_codacy else None,
            phase_id=phase_id,
        )

        self.db.create_project(project)

    def archive_project(self, project_id: int) -> dict:
        """
        Archiviert ein Projekt.

        Hinweis: GitHub Repo muss manuell gelöscht werden (2FA erforderlich).

        Args:
            project_id: Projekt-ID

        Returns:
            Dict mit Ergebnis
        """
        result = {
            "success": False,
            "steps": [],
            "errors": [],
            "github_url": None,  # URL für manuelles Löschen
        }

        project = self.db.get_project(project_id)
        if not project:
            result["errors"].append("Projekt nicht gefunden")
            return result

        # GitHub URL merken für Hinweis
        if project.codacy_org:
            result["github_url"] = f"https://github.com/{project.codacy_org}/{project.name}"

        # 1. Ordner ins Archiv verschieben
        if project.path and Path(project.path).exists():
            try:
                archive_dest = Path(self.archive_path) / project.name
                archive_dest.parent.mkdir(parents=True, exist_ok=True)

                if archive_dest.exists():
                    # Altes Archiv löschen
                    shutil.rmtree(archive_dest)

                shutil.move(project.path, archive_dest)
                result["steps"].append(f"✅ Ordner verschoben: {archive_dest}")
            except Exception as e:
                result["errors"].append(f"Verschieben-Fehler: {e}")

        # 2. DB-Eintrag archivieren
        try:
            self.db.archive_project(project_id)
            result["steps"].append("✅ Projekt archiviert in DB")
        except Exception as e:
            result["errors"].append(f"DB-Fehler: {e}")

        result["success"] = len(result["errors"]) == 0
        return result
