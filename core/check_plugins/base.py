"""
Base classes for the modular check system.

Each check is a separate class that inherits from BaseCheck.
Checks are auto-discovered from builtin/ and custom/ directories.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.database import DatabaseManager, Project


@dataclass
class CheckResult:
    """Result of a single check."""

    name: str
    passed: bool
    message: str
    severity: str = "warning"  # error, warning, info
    details: dict[str, Any] = field(default_factory=dict)


class BaseCheck(ABC):
    """
    Base class for all checks.

    To create a new check:
    1. Create a new file in builtin/ or custom/
    2. Create a class that inherits from BaseCheck
    3. Set name, description, category
    4. Implement the run() method
    5. The check is auto-discovered and available

    Example:
        class MyCheck(BaseCheck):
            name = "My Check"
            description = "Does something useful"
            category = "files"

            def run(self, project_path, db=None, project=None) -> CheckResult:
                # Your check logic here
                return CheckResult(self.name, True, "All good")
    """

    # Metadata (override in subclass)
    name: str = "Unnamed Check"
    description: str = ""
    category: str = "general"  # files, code, issues, git, quality, custom

    # Default phases where this check is active (can be overridden in config)
    # Phase IDs: 1=Initial, 2=Development, 3=Testing, 4=Final
    default_phases: list[int] = [1, 2, 3, 4]  # Active in all phases by default

    # Configurable parameters with defaults (can be overridden in config)
    default_params: dict[str, Any] = {}

    def __init__(self):
        """Initialize check with default params."""
        self.params = dict(self.default_params)

    def configure(self, params: dict[str, Any]) -> None:
        """Update params from config."""
        self.params.update(params)

    @abstractmethod
    def run(
        self,
        project_path: str,
        db: DatabaseManager | None = None,
        project: Project | None = None,
    ) -> CheckResult:
        """
        Execute the check.

        Args:
            project_path: Path to the project directory
            db: DatabaseManager instance (for checks that need DB access)
            project: Project object (for checks that need project metadata)

        Returns:
            CheckResult with passed status and message
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} '{self.name}'>"
