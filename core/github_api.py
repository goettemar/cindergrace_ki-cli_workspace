"""
GitHub API Integration.

Lädt Repositories und Issues von GitHub.
Unterstützt sowohl manuellen Token als auch gh CLI.
"""

from __future__ import annotations

import logging
import subprocess
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from core.database import DatabaseManager

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def get_gh_cli_token() -> str | None:
    """Holt den Token von der gh CLI (falls installiert und eingeloggt)."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def get_gh_cli_user() -> str | None:
    """Holt den eingeloggten User von gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def gh_cli_available() -> bool:
    """Prüft ob gh CLI installiert und eingeloggt ist."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def get_gh_cli_status() -> dict:
    """Holt detaillierten Status von gh CLI."""
    status = {
        "available": False,
        "logged_in": False,
        "user": None,
        "scopes": [],
        "protocol": None,
    }

    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status["available"] = True

        if result.returncode == 0:
            status["logged_in"] = True
            output = result.stderr + result.stdout  # gh gibt auf stderr aus

            # User extrahieren
            for line in output.split("\n"):
                if "Logged in to" in line and "account" in line:
                    # Format: "✓ Logged in to github.com account USERNAME"
                    parts = line.split("account")
                    if len(parts) > 1:
                        user_part = parts[1].strip().split()[0]
                        status["user"] = user_part.strip("()")

                if "Token scopes:" in line:
                    scopes_part = line.split("Token scopes:")[1].strip()
                    status["scopes"] = [s.strip().strip("'") for s in scopes_part.split(",")]

                if "Git operations protocol:" in line:
                    status["protocol"] = line.split(":")[1].strip()

    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return status


def run_gh_command(args: list[str], timeout: int = 30) -> tuple[bool, str]:
    """Führt einen gh CLI Befehl aus."""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout if result.returncode == 0 else result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except FileNotFoundError:
        return False, "gh CLI nicht installiert"
    except subprocess.SubprocessError as e:
        return False, str(e)


class GitHubAPI:
    """GitHub API Client für Repository- und Issue-Management."""

    def __init__(self, token: str | None = None, db: DatabaseManager | None = None):
        """
        Initialisiert den GitHub API Client.

        Args:
            token: GitHub Personal Access Token
            db: DatabaseManager für Token-Lookup
        """
        self._db = db
        self._token = token
        self._token_loaded = False

    @property
    def token(self) -> str | None:
        """Lädt den GitHub Token (lazy, mit Caching)."""
        if self._token:
            return self._token

        if not self._token_loaded:
            self._token_loaded = True

            # 1. Aus Datenbank
            if self._db:
                db_token = self._db.get_setting("github_token")
                if db_token:
                    self._token = db_token
                    return self._token

            # 2. Von gh CLI (falls installiert)
            cli_token = get_gh_cli_token()
            if cli_token:
                logger.info("Nutze gh CLI Token")
                self._token = cli_token
                return self._token

            logger.warning("Kein GitHub Token gesetzt")

        return self._token

    def set_token(self, token: str) -> None:
        """Setzt den GitHub Token (und speichert in DB)."""
        self._token = token
        self._token_loaded = True
        if self._db and token:
            self._db.set_setting(
                "github_token",
                token,
                encrypt=True,
                description="GitHub Personal Access Token",
            )

    def _headers(self) -> dict[str, str]:
        """Gibt die API-Header zurück."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_user(self) -> dict | None:
        """Holt den aktuellen User."""
        if not self.token:
            return None

        try:
            response = requests.get(
                f"{GITHUB_API_BASE}/user",
                headers=self._headers(),
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"GitHub API Fehler: {e}")
            return None

    def get_repos(self, include_private: bool = True) -> list[dict]:
        """
        Holt alle Repositories des Users.

        Args:
            include_private: Auch private Repos einbeziehen

        Returns:
            Liste der Repositories
        """
        if not self.token:
            return []

        repos = []
        page = 1
        per_page = 100

        while True:
            try:
                response = requests.get(
                    f"{GITHUB_API_BASE}/user/repos",
                    headers=self._headers(),
                    params={
                        "per_page": per_page,
                        "page": page,
                        "sort": "updated",
                        "direction": "desc",
                        "affiliation": "owner,collaborator,organization_member",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for repo in data:
                    if not include_private and repo.get("private"):
                        continue
                    repos.append(
                        {
                            "name": repo["name"],
                            "full_name": repo["full_name"],
                            "owner": repo["owner"]["login"],
                            "private": repo["private"],
                            "html_url": repo["html_url"],
                            "clone_url": repo["clone_url"],
                            "ssh_url": repo["ssh_url"],
                            "description": repo.get("description") or "",
                            "updated_at": repo["updated_at"],
                            "archived": repo.get("archived", False),
                        }
                    )

                if len(data) < per_page:
                    break
                page += 1

            except requests.RequestException as e:
                logger.error(f"GitHub API Fehler: {e}")
                break

        return repos

    def get_issues(self, owner: str, repo: str, state: str = "open") -> list[dict]:
        """
        Holt Issues eines Repositories.

        Args:
            owner: Repository Owner
            repo: Repository Name
            state: Issue-Status (open, closed, all)

        Returns:
            Liste der Issues
        """
        if not self.token:
            return []

        issues = []
        page = 1
        per_page = 100

        while True:
            try:
                response = requests.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                    headers=self._headers(),
                    params={
                        "per_page": per_page,
                        "page": page,
                        "state": state,
                        "sort": "updated",
                        "direction": "desc",
                    },
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for issue in data:
                    # Pull Requests überspringen (sind auch in /issues)
                    if "pull_request" in issue:
                        continue

                    issues.append(
                        {
                            "number": issue["number"],
                            "title": issue["title"],
                            "body": issue.get("body") or "",
                            "state": issue["state"],
                            "html_url": issue["html_url"],
                            "created_at": issue["created_at"],
                            "updated_at": issue["updated_at"],
                            "labels": [label["name"] for label in issue.get("labels", [])],
                            "assignees": [a["login"] for a in issue.get("assignees", [])],
                            "user": issue["user"]["login"],
                        }
                    )

                if len(data) < per_page:
                    break
                page += 1

            except requests.RequestException as e:
                logger.error(f"GitHub API Fehler: {e}")
                break

        return issues

    def test_connection(self) -> tuple[bool, str]:
        """
        Testet die GitHub-Verbindung.

        Returns:
            (success, message)
        """
        if not self.token:
            return False, "Kein Token konfiguriert"

        user = self.get_user()
        if user:
            return True, f"Verbunden als: {user.get('login')}"
        return False, "Verbindung fehlgeschlagen"
