"""SFTP and tunnel panel interaction tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

import ssh_it.ui.operations as operations_module
from ssh_it.models import TunnelSpec
from ssh_it.ui.operations import TransferPanel, TunnelPanel

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from pytestqt.qtbot import QtBot


def test_transfer_panel_emits_valid_upload_and_tracks_progress(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Validated upload emits typed paths and displays byte completion."""
    panel = TransferPanel()
    qtbot.addWidget(panel)
    panel.set_connected(True)
    source = tmp_path / "upload.txt"
    source.write_text("payload", encoding="utf-8")
    panel.local_edit.setText(str(source))
    panel.remote_edit.setText("/srv/uploads/upload.txt")
    requests: list[tuple[str, bool, object, str, bool]] = []

    def capture(
        operation_id: str,
        upload: bool,
        local_path: object,
        remote_path: str,
        recurse: bool,
    ) -> None:
        requests.append((operation_id, upload, local_path, remote_path, recurse))

    panel.transfer_requested.connect(capture)
    panel.upload_button.click()
    assert requests
    assert requests[0][1] is True
    operation_id = requests[0][0]
    panel.update_progress(operation_id, 5, 10)
    assert panel.progress.value() == 50
    panel.finish(operation_id, True, "done")
    assert panel.progress.value() == 100
    assert panel.status.text() == "Success: done"


def test_tunnel_panel_emits_start_and_stop(qtbot: QtBot) -> None:
    """Loopback tunnel form creates spec and active table controls stop."""
    panel = TunnelPanel()
    qtbot.addWidget(panel)
    panel.set_connected(True)
    panel.listen_port.setValue(0)
    panel.destination_host.setText("db.internal")
    panel.destination_port.setValue(5432)
    started: list[object] = []
    stopped: list[str] = []
    panel.start_requested.connect(started.append)
    panel.stop_requested.connect(stopped.append)
    panel.start_button.click()
    assert len(started) == 1
    spec = started[0]
    assert isinstance(spec, TunnelSpec)
    panel.tunnel_started(spec.id, 41_234)
    assert panel.table.rowCount() == 1
    endpoint_item = panel.table.item(0, 1)
    assert endpoint_item is not None
    assert "41234" in endpoint_item.text()
    panel.stop_button.click()
    assert stopped == [spec.id]
    panel.tunnel_stopped(spec.id)
    assert panel.table.rowCount() == 0


def test_transfer_panel_validation_browse_and_failure_states(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SFTP form blocks unsafe inputs, supports file/directory browse, and reports failure."""
    panel = TransferPanel()
    qtbot.addWidget(panel)
    panel.set_connected(True)
    warnings: list[str] = []

    def warning(
        _parent: QWidget,
        _title: str,
        message: str,
    ) -> QMessageBox.StandardButton:
        warnings.append(message)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "warning", warning)
    panel.upload_button.click()
    assert warnings[-1] == "Both local and remote paths are required."
    panel.local_edit.setText(str(tmp_path / "missing"))
    panel.remote_edit.setText("/srv/data")
    panel.upload_button.click()
    assert "missing" in warnings[-1]

    directory = tmp_path / "folder"
    directory.mkdir()
    panel.local_edit.setText(str(directory))
    panel.upload_button.click()
    assert warnings[-1] == "Enable recursive transfer to upload a directory."

    source = tmp_path / "chosen.txt"
    source.write_text("payload", encoding="utf-8")

    def choose_file(*_args: object, **_kwargs: object) -> tuple[str, str]:
        return str(source), "All files (*)"

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        choose_file,
    )
    panel.recursive.setChecked(False)
    panel.browse_button.click()
    assert panel.local_edit.text() == str(source)

    def choose_directory(*_args: object, **_kwargs: object) -> str:
        return str(directory)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", choose_directory)
    panel.recursive.setChecked(True)
    panel.browse_button.click()
    assert panel.local_edit.text() == str(directory)

    requests: list[tuple[str, bool, object, str, bool]] = []

    def capture(
        operation_id: str,
        upload: bool,
        local: object,
        remote: str,
        recurse: bool,
    ) -> None:
        requests.append((operation_id, upload, local, remote, recurse))

    panel.transfer_requested.connect(capture)
    panel.download_button.click()
    operation_id = requests[-1][0]
    panel.update_progress("different", 1, 0)
    panel.finish("different", False, "ignored")
    panel.update_progress(operation_id, 3, 0)
    assert panel.progress.maximum() == 0
    assert panel.progress.format() == "3 bytes"
    panel.finish(operation_id, False, "permission denied")
    assert panel.status.text() == "Failed: permission denied"
    assert panel.progress.value() == 0


def test_tunnel_panel_socks_validation_exposure_and_unknown_events(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tunnel form handles SOCKS, invalid destinations, exposure refusal, and stale events."""
    panel = TunnelPanel()
    qtbot.addWidget(panel)
    panel.set_connected(True)
    warnings: list[str] = []

    def warning(_parent: QWidget, _title: str, message: str) -> None:
        warnings.append(message)

    monkeypatch.setattr(QMessageBox, "warning", warning)
    panel.destination_host.clear()
    panel.start_button.click()
    assert warnings

    panel.kind_combo.setCurrentIndex(panel.kind_combo.findData("socks"))
    assert not panel.destination_host.isEnabled()
    starts: list[object] = []
    panel.start_requested.connect(starts.append)
    panel.start_button.click()
    assert len(starts) == 1
    spec = starts[0]
    assert isinstance(spec, TunnelSpec)
    panel.tunnel_started("unknown", 9999)
    assert panel.table.rowCount() == 0
    panel.tunnel_started(spec.id, 10_800)
    assert panel.table.rowCount() == 1
    destination_item = panel.table.item(0, 2)
    assert destination_item is not None
    assert "Chosen per SOCKS request" in destination_item.text()
    panel.tunnel_stopped("unknown")
    assert panel.table.rowCount() == 1
    panel.set_connected(False)
    assert panel.table.rowCount() == 0

    panel.set_connected(True)
    panel.kind_combo.setCurrentIndex(panel.kind_combo.findData("local"))
    panel.destination_host.setText("db.internal")
    panel.listen_host.setText("192.0.2.1")
    decisions: list[bool] = []

    def refuse(*_args: object, **_kwargs: object) -> bool:
        decisions.append(False)
        return False

    monkeypatch.setattr(operations_module, "ask_yes_no", refuse)
    before = len(starts)
    panel.start_button.click()
    assert decisions == [False]
    assert len(starts) == before
    panel.stop_button.click()
