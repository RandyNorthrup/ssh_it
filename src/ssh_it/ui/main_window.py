"""Top-level SSH It window and feature orchestration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ssh_it.completion import CompletionEngine
from ssh_it.credentials import CredentialEntry, CredentialLibrary, PasswordKind
from ssh_it.models import AuthMethod, CommandTemplate, ConnectionProfile, Risk, TunnelSpec
from ssh_it.parameters import parameter_spec
from ssh_it.secrets import CredentialVault, CredentialVaultError
from ssh_it.settings import SettingsStore
from ssh_it.ssh.session import SSHSessionController
from ssh_it.terminal import TerminalBuffer
from ssh_it.terminal_export import (
    EXPORT_FILTERS,
    ensure_export_suffix,
    format_from_dialog,
    render_export,
    write_export,
)
from ssh_it.ui.common import (
    DestructiveCommandDialog,
    ask_yes_no,
    connect_action,
)
from ssh_it.ui.connection import ConnectionPanel
from ssh_it.ui.credential_panel import CredentialLibraryPanel
from ssh_it.ui.library_panel import LibraryPanel
from ssh_it.ui.operations import TransferPanel, TunnelPanel
from ssh_it.ui.terminal_pane import TerminalPane

if TYPE_CHECKING:
    from ssh_it.library import CommandLibrary


class MainWindow(QMainWindow):
    """Coordinate secure connection, discovery, terminal, transfer, and tunnel UI."""

    def __init__(
        self,
        library: CommandLibrary,
        *,
        credential_library: CredentialLibrary | None = None,
        settings: SettingsStore | None = None,
        vault: CredentialVault | None = None,
        controller: SSHSessionController | None = None,
    ) -> None:
        """Build full application window and connect signals."""
        super().__init__()
        self.setWindowTitle("SSH It")
        self.setMinimumSize(820, 620)
        self.resize(1380, 880)
        self._library = library
        self._settings = settings or SettingsStore()
        self._vault = vault or CredentialVault()
        self._controller = controller or SSHSessionController()
        self._completion = CompletionEngine(library)
        self._credential_library = credential_library or CredentialLibrary.load_bundled()
        self._terminal_buffer = TerminalBuffer()
        self._active_profile: ConnectionProfile | None = None
        self._pending_saved_password: str | None = None
        self._explicit_blank_password = False
        self._factory_password_fill = False
        self._connected = False

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        self.connection_panel = ConnectionPanel(library.vendors)
        central_layout.addWidget(self.connection_panel)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setAccessibleName("SSH workspace tabs")
        self.terminal_pane = TerminalPane()
        self.transfer_panel = TransferPanel()
        self.tunnel_panel = TunnelPanel()
        self.tabs.addTab(self.terminal_pane, "Terminal")
        self.tabs.addTab(self.transfer_panel, "Secure Files (SFTP)")
        self.tabs.addTab(self.tunnel_panel, "Tunnels")
        central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        self.library_panel = LibraryPanel(library, self._settings)
        self.credential_panel = CredentialLibraryPanel(self._credential_library)
        self.side_tabs = QTabWidget()
        self.side_tabs.setAccessibleName("Command and default credential libraries")
        self.side_tabs.addTab(self.library_panel, "Commands")
        self.side_tabs.addTab(self.credential_panel, "Default Credentials")
        self.library_dock = QDockWidget("Libraries", self)
        self.library_dock.setObjectName("commandLibraryDock")
        self.library_dock.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.library_dock.setWidget(self.side_tabs)
        self.library_dock.setMinimumWidth(390)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.library_dock)

        self.statusBar().showMessage("Ready · no SSH connection")
        self._create_actions()
        self._connect_signals()
        self._refresh_profiles()
        self.terminal_pane.set_connected(False)
        self.transfer_panel.set_connected(False)
        self.tunnel_panel.set_connected(False)
        self._restore_window_state()

    def _create_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        save_profile = QAction("Save connection profile…", self)
        save_profile.triggered.connect(connect_action(self._save_profile))
        file_menu.addAction(save_profile)
        delete_profile = QAction("Delete selected saved profile…", self)
        delete_profile.triggered.connect(connect_action(self._delete_profile))
        file_menu.addAction(delete_profile)
        export_terminal = QAction("Export terminal transcript…", self)
        export_terminal.setShortcut(QKeySequence("Ctrl+Shift+S"))
        export_terminal.setToolTip(
            "Export bounded terminal scrollback as UTF-8 plain text or safe standalone HTML."
        )
        export_terminal.triggered.connect(connect_action(self._export_terminal))
        file_menu.addAction(export_terminal)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        connection_menu = self.menuBar().addMenu("&Connection")
        connect_action_item = QAction("Connect", self)
        connect_action_item.setShortcut(QKeySequence("Ctrl+Return"))
        connect_action_item.triggered.connect(connect_action(self._connect))
        connection_menu.addAction(connect_action_item)
        disconnect_action = QAction("Disconnect", self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+Shift+D"))
        disconnect_action.triggered.connect(self._controller.disconnect_from_host)
        connection_menu.addAction(disconnect_action)
        forget_password = QAction("Forget saved password for current endpoint…", self)
        forget_password.triggered.connect(connect_action(self._forget_password))
        connection_menu.addAction(forget_password)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.library_dock.toggleViewAction())
        focus_host = QAction("Focus SSH host", self)
        focus_host.setShortcut(QKeySequence("Ctrl+L"))
        focus_host.triggered.connect(self.connection_panel.host_edit.setFocus)
        view_menu.addAction(focus_host)
        focus_search = QAction("Focus command search", self)
        focus_search.setShortcut(QKeySequence("Ctrl+K"))
        focus_search.triggered.connect(self.library_panel.search_edit.setFocus)
        view_menu.addAction(focus_search)

        help_menu = self.menuBar().addMenu("&Help")
        help_action = QAction("SSH It help", self)
        help_action.setShortcut(QKeySequence.StandardKey.HelpContents)
        help_action.triggered.connect(connect_action(self._show_help))
        help_menu.addAction(help_action)
        about_action = QAction("About SSH It", self)
        about_action.triggered.connect(connect_action(self._show_about))
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        panel = self.connection_panel
        panel.connect_clicked.connect(self._connect)
        panel.disconnect_clicked.connect(self._controller.disconnect_from_host)
        panel.save_profile_clicked.connect(self._save_profile)
        panel.favorite_changed.connect(self._set_connection_favorite)
        panel.vendor_changed.connect(self._vendor_changed)
        panel.profile_combo.currentIndexChanged.connect(self._sync_connection_favorite)
        panel.profile_combo.currentIndexChanged.connect(self._clear_factory_fill)
        for widget_signal in (
            panel.host_edit.textChanged,
            panel.user_edit.textChanged,
            panel.port_spin.valueChanged,
        ):
            widget_signal.connect(self._sync_connection_favorite)

        self.library_panel.command_requested.connect(self._library_command_requested)
        self.credential_panel.fill_requested.connect(self._fill_default_credential)
        panel.secret_edit.textEdited.connect(self._secret_edited)
        self.terminal_pane.command_submitted.connect(self._composer_command_requested)
        self.terminal_pane.completion_requested.connect(self._suggest)
        self.terminal_pane.interrupt_requested.connect(self._controller.interrupt)
        self.terminal_pane.terminal_resized.connect(self._resize_terminal)
        self.terminal_pane.parameter_context_requested.connect(self._show_parameter_context)
        self.transfer_panel.transfer_requested.connect(self._controller.transfer)
        self.tunnel_panel.start_requested.connect(self._start_tunnel)
        self.tunnel_panel.stop_requested.connect(self._controller.stop_tunnel)

        controller = self._controller
        controller.state_changed.connect(self.connection_panel.set_connected_state)
        controller.connected.connect(self._on_connected)
        controller.disconnected.connect(self._on_disconnected)
        controller.output_received.connect(self._on_output)
        controller.error_occurred.connect(self._show_error)
        controller.unknown_host_key.connect(self._host_key_prompt)
        controller.transfer_progress.connect(self.transfer_panel.update_progress)
        controller.transfer_finished.connect(self.transfer_panel.finish)
        controller.tunnel_started.connect(self.tunnel_panel.tunnel_started)
        controller.tunnel_stopped.connect(self.tunnel_panel.tunnel_stopped)

    def _connect(self) -> None:
        try:
            profile = self.connection_panel.current_profile()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid connection settings", str(error))
            return
        if profile.private_key is not None and not profile.private_key.is_file():
            QMessageBox.warning(self, "Private key not found", str(profile.private_key))
            return

        secret = self.connection_panel.secret_edit.text()
        password: str | None = None
        passphrase: str | None = None
        self._pending_saved_password = None
        if profile.auth_method is AuthMethod.PASSWORD:
            password = (
                secret
                if secret or self._explicit_blank_password
                else self._load_saved_password(profile)
            )
            if password is None:
                QMessageBox.warning(
                    self,
                    "Password required",
                    "Enter password or store one for this endpoint in OS credential vault.",
                )
                return
            if secret and not self._factory_password_fill:
                self._offer_password_save(profile, password)
        elif profile.auth_method is AuthMethod.PRIVATE_KEY:
            passphrase = secret or None

        self._active_profile = profile
        self.connection_panel.clear_secret()
        self._explicit_blank_password = False
        self._factory_password_fill = False
        self._terminal_buffer.clear()
        self.terminal_pane.set_screen_text("")
        self.statusBar().showMessage(f"Connecting to {profile.host}:{profile.port}…")
        self._controller.connect_to(profile, password=password, passphrase=passphrase)

    def _load_saved_password(self, profile: ConnectionProfile) -> str | None:
        if not self._vault.is_available():
            return None
        try:
            return self._vault.load(profile)
        except CredentialVaultError as error:
            QMessageBox.warning(self, "Credential vault unavailable", str(error))
            return None

    def _offer_password_save(self, profile: ConnectionProfile, password: str) -> None:
        if not self._vault.is_available():
            QMessageBox.information(
                self,
                "Secure password saving unavailable",
                "No recommended OS credential vault is available. Connection will continue with "
                "password in memory only; SSH It will not use plaintext fallback storage.",
            )
            return
        if ask_yes_no(
            self,
            "Save password securely?",
            f"Save password for {profile.username or 'default user'}@"
            f"{profile.host}:{profile.port}?",
            informative_text=(
                "SSH It will store it in operating-system credential vault only after this "
                "connection authenticates successfully."
            ),
        ):
            self._pending_saved_password = password

    def _on_connected(self) -> None:
        self._connected = True
        self.terminal_pane.set_connected(True)
        self.transfer_panel.set_connected(True)
        self.tunnel_panel.set_connected(True)
        profile = self._active_profile
        if profile is not None:
            self._settings.record_recent(profile)
            if self._pending_saved_password is not None:
                try:
                    self._vault.save(profile, self._pending_saved_password)
                except CredentialVaultError as error:
                    QMessageBox.warning(self, "Password not saved", str(error))
                else:
                    self.statusBar().showMessage(
                        f"Connected to {profile.host} · password saved in OS credential vault"
                    )
            else:
                self.statusBar().showMessage(f"Connected to {profile.host}:{profile.port}")
        self._pending_saved_password = None
        self._refresh_profiles()
        self.terminal_pane.command_edit.setFocus()

    def _on_disconnected(self, reason: str) -> None:
        self._connected = False
        self._pending_saved_password = None
        self.terminal_pane.set_connected(False)
        self.transfer_panel.set_connected(False)
        self.tunnel_panel.set_connected(False)
        self.statusBar().showMessage(reason)

    def _show_error(self, title: str, detail: str) -> None:
        self._connected = False
        self._pending_saved_password = None
        self.terminal_pane.set_connected(False)
        self.transfer_panel.set_connected(False)
        self.tunnel_panel.set_connected(False)
        self.statusBar().showMessage(title)
        QMessageBox.critical(self, title, detail)

    def _host_key_prompt(self, host: str, port: int, algorithm: str, fingerprint: str) -> None:
        accepted = ask_yes_no(
            self,
            "Trust unknown SSH host key?",
            f"First connection to {host}:{port}. Verify fingerprint through a separate trusted "
            "channel.",
            informative_text=f"Algorithm: {algorithm}\nSHA-256 fingerprint: {fingerprint}",
        )
        self._controller.answer_host_key(accept=accepted)

    def _on_output(self, data: str) -> None:
        rendered = self._terminal_buffer.feed(data)
        self.terminal_pane.set_screen_text(rendered)

    def _resize_terminal(self, columns: int, rows: int) -> None:
        self._terminal_buffer.resize(columns, rows)
        self._controller.resize_terminal(columns, rows)

    def _export_terminal(self) -> None:
        transcript = self._terminal_buffer.transcript()
        if not transcript:
            QMessageBox.information(
                self,
                "Nothing to export",
                "The terminal transcript is empty. Connect and receive output before exporting.",
            )
            return
        selected_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export terminal transcript",
            "ssh-it-terminal",
            EXPORT_FILTERS,
        )
        if not selected_path:
            return
        path = Path(selected_path)
        export_format = format_from_dialog(path, selected_filter)
        path = ensure_export_suffix(path, export_format)
        try:
            write_export(path, render_export(transcript, export_format))
        except OSError as error:
            QMessageBox.critical(self, "Terminal export failed", str(error))
            return
        self.statusBar().showMessage(f"Terminal transcript exported to {path}")

    def _suggest(self, text: str) -> None:
        vendor = str(self.connection_panel.vendor_combo.currentData() or "")
        self.terminal_pane.set_suggestions(
            self._completion.suggest(
                text,
                vendor=vendor,
                favorite_ids=self._settings.favorite_commands(),
            )
        )

    def _show_parameter_context(self, name: str) -> None:
        spec = parameter_spec(name)
        profile = self._active_profile
        if profile is None:
            try:
                profile = self.connection_panel.current_profile()
            except ValueError:
                profile = None
        candidates = self._completion.suggest_parameter(
            name,
            profile_host=profile.host if profile else "",
            profile_port=profile.port if profile else 0,
            profile_user=profile.username if profile else "",
        )
        self.terminal_pane.show_parameter_context(
            name,
            spec.description,
            spec.format_hint,
            candidates,
        )

    def _library_command_requested(self, value: object, run: bool) -> None:
        if not isinstance(value, CommandTemplate):
            return
        command = value.command
        if value.placeholders:
            self.tabs.setCurrentWidget(self.terminal_pane)
            self.terminal_pane.insert_command(command)
            self.statusBar().showMessage(
                "Fill selected parameter; Tab moves through fields, then review and run"
            )
            return
        if run:
            self._run_command(command, value)
        else:
            self.tabs.setCurrentWidget(self.terminal_pane)
            self.terminal_pane.insert_command(command)
            self.statusBar().showMessage("Command inserted; review before running")

    def _composer_command_requested(self, command: str) -> None:
        if _contains_placeholder(command):
            self.terminal_pane.insert_command(command)
            QMessageBox.information(
                self,
                "Required parameter missing",
                "Fill selected parameter. Tab and Shift+Tab move through remaining fields; "
                "IntelliSense offers typed values.",
            )
            return
        match = self._completion.match_template(command)
        template = match[0] if match else None
        if match is not None:
            try:
                for name, value in match[1].items():
                    parameter_spec(name).validate(value)
            except ValueError as error:
                QMessageBox.warning(self, "Invalid command parameter", str(error))
                return
        self._run_command(command, template)

    def _run_command(self, command: str, template: CommandTemplate | None) -> None:
        if not self._connected:
            self.terminal_pane.insert_command(command)
            QMessageBox.information(
                self,
                "Connect before running",
                "Command remains in composer. Establish SSH connection, review target, then run.",
            )
            return
        if template is not None and template.risk is Risk.DESTRUCTIVE:
            confirm = DestructiveCommandDialog(command, self)
            if confirm.exec() != QDialog.DialogCode.Accepted:
                return
        self._completion.remember(command)
        self.terminal_pane.set_history(self._completion.history)
        self.terminal_pane.insert_command(command, focus=False)
        self.terminal_pane.take_command()
        self._controller.send(command + "\n")
        self.statusBar().showMessage("Command sent")

    def _save_profile(self) -> None:
        try:
            profile = self.connection_panel.current_profile()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid connection settings", str(error))
            return
        name, accepted = QInputDialog.getText(
            self,
            "Save connection profile",
            "Profile name (password is never stored in profile):",
            text=profile.display_name,
        )
        if not accepted or not name.strip():
            return
        self._settings.save_profile(replace(profile, name=name.strip()))
        self._refresh_profiles()
        self.statusBar().showMessage(f"Saved profile: {name.strip()}")

    def _delete_profile(self) -> None:
        selected = self.connection_panel.profile_combo.currentData()
        if not isinstance(selected, ConnectionProfile) or not selected.name:
            QMessageBox.information(
                self, "No saved profile selected", "Choose a named saved profile first."
            )
            return
        if not ask_yes_no(
            self,
            "Delete profile?",
            f"Delete non-secret profile “{selected.display_name}”?",
            informative_text=(
                "Stored password, if any, is managed separately in OS credential vault."
            ),
        ):
            return
        self._settings.delete_profile(selected.canonical_key)
        self._refresh_profiles()

    def _set_connection_favorite(self, favorite: bool) -> None:
        try:
            profile = self.connection_panel.current_profile()
        except ValueError as error:
            self.connection_panel.set_favorite(False)
            QMessageBox.warning(self, "Cannot favorite connection", str(error))
            return
        if favorite and not any(
            item.canonical_key == profile.canonical_key for item in self._settings.profiles()
        ):
            self._settings.save_profile(replace(profile, name=profile.display_name))
        self._settings.set_connection_favorite(profile.canonical_key, favorite)
        self._refresh_profiles()

    def _sync_connection_favorite(self, _value: object = None) -> None:
        try:
            key = self.connection_panel.current_profile().canonical_key
        except ValueError:
            self.connection_panel.set_favorite(False)
            return
        self.connection_panel.set_favorite(key in self._settings.favorite_connections())

    def _refresh_profiles(self) -> None:
        saved = self._settings.profiles()
        recents = self._settings.recents()
        favorite_keys = self._settings.favorite_connections()
        pool = {item.canonical_key: item for item in (*recents, *saved)}
        favorites = tuple(
            sorted(
                (profile for key, profile in pool.items() if key in favorite_keys),
                key=lambda item: item.display_name.casefold(),
            )
        )
        self.connection_panel.set_profiles(favorites, saved, recents)
        self._sync_connection_favorite()

    def _vendor_changed(self, vendor: str) -> None:
        self.library_panel.set_vendor(vendor)
        if self.terminal_pane.command_edit.text():
            self._suggest(self.terminal_pane.command_edit.text())

    def _fill_default_credential(self, value: object, include_password: bool) -> None:
        """Explicitly copy one public factory reference into Quick Connect fields."""
        if not isinstance(value, CredentialEntry):
            return
        panel = self.connection_panel
        panel.set_auth_method(AuthMethod.PASSWORD)
        panel.user_edit.setText(value.username)
        panel.set_vendor(value.command_vendor)
        panel.clear_secret()
        self._explicit_blank_password = False
        self._factory_password_fill = False
        if include_password and value.can_fill_password:
            panel.secret_edit.setText(value.password or "")
            self._explicit_blank_password = value.password_kind is PasswordKind.BLANK
            self._factory_password_fill = True
            message = "Factory username and password filled; review target before connecting"
        else:
            message = "Factory username filled; enter the device-specific or owner password"
        self.statusBar().showMessage(message)
        panel.host_edit.setFocus()

    def _secret_edited(self, _text: str) -> None:
        """Stop treating an edited empty field as an intentional factory blank."""
        self._explicit_blank_password = False
        self._factory_password_fill = False

    def _clear_factory_fill(self, _value: object = None) -> None:
        """Discard factory-password state when a stored profile is selected."""
        self._explicit_blank_password = False
        self._factory_password_fill = False

    def _forget_password(self) -> None:
        try:
            profile = self.connection_panel.current_profile()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid endpoint", str(error))
            return
        if not ask_yes_no(
            self,
            "Forget saved password?",
            f"Remove saved password for {profile.username or 'default user'}@"
            f"{profile.host}:{profile.port}?",
        ):
            return
        try:
            self._vault.delete(profile)
        except CredentialVaultError as error:
            QMessageBox.warning(self, "Password not removed", str(error))
            return
        self.statusBar().showMessage("Saved password removed from OS credential vault")

    def _start_tunnel(self, value: object) -> None:
        if isinstance(value, TunnelSpec):
            self._controller.start_tunnel(value)

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("SSH It help")
        dialog.resize(760, 620)
        layout = QVBoxLayout(dialog)
        help_text = QTextBrowser()
        help_text.setOpenExternalLinks(True)
        help_text.setHtml(
            "<h1>SSH It</h1>"
            "<h2>Safe connection flow</h2>"
            "<ol><li>Choose vendor library or All libraries.</li>"
            "<li>Enter endpoint and authentication. Quick Connect need not be saved.</li>"
            "<li>Verify first-use host fingerprint independently before accepting.</li>"
            "<li>Search or compose command, review exact text, then run.</li></ol>"
            "<h2>Completion</h2><p>Ctrl+Space shows ranked vendor, command, and memory-only "
            "history matches. Template placeholders open labelled fill forms.</p>"
            "<h2>Passwords</h2><p>At connection time, typed password can be saved after successful "
            "authentication. Only recommended OS credential vaults are accepted; no plaintext "
            "fallback exists.</p><p>The Default Credentials tab contains public, product-scoped "
            "factory references. Values fill only after an explicit click and never trigger an "
            "automatic connection. Replace factory access immediately.</p>"
            "<h2>Risk labels</h2><p>Safe is normally read-only. Caution can expose data, run "
            "continuously, or affect session state. Destructive can persist changes or disrupt "
            "service and requires typing RUN.</p>"
            "<h2>Keyboard</h2><p>Ctrl+L host · Ctrl+K library search · Ctrl+Space suggestions · "
            "Enter run · Up/Down history · empty composer Ctrl+C interrupt · Ctrl+Shift+D "
            "disconnect · Ctrl+Shift+S export terminal · F1 help.</p>"
            "<h2>Terminal export</h2><p>File → Export terminal transcript saves bounded "
            "scrollback as UTF-8 plain text or escaped standalone HTML. Review output for "
            "sensitive data before sharing.</p>"
        )
        help_text.setAccessibleName("SSH It help content")
        layout.addWidget(help_text)
        dialog.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About SSH It",
            "SSH It 0.1.0\nSecure SSH workspace with vendor-aware command discovery, "
            "completion, SFTP, and forwarding.\n\nMIT-licensed application; dependencies keep "
            "their "
            "respective licenses.",
        )

    def _restore_window_state(self) -> None:
        settings = QSettings("SSH It", "SSH It")
        geometry = settings.value("ui/geometry")
        state = settings.value("ui/windowState")
        if geometry is not None:
            self.restoreGeometry(geometry)
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Persist layout and shut transport down before closing."""
        settings = QSettings("SSH It", "SSH It")
        settings.setValue("ui/geometry", self.saveGeometry())
        settings.setValue("ui/windowState", self.saveState())
        self._controller.shutdown()
        event.accept()


def _contains_placeholder(command: str) -> bool:
    """Return whether required snippet field remains unresolved."""
    return "${" in command and "}" in command
