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


# Default-Prompts fuer initiale Einrichtung
DEFAULT_PROMPTS = [
    {
        "name": "code_review",
        "description": "Allgemeines Code-Review",
        "prompt": """Reviewe den folgenden Code auf:
- Bugs und Fehler
- Security-Probleme
- Performance-Issues
- Best Practices
- Code-Qualitaet

Datei: {file_name}

```
{file_content}
```

Antworte auf Deutsch mit konkreten Verbesserungsvorschlaegen.""",
        "default_ai": "codex",
        "category": "review",
    },
    {
        "name": "security_audit",
        "description": "Security-Analyse (OWASP)",
        "prompt": """Analysiere den folgenden Code auf Security-Probleme:
- OWASP Top 10
- Injection-Schwachstellen
- Authentication/Authorization
- Sensitive Data Exposure
- Security Misconfiguration

Datei: {file_name}

```
{file_content}
```

Liste alle gefundenen Probleme mit Schweregrad (Critical/High/Medium/Low) und Loesungsvorschlag.""",
        "default_ai": "gemini",
        "category": "security",
    },
    {
        "name": "test_suggestions",
        "description": "Testvorschlaege generieren",
        "prompt": """Analysiere den folgenden Code und schlage Tests vor:
- Unit Tests fuer alle Funktionen
- Edge Cases
- Error Handling Tests
- Integration Tests (falls relevant)

Datei: {file_name}

```
{file_content}
```

Generiere pytest-kompatible Testfaelle mit Erklaerung.""",
        "default_ai": "claude",
        "category": "testing",
    },
    {
        "name": "refactor_ideas",
        "description": "Refactoring-Vorschlaege",
        "prompt": """Analysiere den folgenden Code auf Refactoring-Moeglichkeiten:
- Code-Duplikation
- Komplexitaet reduzieren
- Bessere Abstraktion
- Design Patterns
- Lesbarkeit verbessern

Datei: {file_name}

```
{file_content}
```

Schlage konkrete Refactorings vor mit Vorher/Nachher Beispielen.""",
        "default_ai": "gemini",
        "category": "refactoring",
    },
    {
        "name": "doc_generator",
        "description": "Dokumentation generieren",
        "prompt": """Generiere Dokumentation fuer den folgenden Code:
- Docstrings fuer alle Funktionen/Klassen
- Typen-Annotationen
- Beispiel-Verwendung
- README-Abschnitt

Datei: {file_name}

```
{file_content}
```

Formatiere als Markdown.""",
        "default_ai": "claude",
        "category": "documentation",
    },
    {
        "name": "git_commit_review",
        "description": "Review der uncommitted Aenderungen",
        "prompt": """Reviewe die folgenden Git-Aenderungen:

```diff
{git_diff}
```

Pruefe auf:
- Bugs in den Aenderungen
- Unbeabsichtigte Nebeneffekte
- Fehlende Tests
- Code-Qualitaet

Gib eine Zusammenfassung und Empfehlung (Commit OK / Nachbessern).""",
        "default_ai": "codex",
        "category": "review",
    },
    {
        "name": "explain_code",
        "description": "Code erklaeren",
        "prompt": """Erklaere den folgenden Code ausfuehrlich:
- Was macht der Code?
- Wie funktioniert er?
- Welche Patterns werden verwendet?
- Wichtige Stellen markieren

Datei: {file_name}

```
{file_content}
```

Erklaere so, dass ein Junior-Entwickler es versteht.""",
        "default_ai": "claude",
        "category": "documentation",
    },
    {
        "name": "issue_analysis",
        "description": "Codacy-Issues analysieren",
        "prompt": """Analysiere die folgenden Codacy-Issues fuer Projekt {project}:

{issues}

Fuer jedes Issue:
1. Ist es ein echtes Problem oder False Positive?
2. Wie kritisch ist es wirklich?
3. Wie sollte es behoben werden?
4. Empfehlung: Fix / Ignore (mit Begruendung)

Sortiere nach Prioritaet.""",
        "default_ai": "gemini",
        "category": "analysis",
    },
]
