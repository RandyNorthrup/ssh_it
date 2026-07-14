"""Searchable, filterable, favorite-aware command library dock content."""

# Similarity with the credential table is intentional Qt interaction consistency.
# pylint: disable=duplicate-code

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ssh_it.models import CommandTemplate, Risk
from ssh_it.ui.common import describe_widget

if TYPE_CHECKING:
    from ssh_it.library import CommandLibrary
    from ssh_it.settings import SettingsStore


class LibraryPanel(QWidget):
    """Command discovery, detail, copy, insertion, execution, and favorites."""

    command_requested = Signal(object, bool)
    favorite_changed = Signal(str, bool)

    def __init__(
        self,
        library: CommandLibrary,
        settings: SettingsStore,
        parent: QWidget | None = None,
    ) -> None:
        """Build filters, result table, and detail actions."""
        super().__init__(parent)
        self._library = library
        self._settings = settings
        self._favorites = settings.favorite_commands()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Command Library")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        filter_grid = QGridLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("Search title, command, explanation, tag…")
        describe_widget(
            self.search_edit,
            "Search command library",
            "Fuzzy-search command text, title, explanation, vendor, category, and tags.",
        )
        search_label = QLabel("Search")
        search_label.setBuddy(self.search_edit)
        filter_grid.addWidget(search_label, 0, 0)
        filter_grid.addWidget(self.search_edit, 1, 0, 1, 2)

        self.vendor_combo = QComboBox()
        for vendor in library.vendors:
            self.vendor_combo.addItem(vendor, "" if vendor == "All libraries" else vendor)
        describe_widget(self.vendor_combo, "Library vendor filter", "Filter results to one vendor.")
        self.category_combo = QComboBox()
        self.category_combo.addItem("All categories", "")
        for category in library.categories:
            self.category_combo.addItem(category, category)
        describe_widget(
            self.category_combo, "Command category filter", "Filter results by use case."
        )
        self.risk_combo = QComboBox()
        self.risk_combo.addItem("All risk levels", None)
        for risk in Risk:
            self.risk_combo.addItem(risk.value.title(), risk.value)
        describe_widget(
            self.risk_combo, "Command risk filter", "Filter safe, caution, or destructive items."
        )
        filter_grid.addWidget(self.vendor_combo, 2, 0)
        filter_grid.addWidget(self.category_combo, 2, 1)
        filter_grid.addWidget(self.risk_combo, 3, 0)
        self.favorites_only = QCheckBox("Favorites only")
        describe_widget(
            self.favorites_only,
            "Favorite commands only",
            "Show only commands marked as favorites.",
        )
        filter_grid.addWidget(self.favorites_only, 3, 1)
        filter_grid.setColumnStretch(0, 1)
        filter_grid.setColumnStretch(1, 1)
        layout.addLayout(filter_grid)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["★", "Title", "Risk"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, self.table.horizontalHeader().ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, self.table.horizontalHeader().ResizeMode.ResizeToContents
        )
        describe_widget(
            self.table,
            "Command library results",
            "Filtered commands with favorite and risk columns. Select a row for full explanation.",
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(self._item_double_clicked)
        layout.addWidget(self.table, 3)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setMinimumHeight(180)
        describe_widget(
            self.detail,
            "Selected command details",
            "Command text, explanation, vendor, category, risk, tags, and reference source.",
        )
        layout.addWidget(self.detail, 2)

        buttons = QGridLayout()
        self.favorite_button = QPushButton("☆ Favorite")
        self.favorite_button.setCheckable(True)
        describe_widget(
            self.favorite_button,
            "Favorite selected command",
            "Add or remove selected library item from favorites.",
        )
        self.favorite_button.toggled.connect(self._toggle_favorite)
        buttons.addWidget(self.favorite_button, 0, 0)
        self.copy_button = QPushButton("Copy")
        describe_widget(
            self.copy_button, "Copy command", "Copy exact template to system clipboard."
        )
        self.copy_button.clicked.connect(self._copy_selected)
        buttons.addWidget(self.copy_button, 0, 1)
        self.insert_button = QPushButton("Insert")
        describe_widget(
            self.insert_button,
            "Insert command",
            "Fill placeholders if needed, then place command in terminal composer without running.",
        )
        self.insert_button.clicked.connect(lambda: self._request_selected(False))
        buttons.addWidget(self.insert_button, 1, 0)
        self.run_button = QPushButton("Insert and fill")
        describe_widget(
            self.run_button,
            "Insert and fill selected command",
            "Insert template, select first required parameter, and open typed value "
            "IntelliSense. Run after review.",
        )
        self.run_button.clicked.connect(lambda: self._request_selected(True))
        buttons.addWidget(self.run_button, 1, 1)
        buttons.setColumnStretch(0, 1)
        buttons.setColumnStretch(1, 1)
        layout.addLayout(buttons)

        for widget in (
            self.search_edit,
            self.vendor_combo,
            self.category_combo,
            self.risk_combo,
            self.favorites_only,
        ):
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self.refresh)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self.refresh)
            else:
                widget.toggled.connect(self.refresh)
        self.refresh()

    def set_vendor(self, vendor: str) -> None:
        """Synchronize filter from Quick Connect vendor choice."""
        for index in range(self.vendor_combo.count()):
            if self.vendor_combo.itemData(index) == vendor:
                self.vendor_combo.setCurrentIndex(index)
                return
        self.vendor_combo.setCurrentIndex(0)

    def refresh(self, _value: object = None) -> None:
        """Re-query library and preserve selected command when possible."""
        selected = self.selected_template()
        selected_id = selected.id if selected else ""
        risk_value = self.risk_combo.currentData()
        try:
            risk = Risk(str(risk_value)) if risk_value is not None else None
        except ValueError:
            risk = None
        results = self._library.search(
            self.search_edit.text(),
            vendor=str(self.vendor_combo.currentData() or ""),
            category=str(self.category_combo.currentData() or ""),
            risk=risk,
        )
        if self.favorites_only.isChecked():
            results = tuple(item for item in results if item.id in self._favorites)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        select_row = -1
        for row, command in enumerate(results):
            favorite_item = QTableWidgetItem("★" if command.id in self._favorites else "")
            favorite_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            title_item = QTableWidgetItem(command.title)
            title_item.setData(Qt.ItemDataRole.UserRole, command.id)
            title_item.setToolTip(command.command)
            risk_item = QTableWidgetItem(command.risk.value.title())
            risk_item.setToolTip(_risk_explanation(command.risk))
            self.table.setItem(row, 0, favorite_item)
            self.table.setItem(row, 1, title_item)
            self.table.setItem(row, 2, risk_item)
            if command.id == selected_id:
                select_row = row
        if select_row >= 0:
            self.table.selectRow(select_row)
        elif results:
            self.table.selectRow(0)
        else:
            self.detail.setHtml("<p>No commands match current filters.</p>")
            self._enable_actions(False)

    def selected_template(self) -> CommandTemplate | None:
        """Return command mapped to current selected row."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        if item is None:
            return None
        command_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(command_id, str):
            return None
        try:
            return self._library.get(command_id)
        except KeyError:
            return None

    def _selection_changed(self) -> None:
        command = self.selected_template()
        self._enable_actions(command is not None)
        if command is None:
            return
        source = (
            f'<a href="{html.escape(command.source)}">Official/reference documentation</a>'
            if command.source
            else "No source URL supplied"
        )
        self.detail.setHtml(
            f"<h3>{html.escape(command.title)}</h3>"
            f"<pre>{html.escape(command.command)}</pre>"
            f"<p>{html.escape(command.description)}</p>"
            f"<p><b>Risk:</b> {html.escape(command.risk.value.title())} — "
            f"{html.escape(_risk_explanation(command.risk))}<br>"
            f"<b>Vendors:</b> {html.escape(', '.join(command.vendors))}<br>"
            f"<b>Categories:</b> {html.escape(', '.join(command.categories))}<br>"
            f"<b>Tags:</b> {html.escape(', '.join(command.tags))}<br>"
            f"<b>Reference:</b> {source}</p>"
        )
        favorite = command.id in self._favorites
        self.favorite_button.blockSignals(True)
        self.favorite_button.setChecked(favorite)
        self.favorite_button.setText("★ Favorite" if favorite else "☆ Favorite")
        self.favorite_button.blockSignals(False)

    def _enable_actions(self, enabled: bool) -> None:
        self.favorite_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
        self.insert_button.setEnabled(enabled)
        self.run_button.setEnabled(enabled)

    def _toggle_favorite(self, checked: bool) -> None:
        command = self.selected_template()
        if command is None:
            return
        self._settings.set_command_favorite(command.id, checked)
        if checked:
            self._favorites.add(command.id)
        else:
            self._favorites.discard(command.id)
        self.favorite_button.setText("★ Favorite" if checked else "☆ Favorite")
        self.favorite_changed.emit(command.id, checked)
        self.refresh()

    def _copy_selected(self) -> None:
        command = self.selected_template()
        if command is not None:
            QGuiApplication.clipboard().setText(command.command)

    def _request_selected(self, run: bool) -> None:
        command = self.selected_template()
        if command is not None:
            self.command_requested.emit(command, run)

    def _item_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._request_selected(False)


def _risk_explanation(risk: Risk) -> str:
    """Return text so risk never depends on colour alone."""
    if risk is Risk.SAFE:
        return "Read-only or locally preparatory under normal use."
    if risk is Risk.CAUTION:
        return "May expose sensitive output, run continuously, or affect session state."
    return "Can persist changes, replace files, upgrade, restart, or disrupt service."
