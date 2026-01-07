#!/usr/bin/env python3
"""
KI-Workspace CLI.

Kommandozeilen-Interface für Projekt-Verwaltung und KI-Zusammenarbeit.
"""

from __future__ import annotations

import json
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from core.database import DatabaseManager
from core.project_init import ProjectInitializer

app = typer.Typer(
    name="ki-workspace",
    help="KI-CLI Workspace - Projekt-Verwaltung und Issue-Management",
    add_completion=False,
)
console = Console()


def get_db() -> DatabaseManager:
    """Gibt eine DatabaseManager-Instanz zurück."""
    return DatabaseManager()


# === Init Command ===


@app.command()
def init(
    name: str = typer.Argument(..., help="Projektname (z.B. cindergrace_mein_projekt)"),
    description: str = typer.Option("", "--description", "-d", help="Kurze Beschreibung"),
    status: str = typer.Option(
        "alpha",
        "--status",
        "-s",
        help="Projekt-Status für Badge (alpha, beta, stable)",
    ),
    no_github: bool = typer.Option(False, "--no-github", help="Kein GitHub Repo erstellen"),
    no_codacy: bool = typer.Option(False, "--no-codacy", help="Keine Codacy-Verbindung"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """
    Erstellt ein neues Projekt mit kompletter Struktur.

    Erstellt: Ordner, Git Repo, GitHub Repo, README, LICENSE, etc.
    """
    db = get_db()
    initializer = ProjectInitializer(db)

    if not json_output:
        console.print(f"\n🚀 Erstelle Projekt: [bold]{name}[/bold]\n")

    result = initializer.create_project(
        name=name,
        description=description,
        status=status,
        create_github=not no_github,
        connect_codacy=not no_codacy,
    )

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        # Steps anzeigen
        for step in result["steps"]:
            console.print(step)

        # Errors anzeigen
        for error in result["errors"]:
            console.print(f"❌ {error}", style="red")

        console.print()
        if result["success"]:
            console.print("✅ [bold green]Projekt erfolgreich erstellt![/bold green]")
            console.print(f"   📁 Pfad: {result['path']}")
            if result["github_url"]:
                console.print(f"   🔗 GitHub: {result['github_url']}")
        else:
            console.print("⚠️ [bold yellow]Projekt mit Fehlern erstellt[/bold yellow]")

    sys.exit(0 if result["success"] else 1)


# === Projects Command ===


@app.command()
def projects(
    include_archived: bool = typer.Option(False, "--archived", "-a", help="Archivierte zeigen"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Listet alle Projekte auf."""
    db = get_db()
    project_list = db.get_all_projects(include_archived=include_archived)

    if json_output:
        data = [
            {
                "id": p.id,
                "name": p.name,
                "path": p.path,
                "phase": p.phase_id,
                "archived": p.is_archived,
            }
            for p in project_list
        ]
        print(json.dumps(data, indent=2))
    else:
        table = Table(title="Projekte")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Phase")
        table.add_column("Pfad")
        table.add_column("Status")

        phases = {p.id: p.display_name for p in db.get_all_phases()}

        for p in project_list:
            phase_name = phases.get(p.phase_id, "-") if p.phase_id else "-"
            status = "📦 Archiviert" if p.is_archived else "✅ Aktiv"
            table.add_row(
                str(p.id),
                p.name,
                phase_name,
                p.path or "-",
                status,
            )

        console.print(table)


# === Status Command ===


@app.command()
def status(
    project: str = typer.Argument(..., help="Projektname oder ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Zeigt Status eines Projekts."""
    db = get_db()

    # Projekt finden (nach Name oder ID)
    try:
        project_id = int(project)
        proj = db.get_project(project_id)
    except ValueError:
        proj = db.get_project_by_name(project)

    if not proj:
        console.print(f"❌ Projekt nicht gefunden: {project}", style="red")
        sys.exit(1)

    # Stats holen
    db.update_project_cache(proj.id)
    proj = db.get_project(proj.id)  # Neu laden mit Cache

    phases = {p.id: p.display_name for p in db.get_all_phases()}
    phase_name = phases.get(proj.phase_id, "-") if proj.phase_id else "-"

    if json_output:
        data = {
            "id": proj.id,
            "name": proj.name,
            "path": proj.path,
            "phase": phase_name,
            "git_remote": proj.git_remote,
            "codacy": f"{proj.codacy_provider}/{proj.codacy_org}" if proj.codacy_provider else None,
            "issues": {
                "critical": proj.cache_issues_critical,
                "high": proj.cache_issues_high,
                "medium": proj.cache_issues_medium,
                "low": proj.cache_issues_low,
                "false_positives": proj.cache_issues_fp,
            },
            "release": {
                "passed": proj.cache_release_passed,
                "total": proj.cache_release_total,
                "ready": proj.cache_release_ready,
            },
            "last_sync": str(proj.last_sync) if proj.last_sync else None,
        }
        print(json.dumps(data, indent=2))
    else:
        console.print(f"\n📊 [bold]{proj.name}[/bold] ({phase_name})\n")
        console.print(f"📁 Pfad: {proj.path or 'Nicht gesetzt'}")
        console.print(f"🔗 Git: {proj.git_remote or 'Nicht gesetzt'}")
        if proj.codacy_provider:
            console.print(f"📊 Codacy: {proj.codacy_provider}/{proj.codacy_org}")

        console.print("\n[bold]Issues:[/bold]")
        console.print(f"  🔴 Critical: {proj.cache_issues_critical}")
        console.print(f"  🟠 High: {proj.cache_issues_high}")
        console.print(f"  🟡 Medium: {proj.cache_issues_medium}")
        console.print(f"  🟢 Low: {proj.cache_issues_low}")
        console.print(f"  ⚪ False Positives: {proj.cache_issues_fp}")

        if proj.cache_release_total > 0:
            status_icon = "✅" if proj.cache_release_ready else "⚠️"
            console.print(
                f"\n[bold]Release Check:[/bold] {status_icon} {proj.cache_release_passed}/{proj.cache_release_total}"
            )

        if proj.last_sync:
            console.print(f"\n🕐 Letzter Sync: {proj.last_sync}")


# === Sync Command ===


@app.command()
def sync(
    project: str = typer.Argument(..., help="Projektname oder ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Synchronisiert Issues von Codacy."""
    db = get_db()

    # Projekt finden
    try:
        project_id = int(project)
        proj = db.get_project(project_id)
    except ValueError:
        proj = db.get_project_by_name(project)

    if not proj:
        console.print(f"❌ Projekt nicht gefunden: {project}", style="red")
        sys.exit(1)

    if not proj.codacy_provider or not proj.codacy_org:
        console.print("❌ Projekt hat keine Codacy-Konfiguration", style="red")
        sys.exit(1)

    from core.codacy_sync import CodacySync

    sync_client = CodacySync(db=db)
    result = sync_client.sync_project(db, proj)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        if "error" in result:
            console.print(f"❌ {result['error']}", style="red")
            sys.exit(1)

        console.print(f"\n🔄 Sync für [bold]{proj.name}[/bold] abgeschlossen\n")
        console.print(f"  📊 SRM Issues: {result.get('srm', 0)}")
        console.print(f"  📋 Quality Issues: {result.get('quality', 0)}")
        console.print(f"  ✅ Gesamt: {result.get('synced', 0)}")

        if result.get("errors"):
            console.print("\n⚠️ Fehler:")
            for err in result["errors"]:
                console.print(f"  • {err}", style="yellow")


# === Check Command ===


@app.command()
def check(
    project: str = typer.Argument(..., help="Projektname oder ID"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Führt Release-Readiness Check aus."""
    db = get_db()

    # Projekt finden
    try:
        project_id = int(project)
        proj = db.get_project(project_id)
    except ValueError:
        proj = db.get_project_by_name(project)

    if not proj:
        console.print(f"❌ Projekt nicht gefunden: {project}", style="red")
        sys.exit(1)

    if not proj.path:
        console.print("❌ Projekt hat keinen Pfad konfiguriert", style="red")
        sys.exit(1)

    from core.checks import run_all_checks

    results = run_all_checks(db, proj)
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    # Cache aktualisieren
    db.update_release_cache(proj.id, passed, total, passed == total)

    if json_output:
        data = {
            "project": proj.name,
            "passed": passed,
            "total": total,
            "ready": passed == total,
            "checks": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                }
                for r in results
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        status_icon = "✅" if passed == total else "⚠️"
        console.print(f"\n{status_icon} [bold]Release Check: {passed}/{total}[/bold]\n")

        for r in results:
            icon = "✅" if r.passed else ("⚠️" if r.severity == "warning" else "❌")
            console.print(f"  {icon} {r.name}: {r.message}")

        console.print()
        if passed == total:
            console.print("[bold green]✅ Projekt ist release-ready![/bold green]")
        else:
            console.print("[bold yellow]⚠️ Projekt ist noch nicht release-ready[/bold yellow]")


# === Archive Command ===


@app.command()
def archive(
    project: str = typer.Argument(..., help="Projektname oder ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Ohne Bestätigung"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Archiviert ein Projekt (verschiebt Ordner, markiert in DB)."""
    db = get_db()

    # Projekt finden
    try:
        project_id = int(project)
        proj = db.get_project(project_id)
    except ValueError:
        proj = db.get_project_by_name(project)

    if not proj:
        console.print(f"❌ Projekt nicht gefunden: {project}", style="red")
        sys.exit(1)

    # Bestätigung
    if not force and not json_output:
        console.print(f"\n⚠️ [bold]Projekt archivieren: {proj.name}[/bold]\n")
        console.print("Dies wird:")
        console.print(f"  1. Ordner verschieben nach: projekte/archiv/{proj.name}/")
        console.print("  2. Projekt in DB als archiviert markieren")
        console.print()
        console.print("[dim]Hinweis: GitHub Repo muss manuell gelöscht werden (2FA)[/dim]")
        console.print()

        confirm = typer.prompt("Projektname zur Bestätigung eingeben")
        if confirm != proj.name:
            console.print("❌ Abgebrochen (Name stimmt nicht überein)", style="red")
            sys.exit(1)

    initializer = ProjectInitializer(db)
    result = initializer.archive_project(proj.id)

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        for step in result["steps"]:
            console.print(step)

        for error in result["errors"]:
            console.print(f"❌ {error}", style="red")

        console.print()
        if result["success"]:
            console.print("[bold green]✅ Projekt archiviert[/bold green]")
            if result.get("github_url"):
                console.print("\n[yellow]⚠️ GitHub Repo manuell löschen:[/yellow]")
                console.print(f"   {result['github_url']}/settings")
        else:
            console.print("[bold yellow]⚠️ Projekt mit Fehlern archiviert[/bold yellow]")

    sys.exit(0 if result["success"] else 1)


# === Issues Command ===


@app.command()
def issues(
    project: str = typer.Argument(..., help="Projektname oder ID"),
    priority: str | None = typer.Option(
        None, "--priority", "-p", help="Filter: Critical, High, Medium, Low"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximale Anzahl"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe"),
):
    """Listet Issues eines Projekts."""
    db = get_db()

    # Projekt finden
    try:
        project_id = int(project)
        proj = db.get_project(project_id)
    except ValueError:
        proj = db.get_project_by_name(project)

    if not proj:
        console.print(f"❌ Projekt nicht gefunden: {project}", style="red")
        sys.exit(1)

    issue_list = db.get_issues(
        project_id=proj.id,
        priority=priority,
        status="open",
        is_false_positive=False,
    )[:limit]

    if json_output:
        data = [
            {
                "id": i.id,
                "title": i.title,
                "priority": i.priority,
                "file": i.file_path,
                "line": i.line_number,
                "tool": i.tool,
            }
            for i in issue_list
        ]
        print(json.dumps(data, indent=2))
    else:
        table = Table(title=f"Issues: {proj.name}")
        table.add_column("ID", style="cyan")
        table.add_column("Prio", style="bold")
        table.add_column("Issue")
        table.add_column("Datei")
        table.add_column("Zeile")

        prio_colors = {
            "Critical": "red",
            "High": "yellow",
            "Medium": "blue",
            "Low": "green",
        }

        for i in issue_list:
            color = prio_colors.get(i.priority, "white")
            file_name = i.file_path.split("/")[-1] if i.file_path else "-"
            table.add_row(
                str(i.id),
                f"[{color}]{i.priority}[/{color}]",
                i.title[:50] + ("..." if len(i.title) > 50 else ""),
                file_name,
                str(i.line_number) if i.line_number else "-",
            )

        console.print(table)
        console.print(f"\n{len(issue_list)} Issues angezeigt")


# === FAQ Command ===


@app.command()
def faq(
    key: str | None = typer.Argument(None, help="FAQ-Key oder Suchbegriff"),
    category: str | None = typer.Option(
        None, "--category", "-c", help="Filter: process, workflow, command, concept"
    ),
    search: bool = typer.Option(False, "--search", "-s", help="Volltextsuche statt Key-Lookup"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON-Ausgabe (kompakt für KIs)"),
    add: bool = typer.Option(False, "--add", "-a", help="Neuen FAQ-Eintrag hinzufügen"),
):
    """
    KI-FAQ anzeigen oder durchsuchen.

    Beispiele:
        ki-workspace faq                      # Alle FAQs anzeigen
        ki-workspace faq sync_process         # Bestimmten Eintrag
        ki-workspace faq --category workflow  # Nur Workflows
        ki-workspace faq issue -s             # Suche nach 'issue'
        ki-workspace faq --json               # Kompakt für KI-Konsum
    """
    db = get_db()

    # Neuen Eintrag hinzufügen
    if add:
        if not key:
            console.print("❌ Key erforderlich: ki-workspace faq <KEY> --add", style="red")
            sys.exit(1)

        from core.database import FaqEntry

        faq_category = typer.prompt("Kategorie (process/workflow/command/concept)")
        question = typer.prompt("Frage")
        answer = typer.prompt("Antwort (kompakt)")
        tags = typer.prompt("Tags (kommagetrennt)")

        entry = FaqEntry(
            key=key,
            category=faq_category,
            question=question,
            answer=answer,
            tags=[t.strip() for t in tags.split(",") if t.strip()],
        )
        db.upsert_faq(entry)
        console.print(f"✅ FAQ '{key}' gespeichert")
        return

    # Suche
    if search and key:
        results = db.search_faq(key)
        if not results:
            console.print(f"❌ Keine Treffer für: {key}", style="yellow")
            sys.exit(0)

        if json_output:
            data = [{"key": f.key, "q": f.question, "a": f.answer, "tags": f.tags} for f in results]
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            console.print(f"\n🔍 Suche: '{key}' ({len(results)} Treffer)\n")
            for f in results:
                console.print(f"[bold cyan]{f.key}[/bold cyan] ({f.category})")
                console.print(f"  Q: {f.question}")
                console.print(f"  A: {f.answer}")
                console.print()
        return

    # Einzelner Key
    if key and not search:
        entry = db.get_faq(key)
        if not entry:
            console.print(f"❌ FAQ nicht gefunden: {key}", style="red")
            console.print("Tipp: ki-workspace faq -s {key} für Volltextsuche")
            sys.exit(1)

        if json_output:
            data = {"key": entry.key, "q": entry.question, "a": entry.answer, "tags": entry.tags}
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            console.print(f"\n[bold cyan]{entry.key}[/bold cyan] ({entry.category})\n")
            console.print(f"[bold]Q:[/bold] {entry.question}")
            console.print(f"[bold]A:[/bold] {entry.answer}")
            if entry.tags:
                console.print(f"[dim]Tags: {', '.join(entry.tags)}[/dim]")
        return

    # Alle anzeigen (optional nach Kategorie gefiltert)
    if json_output:
        data = db.get_faq_as_json(category)
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        entries = db.get_all_faq(category)
        if not entries:
            console.print("Keine FAQ-Einträge gefunden")
            return

        current_cat = ""
        for f in entries:
            if f.category != current_cat:
                current_cat = f.category
                console.print(f"\n[bold magenta]═══ {current_cat.upper()} ═══[/bold magenta]\n")

            console.print(f"[bold cyan]{f.key}[/bold cyan]")
            console.print(f"  Q: {f.question}")
            console.print(f"  A: {f.answer[:100]}{'...' if len(f.answer) > 100 else ''}")
            console.print()


# === AI Commit Command ===


@app.command()
def commit(
    auto: bool = typer.Option(
        False, "--auto", "-a", help="Automatisch committen ohne Bestaetigung"
    ),
    model: str = typer.Option("", "--model", "-m", help="OpenRouter Model (ueberschreibt Setting)"),
    repo_path: str = typer.Option(".", "--path", "-p", help="Repository Pfad"),
):
    """
    Generiert AI-powered Commit Message aus staged Changes.

    Nutzt OpenRouter API mit konfigurierbarem Model (z.B. Grok).
    Staged Changes werden analysiert und eine Conventional Commit Message erstellt.
    """
    from core.ai_commit import (
        DEFAULT_MODEL,
        ai_commit,
        create_commit,
        get_staged_diff,
    )
    from core.secrets import get_api_key

    db = get_db()

    # API Key holen (aus OS Keyring oder migriert aus DB)
    api_key = get_api_key("openrouter")
    if not api_key:
        console.print("❌ [bold red]OpenRouter API Key nicht konfiguriert![/bold red]")
        console.print("\nSetze den Key via:")
        console.print("  - Web UI: Einstellungen > API Keys > OpenRouter")
        console.print("  - CLI: ki-workspace set-key openrouter <KEY>")
        sys.exit(1)

    # Model holen (Parameter > Setting > Default)
    if not model:
        model = db.get_setting("openrouter_model") or DEFAULT_MODEL

    # Pruefen ob staged changes existieren
    success, diff_or_error = get_staged_diff(repo_path if repo_path != "." else None)
    if not success:
        console.print(f"❌ {diff_or_error}", style="red")
        sys.exit(1)

    console.print("\n🤖 [bold]AI Commit Generator[/bold]")
    console.print(f"   Model: [cyan]{model}[/cyan]\n")

    # Commit Message generieren
    with console.status("[bold blue]Generiere Commit Message...[/bold blue]"):
        result = ai_commit(
            api_key=api_key,
            model=model,
            repo_path=repo_path if repo_path != "." else None,
            auto_confirm=False,  # Immer erst anzeigen
        )

    if not result.success:
        console.print(f"❌ {result.message}", style="red")
        sys.exit(1)

    # Ergebnis anzeigen
    console.print(f"📝 [bold]Diff:[/bold] {result.diff_summary}\n")
    console.print("[bold green]Generierte Commit Message:[/bold green]")
    console.print("─" * 50)
    console.print(result.message)
    console.print("─" * 50)

    # Bei --auto direkt committen
    if auto:
        success, output = create_commit(
            result.message,
            repo_path if repo_path != "." else None,
        )
        if success:
            console.print("\n✅ [bold green]Commit erstellt![/bold green]")
        else:
            console.print(f"\n❌ {output}", style="red")
            sys.exit(1)
        return

    # User fragen
    console.print()
    action = typer.prompt(
        "Was moechtest du tun?",
        type=str,
        default="c",
        show_default=True,
        prompt_suffix="\n  [c]ommit  [e]dit  [a]bbrechen: ",
    )

    if action.lower() in ("c", "commit", "y", "yes", "j", "ja"):
        success, output = create_commit(
            result.message,
            repo_path if repo_path != "." else None,
        )
        if success:
            console.print("\n✅ [bold green]Commit erstellt![/bold green]")
        else:
            console.print(f"\n❌ {output}", style="red")
            sys.exit(1)

    elif action.lower() in ("e", "edit"):
        console.print("\n[dim]Editiere die Message und druecke Enter (leere Zeile = fertig):[/dim]")
        edited_message = typer.edit(result.message)
        if edited_message and edited_message.strip():
            success, output = create_commit(
                edited_message.strip(),
                repo_path if repo_path != "." else None,
            )
            if success:
                console.print("\n✅ [bold green]Commit erstellt![/bold green]")
            else:
                console.print(f"\n❌ {output}", style="red")
                sys.exit(1)
        else:
            console.print("\n⚠️ Abgebrochen (keine Message)")

    else:
        console.print("\n⚠️ Abgebrochen")


@app.command(name="set-key")
def set_key(
    key_type: str = typer.Argument(..., help="Key-Typ: codacy, github, openrouter"),
    value: str = typer.Argument(..., help="API Key Wert"),
):
    """
    Speichert einen API Key (verschluesselt).

    Beispiele:
      ki-workspace set-key openrouter sk-or-v1-xxx
      ki-workspace set-key codacy xxx
      ki-workspace set-key github ghp_xxx
    """
    from core.secrets import set_api_key

    valid_types = {"codacy", "github", "openrouter"}
    descriptions = {
        "codacy": "Codacy API Token",
        "github": "GitHub Token",
        "openrouter": "OpenRouter API Key",
    }

    if key_type.lower() not in valid_types:
        console.print(f"❌ Unbekannter Key-Typ: {key_type}", style="red")
        console.print(f"Verfuegbar: {', '.join(valid_types)}")
        sys.exit(1)

    stored_in_keyring = set_api_key(key_type.lower(), value)  # type: ignore
    description = descriptions[key_type.lower()]

    if stored_in_keyring:
        console.print(f"✅ [bold green]{description} im OS Keyring gespeichert[/bold green]")
    else:
        console.print(f"⚠️ [bold yellow]{description} als Env-Variable gesetzt[/bold yellow]")
        console.print("   (Keyring nicht verfuegbar - nur fuer aktuelle Session)")


# === KI-Kollegen Befehle ===


@app.command()
def prompts(
    category: str | None = typer.Option(None, "-c", "--category", help="Nach Kategorie filtern"),
    json_output: bool = typer.Option(False, "--json", help="JSON-Ausgabe"),
):
    """
    Listet alle KI-Prompt-Templates auf.

    Beispiele:
      ki-workspace prompts
      ki-workspace prompts --category review
      ki-workspace prompts --json
    """
    db = get_db()
    all_prompts = db.get_all_prompts(category)

    if json_output:
        output = [
            {
                "name": p.name,
                "description": p.description,
                "default_ai": p.default_ai,
                "category": p.category,
                "is_builtin": p.is_builtin,
            }
            for p in all_prompts
        ]
        console.print_json(data=output)
        return

    if not all_prompts:
        console.print("Keine Prompts gefunden.", style="yellow")
        return

    table = Table(title="KI-Prompt-Templates", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", width=20)
    table.add_column("Beschreibung", width=30)
    table.add_column("Default-KI", style="yellow", width=10)
    table.add_column("Kategorie", style="green", width=12)
    table.add_column("Typ", width=8)

    for p in all_prompts:
        table.add_row(
            p.name,
            p.description,
            p.default_ai,
            p.category,
            "builtin" if p.is_builtin else "custom",
        )

    console.print(table)
    console.print(f"\n[dim]Gesamt: {len(all_prompts)} Prompts[/dim]")


@app.command(name="prompt-show")
def prompt_show(
    name: str = typer.Argument(..., help="Name des Prompts"),
):
    """
    Zeigt Details eines Prompts an.

    Beispiel:
      ki-workspace prompt-show code_review
    """
    db = get_db()
    prompt = db.get_prompt(name)

    if not prompt:
        console.print(f"❌ Prompt '{name}' nicht gefunden", style="red")
        sys.exit(1)

    console.print(
        Panel.fit(
            f"[bold cyan]{prompt.name}[/bold cyan]\n"
            f"[dim]{prompt.description}[/dim]\n\n"
            f"[yellow]Default-KI:[/yellow] {prompt.default_ai}\n"
            f"[green]Kategorie:[/green] {prompt.category}\n"
            f"[blue]Typ:[/blue] {'builtin' if prompt.is_builtin else 'custom'}\n\n"
            f"[bold]Prompt-Template:[/bold]\n"
            f"[white]{prompt.prompt}[/white]",
            title="Prompt Details",
        )
    )


@app.command(name="prompt-add")
def prompt_add(
    name: str = typer.Argument(..., help="Eindeutiger Name"),
    prompt_text: str = typer.Option(..., "-p", "--prompt", help="Prompt-Template"),
    description: str = typer.Option("", "-d", "--description", help="Beschreibung"),
    default_ai: str = typer.Option("codex", "--ai", help="Default-KI (codex/gemini/claude)"),
    category: str = typer.Option("general", "-c", "--category", help="Kategorie"),
):
    """
    Erstellt einen neuen Prompt.

    Variablen: {file}, {file_content}, {file_name}, {project}, {project_path},
               {git_diff}, {git_diff_staged}, {issues}, {timestamp}

    Beispiel:
      ki-workspace prompt-add my_review -p "Reviewe {file_content}" -d "Mein Review" --ai gemini
    """
    from core.database import AiPrompt

    db = get_db()

    # Pruefen ob Name bereits existiert
    existing = db.get_prompt(name)
    if existing:
        console.print(f"❌ Prompt '{name}' existiert bereits", style="red")
        sys.exit(1)

    new_prompt = AiPrompt(
        name=name,
        description=description,
        prompt=prompt_text,
        default_ai=default_ai,
        category=category,
        is_builtin=False,
    )

    db.upsert_prompt(new_prompt)
    console.print(f"✅ Prompt '[bold cyan]{name}[/bold cyan]' erstellt")


@app.command(name="prompt-delete")
def prompt_delete(
    name: str = typer.Argument(..., help="Name des Prompts"),
):
    """
    Loescht einen benutzerdefinierten Prompt.

    Builtin-Prompts koennen nicht geloescht werden.
    """
    db = get_db()
    prompt = db.get_prompt(name)

    if not prompt:
        console.print(f"❌ Prompt '{name}' nicht gefunden", style="red")
        sys.exit(1)

    if prompt.is_builtin:
        console.print(f"❌ Builtin-Prompt '{name}' kann nicht geloescht werden", style="red")
        sys.exit(1)

    if db.delete_prompt(name):
        console.print(f"✅ Prompt '[bold cyan]{name}[/bold cyan]' geloescht")
    else:
        console.print("❌ Fehler beim Loeschen", style="red")
        sys.exit(1)


@app.command()
def delegate(
    prompt_name: str = typer.Argument(..., help="Name des Prompt-Templates"),
    ai: str | None = typer.Option(None, "--ai", help="KI (codex/gemini/claude), sonst Default"),
    file: str | None = typer.Option(None, "-f", "--file", help="Zieldatei"),
    project: str | None = typer.Option(None, "-p", "--project", help="Projektname"),
    timeout: int = typer.Option(300, "-t", "--timeout", help="Timeout in Sekunden"),
    output_file: str | None = typer.Option(
        None, "-o", "--output", help="Output in Datei speichern"
    ),
):
    """
    Delegiert einen Task an eine KI.

    Beispiele:
      ki-workspace delegate code_review -f src/module.py
      ki-workspace delegate security_audit -p my_project --ai gemini
      ki-workspace delegate git_commit_review -p netman -o review.md
    """
    from core.ai_delegation import delegate_task, list_available_ais

    db = get_db()

    # Prompt laden
    prompt_obj = db.get_prompt(prompt_name)
    if not prompt_obj:
        console.print(f"❌ Prompt '{prompt_name}' nicht gefunden", style="red")
        console.print("Verfuegbare Prompts: [cyan]ki-workspace prompts[/cyan]")
        sys.exit(1)

    # KI bestimmen
    ai_id = ai or prompt_obj.default_ai

    # Verfuegbarkeit pruefen
    available_ais = list_available_ais()
    ai_info = next((a for a in available_ais if a["id"] == ai_id), None)
    if not ai_info or not ai_info["available"]:
        console.print(f"❌ KI '{ai_id}' nicht verfuegbar", style="red")
        for a in available_ais:
            status = "✅" if a["available"] else "❌"
            console.print(f"  {status} {a['id']}: {a['name']}")
        sys.exit(1)

    # Projekt-Pfad ermitteln
    project_path = None
    project_name = None
    if project:
        proj = db.get_project_by_name(project)
        if proj:
            project_path = proj.path
            project_name = proj.name
        else:
            console.print(f"❌ Projekt '{project}' nicht gefunden", style="red")
            sys.exit(1)

    # File-Pfad aufloesen
    file_path = None
    if file:
        from pathlib import Path

        file_path = str(Path(file).resolve())

    console.print(f"[dim]Delegiere an {ai_id}...[/dim]")

    # Task ausfuehren
    with console.status(f"[bold green]Warte auf {ai_id}...[/bold green]"):
        result = delegate_task(
            prompt_template=prompt_obj.prompt,
            ai_id=ai_id,
            file_path=file_path,
            project_path=project_path,
            project_name=project_name,
            timeout=timeout,
        )

    # Ergebnis ausgeben
    if result.success:
        console.print(f"\n✅ [bold green]Erfolgreich[/bold green] ({result.duration_seconds}s)")

        if output_file:
            from pathlib import Path

            Path(output_file).write_text(result.output)
            console.print(f"[dim]Output gespeichert: {output_file}[/dim]")
        else:
            console.print(Panel(result.output, title=f"Antwort von {ai_id}", border_style="green"))
    else:
        console.print(f"\n❌ [bold red]Fehler[/bold red] ({result.duration_seconds}s)")
        console.print(result.error or result.output, style="red")
        sys.exit(1)


@app.command(name="ai-status")
def ai_status():
    """
    Zeigt Status der verfuegbaren KI-CLIs.
    """
    from core.ai_delegation import list_available_ais

    ais = list_available_ais()

    table = Table(title="KI-CLI Status", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Name", width=20)
    table.add_column("Pfad", width=40)
    table.add_column("Status", width=10)

    for ai in ais:
        status = "[green]✅ OK[/green]" if ai["available"] else "[red]❌ Fehlt[/red]"
        table.add_row(ai["id"], ai["name"], ai["path"], status)

    console.print(table)


if __name__ == "__main__":
    app()
