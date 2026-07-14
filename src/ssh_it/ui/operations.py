"""SFTP transfer and SSH tunnel operation panels."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ssh_it.models import TunnelKind, TunnelSpec
from ssh_it.ui.common import ask_yes_no, describe_widget

_TUNNEL_ID_COLUMN = 4


class TransferPanel(QWidget):
    """Structured SFTP upload and download controls."""

    transfer_requested = Signal(str, bool, object, str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create transfer form and progress state."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        intro = QLabel(
            "Transfer through current verified SSH connection. SFTP avoids shell quoting and "
            "does not execute remote command strings."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        local_row = QWidget()
        local_layout = QHBoxLayout(local_row)
        local_layout.setContentsMargins(0, 0, 0, 0)
        self.local_edit = QLineEdit()
        self.local_edit.setClearButtonEnabled(True)
        describe_widget(
            self.local_edit,
            "Local transfer path",
            "Local source for upload or local destination for download.",
        )
        local_layout.addWidget(self.local_edit, 1)
        self.browse_button = QPushButton("Browse…")
        describe_widget(
            self.browse_button,
            "Browse local path",
            "Choose local file or directory.",
        )
        self.browse_button.clicked.connect(self._browse)
        local_layout.addWidget(self.browse_button)
        form.addRow("Local path", local_row)
        self.remote_edit = QLineEdit()
        self.remote_edit.setClearButtonEnabled(True)
        self.remote_edit.setPlaceholderText("/remote/path")
        describe_widget(
            self.remote_edit,
            "Remote transfer path",
            "Remote source for download or remote destination for upload.",
        )
        form.addRow("Remote path", self.remote_edit)
        self.recursive = QCheckBox("Transfer directory recursively")
        describe_widget(
            self.recursive,
            "Recursive directory transfer",
            "Include directory contents recursively and preserve supported metadata.",
        )
        form.addRow("Options", self.recursive)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.upload_button = QPushButton("Upload local → remote")
        describe_widget(
            self.upload_button,
            "Upload with SFTP",
            "Copy selected local path to remote path over verified SSH connection.",
        )
        self.upload_button.clicked.connect(lambda: self._request(True))
        buttons.addWidget(self.upload_button)
        self.download_button = QPushButton("Download remote → local")
        describe_widget(
            self.download_button,
            "Download with SFTP",
            "Copy selected remote path to local path over verified SSH connection.",
        )
        self.download_button.clicked.connect(lambda: self._request(False))
        buttons.addWidget(self.download_button)
        layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        describe_widget(self.progress, "Transfer progress", "Current SFTP transfer progress.")
        layout.addWidget(self.progress)
        self.status = QLabel("No transfer running")
        self.status.setAccessibleName("Transfer status")
        layout.addWidget(self.status)
        layout.addStretch()
        self._operation_id = ""
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        """Enable transfer actions only during SSH connection."""
        self.upload_button.setEnabled(connected)
        self.download_button.setEnabled(connected)

    def update_progress(self, operation_id: str, copied: int, total: int) -> None:
        """Update active operation byte progress."""
        if operation_id != self._operation_id:
            return
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(int(copied * 100 / total), 100))
            self.progress.setFormat(f"%p% · {copied:,} / {total:,} bytes")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat(f"{copied:,} bytes")

    def finish(self, operation_id: str, success: bool, message: str) -> None:
        """Show transfer completion or failure without relying on colour."""
        if operation_id != self._operation_id:
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if success else 0)
        self.progress.setFormat("Completed" if success else "Failed")
        self.status.setText(("Success: " if success else "Failed: ") + message)
        self.upload_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self._operation_id = ""

    def _browse(self) -> None:
        if self.recursive.isChecked():
            path = QFileDialog.getExistingDirectory(
                self, "Choose local directory", str(Path.home())
            )
        else:
            path, _selected_filter = QFileDialog.getOpenFileName(
                self,
                "Choose local file",
                str(Path.home()),
                "All files (*)",
            )
        if path:
            self.local_edit.setText(path)

    def _request(self, upload: bool) -> None:
        local_path = Path(self.local_edit.text().strip()).expanduser()
        remote_path = self.remote_edit.text().strip()
        if not self.local_edit.text().strip() or not remote_path:
            QMessageBox.warning(self, "Missing path", "Both local and remote paths are required.")
            return
        if upload and not local_path.exists():
            QMessageBox.warning(self, "Local path not found", str(local_path))
            return
        if upload and local_path.is_dir() and not self.recursive.isChecked():
            QMessageBox.warning(
                self,
                "Directory needs recursive option",
                "Enable recursive transfer to upload a directory.",
            )
            return
        self._operation_id = f"transfer.{uuid4().hex}"
        self.progress.setRange(0, 0)
        self.progress.setFormat("Starting…")
        self.status.setText("Transfer running")
        self.upload_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.transfer_requested.emit(
            self._operation_id,
            upload,
            local_path,
            remote_path,
            self.recursive.isChecked(),
        )


class TunnelPanel(QWidget):
    """Create and stop local, remote, and SOCKS SSH forwards."""

    start_requested = Signal(object)
    stop_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create tunnel form and active-list table."""
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        intro = QLabel(
            "Forwarding uses current verified SSH connection. Loopback bind is safest default; "
            "port 0 asks operating system/server to choose a free port."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Local: this computer → remote destination", TunnelKind.LOCAL.value)
        self.kind_combo.addItem("Remote: SSH server → local destination", TunnelKind.REMOTE.value)
        self.kind_combo.addItem("Dynamic: local SOCKS proxy", TunnelKind.SOCKS.value)
        describe_widget(
            self.kind_combo, "Tunnel type", "Choose local, remote, or dynamic SOCKS forwarding."
        )
        self.kind_combo.currentIndexChanged.connect(self._kind_changed)
        form.addRow("Type", self.kind_combo)
        self.listen_host = QLineEdit("127.0.0.1")
        describe_widget(
            self.listen_host,
            "Tunnel listen address",
            "Address that accepts connections. Keep 127.0.0.1 unless exposure is intentional.",
        )
        form.addRow("Listen address", self.listen_host)
        self.listen_port = QSpinBox()
        self.listen_port.setRange(0, 65535)
        self.listen_port.setValue(8080)
        describe_widget(
            self.listen_port, "Tunnel listen port", "Port to listen on; 0 chooses a free port."
        )
        form.addRow("Listen port", self.listen_port)
        self.destination_host = QLineEdit("127.0.0.1")
        describe_widget(
            self.destination_host,
            "Tunnel destination host",
            "Host reached from opposite side of tunnel.",
        )
        form.addRow("Destination host", self.destination_host)
        self.destination_port = QSpinBox()
        self.destination_port.setRange(1, 65535)
        self.destination_port.setValue(80)
        describe_widget(self.destination_port, "Tunnel destination port", "TCP destination port.")
        form.addRow("Destination port", self.destination_port)
        layout.addLayout(form)
        self.start_button = QPushButton("Start tunnel")
        describe_widget(
            self.start_button,
            "Start SSH tunnel",
            "Create forwarding listener after validation and exposure warning if needed.",
        )
        self.start_button.clicked.connect(self._request_start)
        layout.addWidget(self.start_button)
        layout.addWidget(QLabel("Active tunnels"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Type", "Listen", "Destination", "State", "ID"])
        self.table.setColumnHidden(4, True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        describe_widget(
            self.table,
            "Active SSH tunnels",
            "Current forwarding listeners and destinations with explicit running state.",
        )
        layout.addWidget(self.table)
        self.stop_button = QPushButton("Stop selected tunnel")
        describe_widget(
            self.stop_button, "Stop selected tunnel", "Close selected forwarding listener."
        )
        self.stop_button.clicked.connect(self._request_stop)
        layout.addWidget(self.stop_button)
        self._pending: dict[str, TunnelSpec] = {}
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        """Enable tunnel creation only while connected."""
        self.start_button.setEnabled(connected)
        self.stop_button.setEnabled(connected and self.table.rowCount() > 0)
        if not connected:
            self.table.setRowCount(0)
            self._pending.clear()

    def tunnel_started(self, tunnel_id: str, actual_port: int) -> None:
        """Add running tunnel to table using actual dynamically selected port."""
        spec = self._pending.get(tunnel_id)
        if spec is None:
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        destination = (
            "Chosen per SOCKS request"
            if spec.kind is TunnelKind.SOCKS
            else f"{spec.destination_host}:{spec.destination_port}"
        )
        values = [
            spec.kind.value.title(),
            f"{spec.listen_host or '*'}:{actual_port}",
            destination,
            "Running",
            tunnel_id,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == _TUNNEL_ID_COLUMN:
                item.setData(Qt.ItemDataRole.UserRole, tunnel_id)
            self.table.setItem(row, column, item)
        self.table.selectRow(row)
        self.stop_button.setEnabled(True)

    def tunnel_stopped(self, tunnel_id: str) -> None:
        """Remove stopped tunnel from table."""
        self._pending.pop(tunnel_id, None)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 4)
            if item is not None and item.text() == tunnel_id:
                self.table.removeRow(row)
                break
        self.stop_button.setEnabled(self.table.rowCount() > 0)

    def _kind_changed(self) -> None:
        socks = self.kind_combo.currentData() == TunnelKind.SOCKS.value
        self.destination_host.setEnabled(not socks)
        self.destination_port.setEnabled(not socks)

    def _request_start(self) -> None:
        kind_value = self.kind_combo.currentData()
        try:
            kind = TunnelKind(str(kind_value))
        except ValueError:
            kind = TunnelKind.LOCAL
        try:
            spec = TunnelSpec(
                id=f"tunnel.{uuid4().hex}",
                kind=kind,
                listen_host=self.listen_host.text().strip(),
                listen_port=self.listen_port.value(),
                destination_host=self.destination_host.text().strip(),
                destination_port=self.destination_port.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid tunnel", str(error))
            return
        if not spec.is_loopback and not ask_yes_no(
            self,
            "Expose tunnel beyond this computer?",
            "Listen address is not loopback and may expose forwarded service to other systems.",
            informative_text=(
                "Continue only when network exposure and firewall rules are intentional."
            ),
        ):
            return
        self._pending[spec.id] = spec
        self.start_requested.emit(spec)

    def _request_stop(self) -> None:
        row = self.table.currentRow()
        item = self.table.item(row, 4) if row >= 0 else None
        if item is not None:
            self.stop_requested.emit(item.text())
