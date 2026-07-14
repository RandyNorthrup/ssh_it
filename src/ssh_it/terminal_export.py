"""Safe, atomic terminal transcript export helpers."""

from __future__ import annotations

import html
import os
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Final

_HTML_FILTER: Final = "HTML document (*.html *.htm)"
_TEXT_FILTER: Final = "Plain text (*.txt)"
EXPORT_FILTERS: Final = f"{_TEXT_FILTER};;{_HTML_FILTER}"


class ExportFormat(StrEnum):
    """Supported terminal transcript formats."""

    TEXT = "text"
    HTML = "html"


def format_from_dialog(path: Path, selected_filter: str) -> ExportFormat:
    """Infer the requested format from the chosen filter or explicit suffix."""
    suffix = path.suffix.casefold()
    if suffix in {".html", ".htm"}:
        return ExportFormat.HTML
    if suffix == ".txt":
        return ExportFormat.TEXT
    if selected_filter == _HTML_FILTER:
        return ExportFormat.HTML
    return ExportFormat.TEXT


def ensure_export_suffix(path: Path, export_format: ExportFormat) -> Path:
    """Add a conventional suffix only when the user supplied none."""
    if path.suffix:
        return path
    suffix = ".html" if export_format is ExportFormat.HTML else ".txt"
    return path.with_suffix(suffix)


def render_export(text: str, export_format: ExportFormat) -> str:
    """Render terminal text without allowing terminal content to become HTML markup."""
    if export_format is ExportFormat.TEXT:
        return f"{text.rstrip()}\n" if text else ""
    escaped = html.escape(text.rstrip(), quote=True)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>SSH It terminal transcript</title>\n"
        "<style>\n"
        ":root { color-scheme: light dark; }\n"
        "body { margin: 0; padding: 1rem; background: #111827; color: #f3f4f6; }\n"
        "pre { margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; "
        "font: 0.95rem/1.45 ui-monospace, SFMono-Regular, Consolas, monospace; }\n"
        "</style>\n"
        "</head>\n"
        f"<body><main><pre>{escaped}</pre></main></body>\n"
        "</html>\n"
    )


def write_export(path: Path, document: str) -> None:
    """Atomically write UTF-8 export with owner-only permissions where supported."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
