"""密钥安全管理 - 本地加密存储，密钥永不离开本机"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class KeyManager:
    """本地密钥管理器 - Fernet 对称加密 + PBKDF2 主密码派生"""

    VAULT_DIR = Path("./vault")
    VAULT_FILE = "encrypted_keys.json"
    SALT_FILE = "salt.bin"

    def __init__(self, vault_dir: str | Path | None = None):
        self.vault_dir = Path(vault_dir) if vault_dir else self.VAULT_DIR
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._fernet: Fernet | None = None
        self._decrypted_cache: dict[str, str] = {}

    def _get_salt(self) -> bytes:
        salt_path = self.vault_dir / self.SALT_FILE
        if salt_path.exists():
            return salt_path.read_bytes()
        salt = os.urandom(16)
        salt_path.write_bytes(salt)
        return salt

    def _derive_key(self, master_password: str) -> bytes:
        salt = self._get_salt()
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=600_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(master_password.encode()))

    def unlock(self, master_password: str) -> None:
        """用主密码解锁 vault"""
        key = self._derive_key(master_password)
        self._fernet = Fernet(key)

    def _ensure_unlocked(self) -> Fernet:
        if self._fernet is None:
            raise RuntimeError("Vault is locked. Call unlock(master_password) first.")
        return self._fernet

    def store(self, key_name: str, secret_value: str) -> None:
        """加密存储一个密钥"""
        fernet = self._ensure_unlocked()
        encrypted = fernet.encrypt(secret_value.encode())

        vault_path = self.vault_dir / self.VAULT_FILE
        data: dict[str, str] = {}
        if vault_path.exists():
            data = json.loads(vault_path.read_text())

        data[key_name] = base64.urlsafe_b64encode(encrypted).decode()
        vault_path.write_text(json.dumps(data, indent=2))
        vault_path.chmod(0o600)

    def retrieve(self, key_name: str) -> str:
        """解密读取一个密钥（仅在内存中解密）"""
        fernet = self._ensure_unlocked()

        if key_name in self._decrypted_cache:
            return self._decrypted_cache[key_name]

        vault_path = self.vault_dir / self.VAULT_FILE
        if not vault_path.exists():
            raise FileNotFoundError(f"Vault file not found: {vault_path}")

        data = json.loads(vault_path.read_text())
        if key_name not in data:
            raise KeyError(f"Key not found in vault: {key_name}")

        encrypted = base64.urlsafe_b64decode(data[key_name])
        decrypted = fernet.decrypt(encrypted).decode()

        self._decrypted_cache[key_name] = decrypted
        return decrypted

    def list_keys(self) -> list[str]:
        """列出所有已存储的密钥名称（不解密）"""
        vault_path = self.vault_dir / self.VAULT_FILE
        if not vault_path.exists():
            return []
        data = json.loads(vault_path.read_text())
        return list(data.keys())

    def remove(self, key_name: str) -> None:
        """删除一个密钥"""
        vault_path = self.vault_dir / self.VAULT_FILE
        if not vault_path.exists():
            return
        data = json.loads(vault_path.read_text())
        data.pop(key_name, None)
        vault_path.write_text(json.dumps(data, indent=2))
        self._decrypted_cache.pop(key_name, None)

    def clear_cache(self) -> None:
        """清除内存中的解密缓存"""
        self._decrypted_cache.clear()

    def safe_log(self, value: str) -> str:
        """密钥脱敏 - 用于日志输出"""
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}***{value[-4:]}"
