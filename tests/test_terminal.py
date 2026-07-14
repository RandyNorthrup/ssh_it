"""VT terminal screen adapter tests."""

from __future__ import annotations

from ssh_it.terminal import TerminalBuffer


def test_terminal_renders_ansi_without_escape_text() -> None:
    """Colour controls affect screen but never appear as raw garbage."""
    terminal = TerminalBuffer(columns=40, rows=5)
    rendered = terminal.feed("\x1b[31mERROR\x1b[0m\r\nready$ ")
    assert "ERROR" in rendered
    assert "ready$" in rendered
    assert "\x1b" not in rendered


def test_terminal_resize_clamps_minimum_and_clear() -> None:
    """Unsafe tiny dimensions are clamped and reset removes text."""
    terminal = TerminalBuffer()
    terminal.feed("hello")
    terminal.resize(1, 1)
    assert terminal.size == (20, 5)
    terminal.clear()
    assert terminal.render() == ""
    assert terminal.transcript() == ""


def test_terminal_transcript_includes_bounded_scrollback() -> None:
    """Export text includes lines which have scrolled beyond the visible screen."""
    terminal = TerminalBuffer(columns=20, rows=5)
    terminal.feed("one\r\ntwo\r\nthree\r\nfour\r\nfive\r\nsix")
    assert terminal.render().startswith("two")
    assert terminal.transcript().splitlines() == ["one", "two", "three", "four", "five", "six"]
