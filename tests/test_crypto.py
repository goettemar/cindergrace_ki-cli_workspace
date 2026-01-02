"""Tests für CryptoManager."""

import tempfile
from pathlib import Path

from core.crypto import CryptoManager


class TestCryptoManager:
    """Tests für Verschlüsselung."""

    def test_encrypt_decrypt_roundtrip(self):
        """Verschlüsseln und Entschlüsseln funktioniert."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / ".secret"
            crypto = CryptoManager(secret_path=secret_path)

            plaintext = "mein_geheimer_api_key_123"
            encrypted = crypto.encrypt(plaintext)

            # Verschlüsselter Text ist anders als Original
            assert encrypted != plaintext
            assert len(encrypted) > len(plaintext)

            # Entschlüsseln gibt Original zurück
            decrypted = crypto.decrypt(encrypted)
            assert decrypted == plaintext

    def test_encrypt_empty_string(self):
        """Leerer String bleibt leer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / ".secret"
            crypto = CryptoManager(secret_path=secret_path)

            assert crypto.encrypt("") == ""
            assert crypto.decrypt("") == ""

    def test_is_encrypted(self):
        """Erkennt verschlüsselte Texte."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / ".secret"
            crypto = CryptoManager(secret_path=secret_path)

            plaintext = "nicht_verschluesselt"
            encrypted = crypto.encrypt(plaintext)

            assert crypto.is_encrypted(encrypted) is True
            assert crypto.is_encrypted(plaintext) is False
            assert crypto.is_encrypted("") is False

    def test_key_persistence(self):
        """Key wird in Datei gespeichert und wiederverwendet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / ".secret"

            # Erste Instanz erstellt Key
            crypto1 = CryptoManager(secret_path=secret_path)
            encrypted = crypto1.encrypt("test")

            # Zweite Instanz lädt Key
            crypto2 = CryptoManager(secret_path=secret_path)
            decrypted = crypto2.decrypt(encrypted)

            assert decrypted == "test"

    def test_decrypt_invalid_returns_empty(self):
        """Ungültiger Ciphertext gibt leeren String zurück."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / ".secret"
            crypto = CryptoManager(secret_path=secret_path)

            assert crypto.decrypt("invalid_ciphertext") == ""
            assert crypto.decrypt("gAAAAA_invalid") == ""
