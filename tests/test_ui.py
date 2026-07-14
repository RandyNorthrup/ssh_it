"""Accessible, responsive Qt widget smoke tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QEvent, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QWidget,
)

import ssh_it.ui.main_window as main_window_module
from ssh_it.credentials import CredentialLibrary, PasswordKind
from ssh_it.library import CommandLibrary
from ssh_it.models import AuthMethod, CompletionCandidate, Risk
from ssh_it.settings import SettingsStore
from ssh_it.ui.connection import ConnectionPanel
from ssh_it.ui.credential_panel import CredentialLibraryPanel
from ssh_it.ui.library_panel import LibraryPanel
from ssh_it.ui.main_window import MainWindow
from ssh_it.ui.terminal_pane import TerminalPane

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytestqt.qtbot import QtBot

    from ssh_it.secrets import CredentialVault
    from ssh_it.ssh.session import SSHSessionController


class FakeController(QWidget):
    """Signal-compatible controller avoiding network thread in window smoke test."""

    state_changed = Signal(str)
    connected = Signal()
    disconnected = Signal(str)
    output_received = Signal(str)
    error_occurred = Signal(str, str)
    unknown_host_key = Signal(str, int, str, str)
    transfer_progress = Signal(str, int, int)
    transfer_finished = Signal(str, bool, str)
    tunnel_started = Signal(str, int)
    tunnel_stopped = Signal(str)

    def __init__(self) -> None:
        """Create fake with captured calls."""
        super().__init__()
        self.connect_calls: list[tuple[object, object, object]] = []
        self.sent: list[str] = []
        self.resizes: list[tuple[int, int]] = []
        self.host_key_answers: list[bool] = []
        self.tunnels: list[object] = []
        self.shutdown_called = False

    def disconnect_from_host(self) -> None:
        """No-op fake."""

    def interrupt(self) -> None:
        """No-op fake."""

    def transfer(self, *_args: object) -> None:
        """No-op fake."""

    def stop_tunnel(self, _tunnel_id: str) -> None:
        """No-op fake."""

    def start_tunnel(self, _spec: object) -> None:
        """Capture tunnel request."""
        self.tunnels.append(_spec)

    def connect_to(
        self,
        profile: object,
        *,
        password: object = None,
        passphrase: object = None,
    ) -> None:
        """Capture connection request."""
        self.connect_calls.append((profile, password, passphrase))

    def send(self, _text: str) -> None:
        """Capture terminal text."""
        self.sent.append(_text)

    def resize_terminal(self, _columns: int, _rows: int) -> None:
        """Capture terminal dimensions."""
        self.resizes.append((_columns, _rows))

    def answer_host_key(self, *, accept: bool) -> None:
        """Capture host-key decision."""
        self.host_key_answers.append(accept)

    def shutdown(self) -> None:
        """Capture shutdown."""
        self.shutdown_called = True


class UnavailableVault:
    """Fast vault stand-in for UI validation paths which should not persist secrets."""

    def is_available(self) -> bool:
        """Report no secure backend."""
        return False


def test_connection_panel_auth_and_accessibility(qtbot: QtBot) -> None:
    """Auth selection changes fields and important controls expose assistive names."""
    panel = ConnectionPanel(CommandLibrary.load_bundled().vendors)
    qtbot.addWidget(panel)
    assert panel.host_edit.accessibleName() == "SSH host"
    assert panel.profile_combo.accessibleDescription()
    panel.auth_combo.setCurrentIndex(panel.auth_combo.findData(AuthMethod.PASSWORD.value))
    assert panel.secret_edit.isEnabled()
    assert not panel.key_edit.isEnabled()
    panel.auth_combo.setCurrentIndex(panel.auth_combo.findData(AuthMethod.PRIVATE_KEY.value))
    assert panel.secret_edit.isEnabled()
    assert panel.key_edit.isEnabled()


def test_library_panel_search_and_favorite(qtbot: QtBot, tmp_path: Path) -> None:
    """Library UI filters vendor results and persists command favorite."""
    path = tmp_path / "ui.ini"
    store = SettingsStore(QSettings(str(path), QSettings.Format.IniFormat))
    panel = LibraryPanel(CommandLibrary.load_bundled(), store)
    qtbot.addWidget(panel)
    panel.set_vendor("UniFi")
    panel.search_edit.setText("inform")
    assert panel.table.rowCount() >= 1
    assert panel.selected_template() is not None
    panel.favorite_button.setChecked(True)
    assert panel.selected_template().id in store.favorite_commands()  # type: ignore[union-attr]


def test_library_panel_actions_and_filters_fit_narrow_dock(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Two-column responsive grids keep every control reachable at minimum dock width."""
    store = SettingsStore(
        QSettings(str(tmp_path / "narrow-library.ini"), QSettings.Format.IniFormat)
    )
    panel = LibraryPanel(CommandLibrary.load_bundled(), store)
    qtbot.addWidget(panel)
    panel.resize(390, 620)
    panel.show()
    qtbot.wait(1)
    assert panel.minimumSizeHint().width() <= 390
    for widget in (panel.risk_combo, panel.favorites_only, panel.insert_button, panel.run_button):
        right_edge = widget.mapTo(panel, widget.rect().topRight()).x()
        assert 0 <= right_edge < panel.width()


