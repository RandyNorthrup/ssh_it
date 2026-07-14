"""Validated public factory-credential reference library.

This module never stores user credentials. Bundled values are public vendor defaults
with narrow product scopes and official documentation links.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from importlib import resources
from typing import Any, Final, Self, cast

_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")


class PasswordKind(StrEnum):
    """How a factory password is supplied for an entry."""

    STATIC = "static"
    BLANK = "blank"
    DEVICE_SPECIFIC = "device-specific"


@dataclass(frozen=True, slots=True)
class CredentialEntry:
    """One product-scoped, public factory credential reference."""

    id: str
    vendor: str
    command_vendor: str
    product: str
    username: str
    password: str | None
    password_kind: PasswordKind
    description: str
    warning: str
    source: str

    def __post_init__(self) -> None:
        """Reject ambiguous or internally inconsistent reference data."""
        if not _ID_PATTERN.fullmatch(self.id):
            raise ValueError(f"Invalid credential ID: {self.id!r}")
        for name, value in (
            ("vendor", self.vendor),
            ("command_vendor", self.command_vendor),
            ("product", self.product),
            ("username", self.username),
            ("description", self.description),
            ("warning", self.warning),
        ):
            if not value.strip():
                raise ValueError(f"Credential {self.id!r} has blank {name}")
        if any(character in self.username for character in "\x00\r\n"):
            raise ValueError(f"Credential {self.id!r} username contains a control character")
        if self.password is not None and any(
            character in self.password for character in "\x00\r\n"
        ):
            raise ValueError(f"Credential {self.id!r} password contains a control character")
        if self.password_kind is PasswordKind.STATIC and not self.password:
            raise ValueError(f"Credential {self.id!r} static password must be non-empty")
        if self.password_kind is PasswordKind.BLANK and self.password != "":  # nosec B105
            raise ValueError(f"Credential {self.id!r} blank password must be an empty string")
        if self.password_kind is PasswordKind.DEVICE_SPECIFIC and self.password is not None:
            raise ValueError(f"Credential {self.id!r} device-specific password must be omitted")
        if not self.source.startswith("https://"):
            raise ValueError(f"Credential {self.id!r} source must use HTTPS")

    @property
    def can_fill_password(self) -> bool:
        """Return whether a literal or intentionally blank password can be filled."""
        return self.password_kind in {PasswordKind.STATIC, PasswordKind.BLANK}

    @property
    def password_status(self) -> str:
        """Return safe table text which does not reveal a literal password."""
        labels = {
            PasswordKind.STATIC: "Known factory value",
            PasswordKind.BLANK: "Intentionally blank",
            PasswordKind.DEVICE_SPECIFIC: "Device-specific value",
        }
        return labels[self.password_kind]

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> Self:
        """Build and validate an entry from JSON-compatible data."""
        try:
            password_value = value.get("password")
            return cls(
                id=str(value["id"]),
                vendor=str(value["vendor"]),
                command_vendor=str(value["command_vendor"]),
                product=str(value["product"]),
                username=str(value["username"]),
                password=None if password_value is None else str(password_value),
                password_kind=PasswordKind(str(value["password_kind"])),
                description=str(value["description"]),
                warning=str(value["warning"]),
                source=str(value["source"]),
            )
        except KeyError as error:
            raise ValueError(f"Credential item missing field: {error.args[0]}") from error


class CredentialLibrary:
    """Immutable, searchable set of public factory credential references."""

    def __init__(
        self,
        entries: Iterable[CredentialEntry],
        *,
        reviewed_on: date | None = None,
    ) -> None:
        """Store entries and enforce stable unique IDs."""
        items = tuple(entries)
        ids = [item.id for item in items]
        duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
        if duplicates:
            raise ValueError(f"Duplicate credential IDs: {', '.join(duplicates)}")
        if not items:
            raise ValueError("Credential library is empty")
        self._entries = items
        self._by_id = {item.id: item for item in items}
        self._reviewed_on = reviewed_on

    @property
    def entries(self) -> tuple[CredentialEntry, ...]:
        """Return entries in package order."""
        return self._entries

    @property
    def vendors(self) -> tuple[str, ...]:
        """Return sorted vendor choices."""
        return tuple(sorted({item.vendor for item in self._entries}))

    @property
    def reviewed_on(self) -> date | None:
        """Return bundle research review date when loaded from package data."""
        return self._reviewed_on

    def get(self, entry_id: str) -> CredentialEntry:
        """Return one entry by stable ID."""
        return self._by_id[entry_id]

    def search(self, query: str = "", *, vendor: str = "") -> tuple[CredentialEntry, ...]:
        """Filter public references by vendor and case-insensitive words."""
        words = tuple(query.casefold().split())
        vendor_key = vendor.casefold().strip()
        matches: list[CredentialEntry] = []
        for item in self._entries:
            if vendor_key and item.vendor.casefold() != vendor_key:
                continue
            haystack = (
                f"{item.vendor} {item.product} {item.username} {item.description} "
                f"{item.password_status}"
            ).casefold()
            if all(word in haystack for word in words):
                matches.append(item)
        return tuple(matches)

    @classmethod
    def load_bundled(cls) -> CredentialLibrary:
        """Load the validated public reference data bundled with the app."""
        path = resources.files("ssh_it.resources").joinpath("default_credentials.json")
        with path.open("r", encoding="utf-8") as handle:
            raw_value: object = json.load(handle)
        if not isinstance(raw_value, Mapping):
            raise ValueError("Credential library must contain an object")
        raw = cast("dict[str, object]", raw_value)
        reviewed_value = raw.get("reviewed")
        if not isinstance(reviewed_value, str):
            raise ValueError("Credential library must contain an ISO reviewed date")
        try:
            reviewed_on = date.fromisoformat(reviewed_value)
        except ValueError as error:
            raise ValueError("Credential library reviewed date must use YYYY-MM-DD") from error
        entry_values = raw.get("credentials")
        if not isinstance(entry_values, list):
            raise ValueError("Credential library must contain a credentials list")
        entries: list[CredentialEntry] = []
        for index, item_value in enumerate(cast("list[object]", entry_values)):
            if not isinstance(item_value, dict):
                raise ValueError(f"Credential item {index} must be an object")
            try:
                entries.append(CredentialEntry.from_mapping(cast("dict[str, Any]", item_value)))
            except ValueError as error:
                raise ValueError(f"Credential item {index}: {error}") from error
        return cls(entries, reviewed_on=reviewed_on)
