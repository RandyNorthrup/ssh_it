"""Small VT screen adapter for remote administration shells."""

from __future__ import annotations

from typing import Final

import pyte

_MIN_COLUMNS: Final = 20
_MIN_ROWS: Final = 5
_HISTORY_LINES: Final = 10_000


class TerminalBuffer:
    """Convert ANSI/VT output into bounded plain-text screen state."""

    def __init__(self, columns: int = 120, rows: int = 40) -> None:
        """Create screen and parser."""
        self._columns = max(columns, _MIN_COLUMNS)
        self._rows = max(rows, _MIN_ROWS)
        self._screen = pyte.HistoryScreen(
            self._columns,
            self._rows,
            history=_HISTORY_LINES,
        )
        self._stream = pyte.Stream(self._screen)

    @property
    def size(self) -> tuple[int, int]:
        """Return columns and rows."""
        return self._columns, self._rows

    def feed(self, data: str) -> str:
        """Feed remote text and return current rendered screen."""
        self._stream.feed(data)
        return self.render()

    def render(self) -> str:
        """Return screen with trailing blank lines removed."""
        return "\n".join(self._screen.display).rstrip()

    def transcript(self) -> str:
        """Return bounded scrollback plus the current screen as safe plain text."""
        history_lines = [
            "".join(
                line[index].data if index in line else " " for index in range(self._columns)
            ).rstrip()
            for line in self._screen.history.top
        ]
        screen_lines = [line.rstrip() for line in self._screen.display]
        return "\n".join((*history_lines, *screen_lines)).rstrip()

    def resize(self, columns: int, rows: int) -> None:
        """Resize terminal emulator while preserving visible content."""
        columns = max(columns, _MIN_COLUMNS)
        rows = max(rows, _MIN_ROWS)
        if (columns, rows) == (self._columns, self._rows):
            return
        self._columns = columns
        self._rows = rows
        self._screen.resize(lines=rows, columns=columns)

    def clear(self) -> None:
        """Reset screen and parser state."""
        self._screen.reset()
