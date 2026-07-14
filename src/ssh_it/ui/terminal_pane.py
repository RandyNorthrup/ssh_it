"""Accessible terminal screen, command composer, completion, and history."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QKeyEvent, QResizeEvent, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ssh_it.models import CompletionCandidate
from ssh_it.ui.common import describe_widget

_PLACEHOLDER = re.compile(r"\$\{([a-z][a-z0-9_]*)\}")


class CommandLineEdit(QLineEdit):
    """Line edit with terminal-specific keyboard signals."""

    completion_requested = Signal()
    history_requested = Signal(int)
    interrupt_requested = Signal()
    placeholder_navigation_requested = Signal(bool)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Handle completion, history, execution, and empty-line interrupt shortcuts."""
        modifiers = event.modifiers()
        if event.key() == Qt.Key.Key_Space and modifiers & Qt.KeyboardModifier.ControlModifier:
            self.completion_requested.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Up and modifiers == Qt.KeyboardModifier.NoModifier:
            self.history_requested.emit(-1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down and modifiers == Qt.KeyboardModifier.NoModifier:
            self.history_requested.emit(1)
            event.accept()
            return
        if (
            event.key() == Qt.Key.Key_C
            and modifiers & Qt.KeyboardModifier.ControlModifier
            and not self.hasSelectedText()
            and not self.text()
        ):
            self.interrupt_requested.emit()
            event.accept()
            return
        if event.key() in {Qt.Key.Key_Tab, Qt.Key.Key_Backtab} and "${" in self.text():
            forward = not (
                event.key() == Qt.Key.Key_Backtab or modifiers & Qt.KeyboardModifier.ShiftModifier
            )
            self.placeholder_navigation_requested.emit(forward)
            event.accept()
            return
        super().keyPressEvent(event)


class TerminalPane(QWidget):
    """Render VT output and collect locally completed command lines."""

    command_submitted = Signal(str)
    interrupt_requested = Signal()
    completion_requested = Signal(str)
    parameter_context_requested = Signal(str)
    terminal_resized = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create terminal workspace."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.terminal_view = QPlainTextEdit()
        self.terminal_view.setReadOnly(True)
        self.terminal_view.setUndoRedoEnabled(False)
        self.terminal_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.terminal_view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.terminal_view.setPlaceholderText("Connect to an SSH server to begin.")
        describe_widget(
            self.terminal_view,
            "SSH terminal screen",
            "Read-only rendered remote terminal. Use command composer below to send commands.",
        )
        splitter.addWidget(self.terminal_view)

        composer = QWidget()
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel("Command composer")
        composer_layout.addWidget(label)
        self.command_edit = CommandLineEdit()
        self.command_edit.setClearButtonEnabled(True)
        self.command_edit.setPlaceholderText(
            "Type a command; Ctrl+Space suggestions, Up/Down history, Ctrl+Enter run"
        )
        describe_widget(
            self.command_edit,
            "Command composer",
            "Prepare remote command with local vendor-aware completion before sending.",
        )
        label.setBuddy(self.command_edit)
        self.command_edit.textChanged.connect(self._text_changed)
        self.command_edit.returnPressed.connect(self.submit)
        self.command_edit.completion_requested.connect(
            lambda: self.completion_requested.emit(self.command_edit.text())
        )
        self.command_edit.interrupt_requested.connect(self.interrupt_requested)
        self.command_edit.history_requested.connect(self._move_history)
        self.command_edit.placeholder_navigation_requested.connect(self._navigate_placeholder)

        row = QHBoxLayout()
        row.addWidget(self.command_edit, 1)
        self.complete_button = QPushButton("Suggest")
        describe_widget(
            self.complete_button,
            "Show command suggestions",
            "Rank library and session-history completions for current text.",
        )
        self.complete_button.clicked.connect(
            lambda: self.completion_requested.emit(self.command_edit.text())
        )
        row.addWidget(self.complete_button)
        self.run_button = QPushButton("Run")
        describe_widget(
            self.run_button, "Run command", "Send command and newline to remote SSH PTY."
        )
        self.run_button.clicked.connect(self.submit)
        row.addWidget(self.run_button)
        self.interrupt_button = QPushButton("Interrupt")
        describe_widget(
            self.interrupt_button,
            "Interrupt remote command",
            "Send Ctrl+C interrupt byte to remote terminal.",
        )
        self.interrupt_button.clicked.connect(self.interrupt_requested)
        row.addWidget(self.interrupt_button)
        composer_layout.addLayout(row)

        self.parameter_hint = QLabel()
        self.parameter_hint.setWordWrap(True)
        self.parameter_hint.setAccessibleName("Active command parameter guidance")
        self.parameter_hint.hide()
        composer_layout.addWidget(self.parameter_hint)

        self.suggestions = QListWidget()
        self.suggestions.setMaximumHeight(170)
        self.suggestions.setAlternatingRowColors(True)
        self.suggestions.hide()
        describe_widget(
            self.suggestions,
            "Command completion suggestions",
            "Ranked commands. Press Enter or double-click to place selected command in composer.",
        )
        self.suggestions.itemActivated.connect(self._activate_suggestion)
        self.suggestions.itemDoubleClicked.connect(self._activate_suggestion)
        composer_layout.addWidget(self.suggestions)
        splitter.addWidget(composer)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        self._history: tuple[str, ...] = ()
        self._history_index = -1
        self._history_draft = ""
        self._moving_history = False

    def set_screen_text(self, text: str) -> None:
        """Replace rendered terminal screen and keep cursor at end."""
        self.terminal_view.setPlainText(text)
        cursor = self.terminal_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal_view.setTextCursor(cursor)

    def set_suggestions(self, candidates: tuple[CompletionCandidate, ...]) -> None:
        """Populate accessible completion result list."""
        self.suggestions.clear()
        for candidate in candidates:
            risk = candidate.risk.value.upper()
            source = candidate.source.replace("_", " ").title()
            item = QListWidgetItem(f"[{risk} · {source}] {candidate.title} — {candidate.text}")
            item.setToolTip(candidate.description)
            item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.suggestions.addItem(item)
        self.suggestions.setVisible(bool(candidates))
        if candidates:
            self.suggestions.setCurrentRow(0)

    def set_history(self, history: tuple[str, ...]) -> None:
        """Set newest-first history and reset navigation cursor."""
        self._history = history
        self._history_index = -1

    def submit(self) -> None:
        """Emit trimmed composer command when non-empty."""
        command = self.command_edit.text().strip()
        if not command:
            return
        self.command_submitted.emit(command)

    def take_command(self) -> str:
        """Return composer command and reset input state."""
        command = self.command_edit.text().strip()
        self.command_edit.clear()
        self.suggestions.hide()
        self._history_index = -1
        return command

    def insert_command(self, command: str, *, focus: bool = True) -> None:
        """Replace composer content without executing."""
        self.command_edit.setText(command)
        self.command_edit.setCursorPosition(len(command))
        self._navigate_placeholder(True)
        if focus:
            self.command_edit.setFocus()

    def show_parameter_context(
        self,
        name: str,
        description: str,
        format_hint: str,
        candidates: tuple[CompletionCandidate, ...],
    ) -> None:
        """Show type-aware guidance and contextual value dropdown."""
        self.parameter_hint.setText(
            f"Parameter: {name.replace('_', ' ').title()} · {format_hint}. {description} "
            "Choose value or type it; Tab jumps to next required parameter."
        )
        self.parameter_hint.show()
        self.set_suggestions(candidates)

    def set_connected(self, connected: bool) -> None:
        """Enable actions needing remote PTY while retaining offline composition."""
        self.run_button.setEnabled(connected)
        self.interrupt_button.setEnabled(connected)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Debounce terminal cell-size reporting."""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._emit_terminal_size)

    def _emit_terminal_size(self) -> None:
        metrics = self.terminal_view.fontMetrics()
        char_width = max(metrics.horizontalAdvance("M"), 1)
        char_height = max(metrics.lineSpacing(), 1)
        viewport = self.terminal_view.viewport().size()
        columns = max(viewport.width() // char_width, 20)
        rows = max(viewport.height() // char_height, 5)
        self.terminal_resized.emit(columns, rows)

    def _text_changed(self, text: str) -> None:
        if not self._moving_history:
            self._history_index = -1
        if text.strip():
            self.completion_requested.emit(text)
        else:
            self.suggestions.hide()
            self.parameter_hint.hide()

    def _activate_suggestion(self, item: QListWidgetItem) -> None:
        candidate = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(candidate, CompletionCandidate):
            if candidate.source in {"flag", "keyword", "value"}:
                had_placeholder = bool(_PLACEHOLDER.fullmatch(self.command_edit.selectedText()))
                if not had_placeholder:
                    self._select_current_token()
                self.command_edit.insert(candidate.text)
                if had_placeholder:
                    self._navigate_placeholder(True)
                else:
                    cursor = self.command_edit.cursorPosition()
                    text = self.command_edit.text()
                    if cursor == len(text) or not text[cursor].isspace():
                        self.command_edit.insert(" ")
                    self.completion_requested.emit(self.command_edit.text())
            else:
                self.insert_command(candidate.text)
            if not self.parameter_hint.isVisible():
                self.suggestions.hide()

    def _move_history(self, direction: int) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._history_draft = self.command_edit.text()
        self._history_index = max(-1, min(self._history_index - direction, len(self._history) - 1))
        if self._history_index == -1:
            value = self._history_draft
        else:
            value = self._history[self._history_index]
        self._moving_history = True
        try:
            self.command_edit.setText(value)
        finally:
            self._moving_history = False

    def _navigate_placeholder(self, forward: bool) -> None:
        text = self.command_edit.text()
        matches = list(_PLACEHOLDER.finditer(text))
        if not matches:
            self.parameter_hint.hide()
            return
        cursor = self.command_edit.cursorPosition()
        selected_start = self.command_edit.selectionStart()
        selected_text = self.command_edit.selectedText()
        if selected_start >= 0 and _PLACEHOLDER.fullmatch(selected_text):
            cursor = selected_start + (len(selected_text) if forward else 0)
        if forward:
            match = next((item for item in matches if item.start() >= cursor), matches[0])
        else:
            match = next((item for item in reversed(matches) if item.end() <= cursor), matches[-1])
        self.command_edit.setSelection(match.start(), match.end() - match.start())
        self.parameter_context_requested.emit(match.group(1))

    def _select_current_token(self) -> None:
        text = self.command_edit.text()
        cursor = self.command_edit.cursorPosition()
        start = cursor
        while start > 0 and not text[start - 1].isspace():
            start -= 1
        end = cursor
        while end < len(text) and not text[end].isspace():
            end += 1
        self.command_edit.setSelection(start, end - start)
