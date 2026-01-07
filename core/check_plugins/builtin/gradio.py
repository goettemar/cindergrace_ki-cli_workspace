"""Gradio-specific checks."""

import re
from pathlib import Path

from core.check_plugins.base import BaseCheck, CheckResult


class GradioShareCheck(BaseCheck):
    """Check that Gradio apps don't use share=True (security risk)."""

    name = "Gradio Share"
    description = "Checks for share=True in Gradio apps (security risk)"
    category = "security"
    default_phases = [2, 3, 4]  # Development, Testing, Final

    default_params = {
        "skip_dirs": [".venv", "venv", "__pycache__", "node_modules", "build", "dist"],
        "max_files": 100,
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        gradio_files = []
        share_true_files = []

        py_files = list(path.glob("**/*.py"))

        for py_file in py_files[: self.params["max_files"]]:
            # Skip configured directories
            if any(skip_dir in py_file.parts for skip_dir in self.params["skip_dirs"]):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")

                # Check if Gradio is used
                if "import gradio" in content or "from gradio" in content or "gr.Blocks" in content:
                    gradio_files.append(py_file)

                    # Search for share=True
                    share_patterns = [
                        r"\.launch\([^)]*share\s*=\s*True",
                        r"share\s*=\s*True",
                    ]
                    for pattern in share_patterns:
                        if re.search(pattern, content):
                            rel_path = py_file.relative_to(path)
                            share_true_files.append(str(rel_path))
                            break

            except Exception:
                continue

        # No Gradio app found
        if not gradio_files:
            return CheckResult(
                name=self.name,
                passed=True,
                message="No Gradio app found (skipped)",
                severity="info",
            )

        # share=True found
        if share_true_files:
            return CheckResult(
                name=self.name,
                passed=False,
                message=f"share=True in: {', '.join(share_true_files[:3])}",
                severity="error",
            )

        return CheckResult(
            name=self.name,
            passed=True,
            message=f"All {len(gradio_files)} Gradio file(s) have share=False",
            severity="error",
        )


class I18nCheck(BaseCheck):
    """Check if project has internationalization support."""

    name = "i18n Support"
    description = "Checks for translations directory or i18n imports"
    category = "quality"
    default_phases = [4]  # Only Final

    default_params = {
        "trans_dirs": ["translations", "locales", "i18n", "locale"],
        "i18n_imports": ["gradio_i18n", "gettext", "babel", "i18n"],
        "max_files": 50,
    }

    def run(self, project_path: str, **kwargs) -> CheckResult:
        path = Path(project_path)

        # Check for translations directory
        has_trans_dir = any((path / td).exists() for td in self.params["trans_dirs"])

        # Check in src/ as well
        src_path = path / "src"
        has_trans_in_src = False
        if src_path.exists():
            for td in self.params["trans_dirs"]:
                if list(src_path.glob(f"**/{td}")):
                    has_trans_in_src = True
                    break

        # Check for i18n imports in Python files
        has_i18n_import = False
        py_files = list(path.glob("**/*.py"))

        for py_file in py_files[: self.params["max_files"]]:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if any(imp in content for imp in self.params["i18n_imports"]):
                    has_i18n_import = True
                    break
            except Exception:
                continue

        if has_trans_dir or has_trans_in_src or has_i18n_import:
            return CheckResult(
                name=self.name,
                passed=True,
                message="i18n/translations found",
                severity="warning",
            )

        return CheckResult(
            name=self.name,
            passed=False,
            message="No i18n/translations found",
            severity="warning",
        )
