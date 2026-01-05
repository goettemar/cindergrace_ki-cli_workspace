"""
AI Delegation Module - Delegiert Tasks an verschiedene KI-CLIs.

Unterstuetzte KIs:
- Codex (OpenAI): /home/zorinadmin/.npm-global/bin/codex
- Gemini (Google): /home/zorinadmin/.npm-global/bin/gemini
- Claude (Anthropic): claude

Verwendung:
    from core.ai_delegation import delegate_task, list_available_ais

    result = delegate_task(
        prompt_name="code_review",
        target="/path/to/file.py",
        ai="codex"
    )
"""

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# KI-CLI Konfiguration
AI_CONFIGS = {
    "codex": {
        "name": "Codex (OpenAI)",
        "path": "/home/zorinadmin/.npm-global/bin/codex",
        "exec_mode": "exec",  # codex exec --full-auto "prompt"
        "review_mode": "review",  # codex review --uncommitted
    },
    "gemini": {
        "name": "Gemini (Google)",
        "path": "/home/zorinadmin/.npm-global/bin/gemini",
        "exec_mode": "yolo",  # gemini --yolo "prompt"
        "pipe_mode": True,  # echo "content" | gemini "prompt"
    },
    "claude": {
        "name": "Claude (Anthropic)",
        "path": "/home/zorinadmin/.npm-global/bin/claude",
        "exec_mode": "print",  # claude --print "prompt"
        "pipe_mode": True,
    },
}

# Template-Variablen
TEMPLATE_VARS = {
    "{file}": "Dateipfad",
    "{file_content}": "Dateiinhalt",
    "{file_name}": "Dateiname ohne Pfad",
    "{project}": "Projektname",
    "{project_path}": "Projektpfad",
    "{git_diff}": "Uncommitted Git-Aenderungen",
    "{git_diff_staged}": "Staged Git-Aenderungen",
    "{issues}": "Offene Codacy-Issues (JSON)",
    "{timestamp}": "Aktueller Zeitstempel",
}


@dataclass
class DelegationResult:
    """Ergebnis einer KI-Delegation."""

    success: bool
    output: str
    ai_used: str
    prompt_name: str
    duration_seconds: float
    error: str | None = None


def list_available_ais() -> list[dict]:
    """Listet verfuegbare KI-CLIs mit Status."""
    result = []
    for ai_id, config in AI_CONFIGS.items():
        path = config["path"]
        available = shutil.which(path) is not None
        result.append(
            {
                "id": ai_id,
                "name": config["name"],
                "path": path,
                "available": available,
            }
        )
    return result


def get_ai_config(ai_id: str) -> dict | None:
    """Holt KI-Konfiguration."""
    return AI_CONFIGS.get(ai_id)