def test_credential_panel_filters_masks_and_emits_explicit_fill(qtbot: QtBot) -> None:
    """Factory reference UI filters products and emits only after a fill button click."""
    panel = CredentialLibraryPanel(CredentialLibrary.load_bundled())
    qtbot.addWidget(panel)
    panel.vendor_combo.setCurrentIndex(panel.vendor_combo.findData("Cisco"))
    panel.search_edit.setText("Catalyst 1200")
    assert panel.table.rowCount() == 1
    selected = panel.selected_entry()
    assert selected is not None
    assert selected.id == "cisco.catalyst1200-1300"
    assert panel.password_edit.echoMode() is QLineEdit.EchoMode.Password
    fill_requests: list[tuple[object, bool]] = []

    def capture_fill(value: object, include_password: bool) -> None:
        fill_requests.append((value, include_password))

    panel.fill_requested.connect(capture_fill)
    panel.fill_login_button.click()
    assert fill_requests == [(selected, True)]

    panel.vendor_combo.setCurrentIndex(panel.vendor_combo.findData("MikroTik"))
    panel.search_edit.setText("printed")
    assert panel.selected_entry() is not None
    assert panel.selected_entry().password_kind is PasswordKind.DEVICE_SPECIFIC  # type: ignore[union-attr]
    assert not panel.fill_login_button.isEnabled()


def test_main_window_smoke_and_interactive_accessible_names(qtbot: QtBot, tmp_path: Path) -> None:
    """Full window builds offscreen and textless interactive controls have metadata."""
    path = tmp_path / "main.ini"
    store = SettingsStore(QSettings(str(path), QSettings.Format.IniFormat))
    controller = cast("SSHSessionController", FakeController())
    window = MainWindow(CommandLibrary.load_bundled(), settings=store, controller=controller)
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle() == "SSH It"
    assert window.tabs.count() == 3
    for line_edit in window.findChildren(QLineEdit):
        assert line_edit.accessibleName() or line_edit.text()
    for button in window.findChildren(QPushButton):
        assert button.accessibleName() or button.text()


def test_terminal_snippet_selects_and_jumps_parameters(qtbot: QtBot) -> None:
    """Template insertion selects first required input and Tab moves to next one."""
    pane = TerminalPane()
    qtbot.addWidget(pane)
    pane.insert_command("ssh -p ${port} ${user}@${host}")
    assert pane.command_edit.selectedText() == "${port}"
    pane.command_edit.placeholder_navigation_requested.emit(True)
    assert pane.command_edit.selectedText() == "${user}"


