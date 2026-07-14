"""Bundled command schema, breadth, and search tests."""

from __future__ import annotations

from collections import Counter

from ssh_it.library import CommandLibrary
from ssh_it.models import Risk


def test_bundled_library_has_required_breadth_and_unique_ids() -> None:
    """Production bundle covers requested vendors and broader use cases."""
    library = CommandLibrary.load_bundled()
    ids = [item.id for item in library.commands]
    vendors = {vendor for item in library.commands for vendor in item.vendors}
    assert len(library.commands) >= 300
    assert len(ids) == len(set(ids))
    assert {
        "UniFi",
        "Cisco IOS / IOS XE",
        "SSH / OpenSSH",
        "Secure File Operations",
        "General Linux",
        "Juniper Junos",
        "Arista EOS",
        "MikroTik RouterOS",
        "Fortinet FortiOS",
        "Aruba AOS-CX",
        "Cisco NX-OS",
        "Cisco Secure Firewall ASA",
        "Dell SmartFabric OS10",
        "Kubernetes",
        "Netgate pfSense",
        "Palo Alto PAN-OS",
        "Windows PowerShell",
    } <= vendors
    assert len(vendors) >= 18
    assert len(library.categories) >= 150
    assert all(len(library.search(vendor=vendor)) >= 10 for vendor in library.vendors[1:])


def test_bundled_library_has_enterprise_workflow_depth() -> None:
    """Regression gates retain risk, parameter, and technician-use-case depth."""
    library = CommandLibrary.load_bundled()
    risks = Counter(item.risk for item in library.commands)
    assert risks[Risk.SAFE] >= 170
    assert risks[Risk.CAUTION] >= 55
    assert risks[Risk.DESTRUCTIVE] >= 8
    assert sum(bool(item.placeholders) for item in library.commands) >= 65
    category_keywords = " ".join(library.categories).casefold()
    for keyword in (
        "configuration",
        "diagnostics",
        "events",
        "hardware",
        "interfaces",
        "logs",
        "neighbors",
        "routing",
        "security",
        "storage",
        "vpn",
    ):
        assert keyword in category_keywords


def test_unifi_library_has_dedicated_technician_depth() -> None:
    """UniFi remains a deep first-class library across modern and legacy product workflows."""
    library = CommandLibrary.load_bundled()
    unifi = library.search(vendor="UniFi")
    assert len(unifi) >= 35
    categories = {category for item in unifi for category in item.categories}
    assert {
        "UniFi adoption",
        "UniFi gateway logs",
        "UniFi legacy USG",
        "UniFi packet capture",
        "UniFi self-hosted server",
        "UniFi switch support",
    } <= categories
    assert sum(item.risk is Risk.CAUTION for item in unifi) >= 15
    assert sum(bool(item.placeholders) for item in unifi) >= 10


def test_bundled_items_have_metadata_and_valid_sources() -> None:
    """Every command has explanation, category, platform, and secure source link when present."""
    for item in CommandLibrary.load_bundled().commands:
        assert item.description
        assert item.categories
        assert item.platforms
        assert not item.source or item.source.startswith("https://")


def test_vendor_filter_and_fuzzy_search() -> None:
    """Search ranks intended Cisco interface item and excludes other vendors."""
    results = CommandLibrary.load_bundled().search("interface status", vendor="Cisco IOS / IOS XE")
    assert results
    assert results[0].id == "cisco.interface.status"
    assert all("Cisco IOS / IOS XE" in item.vendors for item in results)


def test_all_libraries_blank_vendor_and_risk_filter() -> None:
    """Blank vendor searches all libraries and risk filter is exact."""
    library = CommandLibrary.load_bundled()
    all_results = library.search("routing")
    destructive = library.search(risk=Risk.DESTRUCTIVE)
    assert len({item.vendors[0] for item in all_results}) >= 3
    assert destructive
    assert all(item.risk is Risk.DESTRUCTIVE for item in destructive)


def test_known_templates_expose_expected_placeholders() -> None:
    """Important requested use cases remain parameterized rather than hardcoded."""
    library = CommandLibrary.load_bundled()
    assert "inform_url" in library.get("unifi.adoption.inform").placeholders
    assert {"local_port", "destination_host", "destination_port"} <= set(
        library.get("ssh.tunnel.local").placeholders
    )
