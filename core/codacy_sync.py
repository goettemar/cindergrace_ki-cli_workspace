"""Codacy Synchronisation mit einfacher Issue-API."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)


class CodacySync:
    """Kleine Hilfsklasse zum Abruf und Aktualisieren von Codacy-Issues."""

    def __init__(self, api_token: str | None = None) -> None:
        """Initialisiert den Client mit API-Token oder Umgebungsvariable."""
        self.api_token = api_token or os.environ.get("CODACY_API_TOKEN")

    def sync_issues(self, provider: str, org: str, repo: str) -> list[dict[str, Any]]:
        """Ruft Issues von der Codacy API ab und gibt sie als Liste zurueck."""
        url = (
            "https://app.codacy.com/api/v3/analysis/organizations/"
            f"{provider}/{org}/repositories/{repo}/issues"
        )
        headers = {"api-token": self.api_token or ""}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            logger.exception("Fehler beim Abruf der Codacy-Issues: %s", exc)
            return []
        except ValueError as exc:
            logger.exception("Antwort von Codacy ist kein gueltiges JSON: %s", exc)
            return []

        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            data = payload.get("data", [])
            return data if isinstance(data, list) else []

        logger.error("Unerwartetes Format der Codacy-Antwort: %r", type(payload))
        return []

    def mark_ignored(self, provider: str, org: str, repo: str, issue_id: str, reason: str) -> bool:
        """Markiert ein Codacy-Issue als ignoriert und gibt Erfolg zurueck."""
        url = (
            "https://app.codacy.com/api/v3/analysis/organizations/"
            f"{provider}/{org}/repositories/{repo}/issues/{issue_id}/ignore"
        )
        headers = {"api-token": self.api_token or ""}
        payload = {"reason": reason}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Fehler beim Ignorieren des Issues: %s", exc)
            return False

        return True
