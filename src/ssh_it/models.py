"""Validated domain models shared by transport, library, and UI layers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, Final, Self, cast

from ssh_it.parameters import parameter_spec

_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_PLACEHOLDER_PATTERN: Final = re.compile(r"\$\{([a-z][a-z0-9_]*)\}")
_HOST_CONTROL_PATTERN: Final = re.compile(r"[\x00-\x20\x7f]")
_MAX_PORT: Final = 65_535
_MAX_CONNECT_TIMEOUT: Final = 120.0


class Risk(StrEnum):
    """Operational risk assigned to a reusable command."""

    SAFE = "safe"
    CAUTION = "caution"
    DESTRUCTIVE = "destructive"


class AuthMethod(StrEnum):
    """Supported SSH authentication sources."""

    AGENT = "agent"
    PASSWORD = "password"  # noqa: S105  # nosec B105
    PRIVATE_KEY = "private_key"


class TunnelKind(StrEnum):
    """Supported SSH TCP forwarding directions."""

    LOCAL = "local"
    REMOTE = "remote"
    SOCKS = "socks"


@dataclass(frozen=True, slots=True)
class CommandTemplate:
    """One validated command-library item."""

    id: str
    title: str
    command: str
    description: str
    vendors: tuple[str, ...]
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    risk: Risk
    requires_connection: bool
    platforms: tuple[str, ...]
    source: str = ""

    def __post_init__(self) -> None:
        """Reject unsafe or incomplete package data."""
        if not _ID_PATTERN.fullmatch(self.id):
            msg = f"Invalid command ID: {self.id!r}"
            raise ValueError(msg)
        for name, value in (
            ("title", self.title),
            ("command", self.command),
            ("description", self.description),
        ):
            if not value.strip():
                msg = f"Command {self.id!r} has blank {name}"
                raise ValueError(msg)
        if "\x00" in self.command or "\r" in self.command:
            msg = f"Command {self.id!r} contains unsupported control characters"
            raise ValueError(msg)
        if not self.vendors or not self.categories:
            msg = f"Command {self.id!r} needs vendor and category metadata"
            raise ValueError(msg)
        if self.source and not self.source.startswith("https://"):
            msg = f"Command {self.id!r} source must use HTTPS"
            raise ValueError(msg)

    @property
    def placeholders(self) -> tuple[str, ...]:
        """Return ordered, unique placeholder names in command text."""
        return tuple(dict.fromkeys(_PLACEHOLDER_PATTERN.findall(self.command)))

    def render(self, values: dict[str, str]) -> str:
        """Replace every placeholder, requiring non-empty single-line values."""
        missing = [name for name in self.placeholders if not values.get(name, "").strip()]
        if missing:
            msg = f"Missing values for: {', '.join(missing)}"
            raise ValueError(msg)
        rendered = self.command
        for name in self.placeholders:
            value = values[name].strip()
            parameter_spec(name).validate(value)
            rendered = rendered.replace(f"${{{name}}}", value)
        return rendered

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Self:
        """Build from JSON-compatible mapping with explicit field conversion."""
        try:
            return cls(
                id=str(value["id"]),
                title=str(value["title"]),
                command=str(value["command"]),
                description=str(value["description"]),
                vendors=_string_tuple(value["vendors"], "vendors"),
                categories=_string_tuple(value["categories"], "categories"),
                tags=_string_tuple(value.get("tags", []), "tags"),
                risk=Risk(str(value["risk"])),
                requires_connection=bool(value.get("requires_connection", True)),
                platforms=_string_tuple(value.get("platforms", ["any"]), "platforms"),
                source=str(value.get("source", "")),
            )
        except KeyError as error:
            msg = f"Command item missing field: {error.args[0]}"
            raise ValueError(msg) from error


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    """Non-secret SSH connection settings."""

    name: str
    host: str
    port: int = 22
    username: str = ""
    auth_method: AuthMethod = AuthMethod.AGENT
    private_key: Path | None = None
    vendor: str = ""
    connect_timeout: float = 15.0

    def __post_init__(self) -> None:
        """Validate values before network use."""
        if not self.host or _HOST_CONTROL_PATTERN.search(self.host):
            raise ValueError("Host must be non-empty and contain no whitespace or controls")
        if not 1 <= self.port <= _MAX_PORT:
            raise ValueError("SSH port must be between 1 and 65535")
        if "\x00" in self.username or "\n" in self.username or "\r" in self.username:
            raise ValueError("Username contains unsupported control characters")
        if not 1.0 <= self.connect_timeout <= _MAX_CONNECT_TIMEOUT:
            raise ValueError("Connection timeout must be between 1 and 120 seconds")
        if self.auth_method is AuthMethod.PRIVATE_KEY and self.private_key is None:
            raise ValueError("Private-key authentication needs a key path")

    @property
    def display_name(self) -> str:
        """Return user-facing profile label."""
        return self.name.strip() or f"{self.username + '@' if self.username else ''}{self.host}"

    @property
    def canonical_key(self) -> str:
        """Return stable non-secret identifier for settings and credential lookup."""
        identity = f"{self.username}@{self.host.casefold()}:{self.port}"
        return sha256(identity.encode("utf-8")).hexdigest()[:24]

    def to_mapping(self) -> dict[str, str | int | float | None]:
        """Serialize only non-secret profile fields."""
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_method": self.auth_method.value,
            "private_key": str(self.private_key) if self.private_key else None,
            "vendor": self.vendor,
            "connect_timeout": self.connect_timeout,
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Self:
        """Deserialize versioned settings data."""
        key_value = value.get("private_key")
        return cls(
            name=str(value.get("name", "")),
            host=str(value["host"]),
            port=int(value.get("port", 22)),
            username=str(value.get("username", "")),
            auth_method=AuthMethod(str(value.get("auth_method", AuthMethod.AGENT.value))),
            private_key=Path(str(key_value)).expanduser() if key_value else None,
            vendor=str(value.get("vendor", "")),
            connect_timeout=float(value.get("connect_timeout", 15.0)),
        )


@dataclass(frozen=True, slots=True)
class TunnelSpec:
    """Validated request for one SSH forwarding listener."""

    id: str
    kind: TunnelKind
    listen_host: str
    listen_port: int
    destination_host: str = ""
    destination_port: int = 0

    def __post_init__(self) -> None:
        """Validate local inputs before handing them to AsyncSSH."""
        if not _ID_PATTERN.fullmatch(self.id):
            raise ValueError("Tunnel ID is invalid")
        if not 0 <= self.listen_port <= _MAX_PORT:
            raise ValueError("Listen port must be between 0 and 65535")
        if self.kind is not TunnelKind.SOCKS:
            if not self.destination_host:
                raise ValueError("Forward destination host is required")
            if not 1 <= self.destination_port <= _MAX_PORT:
                raise ValueError("Destination port must be between 1 and 65535")

    @property
    def is_loopback(self) -> bool:
        """Return whether listener is restricted to local host."""
        return self.listen_host.strip().lower() in {"", "localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True, slots=True)
class CompletionCandidate:
    """Ranked text offered to command composer."""

    text: str
    title: str
    description: str
    source: str
    score: float
    risk: Risk = Risk.SAFE
    command_id: str = ""
    placeholders: tuple[str, ...] = field(default_factory=tuple)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    """Validate a JSON list containing unique non-empty strings."""
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise ValueError(msg)
    result = tuple(str(item).strip() for item in cast("list[object]", value))
    if any(not item for item in result):
        msg = f"{field_name} contains a blank value"
        raise ValueError(msg)
    if len(result) != len(set(result)):
        msg = f"{field_name} contains a duplicate value"
        raise ValueError(msg)
    return result
