"""
Codacy API Synchronisation.

Direkte Integration mit der Codacy REST API für autonomen Sync.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from core.database import DatabaseManager, Project

logger = logging.getLogger(__name__)

# Codacy API Base URL
CODACY_API_BASE = "https://app.codacy.com/api/v3"


class CodacySync:
    """Synchronisiert Issues von Codacy REST API in die lokale Datenbank."""

    def __init__(self, api_token: str | None = None):
        """
        Initialisiert den Sync-Client.

        Args:
            api_token: Codacy API Token (oder aus CODACY_API_TOKEN env)
        """
        self.api_token = api_token or os.environ.get("CODACY_API_TOKEN")
        if not self.api_token:
            logger.warning("Kein CODACY_API_TOKEN gesetzt")

    def _headers(self) -> dict[str, str]:
        """Gibt die API-Header zurück."""
        return {
            "api-token": self.api_token or "",
            "Accept": "application/json",
        }

    def _fetch_paginated(
        self, url: str, params: dict | None = None, max_items: int = 500
    ) -> list[dict]:
        """
        Holt paginierte Daten von der API.

        Args:
            url: API Endpoint URL
            params: Query-Parameter
            max_items: Maximale Anzahl Items

        Returns:
            Liste aller Items
        """
        if params is None:
            params = {}

        all_items = []
        params["limit"] = min(100, max_items)
        cursor = None

        while len(all_items) < max_items:
            if cursor:
                params["cursor"] = cursor

            try:
                response = requests.get(url, headers=self._headers(), params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                logger.error(f"API-Fehler: {e}")
                break
            except ValueError as e:
                logger.error(f"JSON-Fehler: {e}")
                break

            items = data.get("data", [])
            if not items:
                break

            all_items.extend(items)

            # Pagination
            pagination = data.get("pagination", {})
            cursor = pagination.get("cursor")
            if not cursor or len(items) < params["limit"]:
                break

        return all_items[:max_items]

    def fetch_srm_items(
        self, provider: str, org: str, repo: str, statuses: list[str] | None = None
    ) -> list[dict]:
        """
        Holt Security/SRM Items von Codacy.

        Args:
            provider: Git Provider (gh, gl, bb)
            org: Organisation/Owner
            repo: Repository Name
            statuses: Filter nach Status (OnTrack, DueSoon, Overdue, etc.)

        Returns:
            Liste der SRM Items
        """
        url = f"{CODACY_API_BASE}/organizations/{provider}/{org}/srm/items"
        params = {"repositories": repo}

        if statuses:
            params["statuses"] = ",".join(statuses)

        return self._fetch_paginated(url, params)

    def fetch_quality_issues(self, provider: str, org: str, repo: str) -> list[dict]:
        """
        Holt Code Quality Issues von Codacy.

        Args:
            provider: Git Provider (gh, gl, bb)
            org: Organisation/Owner
            repo: Repository Name

        Returns:
            Liste der Quality Issues
        """
        url = (
            f"{CODACY_API_BASE}/analysis/organizations/{provider}/{org}"
            f"/repositories/{repo}/issues"
        )
        return self._fetch_paginated(url)

    def sync_project(self, db: DatabaseManager, project: Project) -> dict:
        """
        Synchronisiert alle Issues eines Projekts.

        Args:
            db: DatabaseManager Instanz
            project: Projekt-Objekt mit Codacy-Infos

        Returns:
            Dict mit Sync-Statistiken
        """
        from core.database import Issue

        if not self.api_token:
            return {"error": "Kein CODACY_API_TOKEN gesetzt", "synced": 0}

        if not project.codacy_provider or not project.codacy_org:
            return {"error": "Projekt hat keine Codacy-Konfiguration", "synced": 0}

        provider = project.codacy_provider
        org = project.codacy_org
        repo = project.name

        stats = {"srm": 0, "quality": 0, "errors": []}

        # Status-Mapping
        status_map = {
            "OnTrack": "open",
            "DueSoon": "open",
            "Overdue": "open",
            "ClosedOnTime": "fixed",
            "ClosedLate": "fixed",
            "Ignored": "ignored",
        }

        # Priority-Mapping für Quality Issues
        priority_map = {
            "Error": "Critical",
            "High": "High",
            "Warning": "Medium",
            "Medium": "Medium",
            "Info": "Low",
            "Low": "Low",
        }

        # 1. SRM Items (Security) holen
        try:
            srm_items = self.fetch_srm_items(
                provider, org, repo, statuses=["OnTrack", "DueSoon", "Overdue"]
            )
            for item in srm_items:
                issue = Issue(
                    project_id=project.id,
                    external_id=item.get("id", ""),
                    priority=item.get("priority", "Medium"),
                    status=status_map.get(item.get("status", ""), "open"),
                    scan_type=item.get("scanType", "SAST"),
                    title=item.get("title", "")[:200],
                    message=item.get("title", ""),
                    category=item.get("securityCategory", ""),
                    created_at=self._parse_date(item.get("openedAt")),
                )
                db.upsert_issue(issue)
                stats["srm"] += 1
        except Exception as e:
            logger.error(f"SRM-Sync Fehler: {e}")
            stats["errors"].append(f"SRM: {e}")

        # 2. Quality Issues holen
        try:
            quality_items = self.fetch_quality_issues(provider, org, repo)
            for item in quality_items:
                pattern_info = item.get("patternInfo", {})
                tool_info = item.get("toolInfo", {})
                level = pattern_info.get("severityLevel", "Medium")

                issue = Issue(
                    project_id=project.id,
                    external_id=item.get("issueId", ""),
                    priority=priority_map.get(level, "Medium"),
                    status="open",
                    scan_type="SAST",
                    title=item.get("message", "")[:200],
                    message=item.get("message", ""),
                    file_path=item.get("filePath", ""),
                    line_number=item.get("lineNumber", 0),
                    tool=tool_info.get("name", ""),
                    rule=pattern_info.get("id", ""),
                    category=pattern_info.get("category", ""),
                )
                db.upsert_issue(issue)
                stats["quality"] += 1
        except Exception as e:
            logger.error(f"Quality-Sync Fehler: {e}")
            stats["errors"].append(f"Quality: {e}")

        # Sync-Zeit aktualisieren
        db.update_project_sync_time(project.id)

        stats["synced"] = stats["srm"] + stats["quality"]
        return stats

    def mark_ignored_in_codacy(
        self, provider: str, org: str, repo: str, result_data_id: str, reason: str
    ) -> bool:
        """
        Markiert ein Issue in Codacy als ignoriert.

        Args:
            provider: Git Provider
            org: Organisation
            repo: Repository
            result_data_id: Codacy Result Data ID
            reason: Begründung

        Returns:
            True bei Erfolg
        """
        url = (
            f"{CODACY_API_BASE}/analysis/organizations/{provider}/{org}"
            f"/repositories/{repo}/issues/{result_data_id}"
        )

        try:
            response = requests.patch(
                url,
                headers=self._headers(),
                json={"status": "Ignored", "reason": reason},
                timeout=30,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Fehler beim Ignorieren: {e}")
            return False

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parst ein ISO-Datum."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None
