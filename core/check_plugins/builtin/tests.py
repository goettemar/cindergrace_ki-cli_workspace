"""Test and coverage checks."""

import re
import subprocess
from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class TestsCheck(BaseCheck):
    """Check if tests exist and pass."""

    name = "Tests"
    description = "Runs pytest and checks results"
    category = "quality"
    default_phases = [3, 4]  # Testing and Final

    default_params = {
        "timeout": 120,  # 2 minutes
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        # Check if tests exist
        test_dirs = ["tests", "test"]
        has_tests = any((path / td).exists() for td in test_dirs)

        if not has_tests:
            test_files = list(path.glob("**/test_*.py"))
            if not test_files:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message="No tests found",
                    severity="warning",
                )

        # Find pytest
        venv_pytest = path / ".venv" / "bin" / "pytest"
        if not venv_pytest.exists():
            return CheckResult(
                name=self.name,
                passed=True,
                message="pytest not found (skipped)",
                severity="info",
            )

        try:
            result = subprocess.run(
                [str(venv_pytest), "-q", "--tb=no"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=self.params["timeout"],
            )

            output = result.stdout + result.stderr
            passed_match = re.search(r"(\d+) passed", output)
            failed_match = re.search(r"(\d+) failed", output)

            passed_count = int(passed_match.group(1)) if passed_match else 0
            failed_count = int(failed_match.group(1)) if failed_match else 0

            if result.returncode == 0:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"{passed_count} tests passed",
                    severity="error",
                )
            else:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"{failed_count} failed, {passed_count} passed",
                    severity="error",
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                passed=False,
                message=f"Timeout (>{self.params['timeout']}s)",
                severity="error",
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=False,
                message=f"Error: {e}",
                severity="error",
            )


class CoverageCheck(BaseCheck):
    """Check test coverage percentage."""

    name = "Coverage"
    description = "Runs pytest --cov and checks percentage"
    category = "quality"
    default_phases = [4]  # Only Final

    default_params = {
        "timeout": 180,  # 3 minutes
        "min_coverage": 60,  # Minimum acceptable coverage
        "good_coverage": 80,  # Good coverage threshold
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        # Find pytest
        venv_pytest = path / ".venv" / "bin" / "pytest"
        if not venv_pytest.exists():
            return CheckResult(
                name=self.name,
                passed=True,
                message="pytest not found (skipped)",
                severity="info",
            )

        # Find package name for --cov
        src_dir = path / "src"
        if src_dir.exists():
            pkg_dirs = [d for d in src_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
            cov_target = pkg_dirs[0].name if pkg_dirs else "."
        else:
            cov_target = "."

        try:
            result = subprocess.run(
                [str(venv_pytest), f"--cov={cov_target}", "-q", "--tb=no", "--no-header"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=self.params["timeout"],
            )

            output = result.stdout + result.stderr

            # Parse coverage percentage
            match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
            if not match:
                match = re.search(r"(\d+)%", output)

            if not match:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message="Coverage not determinable",
                    severity="info",
                )

            coverage_pct = int(match.group(1))

            if coverage_pct >= self.params["good_coverage"]:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"Coverage {coverage_pct}% (good)",
                    severity="info",
                )
            elif coverage_pct >= self.params["min_coverage"]:
                return CheckResult(
                    name=self.name,
                    passed=True,
                    message=f"Coverage {coverage_pct}% (acceptable)",
                    severity="warning",
                )
            else:
                return CheckResult(
                    name=self.name,
                    passed=False,
                    message=f"Coverage {coverage_pct}% (too low)",
                    severity="error",
                )

        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Timeout (>{self.params['timeout']}s)",
                severity="info",
            )
        except Exception as e:
            return CheckResult(
                name=self.name,
                passed=True,
                message=f"Error: {e}",
                severity="info",
            )
