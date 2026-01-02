"""
MCP-basierte Codacy Synchronisation.

Dieses Modul wird von Claude direkt aufgerufen um Daten aus Codacy MCP
in die lokale Datenbank zu synchronisieren.
"""

import logging
from datetime import datetime

from core.database import DatabaseManager, Issue

logger = logging.getLogger(__name__)


def sync_srm_items(db: DatabaseManager, project_id: int, items: list[dict]) -> int:
    """
    Synchronisiert Security/SRM Items in die Datenbank.

    Args:
        db: DatabaseManager Instanz
        project_id: ID des Projekts in unserer DB
        items: Liste von SRM Items aus Codacy MCP

    Returns:
        Anzahl der synchronisierten Items
    """
    count = 0
    for item in items:
        # Status-Mapping: Codacy SRM → unsere DB
        status_map = {
            "OnTrack": "open",
            "DueSoon": "open",
            "Overdue": "open",
            "ClosedOnTime": "fixed",
            "ClosedLate": "fixed",
            "Ignored": "ignored",
        }

        issue = Issue(
            project_id=project_id,
            external_id=item.get("id", ""),
            priority=item.get("priority", "Medium"),
            status=status_map.get(item.get("status", ""), "open"),
            scan_type=item.get("scanType", ""),
            title=item.get("title", ""),
            message=item.get("title", ""),  # SRM hat keine separate message
            category=item.get("securityCategory", ""),
            created_at=datetime.fromisoformat(item.get("openedAt", "").replace("Z", "+00:00"))
            if item.get("openedAt")
            else None,
        )
        db.upsert_issue(issue)
        count += 1

    return count


def sync_quality_issues(db: DatabaseManager, project_id: int, items: list[dict]) -> int:
    """
    Synchronisiert Quality Issues in die Datenbank.

    Args:
        db: DatabaseManager Instanz
        project_id: ID des Projekts in unserer DB
        items: Liste von Quality Issues aus Codacy MCP

    Returns:
        Anzahl der synchronisierten Items
    """
    count = 0
    for item in items:
        pattern_info = item.get("patternInfo", {})
        tool_info = item.get("toolInfo", {})

        # Severity-Mapping
        level = pattern_info.get("severityLevel", "Medium")
        priority_map = {"Error": "Critical", "High": "High", "Medium": "Medium", "Low": "Low"}

        issue = Issue(
            project_id=project_id,
            external_id=item.get("issueId", ""),
            priority=priority_map.get(level, "Medium"),
            status="open",
            scan_type="SAST",  # Quality issues sind meist SAST
            title=item.get("message", "")[:200],
            message=item.get("message", ""),
            file_path=item.get("filePath", ""),
            line_number=item.get("lineNumber", 0),
            tool=tool_info.get("name", ""),
            rule=pattern_info.get("id", ""),
            category=pattern_info.get("category", ""),
        )
        db.upsert_issue(issue)
        count += 1

    return count
