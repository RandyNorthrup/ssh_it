"""Domain validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssh_it.models import (
    AuthMethod,
    CommandTemplate,
    ConnectionProfile,
    Risk,
    TunnelKind,
    TunnelSpec,
)


def command(**overrides: object) -> CommandTemplate:
    """Build valid command with targeted overrides."""
    values: dict[str, object] = {
        "id": "test.command",
        "title": "Test command",
        "command": "show ${target} ${target}",
        "description": "Inspect target.",
        "vendors": ["Test vendor"],
        "categories": ["Inspection"],
        "tags": ["test"],
        "risk": "safe",
        "requires_connection": True,
        "platforms": ["any"],
        "source": "https://example.com/docs",
    }
    values.update(overrides)
    return CommandTemplate.from_mapping(values)


def test_command_placeholders_are_unique_and_rendered() -> None:
    """Repeated placeholders need one value and replace every occurrence."""
    template = command()
    assert template.placeholders == ("target",)
    assert template.render({"target": "eth0"}) == "show eth0 eth0"


@pytest.mark.parametrize("value", ["", "line\nbreak", "line\rbreak", "nul\x00byte"])
def test_command_rejects_missing_or_multiline_placeholder(value: str) -> None:
    """Template inputs cannot add command lines or controls."""
    with pytest.raises(ValueError, match=r"Missing|one line"):
        command().render({"target": value})


def test_command_rejects_non_https_source() -> None:
    """Bundled references cannot downgrade source links."""
    with pytest.raises(ValueError, match="HTTPS"):
        command(source="http://example.com")


def test_profile_mapping_has_no_secret_and_stable_key() -> None:
    """Profile serialization remains non-secret and identity remains stable."""
    profile = ConnectionProfile(
        name="Lab",
        host="router.example.com",
        username="admin",
        auth_method=AuthMethod.PRIVATE_KEY,
        private_key=Path("~/.ssh/id_ed25519").expanduser(),
    )
    mapping = profile.to_mapping()
    assert "password" not in mapping
    assert "passphrase" not in mapping
    assert ConnectionProfile.from_mapping(mapping).canonical_key == profile.canonical_key


@pytest.mark.parametrize("host", ["", "bad host", "bad\nhost", "bad\x00host"])
def test_profile_rejects_invalid_host(host: str) -> None:
    """Whitespace and controls never reach network connector."""
    with pytest.raises(ValueError, match="Host"):
        ConnectionProfile(name="", host=host)


def test_tunnel_validation_and_loopback() -> None:
    """Tunnel requires destination except for SOCKS and classifies exposure."""
    local = TunnelSpec("tunnel.local", TunnelKind.LOCAL, "127.0.0.1", 0, "db", 5432)
    socks = TunnelSpec("tunnel.socks", TunnelKind.SOCKS, "::1", 1080)
    exposed = TunnelSpec("tunnel.exposed", TunnelKind.LOCAL, "192.0.2.10", 8080, "web", 80)
    assert local.is_loopback
    assert socks.is_loopback
    assert not exposed.is_loopback
    with pytest.raises(ValueError, match="destination"):
        TunnelSpec("tunnel.bad", TunnelKind.LOCAL, "127.0.0.1", 8080)


def test_risk_values_are_explicit() -> None:
    """Risk enum stays constrained to three UI states."""
    assert {risk.value for risk in Risk} == {"safe", "caution", "destructive"}
