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

                        # Tabellarisches Layout: Label | Status | (Reserve)
                        with gr.Row():
                            gr.Markdown("**📁 Pfad**")
                            dash_info_path = gr.Markdown("*-*")
                            gr.Markdown("")
                        with gr.Row():
                            gr.Markdown("**🔗 GitHub**")
                            dash_info_github = gr.Markdown("*-*")
                            gr.Markdown("")
                        with gr.Row():
                            gr.Markdown("**📊 Codacy**")
                            dash_info_codacy = gr.Markdown("*-*")
                            gr.Markdown("")
                        with gr.Row():
                            gr.Markdown("**✓ Release Check**")
                            dash_release_info = gr.Markdown("*-*")
                            gr.Markdown("")  # Spalte 3 Reserve
                        with gr.Row():
                            gr.Markdown("**🔴 Critical Issues**")
                            dash_critical_list = gr.Markdown("*Keine*")
                            gr.Markdown("")  # Spalte 3 Reserve
                        with gr.Row():
                            gr.Markdown("**🟠 High Issues**")
                            dash_high_list = gr.Markdown("*Keine*")
                            gr.Markdown("")  # Spalte 3 Reserve
                        with gr.Row():
                            gr.Markdown("**📊 Coverage**")
                            dash_coverage = gr.Markdown("*-*")
                            gr.Markdown("")  # Spalte 3 Reserve

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

                    # Details & Aktionen
                    with gr.Row():
                        with gr.Column(scale=2):
                            gr.Markdown("### Issue Details")
                            detail_title = gr.Textbox(label="Titel", interactive=False)
                            detail_message = gr.Textbox(label="Meldung", interactive=False, lines=3)
                            detail_file = gr.Textbox(label="Datei", interactive=False)
                            detail_tool = gr.Textbox(label="Tool/Rule", interactive=False)
                            detail_cve = gr.Textbox(
                                label="CVE Info", interactive=False, visible=True
                            )
                            detail_fp = gr.Textbox(
                                label="False Positive Status", interactive=False, lines=4
                            )

                        with gr.Column(scale=1):
                            gr.Markdown("### Aktionen")
                            selected_issue_id = gr.Number(
                                label="Ausgewählte Issue ID", visible=True
                            )
                            fp_reason = gr.Textbox(
                                label="False Positive Begründung",
                                placeholder="z.B.: Whitelist-Pattern, nur Test-Code...",
                                lines=3,
                            )
                            mark_fp_btn = gr.Button(
                                "✅ Als False Positive markieren", variant="primary"
                            )
                            fp_result = gr.Textbox(label="Ergebnis", interactive=False)

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
                            commit_msg_input = gr.Textbox(
                                label="Commit Message",
                                placeholder="Änderungen beschreiben...",
                                lines=1,
                                max_lines=2,
                            )
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

                        # Rechts: Notifications
                        with gr.Column(scale=1):
                            gr.Markdown("#### 🔔 Notifications")
                            gh_notifications_box = gr.Textbox(
                                value="",
                                lines=10,
                                max_lines=20,
                                interactive=False,
                                show_label=False,
                            )

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
                        """Speichert die Phase eines Projekts."""
                        if not project_id:
                            return "❌ Kein Projekt ausgewählt"
                        if not phase_id:
                            return "❌ Keine Phase ausgewählt"
                        project = self.db.get_project(project_id)
                        if not project:
                            return "❌ Projekt nicht gefunden"
                        project.phase_id = phase_id
                        self.db.update_project(project)
                        phase = self.db.get_phase(phase_id)
                        phase_name = phase.display_name if phase else "Unbekannt"
                        return f"✅ Phase **{phase_name}** gespeichert"

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

                        # --- Check-Matrix ---
                        with gr.Tab("📊 Check-Matrix"):
                            gr.Markdown("### Phasen & Release Checks")
                            gr.Markdown(
                                "Konfiguriere welche Checks in welcher Projekt-Phase aktiv sind "
                                "und wie wichtig sie sind (Blocker vs. Empfohlen)."
                            )

                            # Phase-Auswahl
                            matrix_phase_dropdown = gr.Dropdown(
                                label="Phase auswählen",
                                choices=[],
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

                            def load_matrix_phases():
                                """Lädt Phasen für Matrix-Dropdown."""
                                phases = self.db.get_all_phases()
                                return [(f"{p.display_name} ({p.name})", p.id) for p in phases]

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

                            # Phasen beim Tab-Load
                            @matrix_phase_dropdown.select
                            def update_phases():
                                return gr.update(choices=load_matrix_phases())

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

            # False Positive markieren
            mark_fp_btn.click(
                fn=self.mark_as_false_positive,
                inputs=[selected_issue_id, fp_reason],
                outputs=fp_result,
            ).then(
                fn=update_issues,
                inputs=filter_inputs,
                outputs=issues_table,
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

                project = self.db.get_project_by_id(project_id)
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

            def load_dashboard_data():
                """Lädt alle Projekte mit gecachten Stats für das Dashboard."""
                projects = self.db.get_all_projects(include_archived=False)
                phases = {p.id: p.display_name for p in self.db.get_all_phases()}

                rows = []
                for p in projects:
                    # Phase-Name
                    phase_name = phases.get(p.phase_id, "-") if p.phase_id else "-"

                    # CI Status (letzte GitHub Action)
                    owner = p.github_owner or p.codacy_org
                    ci_status = get_last_ci_status(owner, p.name) if owner else "-"

                    # Git Status (uncommitted/unpushed)
                    git_status = get_git_status_short(p.path) if p.path else "-"

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
                            codacy_str,
                        ]
                    )

                return rows

            def refresh_all_projects():
                """Aktualisiert den Cache für alle Projekte."""
                from core.checks import run_all_checks

                projects = self.db.get_all_projects(include_archived=False)
                updated = 0

                for p in projects:
                    # Issues-Cache aktualisieren
                    self.db.update_project_cache(p.id)

                    # Release-Check ausführen und cachen
                    if p.path:
                        results = run_all_checks(self.db, p)
                        passed = sum(1 for r in results if r.passed)
                        total = len(results)
                        self.db.update_release_cache(p.id, passed, total, passed == total)

                    updated += 1

                return load_dashboard_data(), f"✅ {updated} Projekte aktualisiert"

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
                if not project_id:
                    return (
                        gr.update(visible=False),
                        "",
                        "*-*",
                        "*-*",
                        "*-*",
                        "*Keine*",
                        "*Keine*",
                        "*-*",
                        "*-*",
                        "",
                    )

                project = self.db.get_project(project_id)
                if not project:
                    return (
                        gr.update(visible=False),
                        "",
                        "*-*",
                        "*-*",
                        "*-*",
                        "*Keine*",
                        "*Keine*",
                        "*-*",
                        "*-*",
                        "",
                    )

                # Phase
                phase_name = "-"
                if project.phase_id:
                    phase = self.db.get_phase(project.phase_id)
                    if phase:
                        phase_name = phase.display_name

                # Info-Werte separat
                path_info = (
                    f"`{project.path.replace('/home/zorinadmin/projekte/', '~/')}`"
                    if project.path
                    else "*-*"
                )
                github_info = (
                    f"`{project.git_remote.replace('https://github.com/', '').replace('.git', '')}`"
                    if project.git_remote
                    else "*-*"
                )
                codacy_info = f"`{project.codacy_provider or '-'}/{project.codacy_org or '-'}`"

                # Critical Issues laden (max 5, kompakt)
                critical_issues = self.db.get_issues(
                    project_id=project_id,
                    priority="Critical",
                    status="open",
                    is_false_positive=False,
                )
                if critical_issues:
                    lines = []
                    for i in critical_issues[:5]:
                        title = i.title[:40] + "…" if len(i.title) > 40 else i.title
                        file_name = i.file_path.split("/")[-1][:20] if i.file_path else "-"
                        lines.append(f"• {title} (`{file_name}:{i.line_number or '-'}`)")
                    critical_list = "\n".join(lines)
                    if len(critical_issues) > 5:
                        critical_list += f"\n\n*+{len(critical_issues) - 5} weitere*"
                else:
                    critical_list = "✅ Keine"

                # High Issues laden (max 5, kompakt)
                high_issues = self.db.get_issues(
                    project_id=project_id,
                    priority="High",
                    status="open",
                    is_false_positive=False,
                )
                if high_issues:
                    lines = []
                    for i in high_issues[:5]:
                        title = i.title[:40] + "…" if len(i.title) > 40 else i.title
                        file_name = i.file_path.split("/")[-1][:20] if i.file_path else "-"
                        lines.append(f"• {title} (`{file_name}:{i.line_number or '-'}`)")
                    high_list = "\n".join(lines)
                    if len(high_issues) > 5:
                        high_list += f"\n\n*+{len(high_issues) - 5} weitere*"
                else:
                    high_list = "✅ Keine"

                # Release Check Info (nur Zähler)
                if project.cache_release_total > 0:
                    passed = project.cache_release_passed
                    total = project.cache_release_total
                    status_icon = "✅" if project.cache_release_ready else "⚠️"
                    release_info = f"{status_icon} **{passed}/{total}**"
                else:
                    release_info = "❓ *Nicht geprüft*"

                # Coverage (wird erst nach Check aktualisiert)
                coverage_info = "*-*"

                return (
                    gr.update(visible=True),
                    f"### 📁 {project.name} ({phase_name})",
                    path_info,
                    github_info,
                    codacy_info,
                    critical_list,
                    high_list,
                    release_info,
                    coverage_info,
                    "",
                )

            def on_dashboard_select(evt: gr.SelectData, data):
                """Handler für Klick auf Dashboard-Tabelle."""
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
                return (
                    None,
                    gr.update(visible=False),
                    "",
                    "*-*",
                    "*-*",
                    "*-*",
                    "*Keine*",
                    "*Keine*",
                    "*-*",
                    "*-*",
                    "",
                )

            def dash_sync_project(project_id):
                """Sync für ausgewähltes Projekt."""
                if not project_id:
                    return "⚠️ Kein Projekt ausgewählt"
                result = self.sync_from_codacy(project_id)
                return f"🔄 {result}"

            def dash_check_project(project_id):
                """Release Check für ausgewähltes Projekt."""
                if not project_id:
                    return "*Noch nicht geprüft*", "*-*", "⚠️ Kein Projekt ausgewählt"

                project = self.db.get_project(project_id)
                if not project or not project.path:
                    return "*Projekt hat keinen Pfad*", "*-*", "⚠️ Kein Pfad konfiguriert"

                from core.checks import run_all_checks

                results = run_all_checks(self.db, project)
                passed = sum(1 for r in results if r.passed)
                total = len(results)

                # Cache aktualisieren
                self.db.update_release_cache(project_id, passed, total, passed == total)

                # Coverage aus Ergebnissen extrahieren
                coverage_info = "*-*"
                for r in results:
                    if r.name == "Coverage":
                        # Farbkodierung basierend auf severity
                        if "%" in r.message:
                            import re

                            match = re.search(r"(\d+)%", r.message)
                            if match:
                                pct = int(match.group(1))
                                if pct >= 80:
                                    coverage_info = f"🟢 **{pct}%**"
                                elif pct >= 60:
                                    coverage_info = f"🟡 **{pct}%**"
                                else:
                                    coverage_info = f"🔴 **{pct}%**"
                        else:
                            coverage_info = r.message
                        break

                # Ergebnis formatieren (nur Zähler)
                status_icon = "✅" if passed == total else "⚠️"
                release_info = f"{status_icon} **{passed}/{total}**"

                return release_info, coverage_info, f"✅ Check abgeschlossen ({passed}/{total})"

            # Dashboard Table Select Handler
            dashboard_table.select(
                fn=on_dashboard_select,
                inputs=[dashboard_table],
                outputs=[
                    dash_selected_id,
                    dash_detail_group,
                    dash_detail_header,
                    dash_info_path,
                    dash_info_github,
                    dash_info_codacy,
                    dash_critical_list,
                    dash_high_list,
                    dash_release_info,
                    dash_coverage,
                    dash_detail_msg,
                ],
            )

            # Dashboard Action Buttons
            dash_sync_btn.click(
                fn=dash_sync_project,
                inputs=[dash_selected_id],
                outputs=[dash_detail_msg],
            ).then(
                fn=lambda pid: load_project_details(pid)[5:8] if pid else ("", "", ""),
                inputs=[dash_selected_id],
                outputs=[dash_critical_list, dash_high_list, dash_release_info],
            ).then(
                fn=load_dashboard_data,
                outputs=[dashboard_table],
            )

            dash_check_btn.click(
                fn=dash_check_project,
                inputs=[dash_selected_id],
                outputs=[dash_release_info, dash_coverage, dash_detail_msg],
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

            # Kombinierte Refresh-Funktion für GitHub Tab
            def refresh_all_github_data(project_id):
                """Aktualisiert alle GitHub-Daten auf einmal."""
                gh_status = get_gh_status_display()
                git_status = get_git_status(project_id)
                git_changes = get_git_changes_list(project_id)
                notifications = get_gh_notifications()
                actions_table, actions_debug = get_github_actions(project_id)
                return (
                    gh_status,
                    git_status,
                    git_changes,
                    notifications,
                    actions_table,
                    actions_debug,
                )

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

            # Auto-load Git Status, Changes and Actions on project change
            def on_project_change_github(project_id):
                """Lädt alle GitHub-Daten bei Projektwechsel."""
                git_status = get_git_status(project_id)
                git_changes = get_git_changes_list(project_id)
                actions_table, actions_debug = get_github_actions(project_id)
                return git_status, git_changes, actions_table, actions_debug

            project_dropdown.change(
                fn=on_project_change_github,
                inputs=[project_dropdown],
                outputs=[git_status_box, git_changes_box, gh_actions_table, gh_actions_debug],
            )

            run_gh_cmd_btn.click(
                fn=run_custom_gh_command,
                inputs=[gh_command_input],
                outputs=gh_command_output,
            )

            # === Settings Event Handlers ===

            # --- Token Status Funktionen ---
            def get_github_token_status():
                """Gibt formatierten GitHub Token-Status zurück."""
                token = self.db.get_setting("github_token")
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
                token = self.db.get_setting("codacy_api_token")
                if token:
                    masked = token[:4] + "..." + token[-4:] if len(token) > 10 else "***"
                    return (
                        f"### ✅ Token konfiguriert\n\n"
                        f"**Gespeicherter Token:** `{masked}`\n\n"
                        f"*Verschlüsselt in der Datenbank gespeichert.*"
                    )
                elif os.environ.get("CODACY_API_TOKEN"):
                    return (
                        "### ⚠️ Token aus Umgebungsvariable\n\n"
                        "*Speichere ihn in der DB für mehr Sicherheit.*"
                    )
                return "### ❌ Kein Token konfiguriert"

            # --- Token Speichern ---
            def save_github_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Token eingeben", get_github_token_status()
                self.github.set_token(token.strip())
                return "✅ GitHub Token gespeichert!", get_github_token_status()

            def save_codacy_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Token eingeben", get_codacy_token_status()
                self.codacy.set_api_token(token.strip())
                return "✅ Codacy Token gespeichert!", get_codacy_token_status()

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
                    load_projects_table(False),
                    get_gh_status_display(),
                    get_gh_notifications(),
                )

            app.load(
                fn=initial_load,
                outputs=[
                    github_token_status,
                    token_status_box,
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
