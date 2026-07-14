"""Non-secret settings, recents, and favorites tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from ssh_it.models import AuthMethod, ConnectionProfile
from ssh_it.settings import SettingsStore


def profile(index: int = 0) -> ConnectionProfile:
    """Create unique valid profile."""
    return ConnectionProfile(
        name=f"Lab {index}",
        host=f"router-{index}.example.com",
        port=22 + index,
        username="admin",
        auth_method=AuthMethod.PRIVATE_KEY,
        private_key=Path.home() / ".ssh" / "id_test",
        vendor="Cisco IOS / IOS XE",
    )


def store(tmp_path: Path) -> tuple[SettingsStore, Path]:
    """Create file-backed isolated QSettings."""
    path = tmp_path / "settings.ini"
    settings = QSettings(str(path), QSettings.Format.IniFormat)
    return SettingsStore(settings), path


def test_profiles_round_trip_without_secret_text(tmp_path: Path) -> None:
    """Profile storage round-trips and never contains credential field names."""
    settings, path = store(tmp_path)
    settings.save_profile(profile())
    assert settings.profiles() == (profile(),)
    content = path.read_text(encoding="utf-8").casefold()
    assert "password" not in content
    assert "passphrase" not in content


def test_recents_are_newest_first_deduplicated_and_bounded(tmp_path: Path) -> None:
    """Successful endpoint history remains short and predictable."""
    settings, _path = store(tmp_path)
    for index in range(20):
        settings.record_recent(profile(index))
    settings.record_recent(profile(10))
    assert len(settings.recents()) == 15
    assert settings.recents()[0].canonical_key == profile(10).canonical_key


def test_connection_and_command_favorites_persist(tmp_path: Path) -> None:
    """Favorite IDs persist independently from commands and profile order."""
    settings, _path = store(tmp_path)
    settings.set_connection_favorite(profile().canonical_key, True)
    settings.set_command_favorite("cisco.interface.status", True)
    assert profile().canonical_key in settings.favorite_connections()
    assert "cisco.interface.status" in settings.favorite_commands()
    settings.set_command_favorite("cisco.interface.status", False)
    assert not settings.favorite_commands()


def test_corrupt_settings_fail_closed(tmp_path: Path) -> None:
    """Invalid JSON does not crash startup or synthesize a profile."""
    settings, _path = store(tmp_path)
    raw = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    raw.setValue("connections/profiles", "not-json")
    raw.sync()
    assert settings.profiles() == ()
