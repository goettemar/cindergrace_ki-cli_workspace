"""
Sichere API-Key Verwaltung mit OS Keyring.

Migriert automatisch von der alten SQLite-Speicherung zum OS Keyring.
Nutzt cindergrace_common.SecretStore als Backend.
"""

import logging
from typing import Literal

from cindergrace_common import SecretStore

logger = logging.getLogger(__name__)

# Service Name für Keyring
SERVICE_NAME = "ki-workspace"

# Mapping von Key-Typen zu internen Namen
KEY_MAPPING: dict[str, tuple[str, str]] = {
    "codacy": ("codacy_api_token", "Codacy API Token"),
    "github": ("github_token", "GitHub Token"),
    "openrouter": ("openrouter_api_key", "OpenRouter API Key"),
}

# Singleton SecretStore
_secret_store: SecretStore | None = None


def _get_store() -> SecretStore:
    """Gibt die globale SecretStore-Instanz zurück."""
    global _secret_store
    if _secret_store is None:
        _secret_store = SecretStore(SERVICE_NAME, warn_on_fallback=True)
    return _secret_store


def _migrate_from_db(key_name: str) -> str | None:
    """
    Migriert einen Key von SQLite zum Keyring.

    Prüft ob der Key noch verschlüsselt in der DB liegt,
    entschlüsselt ihn und speichert ihn im Keyring.
    Löscht dann den verschlüsselten Wert aus der DB.

    Returns:
        Entschlüsselter Wert oder None wenn nicht in DB
    """
    # Import hier um zirkuläre Imports zu vermeiden
    from core.database import DatabaseManager

    db = DatabaseManager()

    # Hole Wert direkt aus DB (ohne Entschlüsselung prüfen)
    with db._get_connection() as conn:
        cursor = conn.execute("SELECT value, is_encrypted FROM settings WHERE key = ?", (key_name,))
        row = cursor.fetchone()

        if not row:
            return None

        value, is_encrypted = row["value"], row["is_encrypted"]

        if not value:
            return None

        # Wenn verschlüsselt, entschlüsseln
        if is_encrypted:
            from core.crypto import get_crypto

            decrypted = get_crypto().decrypt(value)
            if decrypted:
                # In Keyring speichern
                store = _get_store()
                stored_in_keyring = store.set(key_name, decrypted)

                if stored_in_keyring:
                    # Aus DB entfernen (Key nicht mehr dort speichern)
                    conn.execute(
                        "UPDATE settings SET value = '[migrated to keyring]', is_encrypted = 0 WHERE key = ?",
                        (key_name,),
                    )
                    conn.commit()
                    logger.info(f"Migriert '{key_name}' von SQLite zu OS Keyring")

                return decrypted

        # Nicht verschlüsselt und nicht "[migrated to keyring]"
        if value != "[migrated to keyring]":
            return value

    return None


def get_api_key(key_type: Literal["codacy", "github", "openrouter"]) -> str | None:
    """
    Holt einen API Key.

    Prüft zuerst den OS Keyring, dann migriert aus SQLite falls nötig.

    Args:
        key_type: Art des Keys (codacy, github, openrouter)

    Returns:
        API Key oder None wenn nicht gefunden
    """
    if key_type not in KEY_MAPPING:
        raise ValueError(f"Unbekannter Key-Typ: {key_type}")

    key_name, _ = KEY_MAPPING[key_type]
    store = _get_store()

    # 1. Versuche aus Keyring zu laden
    value = store.get(key_name)
    if value:
        return value

    # 2. Versuche Migration aus DB
    value = _migrate_from_db(key_name)
    if value:
        return value

    return None


def set_api_key(
    key_type: Literal["codacy", "github", "openrouter"],
    value: str,
) -> bool:
    """
    Speichert einen API Key im OS Keyring.

    Args:
        key_type: Art des Keys (codacy, github, openrouter)
        value: Der API Key

    Returns:
        True wenn im Keyring gespeichert, False wenn nur Env-Var Fallback
    """
    if key_type not in KEY_MAPPING:
        raise ValueError(f"Unbekannter Key-Typ: {key_type}")

    key_name, description = KEY_MAPPING[key_type]
    store = _get_store()

    stored_in_keyring = store.set(key_name, value)

    # Marker in DB setzen (für UI/Status-Anzeige)
    from core.database import DatabaseManager

    db = DatabaseManager()
    with db._get_connection() as conn:
        conn.execute(
            """INSERT INTO settings (key, value, is_encrypted, description)
               VALUES (?, '[stored in keyring]', 0, ?)
               ON CONFLICT(key) DO UPDATE SET
                   value = '[stored in keyring]',
                   is_encrypted = 0""",
            (key_name, description),
        )
        conn.commit()

    return stored_in_keyring


def delete_api_key(key_type: Literal["codacy", "github", "openrouter"]) -> bool:
    """
    Löscht einen API Key aus dem Keyring.

    Args:
        key_type: Art des Keys

    Returns:
        True wenn gelöscht, False wenn nicht gefunden
    """
    if key_type not in KEY_MAPPING:
        raise ValueError(f"Unbekannter Key-Typ: {key_type}")

    key_name, _ = KEY_MAPPING[key_type]
    store = _get_store()

    deleted = store.delete(key_name)

    # Auch aus DB entfernen
    from core.database import DatabaseManager

    db = DatabaseManager()
    with db._get_connection() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key_name,))
        conn.commit()

    return deleted


def get_storage_info() -> dict:
    """
    Gibt Informationen über den aktuellen Speicher-Backend zurück.

    Returns:
        Dict mit Backend-Details
    """
    store = _get_store()
    return store.get_storage_info()


def is_keyring_available() -> bool:
    """
    Prüft ob der sichere Keyring-Speicher verfügbar ist.

    Returns:
        True wenn Keyring funktioniert
    """
    store = _get_store()
    return store.is_keyring_available()
