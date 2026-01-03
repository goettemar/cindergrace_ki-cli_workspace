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
# MAIN
# =============================================================================

if __name__ == "__main__":
    app()
