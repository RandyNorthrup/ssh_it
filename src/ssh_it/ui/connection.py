"""Responsive Quick Connect panel with recents and favorites."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ssh_it.models import AuthMethod, ConnectionProfile
from ssh_it.ui.common import describe_widget

if TYPE_CHECKING:
    from PySide6.QtGui import QResizeEvent

_COMPACT_WIDTH = 980


class ConnectionPanel(QWidget):
    """Always-visible connection fields and stored-profile chooser."""

    connect_clicked = Signal()
    disconnect_clicked = Signal()
    save_profile_clicked = Signal()
    favorite_changed = Signal(bool)
    vendor_changed = Signal(str)

    def __init__(self, vendors: tuple[str, ...], parent: QWidget | None = None) -> None:
        """Create Quick Connect controls."""
        super().__init__(parent)
        self.setObjectName("quickConnectPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 4)
        header = QHBoxLayout()
        title = QLabel("Quick Connect")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        self.state_label = QLabel("Disconnected")
        self.state_label.setAccessibleName("Connection status")
        header.addStretch()
        header.addWidget(self.state_label)
        outer.addLayout(header)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(4)
        outer.addLayout(self._grid)

        self.profile_combo = QComboBox()
        describe_widget(
            self.profile_combo,
            "Connection profile or recent endpoint",
            "Choose Quick Connect, a favorite profile, saved profile, or recently successful "
            "endpoint.",
        )
        self.profile_combo.currentIndexChanged.connect(self._profile_selected)

        self.host_edit = QLineEdit()
        self.host_edit.setClearButtonEnabled(True)
        self.host_edit.setPlaceholderText("device.example.com or 192.0.2.10")
        describe_widget(self.host_edit, "SSH host", "Hostname or IP address of SSH server.")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        describe_widget(self.port_spin, "SSH port", "TCP port used by SSH server; usually 22.")
        self.user_edit = QLineEdit()
        self.user_edit.setClearButtonEnabled(True)
        describe_widget(
            self.user_edit, "SSH username", "Remote account name; blank uses local username."
        )

        self.auth_combo = QComboBox()
        self.auth_combo.addItem("SSH agent / default keys", AuthMethod.AGENT.value)
        self.auth_combo.addItem("Password", AuthMethod.PASSWORD.value)
        self.auth_combo.addItem("Private key file", AuthMethod.PRIVATE_KEY.value)
        describe_widget(
            self.auth_combo,
            "Authentication method",
            "Choose agent/default keys, password, or an explicit private key file.",
        )
        self.auth_combo.currentIndexChanged.connect(self._update_auth_fields)

        self.key_edit = QLineEdit()
        self.key_edit.setClearButtonEnabled(True)
        self.key_edit.setPlaceholderText("Private key path")
        describe_widget(self.key_edit, "Private key file", "Path to private SSH identity file.")
        self.key_button = QPushButton("Browse key…")
        describe_widget(self.key_button, "Browse private key", "Choose private SSH identity file.")
        self.key_button.clicked.connect(self._browse_key)

        self.secret_edit = QLineEdit()
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        describe_widget(
            self.secret_edit,
            "SSH password",
            "Password or private-key passphrase. Cleared after connection attempt.",
        )
        self.show_secret = QToolButton()
        self.show_secret.setText("Show")
        self.show_secret.setCheckable(True)
        describe_widget(
            self.show_secret, "Show secret", "Temporarily reveal password or passphrase."
        )
        self.show_secret.toggled.connect(self._toggle_secret)

        self.vendor_combo = QComboBox()
        self.vendor_combo.addItem("All libraries", "")
        for vendor in vendors:
            if vendor != "All libraries":
                self.vendor_combo.addItem(vendor, vendor)
        describe_widget(
            self.vendor_combo,
            "Vendor command library",
            "Choose completion library before connecting. All libraries searches every vendor.",
        )
        self.vendor_combo.currentIndexChanged.connect(self._vendor_index_changed)

        self.favorite_button = QToolButton()
        self.favorite_button.setText("☆ Favorite")
        self.favorite_button.setCheckable(True)
        describe_widget(
            self.favorite_button,
            "Favorite connection",
            "Add or remove current endpoint from connection favorites.",
        )
        self.favorite_button.toggled.connect(self._favorite_toggled)
        self.save_button = QPushButton("Save profile…")
        describe_widget(
            self.save_button,
            "Save connection profile",
            "Save non-secret connection fields under a name.",
        )
        self.save_button.clicked.connect(self.save_profile_clicked)
        self.connect_button = QPushButton("Connect")
        self.connect_button.setDefault(True)
        describe_widget(
            self.connect_button, "Connect", "Connect using current Quick Connect fields."
        )
        self.connect_button.clicked.connect(self.connect_clicked)
        self.disconnect_button = QPushButton("Disconnect")
        describe_widget(self.disconnect_button, "Disconnect", "Close SSH shell and active tunnels.")
        self.disconnect_button.setEnabled(False)
        self.disconnect_button.clicked.connect(self.disconnect_clicked)

        self._labels: dict[str, QLabel] = {}
        self._compact: bool | None = None
        self._arrange(False)
        self._update_auth_fields()
        QWidget.setTabOrder(self.profile_combo, self.host_edit)
        QWidget.setTabOrder(self.host_edit, self.port_spin)
        QWidget.setTabOrder(self.port_spin, self.user_edit)
        QWidget.setTabOrder(self.user_edit, self.auth_combo)
        QWidget.setTabOrder(self.auth_combo, self.key_edit)
        QWidget.setTabOrder(self.key_edit, self.secret_edit)
        QWidget.setTabOrder(self.secret_edit, self.vendor_combo)
        QWidget.setTabOrder(self.vendor_combo, self.connect_button)

    def set_profiles(
        self,
        favorites: tuple[ConnectionProfile, ...],
        saved: tuple[ConnectionProfile, ...],
        recents: tuple[ConnectionProfile, ...],
    ) -> None:
        """Rebuild chooser with favorite, named, and recent endpoint sections."""
        current_key = self.current_profile().canonical_key if self.host_edit.text().strip() else ""
        blocker = QSignalBlocker(self.profile_combo)
        self.profile_combo.clear()
        self.profile_combo.addItem("Quick Connect (unsaved)", None)
        seen: set[str] = set()
        for prefix, profiles in (("★", favorites), ("Saved", saved), ("Recent", recents)):
            for profile in profiles:
                if profile.canonical_key in seen:
                    continue
                seen.add(profile.canonical_key)
                self.profile_combo.addItem(f"{prefix} · {profile.display_name}", profile)
        del blocker
        if current_key:
            for index in range(self.profile_combo.count()):
                profile = self.profile_combo.itemData(index)
                if isinstance(profile, ConnectionProfile) and profile.canonical_key == current_key:
                    self.profile_combo.setCurrentIndex(index)
                    break

    def current_profile(self, name: str = "") -> ConnectionProfile:
        """Build validated profile from visible non-secret fields."""
        key_text = self.key_edit.text().strip()
        return ConnectionProfile(
            name=name,
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.user_edit.text().strip(),
            auth_method=self.auth_method(),
            private_key=Path(key_text).expanduser() if key_text else None,
            vendor=str(self.vendor_combo.currentData() or ""),
        )

    def auth_method(self) -> AuthMethod:
        """Return selected typed authentication method."""
        value = self.auth_combo.currentData()
        try:
            return AuthMethod(str(value))
        except ValueError:
            return AuthMethod.AGENT

    def set_auth_method(self, method: AuthMethod) -> None:
        """Select authentication method from a trusted application action."""
        self._set_combo_data(self.auth_combo, method.value)

    def set_vendor(self, vendor: str) -> None:
        """Select a command vendor/library when present, otherwise use all libraries."""
        self._set_combo_data(self.vendor_combo, vendor)
        if self.vendor_combo.currentData() != vendor:
            self.vendor_combo.setCurrentIndex(0)

    def set_connected_state(self, state: str) -> None:
        """Update explicit text state and related control enablement."""
        labels = {
            "connecting": "Connecting…",
            "connected": "Connected",
            "disconnecting": "Disconnecting…",
            "host-key-prompt": "Waiting for host-key decision",
            "error": "Connection error",
            "disconnected": "Disconnected",
        }
        self.state_label.setText(labels.get(state, state.replace("-", " ").title()))
        connected = state == "connected"
        busy = state in {"connecting", "disconnecting", "host-key-prompt"}
        self.connect_button.setEnabled(not connected and not busy)
        self.disconnect_button.setEnabled(connected or state == "connecting")

    def set_favorite(self, favorite: bool) -> None:
        """Update favorite toggle without emitting persistence signal."""
        blocker = QSignalBlocker(self.favorite_button)
        self.favorite_button.setChecked(favorite)
        self.favorite_button.setText("★ Favorite" if favorite else "☆ Favorite")
        del blocker

    def clear_secret(self) -> None:
        """Remove secret text and hide field content."""
        self.secret_edit.clear()
        self.show_secret.setChecked(False)

    def load_profile(self, profile: ConnectionProfile) -> None:
        """Populate Quick Connect fields from non-secret profile."""
        self.host_edit.setText(profile.host)
        self.port_spin.setValue(profile.port)
        self.user_edit.setText(profile.username)
        self._set_combo_data(self.auth_combo, profile.auth_method.value)
        self.key_edit.setText(str(profile.private_key) if profile.private_key else "")
        self._set_combo_data(self.vendor_combo, profile.vendor)
        self.clear_secret()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """Reflow fields at narrow width."""
        compact = self.width() < _COMPACT_WIDTH
        if compact != self._compact:
            self._arrange(compact)
        super().resizeEvent(event)

    def _arrange(self, compact: bool) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if isinstance(widget, QLabel):
                widget.setParent(self)
        fields: list[tuple[str, QWidget]] = [
            ("Profile", self.profile_combo),
            ("Host", self.host_edit),
            ("Port", self.port_spin),
            ("Username", self.user_edit),
            ("Authentication", self.auth_combo),
            ("Private key", self._pair(self.key_edit, self.key_button)),
            ("Password / passphrase", self._pair(self.secret_edit, self.show_secret)),
            ("Command library", self.vendor_combo),
        ]
        columns = 2 if compact else 4
        for index, (text, field) in enumerate(fields):
            row = (index // columns) * 2
            column = index % columns
            label = self._labels.setdefault(text, QLabel(text))
            if isinstance(field, (QLineEdit, QComboBox, QSpinBox)):
                label.setBuddy(field)
            self._grid.addWidget(label, row, column)
            self._grid.addWidget(field, row + 1, column)
        button_row = ((len(fields) + columns - 1) // columns) * 2
        button_box = self._pair(
            self.favorite_button,
            self.save_button,
            self.connect_button,
            self.disconnect_button,
        )
        self._grid.addWidget(button_box, button_row, 0, 1, columns)
        self._compact = compact

    @staticmethod
    def _pair(*widgets: QWidget) -> QWidget:
        existing_parent = widgets[0].parentWidget()
        if existing_parent is not None and existing_parent.objectName() == "fieldPair":
            return existing_parent
        container = QWidget()
        container.setObjectName("fieldPair")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for widget in widgets:
            layout.addWidget(widget, 1 if widget is widgets[0] else 0)
        return container

    def _profile_selected(self, _index: int) -> None:
        profile = self.profile_combo.currentData()
        if isinstance(profile, ConnectionProfile):
            self.load_profile(profile)

    def _favorite_toggled(self, checked: bool) -> None:
        self.favorite_button.setText("★ Favorite" if checked else "☆ Favorite")
        self.favorite_changed.emit(checked)

    def _vendor_index_changed(self, _index: int) -> None:
        self.vendor_changed.emit(str(self.vendor_combo.currentData() or ""))

    def _update_auth_fields(self) -> None:
        method = self.auth_method()
        key_enabled = method is AuthMethod.PRIVATE_KEY
        secret_enabled = method is not AuthMethod.AGENT
        self.key_edit.setEnabled(key_enabled)
        self.key_button.setEnabled(key_enabled)
        self.secret_edit.setEnabled(secret_enabled)
        self.show_secret.setEnabled(secret_enabled)
        self.secret_edit.setPlaceholderText(
            "Password" if method is AuthMethod.PASSWORD else "Private-key passphrase (if needed)"
        )
        self.secret_edit.setAccessibleName(
            "SSH password" if method is AuthMethod.PASSWORD else "Private key passphrase"
        )

    def _browse_key(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose private SSH key",
            str(Path.home() / ".ssh"),
            "All files (*)",
        )
        if path:
            self.key_edit.setText(path)

    def _toggle_secret(self, shown: bool) -> None:
        self.secret_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self.show_secret.setText("Hide" if shown else "Show")

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
