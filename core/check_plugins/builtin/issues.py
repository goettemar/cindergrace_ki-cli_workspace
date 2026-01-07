"""Codacy issue checks."""

from core.check_plugins.base import BaseCheck, CheckResult


class CriticalIssuesCheck(BaseCheck):
    """Check for open Critical issues."""

    name = "Critical Issues"
    description = "Checks for open Critical priority issues"
    category = "issues"
    default_phases = [3, 4]  # Testing and Final

    def run(self, project_path: str, db=None, project=None, **kwargs) -> CheckResult:
        if not db or not project:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No DB/project (skipped)",
                severity="info",
            )

        issues = db.get_issues(
            project_id=project.id,
            priority="Critical",
            status="open",
            is_false_positive=False,
        )
        count = len(issues)

        if count == 0:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No Critical issues",
                severity="error",
            )

        return CheckResult(
            name=self.name,
            passed=False,
            message=f"{count} Critical issue(s) found",
            severity="error",
        )


class HighIssuesCheck(BaseCheck):
    """Check for open High issues."""

    name = "High Issues"
    description = "Checks for open High priority issues"
    category = "issues"
    default_phases = [4]  # Only Final

    def run(self, project_path: str, db=None, project=None, **kwargs) -> CheckResult:
        if not db or not project:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No DB/project (skipped)",
                severity="info",
            )

        issues = db.get_issues(
            project_id=project.id,
            priority="High",
            status="open",
            is_false_positive=False,
        )
        count = len(issues)

        if count == 0:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No High issues",
                severity="warning",
            )

        return CheckResult(
            name=self.name,
            passed=False,
            message=f"{count} High issue(s) found",
            severity="warning",
        )
