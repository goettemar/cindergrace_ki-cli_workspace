"""
KI-CLI Workspace - Hauptanwendung

Gradio-basierte GUI für Issue-Management und KI-Zusammenarbeit.
"""

import logging
import os

import gradio as gr

from core.codacy_sync import CodacySync
from core.database import DatabaseManager, Project

# Logging konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class KIWorkspaceApp:
    """Hauptanwendung für KI-CLI Workspace."""

    def __init__(self):
        """Initialisiert die Anwendung."""
        self.db = DatabaseManager()
        self.codacy = CodacySync(db=self.db)
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

    def get_project_choices(self) -> list[tuple[str, int]]:
        """Gibt Projekt-Auswahl für Dropdown zurück."""
        projects = self.db.get_all_projects()
        return [(p.name, p.id) for p in projects]

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

            if stats.get("errors"):
                result += f"\n\n⚠️ Fehler: {', '.join(stats['errors'])}"

            return result
        except Exception as e:
            logger.error(f"Sync-Fehler: {e}")
            return f"❌ Sync-Fehler: {e}"

    def build_ui(self) -> gr.Blocks:
        """Erstellt die Gradio-Oberfläche."""
        with gr.Blocks(title="KI-CLI Workspace") as app:
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

            with gr.Tabs():
                # === Dashboard Tab ===
                with gr.Tab("🏠 Dashboard"):
                    gr.Markdown("### Willkommen im KI-CLI Workspace")
                    gr.Markdown(
                        "Dieses Tool dient der projektübergreifenden Issue-Verwaltung "
                        "und KI-Zusammenarbeit."
                    )

                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### 📊 Statistiken")
                            dashboard_stats = gr.Markdown()
                            refresh_dashboard_btn = gr.Button("🔄 Aktualisieren")

                        with gr.Column():
                            gr.Markdown("### ℹ️ Projekt-Info")
                            project_info = gr.Markdown("*Wähle ein Projekt aus*")

                # === Issues Tab (Codacy) ===
                with gr.Tab("📋 Issues (Codacy)"):
                    # Sync-Bereich
                    with gr.Row():
                        sync_btn = gr.Button("🔄 Sync von Codacy", variant="primary", scale=1)
                        sync_status = gr.Textbox(
                            label="Status", interactive=False, scale=3, max_lines=2
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
                            detail_fp = gr.Textbox(label="False Positive Status", interactive=False)

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

                # === False Positives Tab ===
                with gr.Tab("🚫 False Positives"):
                    gr.Markdown("### Alle False Positives")
                    gr.Markdown("*Kommt in Phase 2 - Übersicht aller FPs mit Sync-Status*")
                    gr.Dataframe(
                        headers=["ID", "Projekt", "Titel", "Begründung", "Markiert am"],
                        datatype=["number", "str", "str", "str", "str"],
                        interactive=False,
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
                            gr.Markdown("### Codacy API Token")
                            gr.Markdown(
                                "Der Token wird **verschlüsselt** in der lokalen Datenbank gespeichert. "
                                "[Token erstellen](https://app.codacy.com/account/apiTokens)"
                            )

                            with gr.Row():
                                api_token_input = gr.Textbox(
                                    label="Codacy API Token",
                                    type="password",
                                    placeholder="Token eingeben...",
                                    scale=3,
                                )
                                save_token_btn = gr.Button("💾 Speichern", variant="primary")

                            token_status = gr.Markdown()

                            gr.Markdown("---")
                            gr.Markdown("### Token-Status")
                            token_info = gr.Markdown()
                            check_token_btn = gr.Button("🔍 Token prüfen")

                        # --- Projekte ---
                        with gr.Tab("📁 Projekte"):
                            gr.Markdown("### Projekt hinzufügen")

                            with gr.Row():
                                new_project_name = gr.Textbox(
                                    label="Name", placeholder="mein-projekt"
                                )
                                new_project_path = gr.Textbox(
                                    label="Lokaler Pfad", placeholder="/home/user/projekte/..."
                                )

                            with gr.Row():
                                new_project_remote = gr.Textbox(
                                    label="Git Remote", placeholder="git@github.com:user/repo.git"
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

                            add_project_btn = gr.Button("➕ Projekt hinzufügen", variant="primary")
                            add_project_status = gr.Markdown()

                            gr.Markdown("---")
                            gr.Markdown("### Vorhandene Projekte")

                            projects_table = gr.Dataframe(
                                headers=["ID", "Name", "Pfad", "Provider", "Organisation"],
                                datatype=["number", "str", "str", "str", "str"],
                                interactive=False,
                            )

                            with gr.Row():
                                delete_project_id = gr.Number(label="Projekt-ID zum Löschen")
                                delete_project_btn = gr.Button("🗑️ Löschen", variant="stop")

                            delete_project_status = gr.Markdown()

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

            def update_project_info(project_id):
                if not project_id:
                    return "*Wähle ein Projekt aus*"
                project = self.db.get_project(project_id)
                if not project:
                    return "*Projekt nicht gefunden*"
                return (
                    f"**Name:** {project.name}\n\n"
                    f"**Pfad:** `{project.path}`\n\n"
                    f"**Git:** `{project.git_remote}`\n\n"
                    f"**Codacy:** {project.codacy_provider}/{project.codacy_org}"
                )

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

            # Projekt-Wechsel aktualisiert alles
            project_dropdown.change(
                fn=update_issues,
                inputs=filter_inputs,
                outputs=issues_table,
            ).then(
                fn=self.get_stats,
                inputs=[project_dropdown],
                outputs=dashboard_stats,
            ).then(
                fn=update_project_info,
                inputs=[project_dropdown],
                outputs=project_info,
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
            ).then(
                fn=self.get_stats,
                inputs=[project_dropdown],
                outputs=dashboard_stats,
            )

            # Dashboard aktualisieren
            refresh_dashboard_btn.click(
                fn=self.get_stats,
                inputs=[project_dropdown],
                outputs=dashboard_stats,
            )

            # === Settings Event Handlers ===

            def save_api_token(token):
                if not token or not token.strip():
                    return "❌ Bitte Token eingeben"
                self.codacy.set_api_token(token.strip())
                return "✅ Token gespeichert (verschlüsselt)"

            def check_token_status():
                token = self.db.get_setting("codacy_api_token")
                if token:
                    # Zeige nur die ersten/letzten Zeichen
                    masked = token[:4] + "..." + token[-4:] if len(token) > 10 else "***"
                    return f"✅ Token gespeichert: `{masked}`"
                elif os.environ.get("CODACY_API_TOKEN"):
                    return "⚠️ Token aus Umgebungsvariable (nicht in DB)"
                return "❌ Kein Token konfiguriert"

            def load_projects_table():
                projects = self.db.get_all_projects()
                return [[p.id, p.name, p.path, p.codacy_provider, p.codacy_org] for p in projects]

            def add_project(name, path, remote, provider, org):
                if not name or not name.strip():
                    return "❌ Name ist erforderlich", load_projects_table()
                try:
                    project = Project(
                        name=name.strip(),
                        path=path.strip() if path else "",
                        git_remote=remote.strip() if remote else "",
                        codacy_provider=provider,
                        codacy_org=org.strip() if org else "",
                    )
                    self.db.create_project(project)
                    return f"✅ Projekt '{name}' hinzugefügt", load_projects_table()
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table()

            def delete_project(project_id):
                if not project_id:
                    return "❌ Keine Projekt-ID angegeben", load_projects_table()
                try:
                    project = self.db.get_project(int(project_id))
                    if not project:
                        return "❌ Projekt nicht gefunden", load_projects_table()
                    self.db.delete_project(int(project_id))
                    return f"✅ Projekt '{project.name}' gelöscht", load_projects_table()
                except Exception as e:
                    return f"❌ Fehler: {e}", load_projects_table()

            def refresh_project_dropdown():
                return gr.update(choices=self.get_project_choices())

            # Token speichern
            save_token_btn.click(
                fn=save_api_token,
                inputs=[api_token_input],
                outputs=[token_status],
            ).then(
                fn=check_token_status,
                outputs=[token_info],
            )

            # Token prüfen
            check_token_btn.click(
                fn=check_token_status,
                outputs=[token_info],
            )

            # Projekt hinzufügen
            add_project_btn.click(
                fn=add_project,
                inputs=[
                    new_project_name,
                    new_project_path,
                    new_project_remote,
                    new_project_provider,
                    new_project_org,
                ],
                outputs=[add_project_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                outputs=[project_dropdown],
            )

            # Projekt löschen
            delete_project_btn.click(
                fn=delete_project,
                inputs=[delete_project_id],
                outputs=[delete_project_status, projects_table],
            ).then(
                fn=refresh_project_dropdown,
                outputs=[project_dropdown],
            )

            # Initial load
            app.load(
                fn=lambda: self.get_stats(None),
                outputs=dashboard_stats,
            )
            app.load(
                fn=check_token_status,
                outputs=token_info,
            )
            app.load(
                fn=load_projects_table,
                outputs=projects_table,
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
