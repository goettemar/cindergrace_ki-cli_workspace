#!/usr/bin/env python3
"""
KI-Workspace CLI - Command Line Interface fuer den KI-CLI Workspace.

Ermoeglicht anderen KIs (Codex, Gemini) und Scripts den Workspace zu bedienen.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.table import Table

from core.database import DatabaseManager

# CLI App
app = typer.Typer(
    name="ki-workspace",
    help="KI-CLI Workspace - Release Readiness & Issue Management",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def get_db() -> DatabaseManager:
    """Gibt die DatabaseManager-Instanz zurueck."""
    return DatabaseManager()


# =============================================================================
# PROJECTS
# =============================================================================


@app.command()
def projects(
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
    include_archived: bool = typer.Option(
        False, "--archived", "-a", help="Archivierte einbeziehen"
    ),
):
    """Listet alle Projekte auf."""
    db = get_db()
    all_projects = db.get_all_projects()

    if not include_archived:
        all_projects = [p for p in all_projects if not p.is_archived]

    if json_output:
        data = [
            {
                "id": p.id,
                "name": p.name,
                "path": p.path,
                "codacy_provider": p.codacy_provider,
                "codacy_org": p.codacy_org,
                "has_codacy": p.has_codacy,
                "is_archived": p.is_archived,
                "last_sync": p.last_sync,
            }
            for p in all_projects
        ]
        console.print_json(json.dumps(data, default=str))
        return

    if not all_projects:
        console.print("[yellow]Keine Projekte gefunden.[/yellow]")
        return

    table = Table(title="Projekte")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Codacy", style="green")
    table.add_column("Letzter Sync", style="dim")

    for p in all_projects:
        codacy = f"{p.codacy_provider}/{p.codacy_org}" if p.has_codacy else "-"
        sync_time = p.last_sync[:16] if p.last_sync else "-"
        table.add_row(str(p.id), p.name, codacy, sync_time)

    console.print(table)


# =============================================================================
# STATUS
# =============================================================================


@app.command()
def status(
    project_name: str = typer.Argument(..., help="Projektname"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
):
    """Zeigt den Status eines Projekts."""
    db = get_db()
    project = db.get_project_by_name(project_name)

    if not project:
        err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
        raise typer.Exit(1)

    # Issue-Statistiken holen
    stats = db.get_issue_stats(project.id)

    if json_output:
        data = {
            "project": {
                "id": project.id,
                "name": project.name,
                "path": project.path,
                "codacy_provider": project.codacy_provider,
                "codacy_org": project.codacy_org,
                "has_codacy": project.has_codacy,
                "last_sync": project.last_sync,
            },
            "issues": stats,
        }
        console.print_json(json.dumps(data, default=str))
        return

    console.print(f"\n[bold cyan]Projekt:[/bold cyan] {project.name}")
    console.print(f"[dim]Pfad:[/dim] {project.path}")

    if project.has_codacy:
        console.print(f"[green]Codacy:[/green] {project.codacy_provider}/{project.codacy_org}")
    else:
        console.print("[yellow]Codacy:[/yellow] nicht konfiguriert")

    sync_time = project.last_sync[:16] if project.last_sync else "nie"
    console.print(f"[dim]Letzter Sync:[/dim] {sync_time}")

    # Issues
    total = stats.get("total", 0)
    critical = stats.get("critical", 0)
    high = stats.get("high", 0)
    fps = stats.get("false_positives", 0)

    console.print(
        f"\n[bold]Issues:[/bold] {total} "
        f"([red]{critical} Critical[/red], [yellow]{high} High[/yellow], "
        f"[dim]{fps} FP[/dim])"
    )


# =============================================================================
# ISSUES
# =============================================================================


@app.command()
def issues(
    project_name: str = typer.Argument(..., help="Projektname"),
    critical: bool = typer.Option(False, "--critical", "-c", help="Nur Critical"),
    high: bool = typer.Option(False, "--high", "-h", help="Nur High"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
):
    """Listet Issues eines Projekts."""
    db = get_db()
    project = db.get_project_by_name(project_name)

    if not project:
        err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
        raise typer.Exit(1)

    # Filter
    priority = None
    if critical:
        priority = "Critical"
    elif high:
        priority = "High"

    all_issues = db.get_issues(project_id=project.id, priority=priority, is_false_positive=False)

    if json_output:
        data = [
            {
                "id": i.id,
                "external_id": i.external_id,
                "priority": i.priority,
                "status": i.status,
                "scan_type": i.scan_type,
                "title": i.title,
                "file_path": i.file_path,
                "line_number": i.line_number,
                "tool": i.tool,
                "rule": i.rule,
                "category": i.category,
                "is_false_positive": i.is_false_positive,
                # KI-Empfehlungsfelder (wichtig: wenn gesetzt, nicht erneut bewerten!)
                "ki_recommendation_category": i.ki_recommendation_category,
                "ki_recommendation": i.ki_recommendation,
                "ki_reviewed_by": i.ki_reviewed_by,
                "ki_reviewed_at": str(i.ki_reviewed_at) if i.ki_reviewed_at else None,
            }
            for i in all_issues
        ]
        console.print_json(json.dumps(data, default=str))
        return

    if not all_issues:
        console.print("[green]Keine Issues gefunden.[/green]")
        return

    table = Table(title=f"Issues - {project.name}")
    table.add_column("ID", style="dim")
    table.add_column("Pri", style="bold")
    table.add_column("Typ", style="cyan")
    table.add_column("Titel")
    table.add_column("Datei", style="dim")

    priority_colors = {
        "Critical": "red",
        "High": "yellow",
        "Medium": "blue",
        "Low": "green",
    }

    for issue in all_issues:
        color = priority_colors.get(issue.priority, "white")
        file_info = f"{issue.file_path}:{issue.line_number}" if issue.file_path else "-"
        table.add_row(
            str(issue.id),
            f"[{color}]{issue.priority}[/{color}]",
            issue.scan_type or "-",
            issue.title[:50] + "..." if len(issue.title or "") > 50 else issue.title,
            file_info[:30],
        )

    console.print(table)


# =============================================================================
# SYNC
# =============================================================================


@app.command()
def sync(
    project_name: str = typer.Argument(..., help="Projektname"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
):
    """Synchronisiert Issues von Codacy."""
    from core.codacy_sync import CodacySync

    db = get_db()
    project = db.get_project_by_name(project_name)

    if not project:
        err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
        raise typer.Exit(1)

    if not project.has_codacy:
        err_console.print(f"[red]Projekt '{project_name}' hat keine Codacy-Konfiguration.[/red]")
        raise typer.Exit(1)

    codacy = CodacySync(db=db)

    if not codacy.api_token:
        err_console.print("[red]Kein CODACY_API_TOKEN konfiguriert.[/red]")
        raise typer.Exit(1)

    if not json_output:
        console.print(f"[dim]Synchronisiere {project.name}...[/dim]")

    result = codacy.sync_project(db, project)

    if json_output:
        console.print_json(json.dumps(result, default=str))
        return

    if result.get("error"):
        err_console.print(f"[red]Fehler: {result['error']}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[green]Sync abgeschlossen:[/green] "
        f"{result.get('srm', 0)} SRM, {result.get('quality', 0)} Quality Issues"
    )


# =============================================================================
# CHECK (Release Readiness)
# =============================================================================


@app.command()
def check(
    project_name: str = typer.Argument(..., help="Projektname"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Nur Exit-Code"),
):
    """Prueft Release Readiness eines Projekts."""
    from core.checks import run_all_checks

    db = get_db()
    project = db.get_project_by_name(project_name)

    if not project:
        err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
        raise typer.Exit(1)

    results = run_all_checks(db, project)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    all_passed = passed == total

    if quiet:
        raise typer.Exit(0 if all_passed else 1)

    if json_output:
        data = {
            "project": project.name,
            "passed": passed,
            "total": total,
            "all_passed": all_passed,
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
        console.print_json(json.dumps(data, default=str))
        raise typer.Exit(0 if all_passed else 1)

    console.print(f"\n[bold]Release Readiness Check - {project.name}[/bold]\n")

    for r in results:
        icon = "[green]OK[/green]" if r.passed else "[red]FAIL[/red]"
        if not r.passed and r.severity == "warning":
            icon = "[yellow]WARN[/yellow]"
        console.print(f"  {icon} {r.name}: {r.message}")

    console.print(f"\n[bold]Status:[/bold] {passed}/{total} Checks bestanden")

    if not all_passed:
        raise typer.Exit(1)


# =============================================================================
# ADD-LICENSE
# =============================================================================


@app.command("add-license")
def add_license(
    project_name: str = typer.Argument(..., help="Projektname"),
    template: str = typer.Option(
        ...,
        "--template",
        "-t",
        help="License Template (polyform-nc, cc-by-nc, mit)",
    ),
):
    """Fuegt eine Lizenz zu einem Projekt hinzu."""
    import shutil
    from pathlib import Path

    db = get_db()
    project = db.get_project_by_name(project_name)

    if not project:
        err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
        raise typer.Exit(1)

    # Template-Mapping
    template_map = {
        "polyform-nc": "POLYFORM_NC.txt",
        "cc-by-nc": "CC_BY_NC_4.txt",
        "mit": "MIT.txt",
    }

    if template.lower() not in template_map:
        err_console.print(f"[red]Unbekanntes Template: {template}[/red]")
        err_console.print(f"Verfuegbar: {', '.join(template_map.keys())}")
        raise typer.Exit(1)

    # Template-Pfad (data/ ist im Projekt-Root, nicht in core/)
    cli_dir = Path(__file__).parent.parent
    template_path = cli_dir / "data" / "licenses" / template_map[template.lower()]

    if not template_path.exists():
        err_console.print(f"[red]Template nicht gefunden: {template_path}[/red]")
        raise typer.Exit(1)

    # Ziel-Pfad
    project_path = Path(project.path)
    if not project_path.exists():
        err_console.print(f"[red]Projekt-Pfad existiert nicht: {project.path}[/red]")
        raise typer.Exit(1)

    license_path = project_path / "LICENSE"

    if license_path.exists():
        err_console.print(f"[yellow]LICENSE existiert bereits in {project.name}[/yellow]")
        if not typer.confirm("Ueberschreiben?"):
            raise typer.Exit(0)

    shutil.copy(template_path, license_path)
    console.print(f"[green]LICENSE hinzugefuegt:[/green] {license_path}")


# =============================================================================
# KI-INFO (Prozessübersicht für KIs)
# =============================================================================


KI_WORKFLOW_INFO = """
# KI-CLI Workspace - Workflow für KIs

