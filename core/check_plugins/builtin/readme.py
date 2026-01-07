"""README file checks."""

from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class ReadmeCheck(BaseCheck):
    """Check if a README file exists and has minimum content."""

    name = "README"
    description = "Checks for README.md with minimum content"
    category = "files"
    default_phases = [2, 3, 4]  # Not required in Initial phase

    default_params = {
        "allowed_names": ["README.md", "README.txt", "README", "README.rst"],
        "min_length": 50,
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        for name in self.params["allowed_names"]:
            readme_path = path / name
            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                if len(content.strip()) < self.params["min_length"]:
                    return CheckResult(
                        name=self.name,
                        passed=False,
                        message=f"{name} too short (< {self.params['min_length']} chars)",
                        severity="warning",
                    )
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{name} found",
                    severity="error",
                )

        return CheckResult(
            name=self.name,
            passed=False,
            message="No README file found",
            severity="error",
        )


class ReadmeEnglishCheck(BaseCheck):
    """Check if README is written in English (no German umlauts)."""

    name = "README English"
    description = "Checks README has no German characters"
    category = "files"
    default_phases = [3, 4]  # Only in Testing and Final

    default_params = {
        "german_chars": "äöüÄÖÜß",
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)
        readme_files = ["README.md", "README.txt", "README", "README.rst"]

        for rf in readme_files:
            readme_path = path / rf
            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                if any(c in content for c in self.params["german_chars"]):
                    return CheckResult(
                        name=self.name,
                        passed=False,
                        message=f"{rf} contains German characters",
                        severity="warning",
                    )
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{rf} is in English",
                    severity="warning",
                )

        return CheckResult(
            name=self.name,
            passed=True,
            message="No README found (skipped)",
            severity="info",
        )


class HobbyNoticeCheck(BaseCheck):
    """Check if README contains hobby/experimental project notice."""

    name = "Hobby Notice"
    description = "Checks for hobby/experimental disclaimer in README"
    category = "files"
    default_phases = [4]  # Only in Final phase

    default_params = {
        "keywords": [
            "hobby",
            "experimental",
            "experiment",
            "not a commercial",
            "no warranties",
            "no support",
            "personal project",
        ],
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)
        readme_files = ["README.md", "README.txt", "README", "README.rst"]

        for rf in readme_files:
            readme_path = path / rf
            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8", errors="ignore").lower()
                if any(kw.lower() in content for kw in self.params["keywords"]):
                    return CheckResult(
                        name=self.name,
                        passed=True,
                        message="Hobby/experimental notice found",
                        severity="warning",
                    )
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"{rf} missing hobby/experimental notice",
                    severity="warning",
                )

        return CheckResult(
            name=self.name,
            passed=True,
            message="No README found (skipped)",
            severity="info",
        )


class ReadmeStatusCheck(BaseCheck):
    """Check if README status matches project phase."""

    name = "README Status"
    description = "Checks **Status:** line matches project phase"
    category = "files"
    default_phases = [3, 4]  # Only in Testing and Final

    def run(self, project_path: str, db=None, project=None, **kwargs) -> CheckResult:
        import re

        path = Path(project_path)
        readme_files = ["README.md", "README.txt", "README", "README.rst"]
        status_pattern = re.compile(r"\*\*Status:\*\*\s*(\w+)", re.IGNORECASE)

        # Get expected phase name
        expected_phase = "Development"
        if project and project.phase_id and db:
            phase = db.get_phase(project.phase_id)
            if phase:
                expected_phase = phase.display_name

        for rf in readme_files:
            readme_path = path / rf
            if readme_path.exists():
                content = readme_path.read_text(encoding="utf-8", errors="ignore")
                match = status_pattern.search(content)

                if not match:
                    return CheckResult(
                        name=self.name,
                        passed=False,
                        message=f"No status line (expected: {expected_phase})",
                        severity="warning",
                    )

                found_status = match.group(1)
                if found_status.lower() == expected_phase.lower():
                    return CheckResult(
                        name=self.name,
                        passed=True,
                        message=f"Status in sync: {found_status}",
                        severity="warning",
                    )
                else:
                    return CheckResult(
                        name=self.name,
                        passed=False,
                        message=f"Status '{found_status}' != Phase '{expected_phase}'",
                        severity="warning",
                    )

        return CheckResult(
            name=self.name,
            passed=True,
            message="No README found (skipped)",
            severity="info",
        )
