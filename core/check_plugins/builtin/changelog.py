"""CHANGELOG file check."""

from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class ChangelogCheck(BaseCheck):
    """Check if a CHANGELOG file exists."""

    name = "CHANGELOG"
    description = "Checks for CHANGELOG.md or HISTORY.md"
    category = "files"
    default_phases = [3, 4]  # Only in Testing and Final

    default_params = {
        "allowed_names": ["CHANGELOG.md", "CHANGELOG.txt", "CHANGELOG", "HISTORY.md"],
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        for name in self.params["allowed_names"]:
            if (path / name).exists():
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{name} found",
                    severity="warning",
                )

        return CheckResult(
            name=self.name,
            passed=False,
            message="No CHANGELOG found",
            severity="warning",
        )
