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

                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("#### gh CLI Status")
                            gh_cli_status_box = gr.Markdown()
                            refresh_gh_status_btn = gr.Button("🔄 Status aktualisieren")

                        with gr.Column(scale=2):
                            gr.Markdown("#### Notifications")
                            gh_notifications_box = gr.Markdown()
                            refresh_notifications_btn = gr.Button("🔄 Notifications laden")

                    gr.Markdown("---")
                    gr.Markdown("#### Meine Pull Requests")

                    with gr.Row():
                        pr_filter = gr.Radio(
                            choices=["Offen", "Erstellt von mir", "Review angefragt"],
                            value="Offen",
                            label="Filter",
                        )
                        refresh_prs_btn = gr.Button("🔄 PRs laden")

                    gh_prs_table = gr.Dataframe(
                        headers=["Repo", "Titel", "Status", "Erstellt", "URL"],
                        datatype=["str", "str", "str", "str", "str"],
                        interactive=False,
                    )

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

                        from core.checks import run_all_checks

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
                        status = "READY" if passed == total else "NOT READY"
                        color = "green" if passed == total else "red"

                        summary = f"### Status: **{passed}/{total}** Checks bestanden - <span style='color:{color}'>{status}</span>"

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
                lines = output.strip().split("\n")[:10]  # Max 10
                return "**Neueste Notifications:**\n\n" + "\n".join(f"• {line}" for line in lines)

            def get_gh_prs(filter_type):
                """Lädt Pull Requests nach Filter."""
                if filter_type == "Offen":
                    cmd = [
                        "pr",
                        "list",
                        "--state",
                        "open",
                        "--limit",
                        "20",
                        "--json",
                        "repository,title,state,createdAt,url",
                    ]
                elif filter_type == "Erstellt von mir":
                    cmd = [
                        "pr",
                        "list",
                        "--author",
                        "@me",
                        "--state",
                        "all",
                        "--limit",
                        "20",
                        "--json",
                        "repository,title,state,createdAt,url",
                    ]
                else:  # Review angefragt
                    cmd = [
                        "pr",
                        "list",
                        "--search",
                        "review-requested:@me",
                        "--state",
                        "open",
                        "--limit",
                        "20",
                        "--json",
                        "repository,title,state,createdAt,url",
                    ]

                success, output = run_gh_command(cmd, timeout=30)
                if not success:
                    return []

                try:
                    import json

                    prs = json.loads(output)
                    rows = []
                    for pr in prs:
                        repo = pr.get("repository", {}).get("name", "?")
                        title = pr.get("title", "")[:50]
                        state = pr.get("state", "")
                        created = pr.get("createdAt", "")[:10]
                        url = pr.get("url", "")
                        rows.append([repo, title, state, created, url])
                    return rows
                except (json.JSONDecodeError, KeyError):
                    return []

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

            # Event Bindings für GitHub Tab
            refresh_gh_status_btn.click(
                fn=get_gh_status_display,
                outputs=gh_cli_status_box,
            )

            refresh_notifications_btn.click(
                fn=get_gh_notifications,
                outputs=gh_notifications_box,
            )

            refresh_prs_btn.click(
                fn=get_gh_prs,
                inputs=[pr_filter],
                outputs=gh_prs_table,
            )

            pr_filter.change(
                fn=get_gh_prs,
                inputs=[pr_filter],
                outputs=gh_prs_table,
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

            def archive_project(project_id, show_archived):
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
                fn=archive_project,
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

            # Initial load - alle in einem
            def initial_load():
                return (
                    self.get_stats(None),
                    get_github_token_status(),
                    get_codacy_token_status(),
                    load_projects_table(False),
                    get_gh_status_display(),
                )

            app.load(
                fn=initial_load,
                outputs=[
                    dashboard_stats,
                    github_token_status,
                    token_status_box,
                    projects_table,
                    gh_cli_status_box,
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