## Wichtigste Regel
**Der lokale Status zieht zuerst!** Wenn ein Issue bereits eine KI-Empfehlung hat
(ki_recommendation gesetzt), NICHT erneut bewerten. Der User hat es evtl. nur
noch nicht in Codacy markiert.

## Verfügbare Befehle

### Issues abfragen
```bash
ki-workspace issues <PROJECT> --json     # Alle offenen Issues
ki-workspace issues <PROJECT> --critical # Nur Critical
ki-workspace issues <PROJECT> --high     # Nur High
```

### Issue zum Ignorieren empfehlen
```bash
ki-workspace recommend-ignore <ISSUE_ID> \\
    --category <KATEGORIE> \\
    --reason "Begründung" \\
    --reviewer <KI_NAME>
```

**Kategorien:**
- `accepted_use` - Bewusst so implementiert
- `false_positive` - Tool-Fehlalarm
- `not_exploitable` - Theoretisch verwundbar, praktisch nicht
- `test_code` - Nur in Tests
- `external_code` - Fremdcode/Vendor

**Reviewer:** `claude`, `codex`, `gemini`

### Ausstehende Empfehlungen prüfen
```bash
ki-workspace pending-ignores [PROJECT]   # Was noch markiert werden muss
```

### Projekt-Status
```bash
ki-workspace status <PROJECT>            # Übersicht mit Issue-Statistiken
ki-workspace check <PROJECT>             # Release Readiness Check
ki-workspace sync <PROJECT>              # Von Codacy synchronisieren
```

