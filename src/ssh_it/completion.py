"""Context-ranked completion for command composer input."""

from __future__ import annotations

import re
import shlex
from collections import deque
from contextlib import suppress
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from ssh_it.models import CommandTemplate, CompletionCandidate, Risk
from ssh_it.parameters import parameter_spec

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ssh_it.library import CommandLibrary

_MAX_HISTORY: Final = 200
_MIN_HISTORY_SIMILARITY: Final = 0.45
_BARE_PLACEHOLDER: Final = re.compile(r"^\$\{([a-z][a-z0-9_]*)\}$")
_TOKEN_PLACEHOLDER: Final = re.compile(r"\$\{([a-z][a-z0-9_]*)\}")


class CompletionEngine:
    """Combine vendor library and memory-only history candidates."""

    def __init__(self, library: CommandLibrary) -> None:
        """Create empty session history for a command library."""
        self._library = library
        self._history: deque[str] = deque(maxlen=_MAX_HISTORY)
        self._parameter_history: dict[str, deque[str]] = {}

    @property
    def history(self) -> tuple[str, ...]:
        """Return newest-first session command history."""
        return tuple(reversed(self._history))

    def remember(self, command: str) -> None:
        """Record non-empty command once at newest position."""
        normalized = command.strip()
        if not normalized:
            return
        with suppress(ValueError):
            self._history.remove(normalized)
        self._history.append(normalized)
        self._remember_parameters(normalized)

    def suggest(
        self,
        text: str,
        *,
        vendor: str = "",
        limit: int = 12,
        favorite_ids: set[str] | None = None,
    ) -> tuple[CompletionCandidate, ...]:
        """Return unique highest-scoring candidates for current composer text."""
        query = text.strip()
        favorites = favorite_ids or set()
        candidates = [
            CompletionCandidate(
                text=item.command,
                title=item.title,
                description=item.description,
                source="library",
                score=_template_score(query, item.command, rank)
                + (120.0 if item.id in favorites else 0.0),
                risk=item.risk,
                command_id=item.id,
                placeholders=item.placeholders,
            )
            for rank, item in enumerate(self._library.search(query, vendor=vendor, limit=limit * 3))
        ]
        candidates.extend(self._grammar_candidates(text, vendor, favorites))
        candidates.extend(self._history_candidates(query))
        unique: dict[str, CompletionCandidate] = {}
        for candidate in candidates:
            current = unique.get(candidate.text)
            if current is None or candidate.score > current.score:
                unique[candidate.text] = candidate
        ranked = sorted(unique.values(), key=lambda item: (-item.score, item.text.casefold()))
        return tuple(ranked[:limit])

    def suggest_parameter(
        self,
        name: str,
        *,
        profile_host: str = "",
        profile_port: int = 0,
        profile_user: str = "",
        limit: int = 10,
    ) -> tuple[CompletionCandidate, ...]:
        """Rank typed values from connection, history, and schema defaults."""
        spec = parameter_spec(name)
        contextual: list[tuple[str, str, float]] = []
        lowered = name.casefold()
        if profile_host and any(
            token in lowered for token in ("host", "hostname", "gateway", "ip")
        ):
            contextual.append((profile_host, "current connection", 500.0))
        if profile_port and "port" in lowered:
            contextual.append((str(profile_port), "current connection", 500.0))
        if profile_user and any(token in lowered for token in ("user", "owner")):
            contextual.append((profile_user, "current connection", 500.0))
        for rank, value in enumerate(reversed(self._parameter_history.get(name, deque()))):
            contextual.append((value, "session history", 400.0 - rank))
        contextual.extend(
            (value, "typed default", 300.0 - rank) for rank, value in enumerate(spec.suggestions)
        )
        unique: dict[str, CompletionCandidate] = {}
        for value, source, score in contextual:
            with suppress(ValueError):
                spec.validate(value)
                unique.setdefault(
                    value,
                    CompletionCandidate(
                        text=value,
                        title=f"{name.replace('_', ' ').title()}: {value} · {source}",
                        description=f"{spec.description} {spec.format_hint}",
                        source="value",
                        score=score,
                        risk=Risk.SAFE,
                    ),
                )
        return tuple(sorted(unique.values(), key=lambda item: -item.score)[:limit])

    def match_template(self, command: str) -> tuple[CommandTemplate, dict[str, str]] | None:
        """Match rendered command to library token grammar and return typed values."""
        actual_tokens = _shell_tokens(command)
        for template in self._library.commands:
            template_tokens = _shell_tokens(template.command)
            if len(template_tokens) != len(actual_tokens):
                continue
            captured: dict[str, str] = {}
            matched = True
            for expected, actual in zip(template_tokens, actual_tokens, strict=True):
                values = _match_template_token(expected, actual)
                if values is None:
                    matched = False
                    break
                captured.update(values)
            if matched:
                return template, captured
        return None

    def _history_candidates(self, query: str) -> Iterable[CompletionCandidate]:
        """Yield ranked memory-only history matches."""
        query_folded = query.casefold()
        for recency, command in enumerate(reversed(self._history)):
            folded = command.casefold()
            if query_folded and query_folded not in folded:
                similarity = SequenceMatcher(None, query_folded, folded).ratio()
                if similarity < _MIN_HISTORY_SIMILARITY:
                    continue
            prefix = 100.0 if folded.startswith(query_folded) else 0.0
            yield CompletionCandidate(
                text=command,
                title="Recent command",
                description="Used earlier in this session; history is not saved to disk.",
                source="history",
                score=240.0 + prefix - recency,
                risk=Risk.CAUTION,
            )

    def _grammar_candidates(
        self,
        text: str,
        vendor: str,
        favorite_ids: set[str],
    ) -> Iterable[CompletionCandidate]:
        """Predict next literal keyword, flag, or placeholder from template token grammar."""
        committed, prefix = _completion_tokens(text)
        for command in self._library.search(vendor=vendor):
            template_tokens = _shell_tokens(command.command)
            if len(template_tokens) <= len(committed):
                continue
            if not _grammar_prefix_matches(committed, template_tokens):
                continue
            next_token = template_tokens[len(committed)]
            placeholder_match = _BARE_PLACEHOLDER.fullmatch(next_token)
            if placeholder_match:
                name = placeholder_match.group(1)
                for value in self.suggest_parameter(name):
                    if not prefix or value.text.casefold().startswith(prefix.casefold()):
                        yield CompletionCandidate(
                            text=value.text,
                            title=f"{name.replace('_', ' ').title()} · {command.title}",
                            description=value.description,
                            source="value",
                            score=value.score + (100.0 if command.id in favorite_ids else 0.0),
                            risk=command.risk,
                            command_id=command.id,
                        )
                continue
            if prefix and not next_token.casefold().startswith(prefix.casefold()):
                continue
            source = "flag" if next_token.startswith("-") else "keyword"
            yield CompletionCandidate(
                text=next_token,
                title=f"{next_token} · {command.title}",
                description=f"Next {source} from {command.title}. {command.description}",
                source=source,
                score=650.0 + (120.0 if command.id in favorite_ids else 0.0),
                risk=command.risk,
                command_id=command.id,
            )

    def _remember_parameters(self, command: str) -> None:
        actual_tokens = _shell_tokens(command)
        for template in self._library.commands:
            template_tokens = _shell_tokens(template.command)
            if len(template_tokens) != len(actual_tokens):
                continue
            captured: dict[str, str] = {}
            matched = True
            for expected, actual in zip(template_tokens, actual_tokens, strict=True):
                values = _match_template_token(expected, actual)
                if values is None:
                    matched = False
                    break
                captured.update(values)
            if not matched:
                continue
            for name, value in captured.items():
                history = self._parameter_history.setdefault(name, deque(maxlen=30))
                with suppress(ValueError):
                    history.remove(value)
                history.append(value)


