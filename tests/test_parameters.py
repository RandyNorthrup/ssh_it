"""Typed IntelliSense parameter schema tests."""

from __future__ import annotations

import pytest

from ssh_it.parameters import ValueKind, parameter_spec


def test_parameter_kind_inference_and_hints() -> None:
    """Common placeholder names gain correct semantic format and human help."""
    assert parameter_spec("destination_port").kind is ValueKind.PORT
    assert parameter_spec("target_host").kind is ValueKind.HOST
    assert parameter_spec("remote_file").kind is ValueKind.PATH
    assert parameter_spec("interface").kind is ValueKind.INTERFACE
    assert "example" in parameter_spec("service").format_hint


@pytest.mark.parametrize("value", ["0", "65536", "twenty-two", "22; reboot"])
def test_port_validation_rejects_invalid_or_injected_values(value: str) -> None:
    """Port placeholders require bounded integers only."""
    with pytest.raises(ValueError, match=r"port|whole|least|most"):
        parameter_spec("remote_port").validate(value)


@pytest.mark.parametrize("value", ["router;reboot", "bad host", "host|cat"])
def test_host_validation_rejects_shell_operators(value: str) -> None:
    """Host values cannot smuggle shell syntax into unquoted template tokens."""
    with pytest.raises(ValueError, match="invalid"):
        parameter_spec("target_host").validate(value)


def test_url_validation_requires_complete_safe_http_url() -> None:
    """URL fields reject missing schemes and unquoted query operators."""
    spec = parameter_spec("inform_url")
    spec.validate("http://controller.example.com:8080/inform")
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        spec.validate("controller.example.com/inform")
    with pytest.raises(ValueError, match="unsafe"):
        spec.validate("https://example.com/file?a=1&b=2")
    with pytest.raises(ValueError, match="unsafe"):
        spec.validate("https://example.com/file#comment")
    with pytest.raises(ValueError, match=r"HTTP\(S\)"):
        spec.validate("https://admin:secret@example.com/file")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("remote_path", "/var/log/report;reboot"),
        ("identity_file", "-oProxyCommand=id"),
        ("local_file", "/home/example/report name.txt"),
        ("container", "api;id"),
    ],
)
def test_unquoted_path_and_generic_values_reject_injection(name: str, value: str) -> None:
    """Every value inserted into an unquoted command token blocks shell and option injection."""
    with pytest.raises(ValueError, match="invalid"):
        parameter_spec(name).validate(value)


def test_safe_path_interface_and_container_tokens_remain_usable() -> None:
    """Strict token validation still supports normal technician identifiers."""
    parameter_spec("remote_path").validate("~/backups/config-2026_07_13.tar.gz")
    parameter_spec("interface").validate("Ethernet1/1.100")
    parameter_spec("container").validate("api-1")
    assert parameter_spec("container").kind is ValueKind.SERVICE


def test_enterprise_library_identifiers_have_typed_context() -> None:
    """Kubernetes and firewall identifiers reject shell operators and offer useful defaults."""
    namespace = parameter_spec("namespace")
    verb = parameter_spec("verb")
    table = parameter_spec("table")
    assert "kube-system" in namespace.suggestions
    assert "delete" in verb.suggestions
    namespace.validate("production")
    table.validate("blocked_hosts")
    with pytest.raises(ValueError, match="invalid"):
        namespace.validate("default;id")
