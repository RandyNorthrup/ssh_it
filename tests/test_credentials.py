"""Factory credential reference schema and search tests."""

from __future__ import annotations

from collections import Counter
from datetime import date
from urllib.parse import urlsplit

import pytest

from ssh_it.credentials import CredentialEntry, CredentialLibrary, PasswordKind
from ssh_it.library import CommandLibrary


def test_bundled_credentials_are_scoped_sourced_and_consistent() -> None:
    """Every bundled reference has unique ID, HTTPS source, and coherent password kind."""
    library = CredentialLibrary.load_bundled()
    assert len(library.entries) >= 50
    assert {
        "Aruba",
        "Cisco",
        "Dell",
        "Extreme Networks",
        "Fortinet",
        "HPE",
        "MikroTik",
        "Netgate",
        "Palo Alto Networks",
        "QNAP",
        "Supermicro",
        "UniFi",
    } <= set(library.vendors)
    assert len(library.vendors) >= 20
    assert library.reviewed_on == date(2026, 7, 13)
    assert len({entry.id for entry in library.entries}) == len(library.entries)
    assert all(entry.source.startswith("https://") for entry in library.entries)
    assert all(entry.product for entry in library.entries)

    blank = library.get("fortinet.fortigate.blank")
    assert blank.password_kind is PasswordKind.BLANK
    assert blank.password == ""
    assert blank.can_fill_password

    sticker = library.get("mikrotik.routeros.sticker")
    assert sticker.password_kind is PasswordKind.DEVICE_SPECIFIC
    assert sticker.password is None
    assert not sticker.can_fill_password

    kinds = Counter(entry.password_kind for entry in library.entries)
    assert kinds[PasswordKind.STATIC] >= 30
    assert kinds[PasswordKind.BLANK] >= 10
    assert kinds[PasswordKind.DEVICE_SPECIFIC] >= 7


def test_bundled_credentials_have_source_and_command_library_integrity() -> None:
    """Every reference is official-source scoped and maps to a real command-library choice."""
    library = CredentialLibrary.load_bundled()
    command_vendors = set(CommandLibrary.load_bundled().vendors)
    source_hosts = {urlsplit(entry.source).hostname for entry in library.entries}
    assert len(source_hosts) >= 20
    assert all(entry.command_vendor in command_vendors for entry in library.entries)
    assert all(entry.source.startswith("https://") for entry in library.entries)
    assert all(len(entry.warning) >= 50 for entry in library.entries)


def test_credential_search_filters_all_terms_and_vendor() -> None:
    """Search requires every query word and combines with exact vendor filtering."""
    library = CredentialLibrary.load_bundled()
    results = library.search("catalyst first", vendor="Cisco")
    assert [entry.id for entry in results] == ["cisco.catalyst1200-1300"]
    assert library.search("printed", vendor="MikroTik") == (
        library.get("mikrotik.routeros.sticker"),
    )
    assert library.search("catalyst", vendor="UniFi") == ()


def test_credential_entry_rejects_ambiguous_password_metadata() -> None:
    """Static, blank, and device-specific kinds cannot contradict their value."""
    with pytest.raises(ValueError, match="static password"):
        CredentialEntry(
            id="test.invalid",
            vendor="Vendor",
            command_vendor="Vendor",
            product="Product",
            username="admin",
            password="",
            password_kind=PasswordKind.STATIC,
            description="Description",
            warning="Warning",
            source="https://example.com/reference",
        )
    with pytest.raises(ValueError, match="device-specific password"):
        CredentialEntry(
            id="test.invalid2",
            vendor="Vendor",
            command_vendor="Vendor",
            product="Product",
            username="admin",
            password="guess",
            password_kind=PasswordKind.DEVICE_SPECIFIC,
            description="Description",
            warning="Warning",
            source="https://example.com/reference",
        )


def test_credential_library_rejects_duplicate_ids() -> None:
    """Stable IDs are globally unique."""
    entry = CredentialLibrary.load_bundled().entries[0]
    with pytest.raises(ValueError, match="Duplicate credential IDs"):
        CredentialLibrary((entry, entry))
