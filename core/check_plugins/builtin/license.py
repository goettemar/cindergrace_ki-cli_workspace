"""LICENSE file check."""

from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class LicenseCheck(BaseCheck):
    """Check if a LICENSE file exists."""

    name = "LICENSE"
    description = "Checks for LICENSE, LICENSE.md, LICENSE.txt"
    category = "files"
    default_phases = [2, 3, 4]  # Not required in Initial phase

    default_params = {
        "allowed_names": ["LICENSE", "LICENSE.md", "LICENSE.txt", "LIZENZ", "MIT-LICENSE"],
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        for name in self.params["allowed_names"]:
            if (path / name).exists():
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{name} found",
                    severity="error",
                )

        return CheckResult(
            name=self.name,
            passed=False,
            message="No LICENSE file found",
            severity="error",
        )
