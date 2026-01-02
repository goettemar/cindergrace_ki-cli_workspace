"""
Verschlüsselung für sensible Daten.

Nutzt Fernet (AES-128-CBC) für symmetrische Verschlüsselung.
Der Master-Key wird aus Umgebungsvariable oder lokaler Datei geladen.
"""

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet


class CryptoManager:
    """Verwaltet Verschlüsselung für API-Keys und andere Secrets."""

    def __init__(self, secret_path: Path | None = None):
        """
        Initialisiert den CryptoManager.

        Args:
            secret_path: Pfad zur Secret-Datei (default: ~/.ai-workspace/.secret)
        """
        if secret_path is None:
            secret_path = Path.home() / ".ai-workspace" / ".secret"
        self.secret_path = secret_path
        self._fernet: Fernet | None = None

    def _get_or_create_key(self) -> bytes:
        """
        Lädt oder erstellt den Master-Key.

        Priorität:
        1. Umgebungsvariable KI_WORKSPACE_SECRET
        2. Lokale Datei .secret
        3. Neu generieren und in .secret speichern
        """
        # 1. Aus Umgebungsvariable
        env_secret = os.environ.get("KI_WORKSPACE_SECRET")
        if env_secret:
            # Hash auf 32 Bytes für Fernet
            return base64.urlsafe_b64encode(hashlib.sha256(env_secret.encode()).digest())

        # 2. Aus Datei laden
        if self.secret_path.exists():
            return self.secret_path.read_bytes().strip()

        # 3. Neu generieren
        key = Fernet.generate_key()
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_path.write_bytes(key)
        # Nur für Owner lesbar
        self.secret_path.chmod(0o600)
        return key

    @property
    def fernet(self) -> Fernet:
        """Lazy-loaded Fernet Instanz."""
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """
        Verschlüsselt einen String.

        Args:
            plaintext: Zu verschlüsselnder Text

        Returns:
            Base64-kodierter verschlüsselter Text
        """
        if not plaintext:
            return ""
        encrypted = self.fernet.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Entschlüsselt einen String.

        Args:
            ciphertext: Verschlüsselter Text (Base64)

        Returns:
            Entschlüsselter Klartext
        """
        if not ciphertext:
            return ""
        try:
            decrypted = self.fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except Exception:
            return ""

    def is_encrypted(self, text: str) -> bool:
        """Prüft ob ein Text verschlüsselt aussieht (Fernet-Format)."""
        if not text:
            return False
        # Fernet-Token beginnen mit "gAAAAA"
        return text.startswith("gAAAAA") and len(text) > 50


# Singleton für einfachen Zugriff
_crypto_manager: CryptoManager | None = None


def get_crypto() -> CryptoManager:
    """Gibt die globale CryptoManager-Instanz zurück."""
    global _crypto_manager
    if _crypto_manager is None:
        _crypto_manager = CryptoManager()
    return _crypto_manager
