"""Typed command-parameter definitions, hints, defaults, and validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urlsplit

_SAFE_HOST = re.compile(r"^[A-Za-z0-9_.:%\[\]-]+$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9_.:/@-]+$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:@%+/,\[\]-]+$")
_SAFE_PATH = re.compile(r"^(?!-)[A-Za-z0-9_./~:@%+,=\[\]-]+$")
_SAFE_URL = re.compile(r"^https?://[A-Za-z0-9_.:%/?+~,=\[\]-]+$")
_FILE_MODE = re.compile(r"^[0-7]{3,4}$")
_INTEGER = re.compile(r"^[0-9]+$")
_MAX_PORT: Final = 65_535


class ValueKind(StrEnum):
    """Semantic input kinds used by command IntelliSense."""

    TEXT = "text"
    HOST = "host or IP"
    PORT = "TCP port"
    INTEGER = "integer"
    PATH = "filesystem path"
    URL = "HTTP(S) URL"
    USER = "username"
    INTERFACE = "interface name"
    SERVICE = "service name"
    FILE_MODE = "octal file mode"


_TOKEN_PATTERNS: Final[dict[ValueKind, re.Pattern[str]]] = {
    ValueKind.TEXT: _SAFE_TOKEN,
    ValueKind.HOST: _SAFE_HOST,
    ValueKind.PATH: _SAFE_PATH,
    ValueKind.USER: _SAFE_NAME,
    ValueKind.INTERFACE: _SAFE_INTERFACE,
    ValueKind.SERVICE: _SAFE_TOKEN,
}


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    """Expected format, help, example, and default values for one placeholder."""

    name: str
    kind: ValueKind
    description: str
    example: str
    suggestions: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None

    @property
    def format_hint(self) -> str:
        """Return short inline type and example hint."""
        return f"Expected {self.kind.value}; example: {self.example}"

    def validate(self, value: str) -> None:
        """Reject missing, multiline, or semantically malformed value."""
        if not value.strip():
            raise ValueError(f"{self.name.replace('_', ' ').title()} is required")
        if any(control in value for control in ("\x00", "\n", "\r")):
            raise ValueError(f"{self.name!r} must be one line")
        stripped = value.strip()
        if self.kind in {ValueKind.PORT, ValueKind.INTEGER}:
            self._validate_integer(stripped)
        elif self.kind is ValueKind.URL:
            self._validate_url(stripped)
        elif self.kind is ValueKind.FILE_MODE:
            if not _FILE_MODE.fullmatch(stripped):
                raise ValueError(f"{self.name!r} must be 3 or 4 octal digits")
        elif (pattern := _TOKEN_PATTERNS.get(self.kind)) is not None and not pattern.fullmatch(
            stripped
        ):
            raise ValueError(f"{self.name!r} contains characters invalid for {self.kind.value}")

    def _validate_integer(self, value: str) -> None:
        if not _INTEGER.fullmatch(value):
            raise ValueError(f"{self.name!r} must be a whole number")
        number = int(value)
        if self.minimum is not None and number < self.minimum:
            raise ValueError(f"{self.name!r} must be at least {self.minimum}")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"{self.name!r} must be at most {self.maximum}")

    def _validate_url(self, value: str) -> None:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(f"{self.name!r} must be a complete HTTP(S) URL")
        if not _SAFE_URL.fullmatch(value):
            raise ValueError(f"{self.name!r} contains unsafe unquoted shell characters")


_EXACT_SPECS: Final[dict[str, ParameterSpec]] = {
    "count": ParameterSpec(
        "count",
        ValueKind.INTEGER,
        "Number of results, probes, or items. Use a bounded value.",
        "10",
        ("4", "10", "20", "50"),
        1,
        100_000,
    ),
    "lines": ParameterSpec(
        "lines",
        ValueKind.INTEGER,
        "Maximum log or output lines to return.",
        "100",
        ("50", "100", "200", "500"),
        1,
        1_000_000,
    ),
    "minutes": ParameterSpec(
        "minutes",
        ValueKind.INTEGER,
        "Safety or timeout interval in minutes.",
        "10",
        ("5", "10", "15", "30"),
        1,
        1_440,
    ),
    "mode": ParameterSpec(
        "mode",
        ValueKind.FILE_MODE,
        "POSIX file mode. Avoid world-writable values.",
        "0640",
        ("0600", "0640", "0644", "0750", "0755"),
    ),
    "inform_url": ParameterSpec(
        "inform_url",
        ValueKind.URL,
        "Full UniFi inform endpoint, normally ending in /inform.",
        "http://controller.example.com:8080/inform",
    ),
    "verified_firmware_url": ParameterSpec(
        "verified_firmware_url",
        ValueKind.URL,
        "Vendor firmware URL verified for exact device model and release.",
        "https://dl.ui.com/unifi/firmware/...",
    ),
    "namespace": ParameterSpec(
        "namespace",
        ValueKind.SERVICE,
        "Kubernetes namespace name.",
        "production",
        ("default", "kube-system", "production", "staging"),
    ),
    "pod": ParameterSpec(
        "pod",
        ValueKind.SERVICE,
        "Kubernetes pod name from the selected namespace.",
        "api-7b9f6d8c5d-x2k4p",
    ),
    "deployment": ParameterSpec(
        "deployment",
        ValueKind.SERVICE,
        "Kubernetes deployment name from the selected namespace.",
        "frontend",
    ),
    "verb": ParameterSpec(
        "verb",
        ValueKind.SERVICE,
        "Kubernetes API action to authorize.",
        "get",
        ("get", "list", "watch", "create", "update", "patch", "delete"),
    ),
    "resource": ParameterSpec(
        "resource",
        ValueKind.SERVICE,
        "Kubernetes API resource type.",
        "pods",
        ("pods", "deployments", "services", "secrets", "configmaps"),
    ),
    "table": ParameterSpec(
        "table",
        ValueKind.SERVICE,
        "Named firewall or address table.",
        "blocked_hosts",
    ),
    "container": ParameterSpec(
        "container",
        ValueKind.SERVICE,
        "Docker or Podman container name or identifier.",
        "api-1",
    ),
}


def parameter_spec(name: str) -> ParameterSpec:
    """Return exact or name-inferred schema for library placeholder."""
    exact = _EXACT_SPECS.get(name)
    if exact is not None:
        return exact
    lowered = name.casefold()
    if "port" in lowered:
        spec = ParameterSpec(
            name,
            ValueKind.PORT,
            "TCP port from 1 through 65535.",
            "22",
            ("22", "80", "443", "8080", "8443"),
            1,
            _MAX_PORT,
        )
    elif any(token in lowered for token in ("host", "hostname", "gateway", "ip")):
        spec = ParameterSpec(
            name,
            ValueKind.HOST,
            "DNS hostname or IPv4/IPv6 address; no shell operators.",
            "router.example.com",
        )
    elif any(token in lowered for token in ("user", "owner", "group")):
        spec = ParameterSpec(
            name,
            ValueKind.USER,
            "Remote username or POSIX owner/group token.",
            "admin",
        )
    elif "interface" in lowered:
        spec = ParameterSpec(
            name,
            ValueKind.INTERFACE,
            "Vendor-specific interface identifier.",
            "GigabitEthernet1/0/1",
        )
    elif "service" in lowered:
        spec = ParameterSpec(
            name,
            ValueKind.SERVICE,
            "System service unit name.",
            "sshd.service",
            ("sshd.service", "docker.service", "NetworkManager.service"),
        )
    elif "url" in lowered:
        spec = ParameterSpec(
            name, ValueKind.URL, "Complete HTTP(S) URL.", "https://example.com/file"
        )
    elif any(
        token in lowered
        for token in ("path", "file", "directory", "archive", "identity", "private_key")
    ):
        spec = ParameterSpec(
            name,
            ValueKind.PATH,
            "Unquoted local or remote path token. Spaces and shell operators are blocked.",
            "/var/log/messages",
        )
    else:
        spec = ParameterSpec(name, ValueKind.TEXT, "Vendor-specific required value.", "value")
    return spec
