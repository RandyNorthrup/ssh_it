"""Credential-vault policy tests."""

from __future__ import annotations

from typing import cast

import pytest

from ssh_it.models import ConnectionProfile
from ssh_it.secrets import CredentialVault, CredentialVaultError, KeyringApi


class SecureBackend:
    """Recommended in-memory test backend marker."""

    name = "Secure test vault"
    priority = 5


class PlaintextBackend:
    """Forbidden backend marker."""

    name = "Plaintext test vault"
    priority = 5


class FakeApi:
    """Small keyring API fake with inspectable storage."""

    def __init__(self, backend: object) -> None:
        """Store selected backend and empty credential map."""
        self.backend = backend
        self.values: dict[tuple[str, str], str] = {}

    def get_keyring(self) -> object:
        """Return selected backend marker."""
        return self.backend

    def get_password(self, service_name: str, username: str) -> str | None:
        """Read in-memory credential."""
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        """Write in-memory credential."""
        self.values[(service_name, username)] = password

    def delete_password(self, service_name: str, username: str) -> None:
        """Delete in-memory credential."""
        del self.values[(service_name, username)]


def test_secure_vault_round_trip() -> None:
    """Recommended backend can store, load, and delete endpoint secret."""
    api = FakeApi(SecureBackend())
    vault = CredentialVault(cast("KeyringApi", api))
    profile = ConnectionProfile("", "router.example.com", username="admin")
    assert vault.is_available()
    vault.save(profile, "correct horse battery staple")
    assert vault.load(profile) == "correct horse battery staple"
    vault.delete(profile)
    assert vault.load(profile) is None


def test_plaintext_backend_is_refused() -> None:
    """High priority cannot make file/plaintext backend acceptable."""
    vault = CredentialVault(cast("KeyringApi", FakeApi(PlaintextBackend())))
    assert not vault.is_available()
    with pytest.raises(CredentialVaultError, match="memory-only"):
        vault.save(ConnectionProfile("", "router.example.com"), "secret")


def test_empty_password_is_refused() -> None:
    """Vault never creates ambiguous empty credential."""
    vault = CredentialVault(cast("KeyringApi", FakeApi(SecureBackend())))
    with pytest.raises(CredentialVaultError, match="empty"):
        vault.save(ConnectionProfile("", "router.example.com"), "")
