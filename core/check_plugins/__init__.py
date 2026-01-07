"""
Modular Check System for Release Readiness.

Checks are auto-discovered from builtin/ and custom/ directories.
Configuration (which checks are active in which phase) is stored in DB.

Usage:
    from core.check_plugins import CheckRegistry, run_checks

    # Discover all checks
    CheckRegistry.discover()

    # Run checks for a project
    results = run_checks(db, project)
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import TYPE_CHECKING

from core.check_plugins.base import BaseCheck, CheckResult

if TYPE_CHECKING:
    from core.database import DatabaseManager, Project

__all__ = ["BaseCheck", "CheckResult", "CheckRegistry", "run_checks", "get_all_checks"]


class CheckRegistry:
    """
    Registry for all available checks.

    Checks are auto-discovered from builtin/ and custom/ directories.
    """

    _checks: dict[str, type[BaseCheck]] = {}
    _discovered: bool = False

    @classmethod
    def register(cls, check_class: type[BaseCheck]) -> type[BaseCheck]:
        """
        Register a check class.

        Can be used as decorator:
            @CheckRegistry.register
            class MyCheck(BaseCheck):
                ...
        """
        if not inspect.isabstract(check_class) and issubclass(check_class, BaseCheck):
            cls._checks[check_class.name] = check_class
        return check_class

    @classmethod
    def discover(cls, force: bool = False) -> None:
        """
        Auto-discover checks from builtin/ and custom/ directories.

        Args:
            force: Re-discover even if already done
        """
        if cls._discovered and not force:
            return

        checks_dir = Path(__file__).parent

        for folder in ["builtin", "custom"]:
            folder_path = checks_dir / folder
            if not folder_path.exists():
                continue

            for py_file in folder_path.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                module_name = f"core.check_plugins.{folder}.{py_file.stem}"
                try:
                    module = importlib.import_module(module_name)

                    # Find all BaseCheck subclasses in module
                    for _name, obj in inspect.getmembers(module, inspect.isclass):
                        if (
                            issubclass(obj, BaseCheck)
                            and obj is not BaseCheck
                            and not inspect.isabstract(obj)
                        ):
                            cls._checks[obj.name] = obj

                except Exception as e:
                    print(f"Warning: Could not load check module {module_name}: {e}")

        cls._discovered = True

    @classmethod
    def get(cls, name: str) -> type[BaseCheck] | None:
        """Get a check class by name."""
        cls.discover()
        return cls._checks.get(name)

    @classmethod
    def get_all(cls) -> dict[str, type[BaseCheck]]:
        """Get all registered checks."""
        cls.discover()
        return dict(cls._checks)

    @classmethod
    def get_by_category(cls, category: str) -> dict[str, type[BaseCheck]]:
        """Get checks filtered by category."""
        cls.discover()
        return {name: check for name, check in cls._checks.items() if check.category == category}

    @classmethod
    def clear(cls) -> None:
        """Clear registry (mainly for testing)."""
        cls._checks.clear()
        cls._discovered = False


def get_all_checks() -> list[dict]:
    """
    Get info about all available checks.

    Returns:
        List of dicts with name, description, category, default_phases
    """
    CheckRegistry.discover()
    checks = []

    for _name, check_cls in CheckRegistry.get_all().items():
        checks.append(
            {
                "name": check_cls.name,
                "description": check_cls.description,
                "category": check_cls.category,
                "default_phases": check_cls.default_phases,
                "params": check_cls.default_params,
            }
        )

    # Sort by category, then name
    checks.sort(key=lambda c: (c["category"], c["name"]))
    return checks


def run_checks(
    db: DatabaseManager,
    project: Project,
    phase_id: int | None = None,
) -> list[CheckResult]:
    """
    Run all checks that are active for the project's phase.

    Args:
        db: DatabaseManager instance
        project: Project to check
        phase_id: Override phase (default: project.phase_id)

    Returns:
        List of CheckResults
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    CheckRegistry.discover()

    # Determine phase
    current_phase = phase_id or project.phase_id or 1

    # Get check configuration from DB
    check_config = db.get_check_config()

    results = []
    checks_to_run = []

    for name, check_cls in CheckRegistry.get_all().items():
        # Get config for this check (or use defaults)
        config = check_config.get(name, {})
        enabled_phases = config.get("phases", check_cls.default_phases)
        params = config.get("params", {})

        # Skip if not active in current phase
        if current_phase not in enabled_phases:
            continue

        # Create check instance and configure
        check = check_cls()
        check.configure(params)
        checks_to_run.append(check)

    # Run checks in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_check = {
            executor.submit(
                check.run,
                project.path,
                db=db,
                project=project,
            ): check
            for check in checks_to_run
        }

        for future in as_completed(future_to_check):
            check = future_to_check[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                results.append(
                    CheckResult(
                        name=check.name,
                        passed=False,
                        message=f"Error: {e}",
                        severity="error",
                    )
                )

    # Sort by severity (errors first), then name
    severity_order = {"error": 0, "warning": 1, "info": 2}
    results.sort(key=lambda r: (severity_order.get(r.severity, 9), r.name))

    return results
