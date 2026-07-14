"""Application bootstrap tests without entering a real event loop."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

import ssh_it.app as app_module
from ssh_it.library import CommandLibrary

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest


class FakeApplication:
    """Small QApplication stand-in capturing bootstrap configuration."""

    last: ClassVar[FakeApplication | None] = None

    def __init__(self, argv: list[str]) -> None:
        """Capture arguments."""
        self.argv = argv
        self.style = ""
        self.attribute: tuple[Qt.ApplicationAttribute, bool] | None = None
        FakeApplication.last = self

    def setStyleSheet(self, style: str) -> None:  # noqa: N802
        """Capture stylesheet."""
        self.style = style

    def setAttribute(self, attribute: Qt.ApplicationAttribute, enabled: bool) -> None:  # noqa: N802
        """Capture application attribute."""
        self.attribute = (attribute, enabled)

    def exec(self) -> int:
        """Return deterministic loop status."""
        return 17


class FakeCoreApplication:
    """Capture organization metadata calls."""

    values: ClassVar[dict[str, str]] = {}

    @classmethod
    def setOrganizationName(cls, value: str) -> None:  # noqa: N802
        """Capture organization."""
        cls.values["organization"] = value

    @classmethod
    def setOrganizationDomain(cls, value: str) -> None:  # noqa: N802
        """Capture domain."""
        cls.values["domain"] = value

    @classmethod
    def setApplicationName(cls, value: str) -> None:  # noqa: N802
        """Capture application name."""
        cls.values["name"] = value

    @classmethod
    def setApplicationVersion(cls, value: str) -> None:  # noqa: N802
        """Capture version."""
        cls.values["version"] = value


class FakeWindow:
    """Main-window stand-in recording display."""

    shown: ClassVar[bool] = False

    def __init__(self, _library: CommandLibrary) -> None:
        """Accept loaded library."""

    def show(self) -> None:
        """Record display."""
        FakeWindow.shown = True

    def close(self) -> None:
        """Support package smoke-test shutdown."""


def test_create_application_configures_qt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bootstrap sets identity, accessibility-friendly style, and explicit attribute."""
    FakeCoreApplication.values.clear()
    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "QCoreApplication", FakeCoreApplication)
    created = app_module.create_application(["ssh-it", "--demo"])
    fake = cast("FakeApplication", created)
    assert fake.argv == ["ssh-it", "--demo"]
    assert "min-height" in fake.style
    assert fake.attribute == (Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    assert FakeCoreApplication.values["organization"] == "SSH It"
    assert FakeCoreApplication.values["domain"] == "ssh-it.local"
    assert FakeCoreApplication.values["name"] == "SSH It"
    assert FakeCoreApplication.values["version"]


def test_main_shows_window_and_returns_event_loop_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful startup validates resources and displays main window."""
    fake_app = FakeApplication(["ssh-it"])
    library = CommandLibrary.load_bundled()
    FakeWindow.shown = False

    def create(_argv: Sequence[str] | None = None) -> QApplication:
        return cast("QApplication", fake_app)

    monkeypatch.setattr(
        app_module,
        "create_application",
        create,
    )
    monkeypatch.setattr(CommandLibrary, "load_bundled", lambda: library)
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)
    assert app_module.main([]) == 17
    assert FakeWindow.shown


def test_main_smoke_test_constructs_then_closes_without_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frozen-package probe validates resources and widgets without hanging in an event loop."""
    fake_app = FakeApplication(["ssh-it"])
    library = CommandLibrary.load_bundled()
    received_arguments: list[str] = []

    def create(arguments: Sequence[str] | None = None) -> QApplication:
        received_arguments.extend(arguments or ())
        return cast("QApplication", fake_app)

    monkeypatch.setattr(app_module, "create_application", create)
    monkeypatch.setattr(CommandLibrary, "load_bundled", lambda: library)
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)
    assert app_module.main(["ssh-it", "--smoke-test"]) == 0
    assert received_arguments == ["ssh-it"]


def test_main_reports_invalid_library(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup fails closed with visible error when package data is invalid."""
    fake_app = FakeApplication(["ssh-it"])
    errors: list[str] = []

    def fail_load() -> CommandLibrary:
        raise ValueError("bad package data")

    def critical(
        _parent: object,
        _title: str,
        message: str,
    ) -> QMessageBox.StandardButton:
        errors.append(message)
        return QMessageBox.StandardButton.Ok

    def create(_argv: Sequence[str] | None = None) -> QApplication:
        return cast("QApplication", fake_app)

    monkeypatch.setattr(
        app_module,
        "create_application",
        create,
    )
    monkeypatch.setattr(CommandLibrary, "load_bundled", fail_load)
    monkeypatch.setattr(QMessageBox, "critical", critical)
    assert app_module.main(cast("Sequence[str]", [])) == 2
    assert errors == ["Bundled command library failed validation:\nbad package data"]
