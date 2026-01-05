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

    def __init__(self, api_token: str | None = None, db: DatabaseManager | None = None):
        """
        Initialisiert den Sync-Client.

        Args:
            api_token: Codacy API Token (oder aus DB/CODACY_API_TOKEN env)
            db: DatabaseManager für Token-Lookup
        """
        self._db = db
        self._api_token = api_token
        self._token_loaded = False

    @property
    def api_token(self) -> str | None:
        """Lädt den API-Token (lazy, mit Caching)."""
        if self._api_token:
            return self._api_token

        if not self._token_loaded:
            self._token_loaded = True
            # 1. Aus Datenbank (verschlüsselt)
            if self._db:
                db_token = self._db.get_setting("codacy_api_token")
                if db_token:
                    self._api_token = db_token
                    return self._api_token

            # 2. Aus Umgebungsvariable
            env_token = os.environ.get("CODACY_API_TOKEN")
            if env_token:
                self._api_token = env_token
                return self._api_token

            logger.warning("Kein CODACY_API_TOKEN gesetzt")

        return self._api_token

    def set_api_token(self, token: str) -> None:
        """Setzt den API-Token (und speichert in DB wenn verfügbar)."""
        self._api_token = token
        self._token_loaded = True
        if self._db and token:
            self._db.set_setting(
                "codacy_api_token",
                token,
                encrypt=True,
                description="Codacy API Token für Issue-Sync",
            )

    def _headers(self) -> dict[str, str]:
        """Gibt die API-Header zurück."""
        return {
            "api-token": self.api_token or "",
            "Accept": "application/json",
        }

    def _fetch_paginated_get(
        self, url: str, params: dict | None = None, max_items: int = 500
    ) -> list[dict]:
        """
        Holt paginierte Daten von der API (GET).

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
                logger.error(f"API-Fehler (GET): {e}")
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

    def _fetch_paginated_post(
        self, url: str, body: dict | None = None, max_items: int = 500
    ) -> list[dict]:
        """
        Holt paginierte Daten von der API (POST).

        Args:
            url: API Endpoint URL
            body: Request Body
            max_items: Maximale Anzahl Items

        Returns:
            Liste aller Items
        """
        if body is None:
            body = {}

        all_items = []
        cursor = None

        while len(all_items) < max_items:
            params = {"limit": min(100, max_items - len(all_items))}
            if cursor:
                params["cursor"] = cursor

            try:
                response = requests.post(
                    url,
                    headers={**self._headers(), "Content-Type": "application/json"},
                    params=params,
                    json=body,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException as e:
                logger.error(f"API-Fehler (POST): {e}")
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
        # Codacy SRM API endpoint - Organisations-Ebene mit Repository-Filter
        url = f"{CODACY_API_BASE}/organizations/{provider}/{org}/security/items/search"
        body = {"repositories": [repo]}
        if statuses:
            body["statuses"] = statuses

        items = self._fetch_paginated_post(url, body)

        # Fallback: Security-Issues über issues/search mit Security-Filter
        if not items:
            logger.info("SRM-Endpoint leer, versuche Security-Issues...")
            items = self.fetch_quality_issues(provider, org, repo, categories=["Security"])

        return items

    def fetch_quality_issues(
        self,
        provider: str,
        org: str,
        repo: str,
        categories: list[str] | None = None,
    ) -> list[dict]:
        """
        Holt Code Quality Issues von Codacy.

        Args:
            provider: Git Provider (gh, gl, bb)
            org: Organisation/Owner
            repo: Repository Name
            categories: Filter nach Kategorien (Security, ErrorProne, etc.)

        Returns:
            Liste der Quality Issues
        """
        url = (
            f"{CODACY_API_BASE}/analysis/organizations/{provider}/{org}"
            f"/repositories/{repo}/issues/search"
        )
        body = {}
        if categories:
            body["categories"] = categories

        return self._fetch_paginated_post(url, body)

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

        # 1. SRM Items (Security) holen - inkl. Ignored für False Positives
        try:
            srm_items = self.fetch_srm_items(
                provider,
                org,
                repo,
                statuses=["OnTrack", "DueSoon", "Overdue", "Ignored", "ClosedOnTime", "ClosedLate"],
            )
            for item in srm_items:
                codacy_status = item.get("status", "")
                # Prüfe ignored-Objekt (nicht nur Status), enthält Reason
                ignored_info = item.get("ignored")
                is_ignored = ignored_info is not None

                # Geschlossene Issues werden auch verarbeitet, um lokalen Status zu aktualisieren
                fp_reason = None
                if is_ignored:
                    fp_reason = ignored_info.get("reason", "Von Codacy als Ignored markiert")

                issue = Issue(
                    project_id=project.id,
                    external_id=item.get("id", ""),
                    codacy_result_id=item.get("itemSourceId", ""),  # Für API-Aufrufe
                    priority=item.get("priority", "Medium"),
                    status=status_map.get(codacy_status, "open"),
                    scan_type=item.get("scanType", "SAST"),
                    title=item.get("title", "")[:200],
                    message=item.get("title", ""),
                    category=item.get("securityCategory", ""),
                    created_at=self._parse_date(item.get("openedAt")),
                    is_false_positive=is_ignored,
                    fp_reason=fp_reason,
                )
                db.upsert_issue(issue)
                stats["srm"] += 1
        except Exception as e:
            logger.error(f"SRM-Sync Fehler: {e}")
            stats["errors"].append(f"SRM: {e}")

        # 2. Quality Issues holen (nur wenn nicht bereits als SRM vorhanden)
        # Sammle alle resultDataIds der SRM-Items für Deduplizierung
        srm_result_ids = {
            item.get("itemSourceId") for item in srm_items if item.get("itemSourceId")
        }

        try:
            quality_items = self.fetch_quality_issues(provider, org, repo)
            for item in quality_items:
                result_data_id = str(item.get("resultDataId", ""))

                # Skip wenn bereits als SRM-Issue vorhanden (Deduplizierung)
                if result_data_id and result_data_id in srm_result_ids:
                    # Update nur file_path/line_number/tool im existierenden SRM-Issue
                    db.update_issue_details_by_result_id(
                        project_id=project.id,
                        codacy_result_id=result_data_id,
                        file_path=item.get("filePath", ""),
                        line_number=item.get("lineNumber", 0),
                        tool=item.get("toolInfo", {}).get("name", ""),
                        rule=item.get("patternInfo", {}).get("id", ""),
                    )
                    continue

                pattern_info = item.get("patternInfo", {})
                tool_info = item.get("toolInfo", {})
                level = pattern_info.get("severityLevel", "Medium")

                issue = Issue(
                    project_id=project.id,
                    external_id=item.get("issueId", ""),
                    codacy_result_id=result_data_id,
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

        # Sync-Zeit und Cache aktualisieren
        db.update_project_sync_time(project.id)
        db.update_project_cache(project.id)

        stats["synced"] = stats["srm"] + stats["quality"]
        return stats

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parst ein ISO-Datum."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            return None
