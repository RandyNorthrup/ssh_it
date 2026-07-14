"""Application bootstrap."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ssh_it import __version__
from ssh_it.library import CommandLibrary
from ssh_it.ui.main_window import MainWindow

if TYPE_CHECKING:
    from collections.abc import Sequence

_SMOKE_TEST_ARGUMENT = "--smoke-test"


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create configured QApplication for production or GUI tests."""
    app = QApplication(list(argv) if argv is not None else sys.argv)
    QCoreApplication.setOrganizationName("SSH It")
    QCoreApplication.setOrganizationDomain("ssh-it.local")
    QCoreApplication.setApplicationName("SSH It")
    QCoreApplication.setApplicationVersion(__version__)
    app.setStyleSheet(
        "QWidget { font-size: 10pt; }"
        "QLineEdit, QComboBox, QSpinBox, QPushButton, QToolButton { min-height: 28px; }"
        "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPushButton:focus, "
        "QToolButton:focus, QTableWidget:focus, QListWidget:focus { "
        "border: 2px solid palette(highlight); }"
        "QLabel#sectionTitle { font-size: 13pt; font-weight: 600; }"
    )
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    return app


def main(argv: Sequence[str] | None = None) -> int:
    """Load validated resources, show main window, and run Qt event loop."""
    arguments = list(argv) if argv is not None else sys.argv
    smoke_test = _SMOKE_TEST_ARGUMENT in arguments
    qt_arguments = [argument for argument in arguments if argument != _SMOKE_TEST_ARGUMENT]
    app = create_application(qt_arguments)
    try:
        library = CommandLibrary.load_bundled()
    except (OSError, ValueError) as error:
        QMessageBox.critical(
            None,
            "SSH It could not start",
            f"Bundled command library failed validation:\n{error}",
        )
        return 2
    window = MainWindow(library)
    if smoke_test:
        window.close()
        return 0
    window.show()
    return app.exec()
