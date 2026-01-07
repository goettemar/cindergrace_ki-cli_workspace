# Review: Architektur v2.0 (KI-CLI Workspace)

## Findings (priorisiert)

### Hoch
1) **Fehlende stabile Identitäten und Versions-/Änderungsmodell für Offline-Sync** (docs/ARCHITECTURE_v2.md:77-116, 221-263)
   - Lokale Tabellen nutzen INTEGER-IDs, Server UUIDs; Mapping per `remote_id` ist vorgesehen, aber es fehlt ein klares Modell für **globale, stabile IDs** und **Operationen/Changesets**. Nur `sync_state` mit `local_version/remote_version` ohne definierte Semantik führt bei Multi-Client-Offline zu schwer lösbaren Konflikten (verlorene Updates, „last write wins“ auf Zeitstempeln).
   - **Vorschlag:** pro Entität eine **global unique id** (UUID/ULID) bereits lokal erzeugen; Sync als **append-only Change Log** (Operationen: create/update/delete mit `entity_id`, `version`, `client_id`, `timestamp`, optional `field_mask`). Serverseitig pro Entity „last_version“ verwalten und Konflikte per **optimistic concurrency** (If-Match/expected_version).

2) **Konfliktstrategie „Last Write Wins“ mit `updated_at` ist riskant** (docs/ARCHITECTURE_v2.md:234-245)
   - Offline-first + mehrere Clients => Uhrenabweichungen, unterschiedliche Zeitzonen, nachträgliche Syncs -> Überschreiben korrekter Änderungen möglich.
   - **Vorschlag:** Konflikterkennung über **Versionsnummern** oder **vector clocks** je Entity. „Last write wins“ nur als explizite Benutzerentscheidung in der UI, nicht als Default für Issues. Alternativ **Merge-Strategien** für bestimmte Felder (z. B. Labels/Tags als Set-Merge).

3) **Server-API und Auth sind zu minimal für Sync-Sicherheit** (docs/ARCHITECTURE_v2.md:265-294)
   - Ein Workspace-API-Key + `X-User-Name` als Header ist leicht zu spoofen; keine Device-Registrierung, kein Token-Rotation, keine Signierung. Offline-Clients können so Konflikte „unsichtbar“ erzeugen.
   - **Vorschlag:** einfache, aber robuste Auth: `client_id` registrieren + **per-client token** (rotierbar), optional HMAC-Signatur pro Request. `X-User-Name` nur als Anzeige, nicht als Auth-Ziel. Audit-Log sollte `client_id` + `user_id` referenzieren.

### Mittel
4) **Datenmodell lässt „soft delete“, Archivierung und Tombstones unklar** (docs/ARCHITECTURE_v2.md:77-116, 138-161)
   - Offline-first braucht **Tombstones** (delete-Events), sonst „gelöschte“ Entities kommen nach Pull wieder.
   - **Vorschlag:** `deleted_at`/`is_deleted` + Change Event „delete“. Serverseitig „purge“ nur per Admin/Retention.

5) **Sync-State Tabelle ist redundant/uneindeutig** (docs/ARCHITECTURE_v2.md:107-116)
   - Mischung aus `sync_state` + `issues.sync_state` + `remote_id` führt zu Inkonsistenzen.
   - **Vorschlag:** Ein konsistentes Modell: Entitäten mit `entity_id`, `version`, `dirty` Flag; `sync_state` als **Queue/Outbox** (Operationen) statt per-entity Status.

6) **Phasenplan unterschätzt Integrations-/Migrationsaufwand** (docs/ARCHITECTURE_v2.md:365-392)
   - Sync-Implementation vor Multi-User ist logisch, aber es fehlen explizite Aufgaben für **Datenmigration**, **Backfill**, **Schema-Versioning**, **Auth/Device Registration** und **E2E-Test-Szenarien**.
   - **Vorschlag:** Phase 2.5 „Migration & Tests“: Migration-Layer, Test-Matrix (Offline/Online/Conflict), Seed-Daten, Canary-Deployment (lokal).

### Niedrig
7) **Settings-Schema enthält Secrets im Klartext** (docs/ARCHITECTURE_v2.md:180-200)
   - `api_token` in Settings DB widerspricht „Via SecretStore“ Kommentar.
   - **Vorschlag:** Im Settings-Schema statt Token nur **Key-Refs** speichern (z. B. `secret_ref`), tatsächliche Tokens im SecretStore.

8) **Projektpfade/Auto-detect** (docs/ARCHITECTURE_v2.md:350-363)
   - Git remote Auto-detect kann fehlschlagen (detached head, no remote). Kein Fallback beschrieben.
   - **Vorschlag:** Fallback-UI: manuelle Eingabe + Validierung; Statusanzeige „Remote nicht gefunden“.

## Antworten auf Fokusfragen

1) **Sauber & erweiterbar?**
   - Struktur mit Service/Data-Layer ist sauber, aber ohne klaren Sync-Domain-Layer (Outbox/ChangeLog, Versioning) bleibt sie schwer erweiterbar. Erweiterbarkeit steigt mit **Domain-Events**, **Repository-Interfaces** und klaren DTOs für Sync.

2) **Probleme im Sync-Konzept?**
   - Ja: Zeitstempel-basierte Konflikte, fehlende Tombstones, fehlende stabile IDs/Versionen und unklare Sync-State-Logik.

3) **Phasenplan realistisch?**
   - Grundsätzlich ja, aber es fehlen Migration/Test/Monitoring/Backups. Sync-Implementation ohne vorherige Datenmodell-Entscheidung führt zu Rework.

4) **Fehlende Aspekte?**
   - Datenmigration + Backfill, Tombstones, Schema-Versioning, Device-Registrierung, Test-Matrix (Offline/Conflict), Observability (metrics/logs), Backup-Retention.

5) **Bessere Alternativen?**
   - **Sync:** Outbox/Inbox + ChangeLog (event-driven) statt „pull/push changes since last_sync“.
   - **IDs:** ULID/UUID lokal generieren, server akzeptiert Client-IDs.
   - **Konflikte:** Versioning/ETags + optional feldbasierter Merge.
   - **Auth:** per-client token + optional HMAC.

## Konkrete Verbesserungsvorschläge (kurz)

- Definiere **globale Entity-IDs** und **Versionsmodell** (optimistic concurrency) als Basis des Sync.
- Ersetze `sync_state` durch **Outbox-Queue** mit Operationen; führe **Tombstones** ein.
- Ergänze Server-API um `If-Match`/`expected_version`, `client_id` Registrierung und Rotations-Token.
- Ergänze Phase 2/3 um **Migration**, **Test-Matrix**, **Schema-Versioning**, **Backup/Retention**.
- Präzisiere Datenfelder: `updated_at` als audit, nicht für Konfliktauflösung; `deleted_at` als Sync-Event.

