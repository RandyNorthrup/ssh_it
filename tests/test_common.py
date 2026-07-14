"""Shared dialog and action helper tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

from ssh_it.library import CommandLibrary
from ssh_it.ui.common import (
    DestructiveCommandDialog,
    PlaceholderDialog,
    ask_yes_no,
    connect_action,
    describe_widget,
)

if TYPE_CHECKING:
    import pytest
    from pytestqt.qtbot import QtBot


def test_describe_widget_and_action_adapter(qtbot: QtBot) -> None:
    """Metadata helper sets all accessible text and action adapter ignores checked state."""
    widget = QWidget()
    qtbot.addWidget(widget)
    describe_widget(widget, "Useful name", "Useful description")
    assert widget.accessibleName() == "Useful name"
    assert widget.accessibleDescription() == "Useful description"
    assert widget.toolTip() == "Useful description"
    calls: list[str] = []
    callback = connect_action(lambda: calls.append("called"))
    callback(True)
    assert calls == ["called"]


def test_placeholder_dialog_validates_and_renders(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Placeholder dialog blocks invalid typed values and accepts a complete command."""
    template = CommandLibrary.load_bundled().get("ssh.connect.basic")
    dialog = PlaceholderDialog(template)
    qtbot.addWidget(dialog)
    port = dialog.findChild(QLineEdit, "placeholder_port")
    user = dialog.findChild(QLineEdit, "placeholder_user")
    host = dialog.findChild(QLineEdit, "placeholder_host")
    assert port is not None
    assert user is not None
    assert host is not None
    warnings: list[str] = []

    def warning(
        _parent: QWidget,
        _title: str,
        text: str,
    ) -> QMessageBox.StandardButton:
        warnings.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", warning)
    port.setText("70000")
    user.setText("operator")
    host.setText("router.example.test")
    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
    ok_button.click()
    assert warnings
    assert dialog.result() == QDialog.DialogCode.Rejected

    port.setText("2222")
    ok_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.rendered_command() == "ssh -p 2222 operator@router.example.test"


def test_destructive_dialog_requires_exact_run(qtbot: QtBot) -> None:
    """Destructive confirmation stays disabled until exact uppercase token is entered."""
    dialog = DestructiveCommandDialog("reload")
    qtbot.addWidget(dialog)
    confirmation = dialog.findChild(QLineEdit)
    assert confirmation is not None
    run_button = next(
        button for button in dialog.findChildren(QPushButton) if button.text() == "Run command"
    )
    assert not run_button.isEnabled()
    confirmation.setText("run")
    assert not run_button.isEnabled()
    confirmation.setText("RUN")
    assert run_button.isEnabled()
    run_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_ask_yes_no_sets_optional_detail_and_returns_choice(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Question helper maps modal result to bool for both detailed and simple prompts."""
    parent = QWidget()
    qtbot.addWidget(parent)

    def answer_yes(_box: QMessageBox) -> QMessageBox.StandardButton:
        return QMessageBox.StandardButton.Yes

    def answer_no(_box: QMessageBox) -> QMessageBox.StandardButton:
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", answer_yes)
    assert ask_yes_no(parent, "Title", "Question", informative_text="More context")
    monkeypatch.setattr(QMessageBox, "exec", answer_no)
    assert not ask_yes_no(parent, "Title", "Question")