def _template_score(query: str, command: str, rank: int) -> float:
    """Prefer prefix continuation while preserving library search rank."""
    if not query:
        return 100.0 - rank
    query_folded = query.casefold()
    command_folded = command.casefold()
    prefix = 180.0 if command_folded.startswith(query_folded) else 0.0
    return 200.0 + prefix - rank


def _shell_tokens(text: str) -> list[str]:
    """Tokenize complete or partial shell text without raising on unfinished quotes."""
    try:
        return shlex.split(text, posix=True)
    except ValueError:
        return text.split()


def _completion_tokens(text: str) -> tuple[list[str], str]:
    tokens = _shell_tokens(text)
    if not tokens or text[-1:].isspace():
        return tokens, ""
    return tokens[:-1], tokens[-1]


def _grammar_prefix_matches(committed: list[str], template: list[str]) -> bool:
    for actual, expected in zip(committed, template, strict=False):
        if (
            _TOKEN_PLACEHOLDER.search(expected)
            and _match_template_token(expected, actual) is not None
        ):
            continue
        if actual.casefold() != expected.casefold():
            return False
    return True


def _match_template_token(expected: str, actual: str) -> dict[str, str] | None:
    """Capture placeholders embedded anywhere within one shell token."""
    matches = tuple(_TOKEN_PLACEHOLDER.finditer(expected))
    if not matches:
        return {} if expected == actual else None
    parts = ["^"]
    position = 0
    for match in matches:
        parts.append(re.escape(expected[position : match.start()]))
        parts.append(f"(?P<{match.group(1)}>.+?)")
        position = match.end()
    parts.append(re.escape(expected[position:]))
    parts.append("$")
    result = re.fullmatch("".join(parts), actual)
    return result.groupdict() if result is not None else None
