"""Git-related checks."""

import subprocess
from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class GitStatusCheck(BaseCheck):
    """Check if Git repository is clean (no uncommitted changes)."""

    name = "Git Status"
    description = "Checks for uncommitted changes"
    category = "git"
    default_phases = [4]  # Only in Final phase

    def run(self, project_path: str, **kwargs) -> CheckResult:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=project_path,
            )

            if result.returncode != 0:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message="Not a Git repository",
                    severity="info",
                )

            if result.stdout.strip():
                lines = len(result.stdout.strip().split("\n"))
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"{lines} uncommitted change(s)",
                    severity="warning",
                )

            return CheckResult(
                name=self.name,
                passed=True,
                message="Repository clean",
                severity="warning",
            )

        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Skipped ({e})",
                severity="info",
            )


class GitignorePatternsCheck(BaseCheck):
    """Check if required patterns are in .gitignore."""

    name = "Gitignore Patterns"
    description = "Checks for required patterns in .gitignore"
    category = "git"
    default_phases = [3, 4]  # Testing and Final

    default_params = {
        "required_patterns": [],  # Configured via DB/settings
    }

    def run(self, project_path: str, db=None, **kwargs) -> CheckResult:
        import json

        path = Path(project_path)
        gitignore_path = path / ".gitignore"

        # Load required patterns from settings if not configured
        required_patterns = self.params.get("required_patterns", [])
        if not required_patterns and db:
            patterns_json = db.get_setting("gitignore_required_patterns") or "[]"
            try:
                required_patterns = json.loads(patterns_json)
            except json.JSONDecodeError:
                required_patterns = []

        if not required_patterns:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No patterns configured",
                severity="info",
            )

        if not gitignore_path.exists():
            return CheckResult(
                name=self.name,
                passed=False,
                message=f"No .gitignore ({len(required_patterns)} patterns missing)",
                severity="warning",
            )

        try:
            content = gitignore_path.read_text(encoding="utf-8", errors="ignore")
            lines = [line.strip() for line in content.splitlines()]
            gitignore_entries = [line for line in lines if line and not line.startswith("#")]

            missing = []
            for pattern in required_patterns:
                pattern_clean = pattern.strip()
                if not pattern_clean:
                    continue

                # Check variants (with/without leading slash, trailing slash)
                pattern_variants = [
                    pattern_clean,
                    pattern_clean.lstrip("/"),
                    pattern_clean.rstrip("/"),
                    pattern_clean.strip("/"),
                    pattern_clean + "/",
                    "/" + pattern_clean.lstrip("/"),
                ]
                found = any(v in gitignore_entries for v in pattern_variants)
                if not found:
                    missing.append(pattern_clean)

            if missing:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"Missing: {', '.join(missing)}",
                    severity="warning",
                )

            return CheckResult(
                name=self.name,
                passed=True,
                message=f"All {len(required_patterns)} patterns present",
                severity="warning",
            )

        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Could not read: {e}",
                severity="info",
            )
