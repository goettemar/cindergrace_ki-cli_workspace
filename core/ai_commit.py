"""
AI-powered Commit Message Generator.

Verwendet OpenRouter API mit konfigurierbarem Model (z.B. Grok)
um hochwertige Commit Messages aus dem git diff zu generieren.
"""

import subprocess
from dataclasses import dataclass

import httpx


@dataclass
class CommitResult:
    """Ergebnis der Commit-Generierung."""

    success: bool
    message: str  # Commit message oder Fehlermeldung
    diff_summary: str = ""  # Kurze Zusammenfassung des Diffs


# Standard-Modelle fuer OpenRouter
DEFAULT_MODEL = "x-ai/grok-3-mini-beta"
AVAILABLE_MODELS = [
    "x-ai/grok-3-mini-beta",
    "x-ai/grok-3-beta",
    "x-ai/grok-2-1212",
    "anthropic/claude-sonnet-4",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "google/gemini-2.0-flash-001",
]

# Prompt fuer Commit Message Generierung
COMMIT_PROMPT = """Du bist ein erfahrener Software-Entwickler. Analysiere den folgenden Git Diff und erstelle eine praezise Commit Message.

REGELN:
1. Nutze Conventional Commits Format: type(scope): description
2. Types: feat, fix, docs, style, refactor, test, chore, perf, ci, build
3. Scope ist optional, aber hilfreich (z.B. api, ui, db, auth)
4. Erste Zeile max 72 Zeichen
5. Bei komplexen Aenderungen: Leerzeile + Bullet Points fuer Details
6. Schreibe auf Englisch
7. Fokussiere auf das WAS und WARUM, nicht das WIE

BEISPIELE:
- feat(auth): add OAuth2 login support
- fix(api): handle null response from external service
- refactor(db): simplify query builder logic
- docs: update README with installation steps

GIT DIFF:
```
{diff}
```

Antworte NUR mit der Commit Message, ohne zusaetzliche Erklaerungen."""


def get_staged_diff(repo_path: str | None = None) -> tuple[bool, str]:
    """
    Holt den staged git diff.

    Args:
        repo_path: Pfad zum Repository (None = aktuelles Verzeichnis)

    Returns:
        (success, diff_or_error)
    """
    try:
        cmd = ["git", "diff", "--staged", "--no-color"]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return False, f"Git error: {result.stderr}"

        diff = result.stdout.strip()
        if not diff:
            return False, "Keine staged Changes gefunden. Nutze 'git add' zuerst."

        return True, diff

    except subprocess.TimeoutExpired:
        return False, "Git timeout"
    except FileNotFoundError:
        return False, "Git nicht gefunden"
    except Exception as e:
        return False, f"Fehler: {e}"


def get_staged_files(repo_path: str | None = None) -> list[str]:
    """Gibt Liste der staged Dateien zurueck."""
    try:
        cmd = ["git", "diff", "--staged", "--name-only"]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return [f for f in result.stdout.strip().split("\n") if f]
        return []
    except Exception:
        return []


def generate_commit_message(
    api_key: str,
    diff: str,
    model: str = DEFAULT_MODEL,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """
    Generiert eine Commit Message via OpenRouter API.

    Args:
        api_key: OpenRouter API Key
        diff: Git diff als String
        model: OpenRouter Model ID
        timeout: Request timeout in Sekunden

    Returns:
        (success, message_or_error)
    """
    if not api_key:
        return False, "OpenRouter API Key nicht konfiguriert"

    if not diff:
        return False, "Kein Diff vorhanden"

    # Diff auf max 15000 Zeichen begrenzen (Token-Limit)
    if len(diff) > 15000:
        diff = diff[:15000] + "\n\n[... diff truncated ...]"

    prompt = COMMIT_PROMPT.format(diff=diff)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/goettemar/cindergrace_ki-cli_workspace",
                    "X-Title": "KI-Workspace Commit Generator",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.3,  # Niedrig fuer konsistente Ergebnisse
                },
            )

            if response.status_code != 200:
                error_text = response.text
                if "invalid_api_key" in error_text.lower():
                    return False, "Ungueltiger OpenRouter API Key"
                if "rate_limit" in error_text.lower():
                    return False, "Rate Limit erreicht, bitte warten"
                return False, f"API Error {response.status_code}: {error_text[:200]}"

            data = response.json()
            message = data["choices"][0]["message"]["content"].strip()

            # Cleanup: Entferne Markdown Code Blocks falls vorhanden
            if message.startswith("```"):
                lines = message.split("\n")
                message = "\n".join(line for line in lines if not line.startswith("```")).strip()

            return True, message

    except httpx.TimeoutException:
        return False, f"Timeout nach {timeout}s - Model zu langsam?"
    except httpx.RequestError as e:
        return False, f"Netzwerk-Fehler: {e}"
    except KeyError:
        return False, "Unerwartete API-Antwort"
    except Exception as e:
        return False, f"Fehler: {e}"


def create_commit(
    message: str,
    repo_path: str | None = None,
    add_ai_footer: bool = True,
) -> tuple[bool, str]:
    """
    Erstellt einen Git Commit mit der gegebenen Message.

    Args:
        message: Commit Message
        repo_path: Pfad zum Repository
        add_ai_footer: Fuegt AI-Footer hinzu

    Returns:
        (success, result_or_error)
    """
    if add_ai_footer:
        message = f"{message}\n\n🤖 Generated with KI-Workspace AI Commit"

    try:
        cmd = ["git", "commit", "-m", message]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "nothing to commit" in stderr.lower():
                return False, "Nichts zum committen"
            return False, f"Git error: {stderr}"

        return True, result.stdout.strip()

    except subprocess.TimeoutExpired:
        return False, "Git timeout"
    except Exception as e:
        return False, f"Fehler: {e}"


def ai_commit(
    api_key: str,
    model: str = DEFAULT_MODEL,
    repo_path: str | None = None,
    auto_confirm: bool = False,
) -> CommitResult:
    """
    Kompletter AI Commit Workflow.

    Args:
        api_key: OpenRouter API Key
        model: OpenRouter Model ID
        repo_path: Pfad zum Repository
        auto_confirm: Wenn True, kein User-Prompt

    Returns:
        CommitResult mit Status und Message
    """
    # 1. Staged Diff holen
    success, diff = get_staged_diff(repo_path)
    if not success:
        return CommitResult(success=False, message=diff)

    staged_files = get_staged_files(repo_path)
    diff_summary = f"{len(staged_files)} Datei(en): {', '.join(staged_files[:5])}"
    if len(staged_files) > 5:
        diff_summary += f" (+{len(staged_files) - 5} weitere)"

    # 2. Commit Message generieren
    success, message = generate_commit_message(api_key, diff, model)
    if not success:
        return CommitResult(success=False, message=message, diff_summary=diff_summary)

    # 3. Bei auto_confirm direkt committen
    if auto_confirm:
        success, result = create_commit(message, repo_path)
        if success:
            return CommitResult(
                success=True,
                message=message,
                diff_summary=diff_summary,
            )
        return CommitResult(success=False, message=result, diff_summary=diff_summary)

    # 4. Sonst nur Message zurueckgeben (CLI fragt User)
    return CommitResult(
        success=True,
        message=message,
        diff_summary=diff_summary,
    )
