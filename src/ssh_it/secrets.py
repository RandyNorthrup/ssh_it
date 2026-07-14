"""Opt-in operating-system credential-vault access."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Protocol

import keyring
from keyring.errors import KeyringError

if TYPE_CHECKING:
    from keyring.backend import KeyringBackend

    from ssh_it.models import ConnectionProfile

_SERVICE: Final = "SSH It"


class CredentialVaultError(RuntimeError):
    """Safe user-facing credential-vault failure."""


class KeyringApi(Protocol):
    """Small keyring interface used for deterministic tests."""

    def get_keyring(self) -> KeyringBackend:
        """Return selected backend."""
        raise NotImplementedError

    def get_password(self, service_name: str, username: str) -> str | None:
        """Read secret."""
        raise NotImplementedError

    def set_password(self, service_name: str, username: str, password: str) -> None:
        """Write secret."""
        raise NotImplementedError

    def delete_password(self, service_name: str, username: str) -> None:
        """Delete secret."""
        raise NotImplementedError


class CredentialVault:
    """Use recommended system vaults and refuse file/plaintext fallback backends."""

    def __init__(self, api: KeyringApi = keyring) -> None:
        """Accept injected keyring API for unit tests."""
        self._api = api

    def backend_name(self) -> str:
        """Return backend display name without accessing any credential."""
        try:
            return self._api.get_keyring().name
        except (KeyringError, RuntimeError) as error:
            raise CredentialVaultError("OS credential vault could not initialize") from error

    def is_available(self) -> bool:
        """Return true only for recommended, non-file, non-degenerate backends."""
        try:
            backend = self._api.get_keyring()
            identity = f"{type(backend).__module__}.{type(backend).__name__}".casefold()
            priority = float(backend.priority)
        except (KeyringError, RuntimeError, TypeError, ValueError):
            return False
        forbidden = ("null", "fail", "plaintext", "keyrings.alt", "cryptfile")
        return priority >= 1 and not any(value in identity for value in forbidden)

    def load(self, profile: ConnectionProfile) -> str | None:
        """Load password for endpoint, failing closed when backend is unsuitable."""
        self._require_available()
        try:
            return self._api.get_password(_SERVICE, self._key(profile))
        except (KeyringError, RuntimeError) as error:
            raise CredentialVaultError(
                "Password could not be read from OS credential vault"
            ) from error

    def save(self, profile: ConnectionProfile, password: str) -> None:
        """Save non-empty password after successful authentication."""
        self._require_available()
        if not password:
            raise CredentialVaultError("Refusing to store an empty password")
        try:
            self._api.set_password(_SERVICE, self._key(profile), password)
        except (KeyringError, RuntimeError) as error:
            raise CredentialVaultError(
                "Password could not be saved to OS credential vault"
            ) from error

    def delete(self, profile: ConnectionProfile) -> None:
        """Delete stored password for endpoint."""
        self._require_available()
        try:
            self._api.delete_password(_SERVICE, self._key(profile))
        except (KeyringError, RuntimeError) as error:
            raise CredentialVaultError(
                "Password could not be removed from OS credential vault"
            ) from error

    def _require_available(self) -> None:
        if not self.is_available():
            raise CredentialVaultError(
                "No recommended OS credential vault is available; password remains memory-only"
            )

    @staticmethod
    def _key(profile: ConnectionProfile) -> str:
        return f"ssh:{profile.canonical_key}:{profile.username}@{profile.host}:{profile.port}"
