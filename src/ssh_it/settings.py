"""Versioned non-secret settings, profiles, recents, and favorites."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final, cast

from PySide6.QtCore import QSettings

from ssh_it.models import ConnectionProfile

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

_SCHEMA_VERSION: Final = 1
_MAX_RECENTS: Final = 15
_PROFILES_KEY: Final = "connections/profiles"
_RECENTS_KEY: Final = "connections/recents"
_FAVORITE_CONNECTIONS_KEY: Final = "connections/favorites"
_FAVORITE_COMMANDS_KEY: Final = "commands/favorites"


class SettingsStore:
    """Read and write non-secret user state through platform-native QSettings."""

    def __init__(self, settings: QSettings | None = None) -> None:
        """Use injected settings in tests or app organization defaults in production."""
        self._settings = settings or QSettings("SSH It", "SSH It")

    def profiles(self) -> tuple[ConnectionProfile, ...]:
        """Return valid named profiles; ignore individual corrupt legacy entries."""
        return self._read_profiles(_PROFILES_KEY)

    def save_profile(self, profile: ConnectionProfile) -> None:
        """Upsert named profile by canonical endpoint identity."""
        profiles = [item for item in self.profiles() if item.canonical_key != profile.canonical_key]
        profiles.append(profile)
        profiles.sort(key=lambda item: item.display_name.casefold())
        self._write_profiles(_PROFILES_KEY, profiles)

    def delete_profile(self, canonical_key: str) -> None:
        """Delete one profile and favorite marker, leaving credential removal explicit."""
        profiles = [item for item in self.profiles() if item.canonical_key != canonical_key]
        self._write_profiles(_PROFILES_KEY, profiles)
        self._write_string_set(
            _FAVORITE_CONNECTIONS_KEY,
            self.favorite_connections() - {canonical_key},
        )

    def recents(self) -> tuple[ConnectionProfile, ...]:
        """Return successful endpoints newest first."""
        return self._read_profiles(_RECENTS_KEY)

    def record_recent(self, profile: ConnectionProfile) -> None:
        """Move endpoint to front of bounded recent list."""
        recents = [item for item in self.recents() if item.canonical_key != profile.canonical_key]
        recents.insert(0, profile)
        self._write_profiles(_RECENTS_KEY, recents[:_MAX_RECENTS])

    def favorite_connections(self) -> set[str]:
        """Return canonical keys of favorite connection profiles."""
        return self._read_string_set(_FAVORITE_CONNECTIONS_KEY)

    def set_connection_favorite(self, canonical_key: str, favorite: bool) -> None:
        """Add or remove connection favorite marker."""
        values = self.favorite_connections()
        if favorite:
            values.add(canonical_key)
        else:
            values.discard(canonical_key)
        self._write_string_set(_FAVORITE_CONNECTIONS_KEY, values)

    def favorite_commands(self) -> set[str]:
        """Return favorite command IDs."""
        return self._read_string_set(_FAVORITE_COMMANDS_KEY)

    def set_command_favorite(self, command_id: str, favorite: bool) -> None:
        """Add or remove a command favorite marker."""
        values = self.favorite_commands()
        if favorite:
            values.add(command_id)
        else:
            values.discard(command_id)
        self._write_string_set(_FAVORITE_COMMANDS_KEY, values)

    def _read_profiles(self, key: str) -> tuple[ConnectionProfile, ...]:
        raw = cast("str", self._settings.value(key, "", str))
        if not raw:
            return ()
        try:
            payload_value: object = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload_value, dict):
            return ()
        payload = cast("dict[str, Any]", payload_value)
        if payload.get("version") != _SCHEMA_VERSION:
            return ()
        items = payload.get("items")
        if not isinstance(items, list):
            return ()
        profiles: list[ConnectionProfile] = []
        for item_value in cast("list[object]", items):
            if not isinstance(item_value, dict):
                continue
            item = cast("dict[str, Any]", item_value)
            try:
                profiles.append(ConnectionProfile.from_mapping(item))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(profiles)

    def _write_profiles(self, key: str, profiles: Iterable[ConnectionProfile]) -> None:
        payload = {
            "version": _SCHEMA_VERSION,
            "items": [profile.to_mapping() for profile in profiles],
        }
        self._settings.setValue(key, json.dumps(payload, separators=(",", ":")))
        self._settings.sync()

    def _read_string_set(self, key: str) -> set[str]:
        raw = cast("list[object]", self._settings.value(key, [], list))
        return {str(item) for item in raw if str(item)}

    def _write_string_set(self, key: str, values: Iterable[str]) -> None:
        self._settings.setValue(key, sorted(set(values)))
        self._settings.sync()
