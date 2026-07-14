"""Shared accessible dialogs and widget helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ssh_it.models import CommandTemplate


def describe_widget(widget: QWidget, name: str, description: str) -> None:
    """Set matching tooltip and assistive-technology metadata."""
    widget.setAccessibleName(name)
    widget.setAccessibleDescription(description)
    widget.setToolTip(description)


class PlaceholderDialog(QDialog):
    """Collect labelled values for command template placeholders."""

    def __init__(self, template: CommandTemplate, parent: QWidget | None = None) -> None:
        """Build one line edit per placeholder."""
        super().__init__(parent)
        self.setWindowTitle(f"Fill command: {template.title}")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._template = template
        self._fields: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)
        explanation = QLabel(template.description)
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        command_preview = QPlainTextEdit(template.command)
        command_preview.setReadOnly(True)
        command_preview.setMaximumHeight(90)
        describe_widget(command_preview, "Command template", "Command with placeholders to fill.")
        layout.addWidget(command_preview)
        form = QFormLayout()
        for name in template.placeholders:
            field = QLineEdit()
            field.setClearButtonEnabled(True)
            field.setObjectName(f"placeholder_{name}")
            describe_widget(field, name.replace("_", " ").title(), f"Value for ${{{name}}}.")
            label = QLabel(name.replace("_", " ").title())
            label.setBuddy(field)
            form.addRow(label, field)
            self._fields[name] = field
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._fields:
            next(iter(self._fields.values())).setFocus()

    def rendered_command(self) -> str:
        """Return validated rendered command after acceptance."""
        return self._template.render({name: field.text() for name, field in self._fields.items()})

    def _validate_and_accept(self) -> None:
        try:
            self.rendered_command()
        except ValueError as error:
            QMessageBox.warning(self, "Missing or invalid value", str(error))
            return
        self.accept()


class DestructiveCommandDialog(QDialog):
    """Require explicit text confirmation before destructive library execution."""

    def __init__(self, command: str, parent: QWidget | None = None) -> None:
        """Show exact command and require typing RUN."""
        super().__init__(parent)
        self.setWindowTitle("Confirm destructive command")
        self.setModal(True)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        warning = QLabel(
            "This library item can change persistent state or disrupt service. "
            "Review exact command, verify target device, then type RUN to enable execution."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        preview = QPlainTextEdit(command)
        preview.setReadOnly(True)
        preview.setMaximumHeight(110)
        describe_widget(preview, "Destructive command", "Exact command proposed for execution.")
        layout.addWidget(preview)
        self._confirmation = QLineEdit()
        self._confirmation.setPlaceholderText("Type RUN")
        describe_widget(
            self._confirmation,
            "Confirmation text",
            "Type uppercase RUN to enable destructive command execution.",
        )
        layout.addWidget(self._confirmation)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText("Run command")
        self._ok_button.setEnabled(False)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._confirmation.textChanged.connect(self._confirmation_changed)
        layout.addWidget(self._buttons)

    def _confirmation_changed(self, text: str) -> None:
        self._ok_button.setEnabled(text == "RUN")


def ask_yes_no(
    parent: QWidget,
    title: str,
    text: str,
    *,
    informative_text: str = "",
) -> bool:
    """Show accessible yes/no question with safe default."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text, parent=parent)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    box.setEscapeButton(QMessageBox.StandardButton.No)
    if informative_text:
        box.setInformativeText(informative_text)
    return box.exec() == QMessageBox.StandardButton.Yes


def connect_action(action: Callable[[], None]) -> Callable[[bool], None]:
    """Adapt QAction/QPushButton checked signal to zero-argument callback."""

    def callback(_checked: bool = False) -> None:
        action()

    return callback
