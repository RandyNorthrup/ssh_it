"""Terminal transcript export tests."""

from __future__ import annotations

import os
from pathlib import Path

from ssh_it.terminal_export import (
    ExportFormat,
    ensure_export_suffix,
    format_from_dialog,
    render_export,
    write_export,
)


def test_plain_text_export_preserves_content_and_adds_final_newline() -> None:
    """Plain export remains interoperable UTF-8 terminal text."""
    assert render_export("router> show version", ExportFormat.TEXT) == "router> show version\n"
    assert render_export("", ExportFormat.TEXT) == ""


def test_html_export_escapes_terminal_controlled_markup() -> None:
    """Remote output cannot inject markup or script into exported HTML."""
    document = render_export('<script>alert("x")</script> & done', ExportFormat.HTML)
    assert "<script>" not in document
    assert "&lt;script&gt;" in document
    assert "&quot;x&quot;" in document
    assert "&amp; done" in document
    assert '<meta charset="utf-8">' in document


def test_dialog_format_suffix_and_atomic_write(tmp_path: Path) -> None:
    """Selected format controls missing suffix and final file replaces atomically."""
    selected = tmp_path / "session"
    export_format = format_from_dialog(selected, "HTML document (*.html *.htm)")
    target = ensure_export_suffix(selected, export_format)
    write_export(target, "first")
    write_export(target, "second")
    assert target.name == "session.html"
    assert target.read_text(encoding="utf-8") == "second"
    if os.name != "nt":
        assert target.stat().st_mode & 0o077 == 0


def test_explicit_suffix_overrides_plain_dialog_filter() -> None:
    """Typing an HTML suffix is honored even when the default filter remains selected."""
    path = Path("terminal.HTM")
    export_format = format_from_dialog(path, "Plain text (*.txt)")
    assert export_format is ExportFormat.HTML
    assert ensure_export_suffix(path, export_format) == path
    assert format_from_dialog(Path("terminal.txt"), "HTML document (*.html *.htm)") is (
        ExportFormat.TEXT
    )
