"""
KI-CLI Workspace - Hauptanwendung

Gradio-basierte GUI für Issue-Management und KI-Zusammenarbeit.
"""

import logging
import os

import gradio as gr

from core.codacy_sync import CodacySync
from core.database import DatabaseManager, Project
from core.github_api import GitHubAPI, get_gh_cli_status, run_gh_command
from core.project_tools import (
    create_backup,
    create_test_clone,
    run_final_workflow,
    run_ruff_fix,
)

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KIWorkspaceApp:
    """Hauptanwendung für KI-CLI Workspace."""

    def __init__(self):
        """Initialisiert die Anwendung."""
        self.db = DatabaseManager()
        self.codacy = CodacySync(db=self.db)
        self.github = GitHubAPI(db=self.db)
        self._init_demo_data()

    def _init_demo_data(self) -> None:
        """Initialisiert Demo-Daten falls DB leer."""
        projects = self.db.get_all_projects()
        if not projects:
            # Demo-Projekte anlegen
            demo_projects = [
                Project(
                    name="cindergrace_music_studio",
                    path="/home/zorinadmin/projekte/cindergrace_music_studio",
                    git_remote="git@github.com:goettemar/cindergrace_music_studio.git",
                    codacy_provider="gh",
                    codacy_org="goettemar",
                ),
                Project(
                    name="cindergrace_toolkit",
                    path="/home/zorinadmin/projekte/cindergrace_toolkit",
                    git_remote="git@github.com:goettemar/cindergrace_toolkit.git",
                    codacy_provider="gh",
                    codacy_org="goettemar",
                ),
                Project(
                    name="cindergrace_git_gui",
                    path="/home/zorinadmin/projekte/cindergrace_git_gui",
                    git_remote="git@github.com:goettemar/cindergrace_git_gui.git",
                    codacy_provider="gh",
                    codacy_org="goettemar",
                ),
                Project(
                    name="cindergrace-comfyui-runpod",
                    path="/home/zorinadmin/projekte/cindergrace-comfyui-runpod",
                    git_remote="git@github.com:goettemar/cindergrace-comfyui-runpod.git",
                    codacy_provider="gh",
                    codacy_org="goettemar",
                ),
            ]
            for p in demo_projects:
                self.db.create_project(p)
            logger.info("Demo-Projekte angelegt")

    def get_project_choices(self, include_archived: bool = False) -> list[tuple[str, int]]:
        """Gibt Projekt-Auswahl für Dropdown zurück."""
        projects = self.db.get_all_projects(include_archived=include_archived)
        result = []
        for p in projects:
            label = p.name
            if p.is_archived:
                label = f"📦 {p.name} (archiviert)"
            elif not p.has_codacy:
                label = f"🔒 {p.name}"  # Nur GitHub, kein Codacy
            result.append((label, p.id))
        return result

    def get_issues_table(
        self,
        project_id: int | None,
        priority_filter: str,
        status_filter: str,
        scan_type_filter: str,
        search_query: str,
        show_fps: bool,
    ) -> list[list]:
        """Lädt Issues für die Tabelle."""
        # Filter vorbereiten
        priority = priority_filter if priority_filter != "Alle" else None
        status = status_filter if status_filter != "Alle" else None
        scan_type = scan_type_filter if scan_type_filter != "Alle" else None
        search = search_query.strip() if search_query else None

        # False Positives einbeziehen oder nicht
        is_fp = None if show_fps else False

        issues = self.db.get_issues(
            project_id=project_id,
            priority=priority,
            status=status,
            scan_type=scan_type,
            is_false_positive=is_fp,
            search=search,
        )

        # Sortierung: open zuerst, dann nach Priority
        status_order = {"open": 0, "fixed": 1, "ignored": 2}
        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        issues.sort(
            key=lambda i: (
                status_order.get(i.status, 9),
                priority_order.get(i.priority, 9),
            )
        )

        # Für Tabelle formatieren
        rows = []
        for issue in issues:
            priority_emoji = {
                "Critical": "🔴",
                "High": "🟠",
                "Medium": "🟡",
                "Low": "🟢",
            }.get(issue.priority, "⚪")

            fp_marker = "✓ FP" if issue.is_false_positive else ""

            rows.append(
                [
                    issue.id,
                    priority_emoji,
                    issue.priority or "",
                    issue.scan_type or "",
                    issue.title[:60] + "..." if len(issue.title or "") > 60 else issue.title,
                    f"{issue.file_path}:{issue.line_number}" if issue.file_path else "",
                    issue.tool or "",
                    fp_marker,
                ]
            )

        return rows

    def get_issue_details(self, issue_id: int | None) -> dict:
        """Lädt Issue-Details."""
        if not issue_id:
            return {
                "title": "",
                "message": "",
                "file_info": "",
                "tool_info": "",
                "fp_info": "",
            }

        with self.db._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM issue_meta WHERE id = ?", (issue_id,))
            row = cursor.fetchone()
            if not row:
                return {
                    "title": "Issue nicht gefunden",
                    "message": "",
                    "file_info": "",
                    "tool_info": "",
                    "fp_info": "",
                }

            issue = dict(row)

        fp_info = ""
        if issue.get("is_false_positive"):
            fp_info = f"✅ Als False Positive markiert\nGrund: {issue.get('fp_reason', '-')}"
            if issue.get("fp_marked_at"):
                fp_info += f"\nMarkiert am: {issue.get('fp_marked_at')}"

        return {
            "title": issue.get("title", ""),
            "message": issue.get("message", ""),
            "file_info": f"Datei: {issue.get('file_path', '-')}:{issue.get('line_number', '')}",
            "tool_info": f"Tool: {issue.get('tool', '-')} | Rule: {issue.get('rule', '-')} | Category: {issue.get('category', '-')}",
            "fp_info": fp_info,
            "cve_info": f"CVE: {issue.get('cve', '-')} | Affected: {issue.get('affected_version', '-')} | Fixed in: {issue.get('fixed_version', '-')}"
            if issue.get("cve")
            else "",
        }

    def mark_as_false_positive(self, issue_id: int | None, reason: str) -> str:
        """Markiert Issue als False Positive."""
        if not issue_id:
            return "❌ Kein Issue ausgewählt"
        if not reason.strip():
            return "❌ Bitte Begründung angeben"

        self.db.mark_false_positive(issue_id, reason.strip())
        return f"✅ Issue #{issue_id} als False Positive markiert"

    def get_stats(self, project_id: int | None) -> str:
        """Gibt Statistiken als formatierten String zurück."""
        stats = self.db.get_issue_stats(project_id)

        lines = [
            f"**Gesamt:** {stats['total']} Issues",
            "",
            "**Nach Priorität:**",
        ]

        for prio, count in sorted(
            stats["by_priority"].items(),
            key=lambda x: ["Critical", "High", "Medium", "Low"].index(x[0])
            if x[0] in ["Critical", "High", "Medium", "Low"]
            else 99,
        ):
            emoji = {"Critical": "🔴", "High": "🟠", "Medium": "🟡", "Low": "🟢"}.get(prio, "⚪")
            lines.append(f"  {emoji} {prio}: {count}")

        lines.extend(["", "**Nach Scan-Typ:**"])
        for stype, count in sorted(stats["by_scan_type"].items()):
            lines.append(f"  • {stype}: {count}")

        lines.extend(
            [
                "",
                f"**False Positives:** {stats['false_positives']}",
            ]
        )

        return "\n".join(lines)

    def sync_from_codacy(self, project_id: int | None) -> str:
        """Synchronisiert Issues von Codacy via REST API."""
        if not project_id:
            return "❌ Kein Projekt ausgewählt"

        project = self.db.get_project(project_id)
        if not project:
            return "❌ Projekt nicht gefunden"

        # Token prüfen
        if not self.codacy.api_token:
            return (
                "❌ Kein CODACY_API_TOKEN gesetzt!\n\n"
                "Setze den Token:\n"
                "export CODACY_API_TOKEN=dein_token\n\n"
                "Token erstellen: https://app.codacy.com/account/apiTokens"
            )

        # Sync durchführen
        try:
            stats = self.codacy.sync_project(self.db, project)

            if "error" in stats:
                return f"❌ {stats['error']}"

            result = f"✅ Sync für {project.name} abgeschlossen!\n\n"
            result += f"📊 Security Issues (SRM): {stats['srm']}\n"
            result += f"📋 Quality Issues: {stats['quality']}\n"
            result += f"📦 Gesamt: {stats['synced']}"

            # Cleanup-Info anzeigen
            cleaned = stats.get("cleaned", 0)
            cleaned_pending = stats.get("cleaned_pending", 0)
            if cleaned or cleaned_pending:
                result += f"\n\n🧹 Bereinigt: {cleaned} Issues, {cleaned_pending} Pending Ignores"

            if stats.get("errors"):
                result += f"\n\n⚠️ Fehler: {', '.join(stats['errors'])}"

            return result
        except Exception as e:
            logger.error(f"Sync-Fehler: {e}")
            return f"❌ Sync-Fehler: {e}"

    def build_ui(self) -> gr.Blocks:
        """Erstellt die Gradio-Oberfläche."""
        # Custom CSS für größere Schrift (Standard: ~14px, jetzt: 18px)
        custom_css = """
        .gradio-container {
            font-size: 18px !important;
        }
        .markdown-text {
            font-size: 18px !important;
        }
        .prose {
            font-size: 18px !important;
        }
        label {
            font-size: 16px !important;
        }
        input, textarea, select {
            font-size: 16px !important;
        }
        button {
            font-size: 16px !important;
        }
        table {
            font-size: 16px !important;
        }
        .dataframe {
            font-size: 15px !important;
        }
        """
        with gr.Blocks(title="KI-CLI Workspace", css=custom_css) as app:
            gr.Markdown("# 🤖 KI-CLI Workspace")
            gr.Markdown("Issue-Management und KI-übergreifende Zusammenarbeit")

            # Globale Projekt-Auswahl
            with gr.Row():
                project_dropdown = gr.Dropdown(
                    choices=self.get_project_choices(),
                    label="Projekt",
                    value=None,
                    interactive=True,
                    scale=3,
                )
                refresh_dropdown_btn = gr.Button("🔄", size="sm", min_width=40)

            with gr.Tabs():
                # === Dashboard Tab ===
                with gr.Tab("📊 Dashboard"):
                    gr.Markdown("### Projekt-Übersicht")
                    gr.Markdown("*Gecachte Daten - aktualisiert bei Sync/Release Check*")

                    with gr.Row():
                        refresh_all_btn = gr.Button("🔄 Alle aktualisieren", variant="primary")
                        new_project_btn = gr.Button("🆕 Neues Projekt", variant="secondary")
                        dashboard_msg = gr.Markdown("")

                    # === Neues Projekt Panel (ausklappbar) ===
                    with gr.Group(visible=False) as new_project_panel:
                        gr.Markdown("### 🆕 Neues Projekt erstellen")
                        with gr.Row():
                            new_proj_name = gr.Textbox(
                                label="Projektname",
                                placeholder="cindergrace_mein_projekt",
                                scale=2,
                            )
                            new_proj_status = gr.Dropdown(
                                choices=["alpha", "beta", "stable"],
                                value="alpha",
                                label="Status",
                                scale=1,
                            )
                        new_proj_desc = gr.Textbox(
                            label="Beschreibung",
                            placeholder="Kurze Beschreibung des Projekts",
                        )
                        with gr.Row():
                            create_proj_btn = gr.Button("🚀 Projekt erstellen", variant="primary")
                            cancel_proj_btn = gr.Button("Abbrechen")
                        new_proj_result = gr.Markdown("")

                    dashboard_table = gr.Dataframe(
                        headers=[
                            "ID",
                            "Projekt",
                            "Phase",
                            "🔴 Crit",
                            "🟠 High",
                            "🟡 Med",
                            "🟢 Low",
                            "FP",
                            "CI",
                            "Git",
                            "Release",
                            "PyPI",
                            "Codacy",
                        ],
                        datatype=[
                            "number",
                            "str",
                            "str",
                            "number",
                            "number",
                            "number",
                            "number",
                            "number",
                            "str",
                            "str",
                            "str",
                            "str",
                            "str",
                        ],
                        interactive=False,
                    )

                    gr.Markdown("---")
                    gr.Markdown(
                        "**Legende:** "
                        "🔴 Critical | 🟠 High | 🟡 Medium | 🟢 Low | "
                        "FP = False Positives + KI-Empfehlungen | "
                        "✅ Ready | ⚠️ Not Ready | ❓ Nicht geprüft"
                    )

                    # === Detail-Panel (erscheint bei Klick auf Projekt) ===
                    gr.Markdown("---")
                    dash_selected_id = gr.State(value=None)

                    with gr.Group(visible=False) as dash_detail_group:
                        # Header: Projektname + Buttons
                        with gr.Row():
                            dash_detail_header = gr.Markdown("### 📁 Projekt")
                            with gr.Row():
                                dash_sync_btn = gr.Button("🔄 Sync", size="sm", min_width=80)
                                dash_check_btn = gr.Button("✓ Check", size="sm", min_width=80)
                                dash_goto_btn = gr.Button("📋 Issues", size="sm", min_width=80)
                                dash_archive_btn = gr.Button(
                                    "📦 Archiv", size="sm", variant="stop", min_width=80
                                )

                        # Zwei-Spalten Layout
                        with gr.Row(equal_height=True):
                            # Linke Spalte: Projekt-Infos
                            with gr.Column(scale=1, min_width=300):
                                dash_info_table = gr.Markdown("*Projekt auswählen...*")

                            # Rechte Spalte: GitHub About + Topics
                            with gr.Column(scale=1, min_width=300):
                                dash_github_about = gr.Markdown("**📝 About:** *-*")
                                dash_github_topics = gr.Markdown("**🏷️ Topics:** *-*")

                        dash_detail_msg = gr.Markdown("")

                        # Archiv-Bestätigung (ausgeblendet)
                        with gr.Group(visible=False) as archive_confirm_group:
                            gr.Markdown("### ⚠️ Projekt archivieren?")
                            gr.Markdown(
                                "Dies verschiebt den Ordner nach `/projekte/archiv/`, "
                                "löscht das GitHub Repo und archiviert in der DB."
                            )
                            archive_confirm_name = gr.Textbox(
                                label="Projektname zur Bestätigung",
                                placeholder="Projektname",
                            )
                            with gr.Row():
                                archive_confirm_btn = gr.Button(
                                    "🗑️ Endgültig archivieren", variant="stop"
                                )
                                archive_cancel_btn = gr.Button("Abbrechen")

                # === Issues Tab (Codacy) ===
                with gr.Tab("📋 Issues (Codacy)"):
                    # Sync-Bereich
                    with gr.Row():
                        sync_btn = gr.Button("🔄 Sync von Codacy", variant="primary", scale=2)
                        dummy_push_btn = gr.Button(
                            "🚀 Dummy Push (Re-Analyse)", variant="secondary", scale=2
                        )
                        sync_status = gr.Textbox(
                            label="Status", interactive=False, scale=4, max_lines=2
                        )

                    gr.Markdown("---")

                    # Filter
                    with gr.Row():
                        priority_filter = gr.Dropdown(
                            choices=["Alle", "Critical", "High", "Medium", "Low"],
                            value="Alle",
                            label="Priorität",
                        )
                        status_filter = gr.Dropdown(
                            choices=["Alle", "open", "ignored", "fixed"],
                            value="Alle",
                            label="Status",
                        )
                        scan_type_filter = gr.Dropdown(
                            choices=["Alle", "SAST", "SCA", "IaC", "Secrets", "CICD"],
                            value="Alle",
                            label="Scan-Typ",
                        )
                        show_fps = gr.Checkbox(label="False Positives zeigen", value=False)

                    search_box = gr.Textbox(
                        label="🔍 Volltextsuche",
                        placeholder="SQL injection, semgrep, manager.py...",
                    )

                    # Issues-Tabelle
                    issues_table = gr.Dataframe(
                        headers=["ID", "Pri", "Priorität", "Typ", "Titel", "Datei", "Tool", "FP"],
                        datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
                        column_count=(8, "fixed"),
                        interactive=False,
                    )

                    # Issue Details
                    gr.Markdown("### Issue Details")
                    detail_title = gr.Textbox(label="Titel", interactive=False)
                    detail_message = gr.Textbox(label="Meldung", interactive=False, lines=3)
                    detail_file = gr.Textbox(label="Datei", interactive=False)
                    detail_tool = gr.Textbox(label="Tool/Rule", interactive=False)
                    detail_cve = gr.Textbox(label="CVE Info", interactive=False, visible=True)
                    detail_fp = gr.Textbox(
                        label="False Positive Status", interactive=False, lines=4
                    )

                    # Hidden: Issue ID für Event-Handler
                    selected_issue_id = gr.Number(visible=False)

                # === Pending Ignores Tab (KI-Empfehlungen) ===
                with gr.Tab("📋 Pending Ignores"):
                    gr.Markdown("### KI-Empfehlungen zum Ignorieren")
                    gr.Markdown(
                        "Issues die eine KI (Claude, Codex, Gemini) zum Ignorieren empfohlen hat, "
                        "aber noch nicht in Codacy als Ignored markiert wurden."
                    )

                    with gr.Row():
                        refresh_pending_btn = gr.Button("🔄 Aktualisieren", variant="primary")
                        pending_count = gr.Markdown("")

                    pending_ignores_table = gr.Dataframe(
                        headers=[
                            "ID",
                            "Pri",
                            "Kategorie",
                            "Titel",
                            "Begründung",
                            "Reviewer",
                            "Datum",
                        ],
                        datatype=["number", "str", "str", "str", "str", "str", "str"],
                        interactive=False,
                    )

                    # Detail-Panel für vollständige Begründung
                    with gr.Accordion("📝 Details für Codacy", open=True):
                        gr.Markdown(
                            "*Klicke auf eine Zeile. Kopiere Kategorie + Begründung für Codacy.*"
                        )
                        detail_issue_info = gr.Markdown("*Keine Auswahl*")

                        with gr.Row():
                            detail_category = gr.Textbox(
                                label="🏷️ Kategorie (in Codacy auswählen)",
                                interactive=False,
                            )
                        detail_category_hint = gr.Markdown("")

                        with gr.Row():
                            detail_reason = gr.Textbox(
                                label="📋 Begründung (in Codacy einfügen)",
                                lines=4,
                                interactive=False,
                                scale=9,
                            )
                            copy_reason_btn = gr.Button(
                                "📋", scale=1, min_width=50, variant="secondary"
                            )
                        copy_result = gr.Markdown("")

                    gr.Markdown("---")
                    gr.Markdown(
                        "**Workflow:**\n"
                        "1. KI analysiert Issue und ruft `ki-workspace recommend-ignore` auf\n"
                        "2. User sieht Empfehlung hier in der Liste\n"
                        "3. User markiert manuell in Codacy Web-UI als Ignored\n"
                        "4. Nächster Sync entfernt Issue aus dieser Liste"
                    )

                    # Kategorie-Legende
                    with gr.Accordion("📖 Kategorien-Erklärung", open=False):
                        gr.Markdown(
                            "| Kategorie | Bedeutung |\n"
                            "|-----------|----------|\n"
                            "| **Accepted use** | Bewusst so implementiert, kein Risiko |\n"
                            "| **False positive** | Tool-Fehlalarm, kein echtes Problem |\n"
                            "| **Not exploitable** | Theoretisch verwundbar, praktisch nicht ausnutzbar |\n"
                            "| **Test code** | Nur in Tests, nicht in Produktion |\n"
                            "| **External code** | Fremdcode/Vendor, nicht von uns wartbar |"
                        )

                # === GitHub Status Tab ===
                with gr.Tab("🐙 GitHub"):
                    gr.Markdown("### GitHub Status")

                    # Obere Reihe: 3 Spalten
                    with gr.Row():
                        # Links: Aktualisieren + gh CLI Status
                        with gr.Column(scale=1):
                            refresh_github_all_btn = gr.Button(
                                "🔄 Aktualisieren", variant="primary", size="lg"
                            )
                            gr.Markdown("#### gh CLI Status")
                            gh_cli_status_box = gr.Markdown()

                        # Mitte: Push & Sync + Git Status + Änderungen
                        with gr.Column(scale=1):
                            with gr.Row():
                                commit_msg_input = gr.Textbox(
                                    label="Commit Message",
                                    placeholder="Änderungen beschreiben...",
                                    lines=1,
                                    max_lines=2,
                                    scale=5,
                                )
                                ai_commit_btn = gr.Button("🤖 AI", variant="secondary", scale=1)
                            with gr.Row():
                                push_sync_btn = gr.Button("🚀 Push & Sync", variant="secondary")
                                push_sync_output = gr.Markdown("")
                            gr.Markdown("#### 📂 Git Status")
                            git_status_box = gr.Markdown("*Projekt auswählen*")
                            gr.Markdown("#### 📝 Änderungen")
                            git_changes_box = gr.Textbox(
                                value="*Projekt auswählen*",
                                lines=8,
                                max_lines=20,
                                interactive=False,
                                show_label=False,
                            )

                        # Rechts: Notifications + Repo Info
                        with gr.Column(scale=1):
                            gr.Markdown("#### 🔔 Notifications")
                            gh_notifications_box = gr.Textbox(
                                value="",
                                lines=4,
                                max_lines=8,
                                interactive=False,
                                show_label=False,
                            )
                            gr.Markdown("#### 📝 About")
                            gh_repo_about = gr.Markdown("*-*")
                            gr.Markdown("#### 🏷️ Topics")
                            gh_repo_topics = gr.Markdown("*-*")

                    gr.Markdown("---")
                    gr.Markdown("#### ⚡ GitHub Actions (letzte 5)")

                    gh_actions_table = gr.Dataframe(
                        headers=["Status", "Workflow", "Branch", "Commit", "Zeit"],
                        datatype=["str", "str", "str", "str", "str"],
                        interactive=False,
                        row_count=5,
                    )
                    gh_actions_debug = gr.Markdown("")  # Debug-Ausgabe

                    gr.Markdown("---")
                    gr.Markdown("#### gh CLI Befehl ausführen")

                    with gr.Row():
                        gh_command_input = gr.Textbox(
                            label="Befehl (ohne 'gh' Prefix)",
                            placeholder="repo list --limit 10",
                            scale=4,
                        )
                        run_gh_cmd_btn = gr.Button("▶️ Ausführen", scale=1)

                    gh_command_output = gr.Code(
                        label="Ausgabe",
                        language=None,
                        lines=10,
                    )

                # === Release Check Tab ===
                with gr.Tab("✅ Release Check"):
                    gr.Markdown("### Release Readiness Check")
                    gr.Markdown("Prüft ob ein Projekt bereit für Release/Publikation ist.")

                    # Projekt-Phase Auswahl
                    with gr.Row():
                        phase_dropdown = gr.Dropdown(
                            label="📊 Projekt-Phase",
                            choices=[],
                            value=None,
                            interactive=True,
                        )
                        save_phase_btn = gr.Button("💾 Phase speichern")

                    phase_info = gr.Markdown("*Phase bestimmt welche Checks aktiv sind*")

                    def load_phases():
                        """Lädt alle Phasen als Choices."""
                        phases = self.db.get_all_phases()
                        return [(f"{p.display_name}", p.id) for p in phases]

                    def get_project_phase(project_id: int | None):
                        """Gibt die aktuelle Phase eines Projekts zurück."""
                        if not project_id:
                            return gr.update(choices=load_phases(), value=None)
                        project = self.db.get_project(project_id)
                        if not project:
                            return gr.update(choices=load_phases(), value=None)
                        choices = load_phases()
                        return gr.update(choices=choices, value=project.phase_id)

                    def save_project_phase(project_id: int | None, phase_id: int | None):
                        """Speichert die Phase eines Projekts und aktualisiert README."""
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        if not phase_id:
                            return "❌ Keine Phase ausgewählt"
                        # set_project_phase aktualisiert auch die README
                        success, msg = self.db.set_project_phase(project_id, phase_id)
                        if success:
                            return f"✅ {msg}"
                        return f"❌ {msg}"

                    def get_phase_description(phase_id: int | None):
                        """Gibt die Beschreibung einer Phase zurück."""
                        if not phase_id:
                            return "*Phase bestimmt welche Checks aktiv sind*"
                        phase = self.db.get_phase(phase_id)
                        if not phase:
                            return "*Phase bestimmt welche Checks aktiv sind*"
                        enabled = self.db.get_enabled_checks_for_phase(phase_id)
                        check_list = ", ".join(sorted(enabled.keys()))
                        return f"**{phase.display_name}**: {phase.description}\n\nAktive Checks: {check_list}"

                    # Bei Projektwechsel Phase laden
                    project_dropdown.change(
                        fn=get_project_phase,
                        inputs=[project_dropdown],
                        outputs=[phase_dropdown],
                    )

                    # Phase-Beschreibung aktualisieren
                    phase_dropdown.change(
                        fn=get_phase_description,
                        inputs=[phase_dropdown],
                        outputs=[phase_info],
                    )

                    # Phase speichern
                    save_phase_btn.click(
                        fn=save_project_phase,
                        inputs=[project_dropdown, phase_dropdown],
                        outputs=[phase_info],
                    )

                    gr.Markdown("---")

                    with gr.Row():
                        check_btn = gr.Button("🔍 Check ausführen", variant="primary")

                    check_output = gr.Dataframe(
                        headers=["Status", "Check", "Ergebnis", "Wichtigkeit"],
                        datatype=["str", "str", "str", "str"],
                        interactive=False,
                        label="Check-Ergebnisse",
                    )

                    check_summary = gr.Markdown("")

                    def run_release_check(project_id: int | None):
                        """Führt Release Check für das Projekt aus."""
                        if not project_id:
                            return [], "❌ Kein Projekt ausgewählt"

                        from core.checks import get_phase_info, run_all_checks

                        project = self.db.get_project(project_id)
                        if not project:
                            return [], "❌ Projekt nicht gefunden"

                        results = run_all_checks(self.db, project)

                        # Severity-Badges mit Farben
                        severity_badges = {
                            "error": "🔴 Blocker",
                            "warning": "🟡 Empfohlen",
                            "info": "⚪ Info",
                        }

                        rows = []
                        for r in results:
                            icon = "✅" if r.passed else "❌"
                            if not r.passed and r.severity == "warning":
                                icon = "⚠️"
                            badge = severity_badges.get(r.severity, r.severity)
                            rows.append([icon, r.name, r.message, badge])

                        passed = sum(1 for r in results if r.passed)
                        total = len(results)
                        ready = passed == total
                        status = "READY" if ready else "NOT READY"
                        color = "green" if ready else "red"

                        # Cache aktualisieren
                        self.db.update_release_cache(project_id, passed, total, ready)

                        # Phase-Info im Summary
                        phase_info_data = get_phase_info(self.db, project.phase_id)
                        phase_text = ""
                        if phase_info_data:
                            phase_text = f" | Phase: **{phase_info_data['display_name']}**"

                        summary = f"### Status: **{passed}/{total}** Checks bestanden{phase_text} - <span style='color:{color}'>{status}</span>"

                        return rows, summary

                    check_btn.click(
                        fn=run_release_check,
                        inputs=[project_dropdown],
                        outputs=[check_output, check_summary],
                    )

                # === KI-Übergaben Tab ===
                with gr.Tab("🤝 KI-Übergaben"):
                    gr.Markdown("### Session-Übergaben zwischen KI-CLIs")
                    gr.Markdown("*Kommt in Phase 2*")

                # === Einstellungen Tab ===
                with gr.Tab("⚙️ Einstellungen"):  # noqa: SIM117
                    with gr.Tabs():
                        # --- API Keys ---
                        with gr.Tab("🔑 API Keys"):
                            # GitHub Token
                            gr.Markdown("## GitHub Token")
                            gr.Markdown(
                                "Für Zugriff auf private Repositories. "
                                "[→ Token erstellen](https://github.com/settings/tokens) "
                                "(Scope: `repo` für private Repos)"
                            )
                            github_token_status = gr.Markdown()

                            with gr.Row():
                                github_token_input = gr.Textbox(
                                    label="GitHub Token",
                                    type="password",
                                    placeholder="ghp_... oder github_pat_...",
                                    scale=4,
                                )
                                save_github_token_btn = gr.Button(
                                    "💾 Speichern", variant="primary", scale=1
                                )
                            github_token_result = gr.Markdown()

                            gr.Markdown("---")

                            # Codacy Token
                            gr.Markdown("## Codacy API Token")
                            gr.Markdown(
                                "Für Issue-Synchronisation. "
                                "[→ Token erstellen](https://app.codacy.com/account/apiTokens)"
                            )

                            # Token Status prominent anzeigen
                            token_status_box = gr.Markdown(
                                elem_classes=["token-status-box"],
                            )

                            with gr.Row():
                                api_token_input = gr.Textbox(
                                    label="Codacy Token",
                                    type="password",
                                    placeholder="Neuen Token hier eingeben um zu ersetzen...",
                                    scale=4,
                                )
                                save_token_btn = gr.Button(
                                    "💾 Speichern", variant="primary", scale=1
                                )

                            token_save_result = gr.Markdown()

                            gr.Markdown("---")

                            # OpenRouter Token
                            gr.Markdown("## OpenRouter API Key")
                            gr.Markdown(
                                "Für AI Commit Messages. "
                                "[→ Key erstellen](https://openrouter.ai/keys)"
                            )
                            openrouter_token_status = gr.Markdown()

                            with gr.Row():
                                openrouter_token_input = gr.Textbox(
                                    label="OpenRouter Key",
                                    type="password",
                                    placeholder="sk-or-v1-...",
                                    scale=4,
                                )
                                save_openrouter_btn = gr.Button(
                                    "💾 Speichern", variant="primary", scale=1
                                )

                            openrouter_save_result = gr.Markdown()

                            # OpenRouter Model
                            gr.Markdown("### AI Commit Model")
                            gr.Markdown(
                                "*Beispiele: `x-ai/grok-3-mini-beta`, `anthropic/claude-sonnet-4`, "
                                "`openai/gpt-4o-mini`, `google/gemini-2.0-flash-001`*"
                            )
                            with gr.Row():
                                openrouter_model_input = gr.Textbox(
                                    label="Model ID",
                                    value=self.db.get_setting("openrouter_model")
                                    or "x-ai/grok-3-mini-beta",
                                    placeholder="z.B. x-ai/grok-3-mini-beta",
                                    scale=4,
                                )
                                save_model_btn = gr.Button(
                                    "💾 Speichern", variant="primary", scale=1
                                )

                            model_save_result = gr.Markdown()

                        # --- Projekte ---
                        with gr.Tab("📁 Projekte"):
                            # GitHub Import
                            gr.Markdown("### 🐙 Von GitHub laden")
                            gr.Markdown(
                                "Lädt alle Repositories aus deinem GitHub-Account. "
                                "Erfordert einen GitHub Token (siehe API Keys)."
                            )

                            with gr.Row():
                                include_private_repos = gr.Checkbox(
                                    label="Private Repos einbeziehen", value=True
                                )
                                load_github_btn = gr.Button(
                                    "🔄 Repos von GitHub laden", variant="primary"
                                )

                            github_import_status = gr.Markdown()

                            gr.Markdown("---")
                            gr.Markdown("### Vorhandene Projekte")

                            with gr.Row():
                                show_archived_toggle = gr.Checkbox(
                                    label="📦 Archivierte anzeigen", value=False
                                )
                                refresh_projects_btn = gr.Button("🔄 Aktualisieren")

                            projects_table = gr.Dataframe(
                                headers=[
                                    "ID",
                                    "Name",
                                    "Owner",
                                    "Codacy",
                                    "Status",
                                ],
                                datatype=["number", "str", "str", "str", "str"],
                                interactive=False,
                            )

                            # Projekt-Aktionen
                            gr.Markdown("### Aktionen")
                            with gr.Row():
                                action_project_id = gr.Number(label="Projekt-ID", precision=0)
                                toggle_codacy_btn = gr.Button("🔀 Codacy umschalten")
                                archive_btn = gr.Button("📦 Archivieren")
                                unarchive_btn = gr.Button("📤 Wiederherstellen")

                            project_action_status = gr.Markdown()

                            # Manuelles Hinzufügen (eingeklappt)
                            with gr.Accordion("➕ Manuell hinzufügen", open=False):
                                with gr.Row():
                                    new_project_name = gr.Textbox(
                                        label="Name", placeholder="mein-projekt"
                                    )
                                    new_project_path = gr.Textbox(
                                        label="Lokaler Pfad",
                                        placeholder="/home/user/projekte/...",
                                    )

                                with gr.Row():
                                    new_project_remote = gr.Textbox(
                                        label="Git Remote",
                                        placeholder="git@github.com:user/repo.git",
                                    )
                                    new_project_provider = gr.Dropdown(
                                        choices=[
                                            ("GitHub", "gh"),
                                            ("GitLab", "gl"),
                                            ("Bitbucket", "bb"),
                                        ],
                                        value="gh",
                                        label="Provider",
                                    )
                                    new_project_org = gr.Textbox(
                                        label="Organisation", placeholder="username"
                                    )

                                new_project_has_codacy = gr.Checkbox(
                                    label="Hat Codacy-Integration", value=True
                                )
                                add_project_btn = gr.Button(
                                    "➕ Projekt hinzufügen", variant="primary"
                                )
                                add_project_status = gr.Markdown()

                            # Pfad-Einstellungen für Projekt-Tools
                            with gr.Accordion("📂 Pfad-Einstellungen", open=False):
                                gr.Markdown("Pfade für Backup und Test-Clone Funktionen.")

                                backup_path_setting = gr.Textbox(
                                    label="Backup-Basis-Pfad",
                                    value=self.db.get_setting("backup_base_path")
                                    or "~/projekte_backup",
                                    placeholder="~/projekte_backup",
                                )
                                test_clone_path_setting = gr.Textbox(
                                    label="Test-Clone-Basis-Pfad",
                                    value=self.db.get_setting("test_clone_base_path")
                                    or "~/projekte_test",
                                    placeholder="~/projekte_test",
                                )

                                with gr.Row():
                                    save_paths_btn = gr.Button(
                                        "💾 Pfade speichern", variant="primary"
                                    )
                                    paths_status = gr.Markdown()

                                def save_tool_paths(backup_path: str, clone_path: str) -> str:
                                    """Speichert die Pfad-Einstellungen."""
                                    msgs = []
                                    if backup_path.strip():
                                        self.db.set_setting("backup_base_path", backup_path.strip())
                                        msgs.append("Backup-Pfad")
                                    if clone_path.strip():
                                        self.db.set_setting(
                                            "test_clone_base_path", clone_path.strip()
                                        )
                                        msgs.append("Test-Clone-Pfad")
                                    if msgs:
                                        return f"✅ Gespeichert: {', '.join(msgs)}"
                                    return "⚠️ Nichts zu speichern"

                                save_paths_btn.click(
                                    fn=save_tool_paths,
                                    inputs=[backup_path_setting, test_clone_path_setting],
                                    outputs=[paths_status],
                                )

                            # Gitignore Required Patterns
                            with gr.Accordion("🚫 Gitignore Patterns", open=False):
                                gr.Markdown(
                                    "Patterns die in jeder .gitignore vorhanden sein müssen. "
                                    "Ein Pattern pro Zeile (z.B. `/temp`, `*.log`)."
                                )

                                import json

                                # Patterns aus DB laden
                                patterns_json = (
                                    self.db.get_setting("gitignore_required_patterns") or "[]"
                                )
                                try:
                                    patterns_list = json.loads(patterns_json)
                                except json.JSONDecodeError:
                                    patterns_list = []
                                patterns_text = "\n".join(patterns_list)

                                gitignore_patterns_input = gr.Textbox(
                                    label="Erforderliche Patterns",
                                    value=patterns_text,
                                    placeholder="/temp\n*.log\n.env",
                                    lines=5,
                                )

                                with gr.Row():
                                    save_patterns_btn = gr.Button(
                                        "💾 Patterns speichern", variant="primary"
                                    )
                                    patterns_status = gr.Markdown()

                                def save_gitignore_patterns(patterns_text: str) -> str:
                                    """Speichert die Gitignore-Patterns."""
                                    import json

                                    lines = [
                                        line.strip()
                                        for line in patterns_text.strip().split("\n")
                                        if line.strip()
                                    ]
                                    self.db.set_setting(
                                        "gitignore_required_patterns", json.dumps(lines)
                                    )
                                    return f"✅ {len(lines)} Pattern(s) gespeichert"

                                save_patterns_btn.click(
                                    fn=save_gitignore_patterns,
                                    inputs=[gitignore_patterns_input],
                                    outputs=[patterns_status],
                                )

                        # --- Check-Matrix ---
                        with gr.Tab("📊 Check-Matrix"):
                            gr.Markdown("### Phasen & Release Checks")
                            gr.Markdown(
                                "Konfiguriere welche Checks in welcher Projekt-Phase aktiv sind "
                                "und wie wichtig sie sind (Blocker vs. Empfohlen)."
                            )

                            # Phase-Auswahl - Phasen direkt laden
                            def load_matrix_phases():
                                """Lädt Phasen für Matrix-Dropdown."""
                                phases = self.db.get_all_phases()
                                return [(f"{p.display_name} ({p.name})", p.id) for p in phases]

                            matrix_phase_dropdown = gr.Dropdown(
                                label="Phase auswählen",
                                choices=load_matrix_phases(),
                                value=None,
                                interactive=True,
                            )

                            matrix_table = gr.Dataframe(
                                headers=["Check", "Aktiv", "Wichtigkeit"],
                                datatype=["str", "bool", "str"],
                                interactive=True,
                                label="Checks für diese Phase",
                            )

                            with gr.Row():
                                save_matrix_btn = gr.Button(
                                    "💾 Matrix speichern", variant="primary"
                                )
                                matrix_status = gr.Markdown()

                            def load_matrix_for_phase(phase_id: int | None):
                                """Lädt die Check-Matrix für eine Phase."""
                                if not phase_id:
                                    return []
                                entries = self.db.get_check_matrix_for_phase(phase_id)
                                rows = []
                                for e in entries:
                                    severity_display = {
                                        "error": "🔴 Blocker",
                                        "warning": "🟡 Empfohlen",
                                        "info": "⚪ Info",
                                    }.get(e.severity, e.severity)
                                    rows.append([e.check_name, e.enabled, severity_display])
                                return rows

                            def save_matrix(phase_id: int | None, matrix_data: list):
                                """Speichert die Check-Matrix."""
                                if not phase_id:
                                    return "❌ Keine Phase ausgewählt"
                                if not matrix_data:
                                    return "❌ Keine Daten"

                                # Severity-Mapping zurück
                                severity_map = {
                                    "🔴 Blocker": "error",
                                    "🟡 Empfohlen": "warning",
                                    "⚪ Info": "info",
                                }

                                for row in matrix_data:
                                    if len(row) >= 3:
                                        check_name = row[0]
                                        enabled = bool(row[1])
                                        severity = severity_map.get(row[2], row[2])
                                        self.db.update_check_matrix_entry(
                                            phase_id, check_name, enabled, severity
                                        )

                                return "✅ Matrix gespeichert"

                            # Initial laden
                            matrix_phase_dropdown.change(
                                fn=load_matrix_for_phase,
                                inputs=[matrix_phase_dropdown],
                                outputs=[matrix_table],
                            )

                            save_matrix_btn.click(
                                fn=save_matrix,
                                inputs=[matrix_phase_dropdown, matrix_table],
                                outputs=[matrix_status],
                            )

                        # --- Über ---
                        with gr.Tab("ℹ️ Über"):
                            gr.Markdown(
                                """
                                ### KI-CLI Workspace

                                **Version:** 0.1.0

                                Ein Tool für projektübergreifendes Issue-Management
                                und KI-Zusammenarbeit.

                                **Features:**
                                - 📋 Codacy Issues synchronisieren
                                - 🚫 False Positives verwalten
                                - 🤝 KI-Session Übergaben
                                - 🔐 Verschlüsselte API-Key Speicherung

                                **Datenbank:** SQLite mit FTS5 Volltextsuche

                                **Verschlüsselung:** Fernet (AES-128-CBC)

                                ---
                                [GitHub](https://github.com/goettemar/cindergrace_ki-cli_workspace)
                                """
                            )

                # === Projekt-Tools Tab ===
                with gr.Tab("🛠️ Projekt-Tools"):
                    gr.Markdown("### Projekt-Werkzeuge")
                    gr.Markdown("Backup, Test-Clone und Code-Formatierung für deine Projekte.")

                    # --- Backup ---
                    with gr.Accordion("📦 Backup erstellen", open=False):
                        gr.Textbox(
                            label="Backup-Pfad",
                            value=self.db.get_setting("backup_base_path") or "~/projekte_backup",
                            interactive=False,
                        )
                        backup_btn = gr.Button("📦 Backup erstellen", variant="primary")
                        backup_status = gr.Markdown()

                    # --- Test-Clone ---
                    with gr.Accordion("🧪 Test-Clone erstellen", open=False):
                        gr.Textbox(
                            label="Test-Clone-Pfad",
                            value=self.db.get_setting("test_clone_base_path") or "~/projekte_test",
                            interactive=False,
                        )
                        clone_btn = gr.Button("🧪 Test-Clone erstellen", variant="primary")
                        clone_status = gr.Markdown()

                    # --- Ruff Fix ---
                    with gr.Accordion("🔧 Ruff Fix + Format", open=False):
                        gr.Markdown(
                            "Führt `ruff check --fix` und `ruff format` aus. "
                            "Korrigiert Stil- und Formatierungsprobleme automatisch."
                        )
                        ruff_btn = gr.Button("🔧 Ruff Fix + Format", variant="primary")
                        ruff_status = gr.Markdown()

                    # --- Final Workflow ---
                    with gr.Accordion("🚀 Final Workflow", open=True):
                        gr.Markdown(
                            """
                            **Kompletter Release-Workflow:**
                            1. 📦 Backup erstellen
                            2. 🔧 Ruff fix + format
                            3. 📝 Git commit (wenn Änderungen)
                            4. ✅ Release Check ausführen
                            5. 🚀 Git push (wenn alle Checks OK)
                            """
                        )
                        workflow_btn = gr.Button("🚀 Final Workflow starten", variant="primary")
                        workflow_log = gr.Markdown()

                    # Event Handlers für Projekt-Tools

                    def do_backup(project_id: int | None) -> str:
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        project = self.db.get_project(project_id)
                        if not project:
                            return "❌ Projekt nicht gefunden"
                        backup_base = self.db.get_setting("backup_base_path") or "~/projekte_backup"
                        backup_base = os.path.expanduser(backup_base)
                        success, result = create_backup(project, backup_base)
                        if success:
                            return f"✅ Backup erstellt: `{result}`"
                        return f"❌ Fehler: {result}"

                    backup_btn.click(
                        fn=do_backup,
                        inputs=[project_dropdown],
                        outputs=[backup_status],
                    )

                    def do_clone(project_id: int | None) -> str:
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        project = self.db.get_project(project_id)
                        if not project:
                            return "❌ Projekt nicht gefunden"
                        clone_base = (
                            self.db.get_setting("test_clone_base_path") or "~/projekte_test"
                        )
                        clone_base = os.path.expanduser(clone_base)
                        success, result = create_test_clone(project, clone_base)
                        if success:
                            return f"✅ Test-Clone erstellt: `{result}`"
                        return f"❌ Fehler: {result}"

                    clone_btn.click(
                        fn=do_clone,
                        inputs=[project_dropdown],
                        outputs=[clone_status],
                    )

                    def do_ruff_fix(project_id: int | None) -> str:
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        project = self.db.get_project(project_id)
                        if not project or not project.path:
                            return "❌ Projekt-Pfad nicht gefunden"
                        success, output, files_changed = run_ruff_fix(project.path)
                        if success:
                            if files_changed > 0:
                                return f"✅ Ruff Fix abgeschlossen. {files_changed} Dateien geändert.\n\n```\n{output[:1000]}\n```"
                            return "✅ Ruff Fix abgeschlossen. Keine Änderungen nötig."
                        return f"❌ Fehler:\n```\n{output[:1000]}\n```"

                    ruff_btn.click(
                        fn=do_ruff_fix,
                        inputs=[project_dropdown],
                        outputs=[ruff_status],
                    )

                    def do_final_workflow(project_id: int | None) -> str:
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        project = self.db.get_project(project_id)
                        if not project:
                            return "❌ Projekt nicht gefunden"
                        backup_base = self.db.get_setting("backup_base_path") or "~/projekte_backup"
                        backup_base = os.path.expanduser(backup_base)
                        results = run_final_workflow(project, self.db, backup_base)

                        # Format results
                        lines = []
                        all_ok = True
                        for step, success, msg in results:
                            emoji = "✅" if success else "❌"
                            lines.append(f"{emoji} **{step}**: {msg}")
                            if not success:
                                all_ok = False

                        summary = (
                            "🎉 **Workflow erfolgreich!**"
                            if all_ok
                            else "⚠️ **Workflow mit Problemen beendet**"
                        )
                        return f"{summary}\n\n" + "\n\n".join(lines)

                    workflow_btn.click(
                        fn=do_final_workflow,
                        inputs=[project_dropdown],
                        outputs=[workflow_log],
                    )

                # === KI-Kollegen Tab ===
                with gr.Tab("🤖 KI-Kollegen"):
                    gr.Markdown("### KI-Delegation")
                    gr.Markdown("Delegiere Tasks an Codex, Gemini oder Claude.")

                    # KI-Status anzeigen
                    with gr.Accordion("📡 KI-Status", open=False):
                        ai_status_md = gr.Markdown()
                        ai_refresh_btn = gr.Button("🔄 Status aktualisieren", size="sm")

                    # Prompt auswählen und ausführen
                    with gr.Accordion("🎯 Task delegieren", open=True):
                        with gr.Row():
                            prompt_dropdown = gr.Dropdown(
                                label="Prompt-Template",
                                choices=[],
                                interactive=True,
                                scale=2,
                            )
                            ai_dropdown = gr.Dropdown(
                                label="KI",
                                choices=["codex", "gemini", "claude"],
                                value="codex",
                                interactive=True,
                                scale=1,
                            )
                        with gr.Row():
                            input_file = gr.Textbox(
                                label="Input File (optional)",
                                placeholder="e.g. src/module.py",
                                scale=2,
                            )
                            timeout_slider = gr.Slider(
                                label="Timeout (Sekunden)",
                                minimum=60,
                                maximum=600,
                                value=300,
                                step=30,
                                scale=1,
                            )
                        with gr.Row():
                            output_dir = gr.Textbox(
                                label="Output Directory",
                                value=self.db.get_setting("delegation_output_dir")
                                or "~/ki-delegation-output",
                                scale=2,
                            )
                            save_output_dir_btn = gr.Button("💾 Save", scale=0)
                        delegate_btn = gr.Button("🚀 Delegieren", variant="primary")
                        delegate_status = gr.Markdown(
                            "_Wähle einen Prompt und starte die Delegation._"
                        )
                        delegate_result = gr.Code(
                            label="Ergebnis",
                            language="markdown",
                            lines=15,
                            visible=False,
                        )

                    # Prompt-Details anzeigen
                    with gr.Accordion("📝 Prompt-Details", open=False):
                        prompt_details = gr.Markdown("_Wähle einen Prompt aus._")

                    # Eigene Prompts erstellen
                    with gr.Accordion("➕ Eigenen Prompt erstellen", open=False):
                        new_prompt_name = gr.Textbox(label="Name", placeholder="mein_prompt")
                        new_prompt_desc = gr.Textbox(label="Beschreibung")
                        new_prompt_text = gr.Textbox(
                            label="Prompt-Template",
                            placeholder="Analysiere {file_content}...",
                            lines=5,
                        )
                        with gr.Row():
                            new_prompt_ai = gr.Dropdown(
                                label="Default-KI",
                                choices=["codex", "gemini", "claude"],
                                value="codex",
                            )
                            new_prompt_cat = gr.Dropdown(
                                label="Kategorie",
                                choices=[
                                    "review",
                                    "security",
                                    "testing",
                                    "documentation",
                                    "refactoring",
                                    "analysis",
                                    "general",
                                ],
                                value="general",
                            )
                        add_prompt_btn = gr.Button("➕ Prompt erstellen", variant="secondary")
                        add_prompt_status = gr.Markdown()

                    # Event Handlers für KI-Kollegen

                    def get_ai_status() -> str:
                        from core.ai_delegation import list_available_ais

                        ais = list_available_ais()
                        lines = ["| KI | Status | Pfad |", "|---|---|---|"]
                        for ai in ais:
                            status = "✅" if ai["available"] else "❌"
                            lines.append(f"| {ai['name']} | {status} | `{ai['path']}` |")
                        return "\n".join(lines)

                    def get_prompt_choices() -> list[tuple[str, str]]:
                        prompts = self.db.get_all_prompts()
                        return [(f"{p.name} ({p.category})", p.name) for p in prompts]

                    def update_prompt_details(prompt_name: str) -> str:
                        if not prompt_name:
                            return "_Wähle einen Prompt aus._"
                        prompt = self.db.get_prompt(prompt_name)
                        if not prompt:
                            return "_Prompt nicht gefunden._"
                        return f"""**{prompt.name}** ({prompt.category})

{prompt.description}

**Default-KI:** {prompt.default_ai}
**Typ:** {'Builtin' if prompt.is_builtin else 'Benutzerdefiniert'}

**Template:**
```
{prompt.prompt}
```

**Verfügbare Variablen:** `{{file}}`, `{{file_content}}`, `{{file_name}}`, `{{project}}`, `{{project_path}}`, `{{git_diff}}`, `{{issues}}`, `{{timestamp}}`
"""

                    def save_output_directory(output_path: str) -> str:
                        """Saves the output directory to settings."""
                        self.db.set_setting(
                            "delegation_output_dir",
                            output_path,
                            description="Output directory for AI delegation results",
                        )
                        return f"✅ Saved: {output_path}"

                    def do_delegate(
                        project_id: int | None,
                        prompt_name: str,
                        ai_id: str,
                        input_file_path: str,
                        timeout: int,
                        output_directory: str,
                    ) -> tuple[str, str, dict]:
                        import os
                        from datetime import datetime
                        from pathlib import Path

                        if not prompt_name:
                            return "❌ Kein Prompt ausgewählt", "", gr.update(visible=False)

                        prompt = self.db.get_prompt(prompt_name)
                        if not prompt:
                            return "❌ Prompt nicht gefunden", "", gr.update(visible=False)

                        # Projekt-Info
                        project_path_str = None
                        project_name = None
                        if project_id:
                            project = self.db.get_project(project_id)
                            if project:
                                project_path_str = project.path
                                project_name = project.name

                        # Input file path resolve
                        file_path_resolved = None
                        if input_file_path and input_file_path.strip():
                            if project_path_str and not os.path.isabs(input_file_path):
                                file_path_resolved = os.path.join(project_path_str, input_file_path)
                            else:
                                file_path_resolved = os.path.expanduser(input_file_path)

                        from core.ai_delegation import delegate_task

                        result = delegate_task(
                            prompt_template=prompt.prompt,
                            ai_id=ai_id or prompt.default_ai,
                            file_path=file_path_resolved,
                            project_path=project_path_str,
                            project_name=project_name,
                            timeout=timeout,
                        )

                        # Auto-generate output filename and save
                        output_path_str = ""
                        if output_directory and output_directory.strip():
                            try:
                                out_dir = Path(os.path.expanduser(output_directory))
                                out_dir.mkdir(parents=True, exist_ok=True)

                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                ai_used = ai_id or prompt.default_ai
                                filename = f"{prompt_name}_{ai_used}_{timestamp}.md"
                                output_file = out_dir / filename

                                # Write output to file
                                with open(output_file, "w") as f:
                                    f.write(f"# {prompt_name} via {ai_used}\n\n")
                                    f.write(f"**Timestamp:** {timestamp}\n")
                                    f.write(f"**Project:** {project_name or '-'}\n")
                                    f.write(f"**Input File:** {input_file_path or '-'}\n")
                                    f.write(f"**Duration:** {result.duration_seconds}s\n")
                                    f.write(f"**Success:** {result.success}\n\n")
                                    f.write("---\n\n")
                                    f.write(result.output or "")

                                output_path_str = f"\n📁 Saved: `{output_file}`"
                            except Exception as e:
                                output_path_str = f"\n⚠️ Save failed: {e}"

                        if result.success:
                            return (
                                f"✅ Success ({result.duration_seconds}s) via {result.ai_used}"
                                + output_path_str,
                                result.output,
                                gr.update(visible=True),
                            )
                        return (
                            f"❌ Error ({result.duration_seconds}s): {result.error}"
                            + output_path_str,
                            result.output or "",
                            gr.update(visible=True),
                        )

                    def do_add_prompt(
                        name: str, desc: str, text: str, ai: str, cat: str
                    ) -> tuple[str, dict]:
                        if not name or not text:
                            return "❌ Name und Prompt-Text sind erforderlich", gr.update()

                        from core.database import AiPrompt

                        existing = self.db.get_prompt(name)
                        if existing:
                            return f"❌ Prompt '{name}' existiert bereits", gr.update()

                        new_prompt = AiPrompt(
                            name=name,
                            description=desc,
                            prompt=text,
                            default_ai=ai,
                            category=cat,
                            is_builtin=False,
                        )
                        self.db.upsert_prompt(new_prompt)
                        return f"✅ Prompt '{name}' erstellt", gr.update(
                            choices=get_prompt_choices()
                        )

                    # Initiale Werte setzen
                    ai_status_md.value = get_ai_status()
                    prompt_dropdown.choices = get_prompt_choices()

                    ai_refresh_btn.click(fn=get_ai_status, outputs=[ai_status_md])

                    prompt_dropdown.change(
                        fn=update_prompt_details,
                        inputs=[prompt_dropdown],
                        outputs=[prompt_details],
                    )

                    save_output_dir_btn.click(
                        fn=save_output_directory,
                        inputs=[output_dir],
                        outputs=[delegate_status],
                    )

                    delegate_btn.click(
                        fn=do_delegate,
                        inputs=[
                            project_dropdown,
                            prompt_dropdown,
                            ai_dropdown,
                            input_file,
                            timeout_slider,
                            output_dir,
                        ],
                        outputs=[delegate_status, delegate_result, delegate_result],
                    )

                    add_prompt_btn.click(
                        fn=do_add_prompt,
                        inputs=[
                            new_prompt_name,
                            new_prompt_desc,
                            new_prompt_text,
                            new_prompt_ai,
                            new_prompt_cat,
                        ],
                        outputs=[add_prompt_status, prompt_dropdown],
                    )

            # === Event Handlers ===

            def update_issues(*args):
                return self.get_issues_table(*args)

            def on_issue_select(evt: gr.SelectData, data):
                try:
                    # Gradio 6.x: evt.index ist ein Tuple (row, col) oder nur row
                    if evt.index is not None:
                        row_idx = evt.index[0] if isinstance(evt.index, list | tuple) else evt.index
                        if data is not None and row_idx < len(data):
                            # data kann Liste oder Dict sein
                            row = data[row_idx] if isinstance(data, list) else data.iloc[row_idx]
                            issue_id = row[0] if isinstance(row, list | tuple) else row.iloc[0]
                            details = self.get_issue_details(int(issue_id))
                            return (
                                int(issue_id),
                                details.get("title", ""),
                                details.get("message", ""),
                                details.get("file_info", ""),
                                details.get("tool_info", ""),
                                details.get("cve_info", ""),
                                details.get("fp_info", ""),
                            )
                except Exception as e:
                    logger.error(f"Fehler bei Issue-Auswahl: {e}")
                return None, "", "", "", "", "", ""

            # Filter-Inputs für Issues
            filter_inputs = [
                project_dropdown,
                priority_filter,
                status_filter,
                scan_type_filter,
                search_box,
                show_fps,
            ]

            # Projekt-Wechsel aktualisiert Issues-Tabelle
            project_dropdown.change(
                fn=update_issues,
                inputs=filter_inputs,
                outputs=issues_table,
            )

            # Filter-Updates (ohne Projekt-Dropdown, das hat eigenen Handler)
            for inp in [priority_filter, status_filter, scan_type_filter, search_box, show_fps]:
                inp.change(
                    fn=update_issues,
                    inputs=filter_inputs,
                    outputs=issues_table,
                )

            # Issue-Auswahl
            issues_table.select(
                fn=on_issue_select,
                inputs=[issues_table],
                outputs=[
                    selected_issue_id,
                    detail_title,
                    detail_message,
                    detail_file,
                    detail_tool,
                    detail_cve,
                    detail_fp,
                ],
            )

            # Sync Button - mit automatischem Refresh der Issues-Tabelle
            sync_btn.click(
                fn=self.sync_from_codacy,
                inputs=[project_dropdown],
                outputs=sync_status,
            ).then(
                fn=update_issues,
                inputs=filter_inputs,
                outputs=issues_table,
            )

            def dummy_push_for_reanalysis(project_id: int | None) -> str:
                """Trigger Codacy re-analysis with a dummy commit."""
                import subprocess

                if not project_id:
                    return "❌ Kein Projekt ausgewählt"

                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "❌ Projekt-Pfad nicht gefunden"

                project_path = project.path
                readme_path = f"{project_path}/README.md"

                try:
                    # Add empty line to README
                    with open(readme_path, "a", encoding="utf-8") as f:
                        f.write("\n")

                    # Git commit and push
                    subprocess.run(
                        ["git", "add", "README.md"],
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "commit",
                            "-m",
                            "chore: Trigger Codacy re-analysis\n\n"
                            "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
                        ],
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    subprocess.run(
                        ["git", "push"],
                        cwd=project_path,
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    return "✅ Dummy Push erfolgreich! Warte ~30s, dann Sync klicken."
                except subprocess.CalledProcessError as e:
                    return f"❌ Git-Fehler: {e.stderr or e.stdout or str(e)}"
                except FileNotFoundError:
                    return f"❌ README.md nicht gefunden in {project_path}"
                except Exception as e:
                    return f"❌ Fehler: {e}"

            dummy_push_btn.click(
                fn=dummy_push_for_reanalysis,
                inputs=[project_dropdown],
                outputs=sync_status,
            )

            # === Pending Ignores Tab Event Handlers ===

            # Kategorie-Labels (wie in Codacy UI)
            ki_category_labels = {
                "accepted_use": "Accepted use",
                "false_positive": "False positive",
                "not_exploitable": "Not exploitable",
                "test_code": "Test code",
                "external_code": "External code",
            }

            def load_pending_ignores(project_id):
                """Lädt Issues mit KI-Empfehlung die noch nicht in Codacy ignored sind."""
                pending = self.db.get_pending_ignores(project_id)

                priority_emoji = {
                    "Critical": "🔴",
                    "High": "🟠",
                    "Medium": "🟡",
                    "Low": "🟢",
                }

                rows = []
                for issue in pending:
                    cat_label = ki_category_labels.get(issue.ki_recommendation_category or "", "-")
                    date_str = str(issue.ki_reviewed_at)[:10] if issue.ki_reviewed_at else "-"
                    rows.append(
                        [
                            issue.id,
                            priority_emoji.get(issue.priority, "⚪"),
                            cat_label,
                            issue.title[:50] + "..."
                            if len(issue.title or "") > 50
                            else issue.title,
                            issue.ki_recommendation[:40] + "..."
                            if len(issue.ki_recommendation or "") > 40
                            else issue.ki_recommendation,
                            issue.ki_reviewed_by or "-",
                            date_str,
                        ]
                    )

                count_text = f"**{len(pending)} Issue(s)** zum manuellen Markieren in Codacy"
                return rows, count_text

            refresh_pending_btn.click(
                fn=load_pending_ignores,
                inputs=[project_dropdown],
                outputs=[pending_ignores_table, pending_count],
            )

            # Auch bei Projekt-Wechsel aktualisieren
            project_dropdown.change(
                fn=load_pending_ignores,
                inputs=[project_dropdown],
                outputs=[pending_ignores_table, pending_count],
            )

            # Kategorie-Labels und Hinweise
            category_hints = {
                "accepted_use": "Bewusst so implementiert, kein Sicherheitsrisiko",
                "false_positive": "Tool-Fehlalarm, kein echtes Problem im Code",
                "not_exploitable": "Theoretisch verwundbar, praktisch nicht ausnutzbar",
                "test_code": "Nur in Tests vorhanden, nicht in Produktion",
                "external_code": "Fremdcode/Vendor, nicht von uns wartbar",
            }

            def show_pending_detail_by_id(table_data, evt: gr.SelectData):
                """Zeigt vollständige Begründung anhand der Issue-ID."""
                empty = ("*Keine Auswahl*", "", "", "")
                if evt.index is None or table_data is None:
                    return empty

                try:
                    row_idx = evt.index[0] if isinstance(evt.index, list | tuple) else evt.index

                    # Pandas DataFrame oder Liste?
                    if hasattr(table_data, "iloc"):
                        if row_idx >= len(table_data):
                            return ("*Ungültige Auswahl*", "", "", "")
                        issue_id = table_data.iloc[row_idx, 0]
                    else:
                        if row_idx >= len(table_data):
                            return ("*Ungültige Auswahl*", "", "", "")
                        issue_id = table_data[row_idx][0]

                    if not issue_id:
                        return ("*Keine Issue-ID*", "", "", "")

                    # Direkte DB-Abfrage für einzelnes Issue
                    with self.db._get_connection() as conn:
                        cursor = conn.execute(
                            "SELECT * FROM issue_meta WHERE id = ?", (int(issue_id),)
                        )
                        row = cursor.fetchone()
                        if not row:
                            return (f"*Issue {issue_id} nicht gefunden*", "", "", "")

                        priority = row["priority"]
                        title = row["title"]
                        ki_category = row["ki_recommendation_category"] or ""
                        ki_reason = row["ki_recommendation"] or ""

                    info = f"**Issue #{issue_id}** | {priority} | {title}"

                    # Kategorie formatieren
                    category_display = ki_category_labels.get(ki_category, ki_category)
                    category_hint = category_hints.get(ki_category, "")
                    if category_hint:
                        category_hint = f"*{category_hint}*"

                    reason = ki_reason or "*Keine Begründung vorhanden*"

                    return (info, category_display, category_hint, reason)
                except (IndexError, TypeError, ValueError) as e:
                    return (f"*Fehler: {e}*", "", "", "")

            pending_ignores_table.select(
                fn=show_pending_detail_by_id,
                inputs=[pending_ignores_table],
                outputs=[detail_issue_info, detail_category, detail_category_hint, detail_reason],
            )

            def copy_to_clipboard(text: str) -> str:
                """Copy text to clipboard (feedback only, JS does the actual copy)."""
                if not text or text.startswith("*"):
                    return "❌ Nichts zum Kopieren"
                return "✅ Kopiert!"

            copy_reason_btn.click(
                fn=copy_to_clipboard,
                inputs=[detail_reason],
                outputs=[copy_result],
                js="(text) => { if(text && !text.startsWith('*')) { navigator.clipboard.writeText(text); } return text; }",
            )

            # === Dashboard Event Handlers ===

            def get_last_ci_status(owner: str, repo: str) -> str:
                """Holt den Status der letzten GitHub Action."""
                if not owner or not repo:
                    return "-"
                import json

                cmd = [
                    "run",
                    "list",
                    "-R",
                    f"{owner}/{repo}",
                    "--limit",
                    "1",
                    "--json",
                    "status,conclusion",
                ]
                success, output = run_gh_command(cmd, timeout=10)
                if not success or not output or output.strip() == "[]":
                    return "-"

                try:
                    runs = json.loads(output)
                    if not runs:
                        return "-"
                    run = runs[0]
                    conclusion = run.get("conclusion", "")
                    status = run.get("status", "")

                    if conclusion == "success":
                        return "✅"
                    elif conclusion == "failure":
                        return "❌"
                    elif status == "in_progress":
                        return "🔄"
                    elif status == "queued":
                        return "⏳"
                    else:
                        return "⚪"
                except (json.JSONDecodeError, KeyError):
                    return "-"

            def get_git_status_short(project_path: str) -> str:
                """Holt kurzen Git-Status für Dashboard."""
                if not project_path:
                    return "-"
                import subprocess
                from pathlib import Path

                path = Path(project_path)
                if not path.exists() or not (path / ".git").exists():
                    return "-"

                try:
                    # Uncommitted changes
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    uncommitted = (
                        len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
                    )

                    # Unpushed commits
                    result = subprocess.run(
                        ["git", "rev-list", "--count", "@{upstream}..HEAD"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    unpushed = int(result.stdout.strip()) if result.returncode == 0 else 0

                    if uncommitted == 0 and unpushed == 0:
                        return "✅"
                    elif uncommitted > 0 and unpushed > 0:
                        return f"📝{uncommitted} ⬆️{unpushed}"
                    elif uncommitted > 0:
                        return f"📝 {uncommitted}"
                    else:
                        return f"⬆️ {unpushed}"
                except Exception:
                    return "-"

            def load_dashboard_data(with_live_status: bool = False):
                """
                Lädt alle Projekte für das Dashboard.

                Args:
                    with_live_status: True = CI/Git Status live holen (langsam),
                                     False = nur "-" anzeigen (schnell)
                """
                projects = self.db.get_all_projects(include_archived=False)
                phases = {p.id: p.display_name for p in self.db.get_all_phases()}

                rows = []
                for p in projects:
                    # Phase-Name
                    phase_name = phases.get(p.phase_id, "-") if p.phase_id else "-"

                    # CI/Git Status: nur bei explizitem Refresh holen
                    if with_live_status:
                        owner = p.github_owner or p.codacy_org
                        ci_status = get_last_ci_status(owner, p.name) if owner else "-"
                        git_status = get_git_status_short(p.path) if p.path else "-"
                    else:
                        ci_status = "-"
                        git_status = "-"

                    # Release Status
                    if p.cache_release_total > 0:
                        release_str = f"{p.cache_release_passed}/{p.cache_release_total}"
                        if p.cache_release_ready:
                            release_str = f"✅ {release_str}"
                        else:
                            release_str = f"⚠️ {release_str}"
                    else:
                        release_str = "-"

                    # Codacy Sync-Zeit formatieren
                    codacy_str = str(p.last_sync)[:16].replace("T", " ") if p.last_sync else "nie"

                    # PyPI Status formatieren (nur Version, ohne Index-Check)
                    pypi_str = p.pypi_version if p.pypi_package and p.pypi_version else "-"

                    rows.append(
                        [
                            p.id,
                            p.name,
                            phase_name,
                            p.cache_issues_critical,
                            p.cache_issues_high,
                            p.cache_issues_medium,
                            p.cache_issues_low,
                            p.cache_issues_fp,
                            ci_status,
                            git_status,
                            release_str,
                            pypi_str,
                            codacy_str,
                        ]
                    )

                return rows

            def refresh_all_projects():
                """Aktualisiert alle Projekte: Codacy-Sync + Release-Checks + PyPI (parallel)."""
                from concurrent.futures import ThreadPoolExecutor, as_completed

                from core.checks import get_pypi_info_from_dist, run_all_checks

                projects = self.db.get_all_projects(include_archived=False)
                sync_results = {"synced": 0, "checked": 0, "pypi": 0, "errors": []}

                def refresh_single_project(project):
                    """Sync + Check + PyPI für ein einzelnes Projekt."""
                    result = {
                        "name": project.name,
                        "synced": False,
                        "checked": False,
                        "pypi": False,
                    }

                    # 1. Codacy-Sync (wenn konfiguriert)
                    if project.codacy_provider and project.codacy_org and self.codacy.api_token:
                        try:
                            stats = self.codacy.sync_project(self.db, project)
                            if "error" not in stats:
                                result["synced"] = True
                        except Exception as e:
                            logger.warning(f"Sync-Fehler {project.name}: {e}")

                    # 2. Release-Check (wenn lokaler Pfad)
                    if project.path:
                        try:
                            results = run_all_checks(self.db, project)
                            passed = sum(1 for r in results if r.passed)
                            total = len(results)
                            self.db.update_release_cache(project.id, passed, total, passed == total)
                            result["checked"] = True
                        except Exception as e:
                            logger.warning(f"Check-Fehler {project.name}: {e}")

                    # 3. PyPI-Status (aus /dist lesen, ohne Index-Check)
                    if project.path:
                        try:
                            pypi_info = get_pypi_info_from_dist(project.path)
                            package = pypi_info.get("package")
                            version = pypi_info.get("version")

                            if package and version:
                                # Nur Paket und Version speichern (kein Index-Check)
                                self.db.update_pypi_cache(project.id, package, version, False, None)
                                result["pypi"] = True
                            elif project.pypi_package:
                                # Kein dist mehr vorhanden - Cache leeren
                                self.db.update_pypi_cache(project.id, None, None, False, None)
                                result["pypi"] = True
                        except Exception as e:
                            logger.warning(f"PyPI-Check-Fehler {project.name}: {e}")

                    return result

                # Alle Projekte parallel aktualisieren
                with ThreadPoolExecutor(max_workers=len(projects) or 1) as executor:
                    futures = {executor.submit(refresh_single_project, p): p for p in projects}
                    for future in as_completed(futures):
                        try:
                            res = future.result()
                            if res["synced"]:
                                sync_results["synced"] += 1
                            if res["checked"]:
                                sync_results["checked"] += 1
                            if res["pypi"]:
                                sync_results["pypi"] += 1
                        except Exception as e:
                            sync_results["errors"].append(str(e))

                msg = f"✅ {sync_results['synced']} synced, {sync_results['checked']} checked"
                if sync_results["pypi"] > 0:
                    msg += f", {sync_results['pypi']} PyPI"
                if sync_results["errors"]:
                    msg += f" ({len(sync_results['errors'])} Fehler)"
                # Mit live CI/Git Status laden
                return load_dashboard_data(with_live_status=True), msg

            # Dashboard beim App-Start laden
            app.load(fn=load_dashboard_data, outputs=[dashboard_table])

            refresh_all_btn.click(
                fn=refresh_all_projects,
                outputs=[dashboard_table, dashboard_msg],
            )

            # === Neues Projekt Event Handlers ===

            def toggle_new_project_panel(visible: bool):
                """Zeigt/versteckt das Neues-Projekt-Panel."""
                return gr.update(visible=visible)

            def create_new_project(name: str, description: str, status: str):
                """Erstellt ein neues Projekt."""
                if not name:
                    return (
                        gr.update(visible=True),
                        "❌ Bitte Projektnamen eingeben",
                        load_dashboard_data(),
                    )

                from core.project_init import ProjectInitializer

                initializer = ProjectInitializer(self.db)
                result = initializer.create_project(
                    name=name,
                    description=description,
                    status=status,
                    create_github=True,
                    connect_codacy=True,
                )

                if result["success"]:
                    # Panel schließen, Tabelle aktualisieren
                    steps = "\n".join(result["steps"])
                    return (
                        gr.update(visible=False),
                        f"✅ **Projekt erstellt!**\n\n{steps}\n\n📁 `{result['path']}`",
                        load_dashboard_data(),
                    )
                else:
                    errors = "\n".join(result["errors"])
                    steps = "\n".join(result["steps"])
                    return (
                        gr.update(visible=True),
                        f"⚠️ **Fehler:**\n{errors}\n\n**Ausgeführt:**\n{steps}",
                        load_dashboard_data(),
                    )

            new_project_btn.click(
                fn=lambda: gr.update(visible=True),
                outputs=[new_project_panel],
            )

            cancel_proj_btn.click(
                fn=lambda: (gr.update(visible=False), ""),
                outputs=[new_project_panel, new_proj_result],
            )

            create_proj_btn.click(
                fn=create_new_project,
                inputs=[new_proj_name, new_proj_desc, new_proj_status],
                outputs=[new_project_panel, new_proj_result, dashboard_table],
            )

            # === Archiv Event Handlers ===

            def show_archive_confirm(project_id):
                """Zeigt Archiv-Bestätigung."""
                if not project_id:
                    return gr.update(visible=False), ""
                return gr.update(visible=True), ""

            def hide_archive_confirm():
                """Versteckt Archiv-Bestätigung."""
                return gr.update(visible=False), ""

            def archive_project(project_id, confirm_name):
                """Archiviert das Projekt nach Bestätigung."""
                if not project_id:
                    return (
                        gr.update(visible=False),
                        "❌ Kein Projekt ausgewählt",
                        load_dashboard_data(),
                    )

                project = self.db.get_project(project_id)
                if not project:
                    return (
                        gr.update(visible=False),
                        "❌ Projekt nicht gefunden",
                        load_dashboard_data(),
                    )

                if confirm_name != project.name:
                    return (
                        gr.update(visible=True),
                        "❌ Projektname stimmt nicht überein",
                        load_dashboard_data(),
                    )

                from core.project_init import ProjectInitializer

                initializer = ProjectInitializer(self.db)
                result = initializer.archive_project(project_id)

                if result["success"]:
                    steps = "\n".join(result["steps"])
                    return (
                        gr.update(visible=False),
                        f"✅ **Projekt archiviert!**\n\n{steps}",
                        load_dashboard_data(),
                    )
                else:
                    errors = "\n".join(result["errors"])
                    return (
                        gr.update(visible=False),
                        f"⚠️ **Fehler beim Archivieren:**\n{errors}",
                        load_dashboard_data(),
                    )

            dash_archive_btn.click(
                fn=show_archive_confirm,
                inputs=[dash_selected_id],
                outputs=[archive_confirm_group, archive_confirm_name],
            )

            archive_cancel_btn.click(
                fn=hide_archive_confirm,
                outputs=[archive_confirm_group, archive_confirm_name],
            )

            archive_confirm_btn.click(
                fn=archive_project,
                inputs=[dash_selected_id, archive_confirm_name],
                outputs=[archive_confirm_group, dash_detail_msg, dashboard_table],
            )

            def load_project_details(project_id):
                """Lädt Detail-Informationen für ein Projekt."""
                empty_result = (
                    gr.update(visible=False),
                    "",
                    "*Projekt auswählen...*",
                    "**📝 About:** *-*",
                    "**🏷️ Topics:** *-*",
                    "",
                )
                if not project_id:
                    return empty_result

                project = self.db.get_project(project_id)
                if not project:
                    return empty_result

                # Phase
                phase_name = "-"
                if project.phase_id:
                    phase = self.db.get_phase(project.phase_id)
                    if phase:
                        phase_name = phase.display_name

                # Info-Werte für Tabelle
                path_short = (
                    project.path.replace("/home/zorinadmin/projekte/", "~/")
                    if project.path
                    else "-"
                )
                github_short = (
                    project.git_remote.replace("https://github.com/", "")
                    .replace("git@github.com:", "")
                    .replace(".git", "")
                    if project.git_remote
                    else "-"
                )
                codacy_short = f"{project.codacy_provider or '-'}/{project.codacy_org or '-'}"

                # Critical/High Issues: Nur Anzahl
                critical_count = len(
                    self.db.get_issues(
                        project_id=project_id,
                        priority="Critical",
                        status="open",
                        is_false_positive=False,
                    )
                )
                critical_str = "✅ 0" if critical_count == 0 else f"🔴 {critical_count}"

                high_count = len(
                    self.db.get_issues(
                        project_id=project_id,
                        priority="High",
                        status="open",
                        is_false_positive=False,
                    )
                )
                high_str = "✅ 0" if high_count == 0 else f"🟠 {high_count}"

                # Release Check Info (nur Zähler)
                if project.cache_release_total > 0:
                    passed = project.cache_release_passed
                    total = project.cache_release_total
                    status_icon = "✅" if project.cache_release_ready else "⚠️"
                    release_info = f"{status_icon} {passed}/{total}"
                else:
                    release_info = "❓ -"

                # Info-Block formatieren (Markdown) - mit Zeilenumbrüchen
                pypi_line = ""
                if project.pypi_package:
                    google_url = (
                        f"https://www.google.com/search?q=site:pypi.org+{project.pypi_package}"
                    )
                    pypi_line = (
                        f"\n\n**📦 PyPI:** [{project.pypi_package}]({google_url}) (Google Index)"
                    )

                info_table = f"""**📂 Pfad:** `{path_short}`

**🐙 GitHub:** `{github_short}`

**🔍 Codacy:** `{codacy_short}`{pypi_line}

**🔴 Critical:** {critical_str}

**🟠 High:** {high_str}

**✓ Release:** {release_info}"""

                # GitHub About + Topics laden
                about_text = "*-*"
                topics_text = "*-*"

                # Owner aus git_remote extrahieren
                owner = project.github_owner
                if not owner and project.git_remote:
                    import re

                    match = re.search(r"github\.com[:/]([^/]+)/", project.git_remote)
                    if match:
                        owner = match.group(1)

                if owner:
                    try:
                        import json
                        import subprocess

                        result = subprocess.run(
                            [
                                "gh",
                                "repo",
                                "view",
                                f"{owner}/{project.name}",
                                "--json",
                                "description,repositoryTopics",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0:
                            data = json.loads(result.stdout)
                            if data.get("description"):
                                about_text = data["description"]
                            topic_list = data.get("repositoryTopics", [])
                            if topic_list:
                                topic_names = [t["name"] for t in topic_list]
                                topics_text = " ".join(f"`{t}`" for t in topic_names)
                    except Exception as e:
                        logger.warning(f"GitHub info error: {e}")

                # Mit Labels formatieren
                github_about = f"**📝 About:** {about_text}"
                github_topics = f"**🏷️ Topics:** {topics_text}"

                return (
                    gr.update(visible=True),
                    f"### 📁 {project.name} ({phase_name})",
                    info_table,
                    github_about,
                    github_topics,
                    "",
                )

            def on_dashboard_select(evt: gr.SelectData, data):
                """Handler für Klick auf Dashboard-Tabelle."""
                empty_result = (
                    None,
                    gr.update(visible=False),
                    "",
                    "*Projekt auswählen...*",
                    "**📝 About:** *-*",
                    "**🏷️ Topics:** *-*",
                    "",
                )
                try:
                    if evt.index is not None:
                        row_idx = evt.index[0] if isinstance(evt.index, list | tuple) else evt.index
                        if data is not None and row_idx < len(data):
                            # Projekt-ID aus erster Spalte
                            if hasattr(data, "iloc"):
                                project_id = int(data.iloc[row_idx, 0])
                            else:
                                project_id = int(data[row_idx][0])
                            return project_id, *load_project_details(project_id)
                except Exception as e:
                    logger.error(f"Dashboard select error: {e}")
                return empty_result

            def dash_sync_project(project_id):
                """Sync für ausgewähltes Projekt."""
                if not project_id:
                    return "⚠️ Kein Projekt ausgewählt"
                result = self.sync_from_codacy(project_id)
                return f"🔄 {result}"

            def dash_check_project(project_id):
                """Release Check für ausgewähltes Projekt."""
                if not project_id:
                    return "*Projekt auswählen...*", "⚠️ Kein Projekt ausgewählt"

                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "*Projekt auswählen...*", "⚠️ Kein Pfad konfiguriert"

                from core.checks import run_all_checks

                results = run_all_checks(self.db, project)
                passed = sum(1 for r in results if r.passed)
                total = len(results)

                # Cache aktualisieren
                self.db.update_release_cache(project_id, passed, total, passed == total)

                # Tabelle neu laden mit aktuellen Werten
                details = load_project_details(project_id)
                # details[2] ist die info_table

                return details[2], f"✅ Check abgeschlossen ({passed}/{total})"

            # Dashboard Table Select Handler
            dashboard_table.select(
                fn=on_dashboard_select,
                inputs=[dashboard_table],
                outputs=[
                    dash_selected_id,
                    dash_detail_group,
                    dash_detail_header,
                    dash_info_table,
                    dash_github_about,
                    dash_github_topics,
                    dash_detail_msg,
                ],
            )

            # Dashboard Action Buttons
            dash_sync_btn.click(
                fn=dash_sync_project,
                inputs=[dash_selected_id],
                outputs=[dash_detail_msg],
            ).then(
                fn=lambda pid: load_project_details(pid)[2] if pid else "*-*",
                inputs=[dash_selected_id],
                outputs=[dash_info_table],
            ).then(
                fn=load_dashboard_data,
                outputs=[dashboard_table],
            )

            dash_check_btn.click(
                fn=dash_check_project,
                inputs=[dash_selected_id],
                outputs=[dash_info_table, dash_detail_msg],
            ).then(
                fn=load_dashboard_data,
                outputs=[dashboard_table],
            )

            # Goto Issues Tab - setzt Projekt-Dropdown
            dash_goto_btn.click(
                fn=lambda pid: pid,
                inputs=[dash_selected_id],
                outputs=[project_dropdown],
            )

            # === GitHub Tab Event Handlers ===

            def get_gh_status_display():
                """Formatierter gh CLI Status."""
                status = get_gh_cli_status()
                if not status["available"]:
                    return "❌ **gh CLI nicht installiert**\n\n`sudo apt install gh` oder [gh.cli.github.com](https://cli.github.com/)"
                if not status["logged_in"]:
                    return "⚠️ **Nicht eingeloggt**\n\n`gh auth login`"
                return (
                    f"✅ **Eingeloggt als:** {status['user']}\n\n"
                    f"**Scopes:** {', '.join(status['scopes'])}\n\n"
                    f"**Protocol:** {status['protocol']}"
                )

            def get_gh_notifications():
                """Lädt GitHub Notifications."""
                success, output = run_gh_command(
                    ["api", "notifications", "--jq", '.[].subject | .title + " (" + .type + ")"'],
                    timeout=15,
                )
                if not success:
                    return f"❌ Fehler: {output}"
                if not output.strip():
                    return "✅ Keine neuen Notifications"
                lines = output.strip().split("\n")[:20]  # Max 20
                result = "\n".join(f"• {line}" for line in lines)
                if len(output.strip().split("\n")) > 20:
                    result += f"\n... und {len(output.strip().split(chr(10))) - 20} weitere"
                return result

            def run_custom_gh_command(cmd_str):
                """Führt benutzerdefinierten gh Befehl aus."""
                if not cmd_str or not cmd_str.strip():
                    return "Bitte Befehl eingeben"
                # Sicherheitscheck: Keine gefährlichen Befehle
                dangerous = ["delete", "rm", "remove", "--force", "-f"]
                if any(d in cmd_str.lower() for d in dangerous):
                    return "⚠️ Potenziell gefährlicher Befehl blockiert"
                args = cmd_str.strip().split()
                success, output = run_gh_command(args, timeout=30)
                return output if output else "(Keine Ausgabe)"

            def get_git_status(project_id: int | None):
                """Holt Git-Status für ein Projekt (uncommitted, unpushed)."""
                if not project_id:
                    return "*Projekt auswählen*"
                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "❌ Kein lokaler Pfad"

                import subprocess
                from pathlib import Path

                path = Path(project.path)
                if not path.exists():
                    return f"❌ Pfad: {path}"
                if not (path / ".git").exists():
                    return "❌ Kein Git-Repository"

                try:
                    # Uncommitted changes
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    uncommitted = result.stdout.strip().split("\n") if result.stdout.strip() else []
                    uncommitted_count = len(uncommitted)

                    # Staged changes (ready to commit)
                    result = subprocess.run(
                        ["git", "diff", "--cached", "--name-only"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    staged = result.stdout.strip().split("\n") if result.stdout.strip() else []
                    staged_count = len(staged)

                    # Unpushed commits
                    result = subprocess.run(
                        ["git", "rev-list", "--count", "@{upstream}..HEAD"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    unpushed = int(result.stdout.strip()) if result.returncode == 0 else 0

                    # Build status display
                    lines = []
                    if uncommitted_count > 0:
                        lines.append(f"📝 **{uncommitted_count}** Änderungen")
                    if staged_count > 0:
                        lines.append(f"✅ **{staged_count}** staged")
                    if unpushed > 0:
                        lines.append(f"⬆️ **{unpushed}** unpushed")
                    if not lines:
                        lines.append("✨ Alles synchron!")

                    return "\n".join(lines)

                except subprocess.SubprocessError as e:
                    return f"❌ Git-Fehler: {e}"

            def get_git_changes_list(project_id: int | None):
                """Holt Liste aller Änderungen für ein Projekt."""
                if not project_id:
                    return "*Projekt auswählen*"
                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "Kein lokaler Pfad"

                import subprocess
                from pathlib import Path

                path = Path(project.path)
                if not path.exists() or not (path / ".git").exists():
                    return "Kein Git-Repository"

                try:
                    # git status --porcelain liefert alle Änderungen
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if not result.stdout.strip():
                        return "✨ Keine Änderungen"

                    changes = result.stdout.strip().split("\n")
                    lines = []
                    for change in changes[:20]:  # Max 20 Zeilen
                        # Format: XY filename
                        # X = staged, Y = unstaged
                        status = change[:2]
                        filename = change[3:]
                        # Status Icons
                        if status[0] == "M" or status[1] == "M":
                            icon = "📝"  # Modified
                        elif status[0] == "A":
                            icon = "➕"  # Added
                        elif status[0] == "D" or status[1] == "D":
                            icon = "🗑️"  # Deleted
                        elif status == "??":
                            icon = "❓"  # Untracked
                        elif status[0] == "R":
                            icon = "📛"  # Renamed
                        else:
                            icon = "•"
                        lines.append(f"{icon} {filename}")

                    if len(changes) > 20:
                        lines.append(f"... und {len(changes) - 20} weitere")

                    return "\n".join(lines)

                except subprocess.SubprocessError as e:
                    return f"Fehler: {e}"

            def push_and_sync(project_id: int | None, commit_message: str = ""):
                """Führt git add, commit (falls nötig), pull --rebase und push aus."""
                if not project_id:
                    return "❌ Kein Projekt ausgewählt", "*Projekt auswählen*"
                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "❌ Kein lokaler Pfad", "❌ Kein lokaler Pfad"

                import subprocess
                from pathlib import Path

                path = Path(project.path)
                if not path.exists() or not (path / ".git").exists():
                    return "❌ Kein Git-Repository", "❌ Kein Git-Repository"

                # Default commit message wenn leer
                if not commit_message or not commit_message.strip():
                    commit_message = "Update via KI-Workspace"

                messages = []
                try:
                    # Check for changes
                    result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    has_changes = bool(result.stdout.strip())

                    if has_changes:
                        # git add .
                        subprocess.run(["git", "add", "."], cwd=path, check=True, timeout=30)
                        messages.append("✅ add")

                        # git commit mit User-Message
                        result = subprocess.run(
                            ["git", "commit", "-m", commit_message],
                            cwd=path,
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                        if result.returncode == 0:
                            messages.append("✅ commit")
                        else:
                            messages.append(f"⚠️ {result.stderr.strip()[:40]}")

                    # Check for unpushed
                    result = subprocess.run(
                        ["git", "rev-list", "--count", "@{upstream}..HEAD"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    unpushed = int(result.stdout.strip()) if result.returncode == 0 else 0

                    if unpushed > 0 or has_changes:
                        # Erst git fetch um zu prüfen ob divergiert
                        subprocess.run(["git", "fetch"], cwd=path, capture_output=True, timeout=30)

                        # Prüfen ob divergiert
                        result = subprocess.run(
                            ["git", "status", "-sb"],
                            cwd=path,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if "diverged" in result.stdout or "behind" in result.stdout:
                            # git pull --rebase
                            result = subprocess.run(
                                ["git", "pull", "--rebase"],
                                cwd=path,
                                capture_output=True,
                                text=True,
                                timeout=60,
                            )
                            if result.returncode == 0:
                                messages.append("✅ pull --rebase")
                            else:
                                return (
                                    f"❌ Rebase-Konflikt: {result.stderr.strip()[:60]}",
                                    get_git_status(project_id),
                                )

                        # git push
                        result = subprocess.run(
                            ["git", "push"], cwd=path, capture_output=True, text=True, timeout=60
                        )
                        if result.returncode == 0:
                            messages.append("✅ push")
                        else:
                            messages.append(f"❌ {result.stderr.strip()[:60]}")
                    else:
                        messages.append("✨ Synchron")

                    return " | ".join(messages), get_git_status(project_id)

                except subprocess.SubprocessError as e:
                    return f"❌ Fehler: {e}", get_git_status(project_id)

            def get_github_actions(project_id: int | None):
                """Holt die letzten 5 GitHub Actions für ein Projekt."""
                if not project_id:
                    return [], "*Projekt auswählen*"
                project = self.db.get_project(project_id)
                # Use github_owner or codacy_org for the owner
                owner = project.github_owner or project.codacy_org if project else None
                if not project or not owner:
                    return (
                        [],
                        f"❌ Kein Owner gefunden (github_owner={project.github_owner if project else None}, codacy_org={project.codacy_org if project else None})",
                    )

                import json
                from datetime import datetime

                repo_name = f"{owner}/{project.name}"

                # gh run list
                cmd = [
                    "run",
                    "list",
                    "-R",
                    repo_name,
                    "--limit",
                    "5",
                    "--json",
                    "status,conclusion,name,headBranch,headSha,createdAt",
                ]
                success, output = run_gh_command(cmd, timeout=30)

                if not success:
                    return (
                        [],
                        f"❌ gh Fehler für `{repo_name}`: {output[:100] if output else 'Keine Ausgabe'}",
                    )

                if not output or output.strip() == "[]":
                    return (
                        [],
                        f"ℹ️ Keine Actions für `{repo_name}` (evtl. keine Workflows definiert)",
                    )

                try:
                    runs = json.loads(output)
                    rows = []
                    for run in runs:
                        # Status icon
                        conclusion = run.get("conclusion", "")
                        status = run.get("status", "")
                        if conclusion == "success":
                            icon = "✅"
                        elif conclusion == "failure":
                            icon = "❌"
                        elif status == "in_progress":
                            icon = "🔄"
                        elif status == "queued":
                            icon = "⏳"
                        else:
                            icon = "⚪"

                        # Time formatting
                        created = run.get("createdAt", "")
                        if created:
                            try:
                                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                                time_str = dt.strftime("%d.%m. %H:%M")
                            except ValueError:
                                time_str = created[:16]
                        else:
                            time_str = "-"

                        rows.append(
                            [
                                icon,
                                run.get("name", "")[:25],
                                run.get("headBranch", "")[:15],
                                run.get("headSha", "")[:7],
                                time_str,
                            ]
                        )
                    return rows, f"✅ {len(rows)} Actions für `{repo_name}`"
                except (json.JSONDecodeError, KeyError) as e:
                    return [], f"❌ JSON-Fehler: {e}"

            def get_repo_info(project_id):
                """Lädt About und Topics für ein Repository."""
                if not project_id:
                    return "*-*", "*-*"

                project = self.db.get_project(project_id)
                if not project:
                    return "*-*", "*-*"

                # Owner aus github_owner oder git_remote extrahieren
                owner = project.github_owner
                if not owner and project.git_remote:
                    import re

                    # git@github.com:owner/repo.git oder https://github.com/owner/repo.git
                    match = re.search(r"github\.com[:/]([^/]+)/", project.git_remote)
                    if match:
                        owner = match.group(1)

                if not owner:
                    return "*-*", "*-*"

                about = "*-*"
                topics = "*-*"
                try:
                    import json
                    import subprocess

                    result = subprocess.run(
                        [
                            "gh",
                            "repo",
                            "view",
                            f"{owner}/{project.name}",
                            "--json",
                            "description,repositoryTopics",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        data = json.loads(result.stdout)
                        if data.get("description"):
                            about = data["description"]
                        topic_list = data.get("repositoryTopics", [])
                        if topic_list:
                            topic_names = [t["name"] for t in topic_list]
                            topics = " ".join(f"`{t}`" for t in topic_names)
                except Exception as e:
                    logger.warning(f"Repo info error: {e}")

                return about, topics

            # Kombinierte Refresh-Funktion für GitHub Tab
            def refresh_all_github_data(project_id):
                """Aktualisiert alle GitHub-Daten auf einmal."""
                gh_status = get_gh_status_display()
                git_status = get_git_status(project_id)
                git_changes = get_git_changes_list(project_id)
                notifications = get_gh_notifications()
                actions_table, actions_debug = get_github_actions(project_id)
                repo_about, repo_topics = get_repo_info(project_id)
                return (
                    gh_status,
                    git_status,
                    git_changes,
                    notifications,
                    actions_table,
                    actions_debug,
                    repo_about,
                    repo_topics,
                )

            def generate_ai_commit_message(project_id: int | None):
                """Generiert AI Commit Message für staged Changes."""
                if not project_id:
                    return "❌ Kein Projekt ausgewählt"

                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "❌ Kein lokaler Pfad"

                # API Key prüfen (aus OS Keyring)
                from core.secrets import get_api_key

                api_key = get_api_key("openrouter")
                if not api_key:
                    return "❌ OpenRouter Key nicht konfiguriert (Einstellungen > API Keys)"

                model = self.db.get_setting("openrouter_model") or "x-ai/grok-3-mini-beta"

                # AI Commit Message generieren
                from core.ai_commit import generate_commit_message, get_staged_diff

                success, diff = get_staged_diff(project.path)
                if not success:
                    # Falls keine staged changes, alle uncommitted nehmen
                    import subprocess

                    result = subprocess.run(
                        ["git", "diff", "--no-color"],
                        cwd=project.path,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    diff = result.stdout.strip()
                    if not diff:
                        return "❌ Keine Änderungen gefunden"

                success, message = generate_commit_message(api_key, diff, model)
                if not success:
                    return f"❌ {message}"

                return message

            # Event Bindings für GitHub Tab
            refresh_github_all_btn.click(
                fn=refresh_all_github_data,
                inputs=[project_dropdown],
                outputs=[
                    gh_cli_status_box,
                    git_status_box,
                    git_changes_box,
                    gh_notifications_box,
                    gh_actions_table,
                    gh_actions_debug,
                    gh_repo_about,
                    gh_repo_topics,
                ],
            )

            push_sync_btn.click(
                fn=push_and_sync,
                inputs=[project_dropdown, commit_msg_input],
                outputs=[push_sync_output, git_status_box],
            ).then(
                fn=get_git_changes_list,
                inputs=[project_dropdown],
                outputs=git_changes_box,
            ).then(
                fn=lambda: "",  # Clear commit message after push
                outputs=commit_msg_input,
            )

            # AI Commit Message generieren
            ai_commit_btn.click(
                fn=generate_ai_commit_message,
                inputs=[project_dropdown],
                outputs=commit_msg_input,
            )

            # Auto-load Git Status, Changes, Actions and Repo Info on project change
            def on_project_change_github(project_id):
                """Lädt alle GitHub-Daten bei Projektwechsel."""
                git_status = get_git_status(project_id)
                git_changes = get_git_changes_list(project_id)
                actions_table, actions_debug = get_github_actions(project_id)
                repo_about, repo_topics = get_repo_info(project_id)
                return (
                    git_status,
                    git_changes,
                    actions_table,
                    actions_debug,
                    repo_about,
                    repo_topics,
                )

            project_dropdown.change(
                fn=on_project_change_github,
                inputs=[project_dropdown],
                outputs=[
                    git_status_box,
                    git_changes_box,
                    gh_actions_table,
                    gh_actions_debug,
                    gh_repo_about,
                    gh_repo_topics,
                ],
            )

            run_gh_cmd_btn.click(
                fn=run_custom_gh_command,
                inputs=[gh_command_input],
                outputs=gh_command_output,
            )

            # === Settings Event Handlers ===

            # --- Token Status Funktionen (verwenden OS Keyring via SecretStore) ---
            from core.secrets import get_api_key, get_storage_info, set_api_key

            def get_github_token_status():
                """Gibt formatierten GitHub Token-Status zurück."""
                token = get_api_key("github")
                if token:
                    masked = token[:4] + "..." + token[-4:] if len(token) > 10 else "***"
                    # Verbindung testen
                    success, msg = self.github.test_connection()
                    if success:
                        return (
                            f"✅ **Verbunden:** {msg.replace('Verbunden als: ', '')}\n\n`{masked}`"
                        )
                    return f"⚠️ **Token gespeichert aber Verbindung fehlgeschlagen**\n\n`{masked}`"
                return "❌ Kein GitHub Token konfiguriert"

            def get_codacy_token_status():
                """Gibt formatierten Codacy Token-Status zurück."""
                token = get_api_key("codacy")
                storage = get_storage_info()
                backend = "OS Keyring" if storage.get("keyring_functional") else "Environment"

                if token:
                    masked = token[:4] + "..." + token[-4:] if len(token) > 10 else "***"
                    return (
                        f"### ✅ Token konfiguriert\n\n"
                        f"**Gespeicherter Token:** `{masked}`\n\n"
                        f"*Sicher im {backend} gespeichert.*"
                    )
                elif os.environ.get("CODACY_API_TOKEN"):
                    return (
                        "### ⚠️ Token aus Umgebungsvariable\n\n"
                        "*Speichere ihn für mehr Sicherheit (wird im Keyring gespeichert).*"
                    )
                return "### ❌ Kein Token konfiguriert"

            # --- Token Speichern (in OS Keyring) ---
            def save_github_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Token eingeben", get_github_token_status()
                self.github.set_token(token.strip())
                return "✅ GitHub Token im Keyring gespeichert!", get_github_token_status()

            def save_codacy_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Token eingeben", get_codacy_token_status()
                self.codacy.set_api_token(token.strip())
                return "✅ Codacy Token im Keyring gespeichert!", get_codacy_token_status()

            # --- OpenRouter ---
            def get_openrouter_token_status():
                """Gibt formatierten OpenRouter Token-Status zurück."""
                token = get_api_key("openrouter")
                storage = get_storage_info()
                backend = "OS Keyring" if storage.get("keyring_functional") else "Environment"

                if token:
                    masked = token[:8] + "..." + token[-4:] if len(token) > 14 else "***"
                    return (
                        f"### ✅ Key konfiguriert\n\n"
                        f"**Gespeicherter Key:** `{masked}`\n\n"
                        f"*Sicher im {backend} gespeichert.*"
                    )
                return "### ❌ Kein Key konfiguriert"

            def save_openrouter_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Key eingeben", get_openrouter_token_status()
                set_api_key("openrouter", token.strip())
                return "✅ OpenRouter Key im Keyring gespeichert!", get_openrouter_token_status()

            def save_openrouter_model(model):
                if not model:
                    return "❌ Kein Model ausgewählt"
                self.db.set_setting(
                    "openrouter_model",
                    model,
                    encrypt=False,
                    description="OpenRouter Model für AI Commits",
                )
                return f"✅ Model gespeichert: {model}"

            # --- Projekte Tabelle ---
            def load_projects_table(show_archived=False):
                """Lädt Projekte für Tabelle."""
                projects = self.db.get_all_projects(include_archived=show_archived)
                rows = []
                for p in projects:
                    codacy_status = "✅" if p.has_codacy else "❌"
                    if p.is_archived:
                        status = "📦 Archiviert"
                    elif p.is_archived is False and not p.has_codacy:
                        status = "🔒 Nur GitHub"
                    else:
                        status = "✅ Aktiv"
                    rows.append(
                        [p.id, p.name, p.github_owner or p.codacy_org, codacy_status, status]
                    )
                return rows

            def refresh_project_dropdown(show_archived=False):
                return gr.update(choices=self.get_project_choices(include_archived=show_archived))

            # --- GitHub Import ---
            def load_repos_from_github(include_private, show_archived):
                """Lädt Repos von GitHub und erstellt/aktualisiert Projekte."""
                if not self.github.token:
                    return (
                        "❌ Kein GitHub Token konfiguriert!\n\n"
                        "Bitte zuerst unter API Keys einen Token hinterlegen.",
                        load_projects_table(show_archived),
                    )

                repos = self.github.get_repos(include_private=include_private)
                if not repos:
                    return (
                        "⚠️ Keine Repositories gefunden oder Fehler beim Laden",
                        load_projects_table(show_archived),
                    )

                added = 0
                updated = 0
                skipped = 0

                for repo in repos:
                    # Prüfen ob bereits vorhanden
                    existing = None
                    for p in self.db.get_all_projects(include_archived=True):
                        if p.name == repo["name"] and (
                            p.github_owner == repo["owner"] or p.codacy_org == repo["owner"]
                        ):
                            existing = p
                            break

                    if existing:
                        # Aktualisieren wenn nötig
                        if existing.github_owner != repo["owner"]:
                            existing.github_owner = repo["owner"]
                            self.db.update_project(existing)
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        # Neues Projekt anlegen
                        project = Project(
                            name=repo["name"],
                            path="",  # Lokal nicht bekannt
                            git_remote=repo["ssh_url"],
                            codacy_provider="gh",
                            codacy_org=repo["owner"],
                            github_owner=repo["owner"],
                            has_codacy=True,  # Standard: annehmen dass Codacy vorhanden
                            is_archived=repo.get("archived", False),
                        )
                        self.db.create_project(project)
                        added += 1

                return (
                    f"✅ **Import abgeschlossen**\n\n"
                    f"- **Neu:** {added} Projekte\n"
                    f"- **Aktualisiert:** {updated}\n"
                    f"- **Übersprungen:** {skipped} (bereits vorhanden)",
                    load_projects_table(show_archived),
                )

            # --- Projekt-Aktionen ---
            def toggle_project_codacy(project_id, show_archived):
                if not project_id:
                    return "❌ Keine Projekt-ID angegeben", load_projects_table(show_archived)
                try:
                    project = self.db.get_project(int(project_id))
                    if not project:
                        return "❌ Projekt nicht gefunden", load_projects_table(show_archived)
                    project.has_codacy = not project.has_codacy
                    self.db.update_project(project)
                    status = "aktiviert" if project.has_codacy else "deaktiviert"
                    return f"✅ Codacy für '{project.name}' {status}", load_projects_table(
                        show_archived
                    )
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table(show_archived)

            def archive_project_db(project_id, show_archived):
                """Archiviert ein Projekt nur in der Datenbank (ohne Dateisystem)."""
                if not project_id:
                    return "❌ Keine Projekt-ID angegeben", load_projects_table(show_archived)
                try:
                    project = self.db.get_project(int(project_id))
                    if not project:
                        return "❌ Projekt nicht gefunden", load_projects_table(show_archived)
                    self.db.archive_project(int(project_id))
                    return f"📦 Projekt '{project.name}' archiviert", load_projects_table(
                        show_archived
                    )
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table(show_archived)

            def unarchive_project(project_id, show_archived):
                if not project_id:
                    return "❌ Keine Projekt-ID angegeben", load_projects_table(show_archived)
                try:
                    project = self.db.get_project(int(project_id))
                    if not project:
                        return "❌ Projekt nicht gefunden", load_projects_table(show_archived)
                    self.db.unarchive_project(int(project_id))
                    return f"📤 Projekt '{project.name}' wiederhergestellt", load_projects_table(
                        show_archived
                    )
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table(show_archived)

            def add_project(name, path, remote, provider, org, has_codacy, show_archived):
                if not name or not name.strip():
                    return "❌ Name ist erforderlich", load_projects_table(show_archived)
                try:
                    project = Project(
                        name=name.strip(),
                        path=path.strip() if path else "",
                        git_remote=remote.strip() if remote else "",
                        codacy_provider=provider,
                        codacy_org=org.strip() if org else "",
                        github_owner=org.strip() if org else "",
                        has_codacy=has_codacy,
                    )
                    self.db.create_project(project)
                    return f"✅ Projekt '{name}' hinzugefügt", load_projects_table(show_archived)
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table(show_archived)

            # === Event Bindings ===

            # GitHub Token speichern
            save_github_token_btn.click(
                fn=save_github_token,
                inputs=[github_token_input],
                outputs=[github_token_result, github_token_status],
            )

            # Codacy Token speichern
            save_token_btn.click(
                fn=save_codacy_token,
                inputs=[api_token_input],
                outputs=[token_save_result, token_status_box],
            )

            # OpenRouter Token speichern
            save_openrouter_btn.click(
                fn=save_openrouter_token,
                inputs=[openrouter_token_input],
                outputs=[openrouter_save_result, openrouter_token_status],
            )

            # OpenRouter Model speichern
            save_model_btn.click(
                fn=save_openrouter_model,
                inputs=[openrouter_model_input],
                outputs=[model_save_result],
            )

            # GitHub Import
            load_github_btn.click(
                fn=load_repos_from_github,
                inputs=[include_private_repos, show_archived_toggle],
                outputs=[github_import_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            # Archivierte Toggle
            show_archived_toggle.change(
                fn=load_projects_table,
                inputs=[show_archived_toggle],
                outputs=[projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            # Projekte aktualisieren
            refresh_projects_btn.click(
                fn=load_projects_table,
                inputs=[show_archived_toggle],
                outputs=[projects_table],
            )

            # Projekt-Aktionen
            toggle_codacy_btn.click(
                fn=toggle_project_codacy,
                inputs=[action_project_id, show_archived_toggle],
                outputs=[project_action_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            archive_btn.click(
                fn=archive_project_db,
                inputs=[action_project_id, show_archived_toggle],
                outputs=[project_action_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            unarchive_btn.click(
                fn=unarchive_project,
                inputs=[action_project_id, show_archived_toggle],
                outputs=[project_action_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            # Projekt manuell hinzufügen
            add_project_btn.click(
                fn=add_project,
                inputs=[
                    new_project_name,
                    new_project_path,
                    new_project_remote,
                    new_project_provider,
                    new_project_org,
                    new_project_has_codacy,
                    show_archived_toggle,
                ],
                outputs=[add_project_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            # Globaler Refresh-Button für Projekt-Dropdown
            refresh_dropdown_btn.click(
                fn=refresh_project_dropdown,
                inputs=[show_archived_toggle],
                outputs=[project_dropdown],
            )

            # Initial load - alle in einem
            def initial_load():
                return (
                    get_github_token_status(),
                    get_codacy_token_status(),
                    get_openrouter_token_status(),
                    load_projects_table(False),
                    get_gh_status_display(),
                    get_gh_notifications(),
                )

            app.load(
                fn=initial_load,
                outputs=[
                    github_token_status,
                    token_status_box,
                    openrouter_token_status,
                    projects_table,
                    gh_cli_status_box,
                    gh_notifications_box,
                ],
            )

        return app


def main():
    """Startet die Anwendung."""
    app = KIWorkspaceApp()
    ui = app.build_ui()
    ui.launch(
        server_name="127.0.0.1",
        server_port=7870,
        share=False,
    )


if __name__ == "__main__":
    main()
