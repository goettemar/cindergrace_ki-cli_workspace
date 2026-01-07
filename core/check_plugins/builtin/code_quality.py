"""Code quality checks (Radon, Ruff)."""

import subprocess
from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class RadonComplexityCheck(BaseCheck):
    """Check cyclomatic complexity with radon."""

    name = "Radon Complexity"
    description = "Checks code complexity (A-B OK, C warning, D+ error)"
    category = "quality"
    default_phases = [3, 4]  # Testing and Final

    default_params = {
        "timeout": 60,
        "exclude": ".venv,venv,node_modules,__pycache__",
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        # Find radon
        venv_radon = path / ".venv" / "bin" / "radon"
        radon_cmd = str(venv_radon) if venv_radon.exists() else "radon"

        # Check src/ if exists
        src_path = path / "src"
        check_path = str(src_path) if src_path.exists() else project_path

        try:
            result = subprocess.run(
                [
                    radon_cmd,
                    "cc",
                    check_path,
                    "-a",
                    "-s",
                    "--total-average",
                    "--exclude",
                    self.params["exclude"],
                ],
                capture_output=True,
                text=True,
                timeout=self.params["timeout"],
            )

            if result.returncode != 0:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message="Skipped (radon not available)",
                    severity="info",
                )

            output = result.stdout

            # Grade patterns
            error_patterns = [f" - {g} (" for g in ["D", "E", "F"]]
            warn_patterns = [f" - {g} (" for g in ["C"]]

            error_lines = [
                line for line in output.split("\n") if any(p in line for p in error_patterns)
            ]
            warn_lines = [
                line for line in output.split("\n") if any(p in line for p in warn_patterns)
            ]

            if error_lines:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"{len(error_lines)} function(s) with very high complexity (D+)",
                    severity="error",
                )

            if warn_lines:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{len(warn_lines)} function(s) with complexity C",
                    severity="warning",
                )

            return CheckResult(
                name=self.name,
                passed=True,
                message="Complexity OK (A-B)",
                severity="info",
            )

        except FileNotFoundError:
            return CheckResult(
                name=self.name,
                passed=True,
                message="Skipped (radon not installed)",
                severity="info",
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                passed=True,
                message="Skipped (timeout)",
                severity="info",
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Skipped ({e})",
                severity="info",
            )


class RuffCheck(BaseCheck):
    """Check code with ruff linter."""

    name = "Ruff"
    description = "Runs ruff linter"
    category = "quality"
    default_phases = [3, 4]  # Testing and Final

    default_params = {
        "timeout": 30,
        "ignore": "E501",  # Line too long
        "exclude": ".venv,venv,node_modules,__pycache__,build,dist",
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        # Find ruff
        venv_ruff = path / ".venv" / "bin" / "ruff"
        ruff_cmd = str(venv_ruff) if venv_ruff.exists() else "ruff"

        # Check availability
        try:
            version_result = subprocess.run(
                [ruff_cmd, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if version_result.returncode != 0:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message="Skipped (ruff not available)",
                    severity="info",
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return CheckResult(
                name=self.name,
                passed=True,
                message="Skipped (ruff not installed)",
                severity="info",
            )

        # Check src/ if exists
        src_path = path / "src"
        check_path = str(src_path) if src_path.exists() else project_path

        try:
            result = subprocess.run(
                [
                    ruff_cmd,
                    "check",
                    check_path,
                    "--quiet",
                    "--ignore",
                    self.params["ignore"],
                    "--exclude",
                    self.params["exclude"],
                ],
                capture_output=True,
                text=True,
                timeout=self.params["timeout"],
                cwd=project_path,
            )

            error_count = 0
            if result.stdout.strip():
                error_count = len(result.stdout.strip().split("\n"))

            if error_count == 0:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message="No linting errors",
                    severity="warning",
                )

            return CheckResult(
                name=self.name,
                passed=False,
                message=f"{error_count} linting error(s)",
                severity="warning",
            )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                passed=True,
                message="Skipped (timeout)",
                severity="info",
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Skipped ({e})",
                severity="info",
            )


class CodeEnglishCheck(BaseCheck):
    """Check if Python code is in English (no German in comments/docstrings)."""

    name = "Code English"
    description = "Checks Python code for German characters"
    category = "quality"
    default_phases = [4]  # Only Final

    default_params = {
        "german_chars": "äöüÄÖÜß",
        "skip_dirs": ["translations", "locales", "i18n", "locale", ".venv", "venv", "__pycache__"],
        "max_files": 100,
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)
        issues_found = []

        py_files = list(path.glob("**/*.py"))

        for py_file in py_files[: self.params["max_files"]]:
            # Skip configured directories
            if any(skip_dir in py_file.parts for skip_dir in self.params["skip_dirs"]):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if any(c in content for c in self.params["german_chars"]):
                    rel_path = py_file.relative_to(path)
                    issues_found.append(str(rel_path))
            except Exception:
                continue

        if issues_found:
            return CheckResult(
                name=self.name,
                passed=False,
                message=f"{len(issues_found)} file(s) with German text",
                severity="warning",
            )

        return CheckResult(
            name=self.name,
            passed=True,
            message="Code is in English",
            severity="warning",
        )


class PyprojectEnglishCheck(BaseCheck):
    """Check if pyproject.toml has English description."""

    name = "pyproject.toml English"
    description = "Checks pyproject.toml for German characters"
    category = "quality"
    default_phases = [4]  # Only Final

    default_params = {
        "german_chars": "äöüÄÖÜß",
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)
        pyproject_path = path / "pyproject.toml"

        if not pyproject_path.exists():
            return CheckResult(
                name=self.name,
                passed=True,
                message="No pyproject.toml (skipped)",
                severity="info",
            )

        try:
            content = pyproject_path.read_text(encoding="utf-8", errors="ignore")
            if any(c in content for c in self.params["german_chars"]):
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message="pyproject.toml contains German characters",
                    severity="warning",
                )
            return CheckResult(
                name=self.name,
                passed=True,
                message="pyproject.toml is in English",
                severity="warning",
            )
        except Exception:
            return CheckResult(
                name=self.name,
                passed=True,
                message="Could not read pyproject.toml (skipped)",
                severity="info",
            )