## Workflow für Issue-Review

1. **Issues laden:** `ki-workspace issues <PROJECT> --json`
2. **Prüfen:** Hat Issue bereits `ki_recommendation`? → SKIP
3. **Analysieren:** Code-Kontext prüfen, ist es ein echtes Problem?
4. **Empfehlen:** `ki-workspace recommend-ignore <ID> --category ... --reason "..."`
5. **User informieren:** "Bitte in Codacy als Ignored markieren"

## Beispiel

```bash
# Critical Issues eines Projekts anzeigen
ki-workspace issues cindergrace-comfyui-runpod --critical --json

# SQL-Injection als False Positive markieren (parameterisierte Query)
ki-workspace recommend-ignore 42 \\
    --category false_positive \\
    --reason "Query ist parameterisiert, Parameter werden nicht in SQL eingebettet" \\
    --reviewer claude

# Prüfen was noch offen ist
ki-workspace pending-ignores cindergrace-comfyui-runpod
```

## Wichtig für den User

Nach KI-Empfehlungen muss der User manuell in Codacy:
1. Issue öffnen
2. "Ignore" klicken
3. Kategorie wählen (wie von KI empfohlen)
4. Kommentar einfügen (KI-Begründung)
5. Speichern

Beim nächsten Sync wird der FP-Status automatisch übernommen.
"""


@app.command("ki-info")
def ki_info(
    markdown: bool = typer.Option(False, "--md", help="Als Markdown ausgeben"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Als JSON"),
):
    """Zeigt Workflow-Infos für KIs an. IMMER ZUERST LESEN!"""
    if json_output:
        data = {
            "commands": {
                "issues": "ki-workspace issues <PROJECT> [--critical|--high] [--json]",
                "recommend-ignore": "ki-workspace recommend-ignore <ID> -c <CATEGORY> -r <REASON>",
                "pending-ignores": "ki-workspace pending-ignores [PROJECT]",
                "status": "ki-workspace status <PROJECT>",
                "check": "ki-workspace check <PROJECT>",
                "sync": "ki-workspace sync <PROJECT>",
            },
            "categories": list(IGNORE_CATEGORIES.keys()),
            "reviewers": ["claude", "codex", "gemini"],
            "important": "Lokaler Status zieht zuerst! Nicht erneut bewerten wenn ki_recommendation bereits gesetzt.",
        }
        console.print_json(json.dumps(data))
        return

    if markdown:
        console.print(KI_WORKFLOW_INFO)
    else:
        # Farbige Ausgabe für Terminal
        console.print("[bold cyan]KI-CLI Workspace - Workflow für KIs[/bold cyan]\n")
        console.print("[bold red]WICHTIG:[/bold red] Lokaler Status zieht zuerst!")
        console.print("Wenn ki_recommendation bereits gesetzt → NICHT erneut bewerten!\n")

        console.print("[bold]Verfügbare Befehle:[/bold]")
        console.print("  issues <PROJECT> [--critical|--high] [--json]")
        console.print("  recommend-ignore <ID> -c <CATEGORY> -r <REASON> --reviewer <KI>")
        console.print("  pending-ignores [PROJECT]")
        console.print("  status <PROJECT>")
        console.print("  check <PROJECT>")
        console.print("  sync <PROJECT>\n")

        console.print("[bold]Kategorien für recommend-ignore:[/bold]")
        for key, label in IGNORE_CATEGORIES.items():
            console.print(f"  [cyan]{key}[/cyan] - {label}")

        console.print("\n[dim]Für ausführliche Doku: ki-workspace ki-info --md[/dim]")


# =============================================================================
# RECOMMEND-IGNORE (KI-Empfehlung)
# =============================================================================


# Gültige Kategorien (entsprechen Codacy UI)
IGNORE_CATEGORIES = {
    "accepted_use": "Accepted use",
    "false_positive": "False positive",
    "not_exploitable": "Not exploitable",
    "test_code": "Test code",
    "external_code": "External code",
}


@app.command("recommend-ignore")
def recommend_ignore(
    issue_id: int = typer.Argument(..., help="Issue ID"),
    category: str = typer.Option(
        ...,
        "--category",
        "-c",
        help="Kategorie: accepted_use, false_positive, not_exploitable, test_code, external_code",
    ),
    reason: str = typer.Option(..., "--reason", "-r", help="Begruendung"),
    reviewer: str = typer.Option("claude", "--reviewer", help="KI-Name (claude, codex, gemini)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
):
    """KI empfiehlt ein Issue zum Ignorieren. User setzt dann manuell in Codacy."""
    db = get_db()

    if category not in IGNORE_CATEGORIES:
        err_console.print(f"[red]Ungueltige Kategorie: {category}[/red]")
        err_console.print(f"Erlaubt: {', '.join(IGNORE_CATEGORIES.keys())}")
        raise typer.Exit(1)

    # Prüfen ob Issue existiert
    issues = db.get_issues()
    issue = next((i for i in issues if i.id == issue_id), None)

    if not issue:
        err_console.print(f"[red]Issue {issue_id} nicht gefunden.[/red]")
        raise typer.Exit(1)

    try:
        db.recommend_ignore(issue_id, category, reason, reviewer)
    except ValueError as e:
        err_console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    if json_output:
        data = {
            "issue_id": issue_id,
            "category": category,
            "category_label": IGNORE_CATEGORIES[category],
            "reason": reason,
            "reviewer": reviewer,
            "status": "pending",
        }
        console.print_json(json.dumps(data))
        return

    console.print(
        f"[green]Empfehlung gespeichert:[/green] Issue #{issue_id}\n"
        f"  Kategorie: {IGNORE_CATEGORIES[category]}\n"
        f"  Grund: {reason}\n"
        f"  Reviewer: {reviewer}\n"
        f"[dim]Bitte manuell in Codacy als Ignored markieren.[/dim]"
    )


# =============================================================================
# PENDING-IGNORES (Noch nicht in Codacy markiert)
# =============================================================================


@app.command("pending-ignores")
def pending_ignores(
    project_name: str = typer.Argument(None, help="Projektname (optional)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON Output"),
):
    """Listet Issues mit KI-Empfehlung die noch nicht in Codacy ignoriert wurden."""
    db = get_db()

    project_id = None
    if project_name:
        project = db.get_project_by_name(project_name)
        if not project:
            err_console.print(f"[red]Projekt '{project_name}' nicht gefunden.[/red]")
            raise typer.Exit(1)
        project_id = project.id

    pending = db.get_pending_ignores(project_id)

    if json_output:
        data = [
            {
                "id": i.id,
                "project_id": i.project_id,
                "title": i.title,
                "priority": i.priority,
                "ki_category": i.ki_recommendation_category,
                "ki_category_label": IGNORE_CATEGORIES.get(i.ki_recommendation_category or "", ""),
                "ki_reason": i.ki_recommendation,
                "ki_reviewer": i.ki_reviewed_by,
                "ki_reviewed_at": str(i.ki_reviewed_at) if i.ki_reviewed_at else None,
            }
            for i in pending
        ]
        console.print_json(json.dumps(data, default=str))
        return

    if not pending:
        console.print("[green]Keine ausstehenden Ignore-Empfehlungen.[/green]")
        return

    table = Table(title="Ausstehende Ignore-Empfehlungen")
    table.add_column("ID", style="dim")
    table.add_column("Pri", style="bold")
    table.add_column("Kategorie", style="cyan")
    table.add_column("Titel")
    table.add_column("Reviewer", style="dim")

    priority_colors = {
        "Critical": "red",
        "High": "yellow",
        "Medium": "blue",
        "Low": "green",
    }

    for issue in pending:
        color = priority_colors.get(issue.priority, "white")
        cat_label = IGNORE_CATEGORIES.get(issue.ki_recommendation_category or "", "-")
        table.add_row(
            str(issue.id),
            f"[{color}]{issue.priority}[/{color}]",
            cat_label,
            issue.title[:40] + "..." if len(issue.title or "") > 40 else issue.title,
            issue.ki_reviewed_by or "-",
        )

    console.print(table)
    console.print(f"\n[dim]Gesamt: {len(pending)} Issue(s) zum manuellen Markieren in Codacy[/dim]")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    app()
