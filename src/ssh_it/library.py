"""Command package-data loading, validation, filtering, and ranking."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from importlib import resources
from typing import TYPE_CHECKING, Final, cast

from ssh_it.models import CommandTemplate, Risk

if TYPE_CHECKING:
    from typing import Any

_TOKEN_PATTERN: Final = re.compile(r"[a-z0-9_.:/-]+")
_ALL_VENDOR: Final = "All libraries"
_MIN_SEARCH_SCORE: Final = 35.0


class CommandLibrary:
    """Immutable, searchable set of validated command templates."""

    def __init__(self, commands: Iterable[CommandTemplate]) -> None:
        """Store commands and enforce global ID uniqueness."""
        items = tuple(commands)
        ids = [item.id for item in items]
        duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
        if duplicates:
            msg = f"Duplicate command IDs: {', '.join(duplicates)}"
            raise ValueError(msg)
        self._commands = items
        self._by_id = {item.id: item for item in items}

    @property
    def commands(self) -> tuple[CommandTemplate, ...]:
        """Return all templates in package order."""
        return self._commands

    @property
    def vendors(self) -> tuple[str, ...]:
        """Return sorted vendor/library choices including all-libraries label."""
        values = sorted({vendor for item in self._commands for vendor in item.vendors})
        return (_ALL_VENDOR, *values)

    @property
    def categories(self) -> tuple[str, ...]:
        """Return sorted category values."""
        return tuple(sorted({category for item in self._commands for category in item.categories}))

    def get(self, command_id: str) -> CommandTemplate:
        """Look up one command or raise KeyError."""
        return self._by_id[command_id]

    def search(
        self,
        query: str = "",
        *,
        vendor: str = "",
        category: str = "",
        risk: Risk | None = None,
        limit: int | None = None,
    ) -> tuple[CommandTemplate, ...]:
        """Filter and rank templates with deterministic fuzzy scoring."""
        normalized_vendor = "" if vendor == _ALL_VENDOR else vendor.casefold().strip()
        query_text = query.casefold().strip()
        ranked: list[tuple[float, CommandTemplate]] = []
        for item in self._commands:
            if normalized_vendor and normalized_vendor not in {
                value.casefold() for value in item.vendors
            }:
                continue
            if category and category not in item.categories:
                continue
            if risk is not None and item.risk is not risk:
                continue
            score = _command_score(query_text, item)
            if query_text and score <= 0:
                continue
            ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].title.casefold(), pair[1].id))
        result = tuple(item for _, item in ranked)
        return result[:limit] if limit is not None else result

    @classmethod
    def load_bundled(cls) -> CommandLibrary:
        """Load every JSON library bundled in package resources."""
        root = resources.files("ssh_it.resources.commands")
        commands: list[CommandTemplate] = []
        for path in sorted(root.iterdir(), key=lambda item: item.name):
            if path.name.startswith("_") or not path.name.endswith(".json"):
                continue
            with path.open("r", encoding="utf-8") as handle:
                raw_value: object = json.load(handle)
            if not isinstance(raw_value, Mapping):
                msg = f"Library {path.name!r} must contain an object"
                raise ValueError(msg)
            raw = cast("dict[str, object]", raw_value)
            command_values = raw.get("commands")
            if not isinstance(command_values, list):
                msg = f"Library {path.name!r} must contain a commands list"
                raise ValueError(msg)
            defaults_value = raw.get("defaults", {})
            if not isinstance(defaults_value, dict):
                msg = f"Library {path.name!r} defaults must be an object"
                raise ValueError(msg)
            defaults = cast("dict[str, Any]", defaults_value)
            for index, item_value in enumerate(cast("list[object]", command_values)):
                if not isinstance(item_value, dict):
                    msg = f"Library {path.name!r} item {index} must be an object"
                    raise ValueError(msg)
                item = cast("dict[str, Any]", item_value)
                try:
                    commands.append(CommandTemplate.from_mapping({**defaults, **item}))
                except ValueError as error:
                    msg = f"Library {path.name!r} item {index}: {error}"
                    raise ValueError(msg) from error
        if not commands:
            raise ValueError("Bundled command library is empty")
        return cls(commands)


def _command_score(query: str, item: CommandTemplate) -> float:
    """Score exact, prefix, token, and fuzzy matches across useful fields."""
    if not query:
        return 1.0
    title = item.title.casefold()
    command = item.command.casefold()
    description = item.description.casefold()
    metadata = " ".join((*item.vendors, *item.categories, *item.tags)).casefold()
    score = 0.0
    if command.startswith(query):
        score += 180.0
    elif query in command:
        score += 120.0
    if title.startswith(query):
        score += 150.0
    elif query in title:
        score += 100.0
    if query in description:
        score += 55.0
    if query in metadata:
        score += 45.0
    query_tokens = set(_TOKEN_PATTERN.findall(query))
    haystack_tokens = set(_TOKEN_PATTERN.findall(f"{title} {command} {description} {metadata}"))
    if query_tokens:
        score += 90.0 * len(query_tokens & haystack_tokens) / len(query_tokens)
    score += 40.0 * max(
        SequenceMatcher(None, query, title).ratio(),
        SequenceMatcher(None, query, command[: max(len(query), 1) * 3]).ratio(),
    )
    return score if score >= _MIN_SEARCH_SCORE else 0.0
