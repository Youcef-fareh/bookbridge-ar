"""Secure OS Keyring Manager with encrypted local fallback.

Never logs secrets or stores them in plaintext SQLite.
"""

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Optional
from cryptography.fernet import Fernet
from bookbridge.config.settings import settings

logger = logging.getLogger(__name__)


class KeyringManager:
    SERVICE_NAME = "BookBridge"

    def __init__(self):
        self._keyring_available = False
        self._keyring = None
        try:
            import keyring
            self._keyring = keyring
            # Test if keyring backend works
            test_val = self._keyring.get_password(self.SERVICE_NAME, "__test__")
            self._keyring_available = True
            logger.info("Keyring backend available and working")
        except Exception as e:
            logger.warning(f"Keyring backend not available, using encrypted fallback: {str(e)}")
            self._keyring_available = False

    @property
    def _cipher(self) -> Fernet:
        """Derive a consistent machine/user encryption key for fallback storage."""
        user_entropy = f"{os.getlogin() if hasattr(os, 'getlogin') else 'user'}:{Path.home()}:BookBridgeSecretSalt"
        key_32 = hashlib.sha256(user_entropy.encode()).digest()
        b64_key = base64.urlsafe_b64encode(key_32)
        return Fernet(b64_key)

    def _ensure_vault_dir(self) -> bool:
        """Ensure vault directory exists with explicit error handling."""
        vault_dir = settings.data_dir / ".vault"
        try:
            # Create with explicit mode
            vault_dir.mkdir(parents=True, exist_ok=True, mode=0o755)
            logger.debug(f"Vault directory ready: {vault_dir}")
            return True
        except PermissionError as e:
            logger.error(f"Permission denied creating vault directory {vault_dir}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Failed to create vault directory {vault_dir}: {str(e)}")
            return False

    @property
    def fallback_path(self) -> Path:
        # Use a subdirectory to isolate vault from other files
        return settings.data_dir / ".vault" / "secrets.enc"

    def _read_fallback_vault(self) -> dict:
        vault_file = self.fallback_path
        if not vault_file.exists():
            return {}
        try:
            # Ensure directory exists before reading
            if not self._ensure_vault_dir():
                logger.warning("Vault directory unavailable, returning empty vault")
                return {}
            encrypted_data = vault_file.read_bytes()
            decrypted = self._cipher.decrypt(encrypted_data)
            return json.loads(decrypted.decode("utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read fallback vault: {str(e)}")
            return {}

    def _write_fallback_vault(self, vault: dict) -> None:
        vault_file = self.fallback_path
        try:
            # CRITICAL: Ensure directory exists BEFORE writing
            if not self._ensure_vault_dir():
                raise RuntimeError(f"Cannot create vault directory {vault_file.parent}")
            
            # Write with explicit encoding
            data = json.dumps(vault).encode("utf-8")
            encrypted = self._cipher.encrypt(data)
            
            # Use atomic write pattern to prevent corruption
            temp_file = vault_file.with_suffix(".tmp")
            temp_file.write_bytes(encrypted)
            temp_file.replace(vault_file)
            
            logger.info(f"Saved {len(vault)} secret(s) to fallback vault at {vault_file}")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to write fallback vault to {vault_file}: {str(e)}")
            logger.error(f"Details - Vault dir: {vault_file.parent}, Data dir: {settings.data_dir}")
            raise

    def save_secret(self, credential_id: str, secret_key: str) -> bool:
        """Save API secret securely. Always saves to fallback vault for reliability."""
        if not secret_key or not secret_key.strip():
            logger.error(f"Cannot save empty secret for credential '{credential_id}'")
            return False
        
        clean_secret = secret_key.strip()
        saved_somewhere = False
        
        # Try to save to keyring first (if available)
        if self._keyring_available:
            try:
                self._keyring.set_password(self.SERVICE_NAME, credential_id, clean_secret)
                logger.info(f"Saved secret to keyring for credential '{credential_id}'")
                saved_somewhere = True
            except Exception as e:
                logger.warning(f"Failed to save to keyring: {str(e)}, using fallback vault")
        
        # Always persist to fallback vault for portability and reliability
        try:
            vault = self._read_fallback_vault()
            vault[credential_id] = clean_secret
            self._write_fallback_vault(vault)
            logger.info(f"Saved secret to fallback vault for credential '{credential_id}'")
            saved_somewhere = True
        except Exception as e:
            logger.error(f"CRITICAL: Failed to save secret to fallback vault: {str(e)}")
            logger.error(f"Vault path: {self.fallback_path}")
            logger.error(f"Data dir: {settings.data_dir}")
            return False
        
        return saved_somewhere

    def get_secret(self, credential_id: str) -> Optional[str]:
        """Retrieve API secret without revealing or logging."""
        # Try keyring first
        if self._keyring_available:
            try:
                val = self._keyring.get_password(self.SERVICE_NAME, credential_id)
                if val:
                    logger.debug(f"Retrieved secret from keyring for credential '{credential_id}'")
                    return val
            except Exception as e:
                logger.debug(f"Keyring lookup failed: {str(e)}")
                pass

        # Fall back to encrypted vault
        vault = self._read_fallback_vault()
        secret = vault.get(credential_id)
        if secret:
            logger.debug(f"Retrieved secret from fallback vault for credential '{credential_id}'")
            return secret
        
        logger.error(f"Secret not found for credential '{credential_id}' in either keyring or fallback vault")
        return None

    def delete_secret(self, credential_id: str) -> bool:
        """Delete secret securely from both locations."""
        deleted = False
        
        # Delete from keyring
        if self._keyring_available:
            try:
                self._keyring.delete_password(self.SERVICE_NAME, credential_id)
                deleted = True
                logger.debug(f"Deleted secret from keyring for credential '{credential_id}'")
            except Exception as e:
                logger.debug(f"Failed to delete from keyring: {str(e)}")
        
        # Delete from fallback vault
        vault = self._read_fallback_vault()
        if credential_id in vault:
            del vault[credential_id]
            self._write_fallback_vault(vault)
            deleted = True
            logger.debug(f"Deleted secret from fallback vault for credential '{credential_id}'")
        
        return deleted


# Global keyring manager singleton
keyring_manager = KeyringManager()