def test_main_window_quick_connect_terminal_and_disconnect(qtbot: QtBot, tmp_path: Path) -> None:
    """Quick Connect drives controller; connection enables command send and recents."""
    settings = SettingsStore(QSettings(str(tmp_path / "flow.ini"), QSettings.Format.IniFormat))
    fake = FakeController()
    window = MainWindow(
        CommandLibrary.load_bundled(),
        settings=settings,
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    window.connection_panel.host_edit.setText("router.example.com")
    window.connection_panel.user_edit.setText("admin")
    window.connection_panel.connect_button.click()
    assert len(fake.connect_calls) == 1
    fake.connected.emit()
    assert window.terminal_pane.run_button.isEnabled()
    assert settings.recents()[0].host == "router.example.com"
    fake.output_received.emit("ready$ ")
    assert "ready$" in window.terminal_pane.terminal_view.toPlainText()
    window.terminal_pane.insert_command("show version")
    window.terminal_pane.run_button.click()
    assert fake.sent[-1] == "show version\n"
    fake.disconnected.emit("test complete")
    assert not window.terminal_pane.run_button.isEnabled()
    window.close()
    assert fake.shutdown_called


def test_new_connection_clears_prior_target_transcript(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting another connection prevents output from different targets mixing in one export."""
    fake = FakeController()
    window = MainWindow(
        CommandLibrary.load_bundled(),
        settings=SettingsStore(
            QSettings(str(tmp_path / "isolation.ini"), QSettings.Format.IniFormat)
        ),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    fake.output_received.emit("old-router-secret")
    window.connection_panel.host_edit.setText("new-router.example.test")
    window.connection_panel.connect_button.click()
    assert window.terminal_pane.terminal_view.toPlainText() == ""
    fake.output_received.emit("new-router-output")

    def choose_export(*_args: object) -> tuple[str, str]:
        return str(tmp_path / "isolated.txt"), "Plain text (*.txt)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_export)
    actions = {action.text(): action for action in window.findChildren(QAction)}
    actions["Export terminal transcript…"].trigger()
    transcript = (tmp_path / "isolated.txt").read_text(encoding="utf-8")
    assert "new-router-output" in transcript
    assert "old-router-secret" not in transcript


def test_main_window_exports_terminal_as_safe_html(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File action exports scrollback, adds suffix, and escapes remote-controlled HTML."""
    fake = FakeController()
    window = MainWindow(
        CommandLibrary.load_bundled(),
        settings=SettingsStore(QSettings(str(tmp_path / "export.ini"), QSettings.Format.IniFormat)),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    fake.output_received.emit('router> <script>alert("bad")</script>')

    def choose_export(*_args: object) -> tuple[str, str]:
        return str(tmp_path / "terminal-session"), "HTML document (*.html *.htm)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_export)
    actions = {action.text(): action for action in window.findChildren(QAction)}
    actions["Export terminal transcript…"].trigger()
    document = (tmp_path / "terminal-session.html").read_text(encoding="utf-8")
    assert "router&gt;" in document
    assert "<script>" not in document
    assert "exported" in window.statusBar().currentMessage()


def test_terminal_keyword_and_value_suggestion_insertion(qtbot: QtBot) -> None:
    """IntelliSense token replaces current prefix and snippet value replaces selected field."""
    pane = TerminalPane()
    qtbot.addWidget(pane)
    pane.insert_command("show inte")
    keyword = CompletionCandidate(
        "interfaces",
        "interfaces keyword",
        "Next keyword",
        "keyword",
        700,
    )
    pane.set_suggestions((keyword,))
    pane.suggestions.item(0).setSelected(True)
    pane.suggestions.itemActivated.emit(pane.suggestions.item(0))
    assert pane.command_edit.text() == "show interfaces "

    pane.insert_command("ssh -p ${port} host")
    value = CompletionCandidate("2222", "Port 2222", "Prior port", "value", 500, Risk.SAFE)
    pane.set_suggestions((value,))
    pane.suggestions.itemActivated.emit(pane.suggestions.item(0))
    assert pane.command_edit.text() == "ssh -p 2222 host"


def test_default_credential_fill_never_auto_connects_and_passes_static_password(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Explicit factory fill prepares Quick Connect but connection remains a separate action."""
    fake = FakeController()
    window = MainWindow(
        CommandLibrary.load_bundled(),
        settings=SettingsStore(
            QSettings(str(tmp_path / "factory.ini"), QSettings.Format.IniFormat)
        ),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    panel = window.credential_panel
    panel.vendor_combo.setCurrentIndex(panel.vendor_combo.findData("Cisco"))
    panel.search_edit.setText("Catalyst 1200")
    panel.fill_login_button.click()
    assert fake.connect_calls == []
    assert window.connection_panel.user_edit.text() == "cisco"
    assert window.connection_panel.vendor_combo.currentData() == "Cisco IOS / IOS XE"
    window.connection_panel.host_edit.setText("switch.example.test")
    window.connection_panel.connect_button.click()
    assert len(fake.connect_calls) == 1
    assert fake.connect_calls[0][1] == "cisco"


def test_explicit_factory_blank_password_is_not_rejected(qtbot: QtBot, tmp_path: Path) -> None:
    """A selected documented blank differs from a missing password and reaches transport."""
    fake = FakeController()
    window = MainWindow(
        CommandLibrary.load_bundled(),
        settings=SettingsStore(QSettings(str(tmp_path / "blank.ini"), QSettings.Format.IniFormat)),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    panel = window.credential_panel
    panel.vendor_combo.setCurrentIndex(panel.vendor_combo.findData("Fortinet"))
    panel.search_edit.setText("factory reset")
    assert panel.selected_entry() is not None
    panel.fill_login_button.click()
    window.connection_panel.host_edit.setText("fortigate.example.test")
    window.connection_panel.connect_button.click()
    assert len(fake.connect_calls) == 1
    assert fake.connect_calls[0][1] == ""


def test_terminal_keyboard_history_submit_and_command_completion(qtbot: QtBot) -> None:
    """Composer keyboard paths expose completion, history, interrupt, submit, and snippets."""
    pane = TerminalPane()
    qtbot.addWidget(pane)
    requested: list[str] = []
    submitted: list[str] = []
    interrupted: list[bool] = []
    pane.completion_requested.connect(requested.append)
    pane.command_submitted.connect(submitted.append)
    pane.interrupt_requested.connect(lambda: interrupted.append(True))

    pane.command_edit.setText("show version")
    QTest.keyClick(
        pane.command_edit,
        Qt.Key.Key_Space,
        modifier=Qt.KeyboardModifier.ControlModifier,
    )
    assert requested[-1] == "show version"
    pane.submit()
    assert submitted == ["show version"]
    assert pane.take_command() == "show version"
    pane.submit()
    assert submitted == ["show version"]

    pane.set_history(("new command", "old command"))
    pane.command_edit.setText("draft")
    QTest.keyClick(pane.command_edit, Qt.Key.Key_Up)
    assert pane.command_edit.text() == "new command"
    QTest.keyClick(pane.command_edit, Qt.Key.Key_Up)
    assert pane.command_edit.text() == "old command"
    QTest.keyClick(pane.command_edit, Qt.Key.Key_Down)
    assert pane.command_edit.text() == "new command"

    pane.command_edit.clear()
    QTest.keyClick(
        pane.command_edit,
        Qt.Key.Key_C,
        modifier=Qt.KeyboardModifier.ControlModifier,
    )
    assert interrupted == [True]
    pane.insert_command("ssh ${user}@${host}")
    pane.command_edit.keyPressEvent(
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Tab,
            Qt.KeyboardModifier.NoModifier,
        )
    )
    assert pane.command_edit.selectedText() == "${host}"
    pane.command_edit.keyPressEvent(
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Backtab,
            Qt.KeyboardModifier.ShiftModifier,
        )
    )
    assert pane.command_edit.selectedText() == "${user}"

    pane.insert_command("show inte rest")
    pane.command_edit.setCursorPosition(8)
    candidate = CompletionCandidate(
        "interfaces",
        "Interfaces",
        "Complete current token",
        "keyword",
        600,
    )
    pane.set_suggestions((candidate,))
    pane.suggestions.itemActivated.emit(pane.suggestions.item(0))
    assert pane.command_edit.text() == "show interfaces rest"

    full_command = CompletionCandidate(
        "show clock",
        "Show clock",
        "Library command",
        "library",
        500,
    )
    pane.set_suggestions((full_command,))
    pane.suggestions.itemActivated.emit(pane.suggestions.item(0))
    assert pane.command_edit.text() == "show clock"
    pane.set_suggestions(())
    assert not pane.suggestions.isVisible()


def test_terminal_context_screen_and_size_reporting(qtbot: QtBot) -> None:
    """Terminal exposes rendered output, parameter help, and accessible cell dimensions."""
    pane = TerminalPane()
    qtbot.addWidget(pane)
    sizes: list[tuple[int, int]] = []

    def capture_size(columns: int, rows: int) -> None:
        sizes.append((columns, rows))

    pane.terminal_resized.connect(capture_size)
    pane.resize(640, 480)
    pane.show()
    qtbot.wait(1)
    pane.set_screen_text("line one\nline two")
    assert pane.terminal_view.toPlainText().endswith("line two")
    candidate = CompletionCandidate("22", "Port 22", "Default SSH port", "value", 100)
    pane.command_edit.setText("ssh -p ${remote_port} host")
    pane.show_parameter_context("remote_port", "Remote port", "1-65535", (candidate,))
    assert pane.parameter_hint.isVisible()
    assert "Remote Port" in pane.parameter_hint.text()
    assert sizes
    assert sizes[-1][0] >= 20
    assert sizes[-1][1] >= 5
    pane.command_edit.clear()
    assert not pane.parameter_hint.isVisible()


def test_main_window_validation_help_host_key_and_command_safety_paths(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Main orchestration reports invalid input and preserves explicit command safety gates."""
    library = CommandLibrary.load_bundled()
    fake = FakeController()
    window = MainWindow(
        library,
        settings=SettingsStore(QSettings(str(tmp_path / "paths.ini"), QSettings.Format.IniFormat)),
        vault=cast("CredentialVault", UnavailableVault()),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    warnings: list[str] = []
    information: list[str] = []
    criticals: list[str] = []

    def warning(
        _parent: QWidget,
        _title: str,
        detail: str,
    ) -> QMessageBox.StandardButton:
        warnings.append(detail)
        return QMessageBox.StandardButton.Ok

    def info(
        _parent: QWidget,
        _title: str,
        detail: str,
    ) -> QMessageBox.StandardButton:
        information.append(detail)
        return QMessageBox.StandardButton.Ok

    def critical(
        _parent: QWidget,
        _title: str,
        detail: str,
    ) -> QMessageBox.StandardButton:
        criticals.append(detail)
        return QMessageBox.StandardButton.Ok

    def approve(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr(QMessageBox, "warning", warning)
    monkeypatch.setattr(QMessageBox, "information", info)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    monkeypatch.setattr(main_window_module, "ask_yes_no", approve)

    window.connection_panel.connect_button.click()
    assert "Host must be non-empty" in warnings[-1]
    window.connection_panel.host_edit.setText("router.example.test")
    window.connection_panel.set_auth_method(AuthMethod.PASSWORD)
    window.connection_panel.connect_button.click()
    assert "Enter password" in warnings[-1]
    window.connection_panel.set_auth_method(AuthMethod.PRIVATE_KEY)
    window.connection_panel.key_edit.setText(str(tmp_path / "missing-key"))
    window.connection_panel.connect_button.click()
    assert "missing-key" in warnings[-1]

    fake.error_occurred.emit("Transport error", "safe detail")
    assert criticals[-1] == "safe detail"
    fake.unknown_host_key.emit("router.example.test", 22, "ssh-ed25519", "SHA256:test")
    assert fake.host_key_answers == [True]

    window.connection_panel.set_auth_method(AuthMethod.AGENT)
    window.connection_panel.key_edit.clear()
    window.terminal_pane.parameter_context_requested.emit("port")
    assert "Port" in window.terminal_pane.parameter_hint.text()
    window.library_panel.command_requested.emit("not a template", False)
    placeholder = library.get("ssh.connect.basic")
    window.library_panel.command_requested.emit(placeholder, False)
    assert "${port}" in window.terminal_pane.command_edit.text()
    window.terminal_pane.command_submitted.emit(window.terminal_pane.command_edit.text())
    assert "Fill selected parameter" in information[-1]

    safe = library.get("cisco.system.version")
    window.library_panel.command_requested.emit(safe, False)
    assert window.terminal_pane.command_edit.text() == safe.command
    window.library_panel.command_requested.emit(safe, True)
    assert "Establish SSH connection" in information[-1]
    window.terminal_pane.command_submitted.emit("ssh -p 70000 admin@router.example.test")
    assert "port" in warnings[-1].casefold()


def test_main_window_destructive_confirmation_and_help_actions(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Connected destructive commands need approval and Help actions stay modal and reachable."""
    library = CommandLibrary.load_bundled()
    fake = FakeController()
    window = MainWindow(
        library,
        settings=SettingsStore(QSettings(str(tmp_path / "guards.ini"), QSettings.Format.IniFormat)),
        controller=cast("SSHSessionController", fake),
    )
    qtbot.addWidget(window)
    fake.connected.emit()

    class RejectDialog:
        """Deterministic destructive-dialog rejection."""

        def __init__(self, _command: str, _parent: QWidget) -> None:
            """Accept constructor values."""

        def exec(self) -> QDialog.DialogCode:
            """Reject execution."""
            return QDialog.DialogCode.Rejected

    destructive = library.get("cisco.config.save")
    fake.connected.emit()
    monkeypatch.setattr(main_window_module, "DestructiveCommandDialog", RejectDialog)
    window.library_panel.command_requested.emit(destructive, True)
    assert fake.sent == []

    class AcceptDialog(RejectDialog):
        """Deterministic destructive-dialog acceptance."""

        def exec(self) -> QDialog.DialogCode:
            """Accept execution."""
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "DestructiveCommandDialog", AcceptDialog)
    window.library_panel.command_requested.emit(destructive, True)
    assert fake.sent[-1] == destructive.command + "\n"

    def reject_help(_dialog: QDialog) -> QDialog.DialogCode:
        return QDialog.DialogCode.Rejected

    about_calls: list[str] = []

    def about(_parent: QWidget, _title: str, detail: str) -> None:
        about_calls.append(detail)

    monkeypatch.setattr(QDialog, "exec", reject_help)
    monkeypatch.setattr(QMessageBox, "about", about)
    actions = {action.text(): action for action in window.findChildren(QAction)}
    actions["SSH It help"].trigger()
    actions["About SSH It"].trigger()
    assert about_calls
