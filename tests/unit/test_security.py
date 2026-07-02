"""单元测试 - 密钥管理"""

import pytest
from pathlib import Path

from security.key_manager import KeyManager


class TestKeyManager:
    def test_store_and_retrieve(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        km.unlock("test_master_password")

        km.store("binance_api_key", "test_api_key_12345")
        result = km.retrieve("binance_api_key")
        assert result == "test_api_key_12345"

    def test_wrong_password_fails(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        km.unlock("correct_password")
        km.store("key1", "secret_value")

        km2 = KeyManager(vault_dir=tmp_path)
        km2.unlock("wrong_password")
        with pytest.raises(Exception):
            km2.retrieve("key1")

    def test_list_keys(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        km.unlock("password")
        km.store("key_a", "value_a")
        km.store("key_b", "value_b")

        keys = km.list_keys()
        assert "key_a" in keys
        assert "key_b" in keys

    def test_remove_key(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        km.unlock("password")
        km.store("key_to_remove", "value")
        km.remove("key_to_remove")

        with pytest.raises(KeyError):
            km.retrieve("key_to_remove")

    def test_safe_log_masks_secrets(self):
        km = KeyManager()
        assert km.safe_log("abcdefghij") == "abcd***ghij"
        assert km.safe_log("short") == "***"

    def test_vault_locked_raises(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        with pytest.raises(RuntimeError, match="locked"):
            km.store("key", "value")

    def test_encrypted_file_permissions(self, tmp_path):
        km = KeyManager(vault_dir=tmp_path)
        km.unlock("password")
        km.store("key1", "value1")

        vault_file = tmp_path / "encrypted_keys.json"
        assert vault_file.exists()
        mode = oct(vault_file.stat().st_mode)[-3:]
        assert mode == "600"