def expand_template(
    template: str,
    file_path: str | None = None,
    project_path: str | None = None,
    project_name: str | None = None,
    issues_json: str | None = None,
) -> str:
    """
    Expandiert Template-Variablen im Prompt.

    Args:
        template: Prompt-Template mit {variablen}
        file_path: Pfad zur Zieldatei
        project_path: Pfad zum Projekt
        project_name: Name des Projekts
        issues_json: JSON-String mit Issues
    """
    result = template

    # Timestamp
    result = result.replace("{timestamp}", datetime.now().isoformat())

    # Datei-bezogene Variablen
    if file_path:
        path = Path(file_path)
        result = result.replace("{file}", str(path))
        result = result.replace("{file_name}", path.name)
        if path.exists():
            try:
                content = path.read_text(errors="replace")
                result = result.replace("{file_content}", content)
            except Exception:
                result = result.replace("{file_content}", "[Datei nicht lesbar]")
        else:
            result = result.replace("{file_content}", "[Datei nicht gefunden]")

    # Projekt-bezogene Variablen
    if project_name:
        result = result.replace("{project}", project_name)
    if project_path:
        result = result.replace("{project_path}", project_path)

        # Git-Diff
        try:
            git_diff = subprocess.run(
                ["git", "diff"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            result = result.replace("{git_diff}", git_diff.stdout or "[Keine Aenderungen]")
        except Exception:
            result = result.replace("{git_diff}", "[Git nicht verfuegbar]")

        try:
            git_diff_staged = subprocess.run(
                ["git", "diff", "--staged"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            result = result.replace(
                "{git_diff_staged}", git_diff_staged.stdout or "[Keine staged Aenderungen]"
            )
        except Exception:
            result = result.replace("{git_diff_staged}", "[Git nicht verfuegbar]")

    # Issues
    if issues_json:
        result = result.replace("{issues}", issues_json)
    else:
        result = result.replace("{issues}", "[]")

    return result


def run_codex(prompt: str, project_path: str | None = None, timeout: int = 300) -> tuple[bool, str]:
    """
    Fuehrt Codex CLI aus.

    Args:
        prompt: Der Prompt fuer Codex
        project_path: Working Directory
        timeout: Timeout in Sekunden
    """
    config = AI_CONFIGS["codex"]
    cmd_path = config["path"]

    if not shutil.which(cmd_path):
        return False, "Codex CLI nicht gefunden"

    try:
        cmd = [cmd_path, "exec", "--full-auto", prompt]
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout nach {timeout}s"
    except Exception as e:
        return False, f"Fehler: {e}"


def run_codex_review(
    project_path: str, uncommitted: bool = True, timeout: int = 300
) -> tuple[bool, str]:
    """
    Fuehrt Codex Review aus.

    Args:
        project_path: Projekt-Pfad (muss Git-Repo sein)
        uncommitted: True fuer uncommitted changes, False fuer letzten Commit
        timeout: Timeout in Sekunden
    """
    config = AI_CONFIGS["codex"]
    cmd_path = config["path"]

    if not shutil.which(cmd_path):
        return False, "Codex CLI nicht gefunden"

    try:
        cmd = [cmd_path, "review"]
        if uncommitted:
            cmd.append("--uncommitted")
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout nach {timeout}s"
    except Exception as e:
        return False, f"Fehler: {e}"


def run_gemini(
    prompt: str,
    input_content: str | None = None,
    project_path: str | None = None,
    timeout: int = 300,
) -> tuple[bool, str]:
    """
    Fuehrt Gemini CLI aus.

    Args:
        prompt: Der Prompt fuer Gemini
        input_content: Optional - Content der per Pipe uebergeben wird
        project_path: Working Directory
        timeout: Timeout in Sekunden
    """
    config = AI_CONFIGS["gemini"]
    cmd_path = config["path"]

    if not shutil.which(cmd_path):
        return False, "Gemini CLI nicht gefunden"

    try:
        cmd = [cmd_path, "--yolo", prompt]
        result = subprocess.run(
            cmd,
            cwd=project_path,
            input=input_content,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout nach {timeout}s"
    except Exception as e:
        return False, f"Fehler: {e}"


def run_claude(
    prompt: str,
    input_content: str | None = None,
    project_path: str | None = None,
    timeout: int = 300,
) -> tuple[bool, str]:
    """
    Fuehrt Claude CLI aus.

    Args:
        prompt: Der Prompt fuer Claude
        input_content: Optional - Content der per Pipe uebergeben wird
        project_path: Working Directory
        timeout: Timeout in Sekunden
    """
    config = AI_CONFIGS["claude"]
    cmd_path = config["path"]

    if not shutil.which(cmd_path):
        return False, "Claude CLI nicht gefunden"

    try:
        # Claude mit --print fuer non-interactive mode
        full_prompt = prompt
        if input_content:
            full_prompt = f"{prompt}\n\n```\n{input_content}\n```"

        cmd = [cmd_path, "--print", full_prompt]
        result = subprocess.run(
            cmd,
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout nach {timeout}s"
    except Exception as e:
        return False, f"Fehler: {e}"


def delegate_to_ai(
    ai_id: str,
    prompt: str,
    input_content: str | None = None,
    project_path: str | None = None,
    timeout: int = 300,
) -> tuple[bool, str]:
    """
    Delegiert einen Prompt an die gewaehlte KI.

    Args:
        ai_id: KI-ID (codex, gemini, claude)
        prompt: Der auszufuehrende Prompt
        input_content: Optional - Zusaetzlicher Content
        project_path: Working Directory
        timeout: Timeout in Sekunden

    Returns:
        Tuple (success, output)
    """
    if ai_id == "codex":
        return run_codex(prompt, project_path, timeout)
    elif ai_id == "gemini":
        return run_gemini(prompt, input_content, project_path, timeout)
    elif ai_id == "claude":
        return run_claude(prompt, input_content, project_path, timeout)
    else:
        return False, f"Unbekannte KI: {ai_id}"


def delegate_task(
    prompt_template: str,
    ai_id: str = "codex",
    file_path: str | None = None,
    project_path: str | None = None,
    project_name: str | None = None,
    issues_json: str | None = None,
    timeout: int = 300,
) -> DelegationResult:
    """
    Fuehrt einen Prompt-Task mit der gewaehlten KI aus.

    Args:
        prompt_template: Prompt mit {variablen}
        ai_id: KI-ID (codex, gemini, claude)
        file_path: Pfad zur Zieldatei
        project_path: Pfad zum Projekt
        project_name: Name des Projekts
        issues_json: JSON-String mit Issues
        timeout: Timeout in Sekunden

    Returns:
        DelegationResult mit Ergebnis
    """
    import time

    start_time = time.time()

    # Template expandieren
    expanded_prompt = expand_template(
        prompt_template,
        file_path=file_path,
        project_path=project_path,
        project_name=project_name,
        issues_json=issues_json,
    )

    # Input-Content vorbereiten (fuer Pipe-faehige KIs)
    input_content = None
    if file_path and Path(file_path).exists():
        import contextlib

        with contextlib.suppress(Exception):
            input_content = Path(file_path).read_text(errors="replace")

    # An KI delegieren
    success, output = delegate_to_ai(
        ai_id=ai_id,
        prompt=expanded_prompt,
        input_content=input_content,
        project_path=project_path,
        timeout=timeout,
    )

    duration = time.time() - start_time

    return DelegationResult(
        success=success,
        output=output,
        ai_used=ai_id,
        prompt_name=prompt_template[:50] + "..." if len(prompt_template) > 50 else prompt_template,
        duration_seconds=round(duration, 2),
        error=None if success else output,
    )


# Default prompts for initial setup (English for AI-to-AI communication)
DEFAULT_PROMPTS = [
    {
        "name": "code_review",
        "description": "General code review",
        "prompt": """Review the following code for:
- Bugs and errors
- Security issues
- Performance problems
- Best practices violations
- Code quality issues

File: {file_name}

```
{file_content}
```

Provide specific improvement suggestions with code examples where applicable.""",
        "default_ai": "codex",
        "category": "review",
    },
    {
        "name": "security_audit",
        "description": "Security analysis (OWASP)",
        "prompt": """Analyze the following code for security vulnerabilities:
- OWASP Top 10
- Injection vulnerabilities (SQL, Command, XSS)
- Authentication/Authorization issues
- Sensitive data exposure
- Security misconfiguration

File: {file_name}

```
{file_content}
```

List all findings with severity (Critical/High/Medium/Low) and remediation steps.""",
        "default_ai": "gemini",
        "category": "security",
    },
    {
        "name": "test_suggestions",
        "description": "Generate test suggestions",
        "prompt": """Analyze the following code and suggest tests:
- Unit tests for all functions/methods
- Edge cases and boundary conditions
- Error handling tests
- Integration tests (if applicable)

File: {file_name}

```
{file_content}
```

Generate pytest-compatible test cases with explanations.""",
        "default_ai": "claude",
        "category": "testing",
    },
    {
        "name": "refactor_ideas",
        "description": "Refactoring suggestions",
        "prompt": """Analyze the following code for refactoring opportunities:
- Code duplication
- Complexity reduction
- Better abstractions
- Design patterns
- Readability improvements

File: {file_name}

```
{file_content}
```

Suggest concrete refactorings with before/after examples.""",
        "default_ai": "gemini",
        "category": "refactoring",
    },
    {
        "name": "doc_generator",
        "description": "Generate documentation",
        "prompt": """Generate documentation for the following code:
- Docstrings for all functions/classes
- Type annotations
- Usage examples
- README section

File: {file_name}

```
{file_content}
```

Format as Markdown.""",
        "default_ai": "claude",
        "category": "documentation",
    },
    {
        "name": "git_commit_review",
        "description": "Review uncommitted changes",
        "prompt": """Review the following Git changes:

```diff
{git_diff}
```

Check for:
- Bugs in the changes
- Unintended side effects
- Missing tests
- Code quality issues

Provide a summary and recommendation (OK to commit / Needs work).""",
        "default_ai": "codex",
        "category": "review",
    },
    {
        "name": "explain_code",
        "description": "Explain code",
        "prompt": """Explain the following code in detail:
- What does the code do?
- How does it work?
- What patterns are used?
- Highlight important sections

File: {file_name}

```
{file_content}
```

Explain so that a junior developer can understand.""",
        "default_ai": "claude",
        "category": "documentation",
    },
    {
        "name": "issue_analysis",
        "description": "Analyze Codacy issues",
        "prompt": """Analyze the following Codacy issues for project {project}:

{issues}

For each issue:
1. Is it a real problem or false positive?
2. How critical is it really?
3. How should it be fixed?
4. Recommendation: Fix / Ignore (with justification)

Sort by priority.""",
        "default_ai": "gemini",
        "category": "analysis",
    },
]
