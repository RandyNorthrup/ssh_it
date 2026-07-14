"""Searchable public factory-credential reference panel."""

# Similarity with the command table is intentional Qt interaction consistency.
# pylint: disable=duplicate-code

from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ssh_it.credentials import CredentialEntry, CredentialLibrary, PasswordKind
from ssh_it.ui.common import describe_widget


class CredentialLibraryPanel(QWidget):
    """Browse carefully scoped public defaults and explicitly fill Quick Connect."""

    fill_requested = Signal(object, bool)

    def __init__(
        self,
        library: CredentialLibrary,
        parent: QWidget | None = None,
    ) -> None:
        """Build accessible filters, details, masked value, and fill actions."""
        super().__init__(parent)
        self._library = library
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        reviewed = library.reviewed_on.isoformat() if library.reviewed_on else "unknown"
        title = QLabel(f"Default Credentials · {len(library.entries)} references")
        title.setObjectName("sectionTitle")
        title.setToolTip(f"Official-source credential library reviewed {reviewed}.")
        title.setAccessibleDescription(
            f"Public factory credential reference library reviewed {reviewed}."
        )
        layout.addWidget(title)
        warning = QLabel(
            "Authorized devices only. Defaults are product-specific public references, never "
            "tried automatically, and should be replaced immediately."
        )
        warning.setObjectName("securityNotice")
        warning.setWordWrap(True)
        warning.setAccessibleName("Factory credential safety notice")
        layout.addWidget(warning)

        filters = QGridLayout()
        search_label = QLabel("Search")
        self.search_edit = QLineEdit()
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setPlaceholderText("Search vendor, product, username…")
        describe_widget(
            self.search_edit,
            "Search default credentials",
            "Filter public factory references by vendor, product, username, or password type.",
        )
        search_label.setBuddy(self.search_edit)
        filters.addWidget(search_label, 0, 0)
        filters.addWidget(self.search_edit, 1, 0)
        vendor_label = QLabel("Vendor")
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItem("All vendors", "")
        for vendor in library.vendors:
            self.vendor_combo.addItem(vendor, vendor)
        describe_widget(
            self.vendor_combo,
            "Default credential vendor filter",
            "Limit factory reference results to one vendor.",
        )
        vendor_label.setBuddy(self.vendor_combo)
        filters.addWidget(vendor_label, 0, 1)
        filters.addWidget(self.vendor_combo, 1, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Vendor", "Product scope", "Password"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
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
            "Default credential results",
            "Product-scoped public factory credentials. Select a row to inspect its warning "
            "and official source.",
        )
        self.table.itemSelectionChanged.connect(self._selection_changed)
        layout.addWidget(self.table, 3)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setMinimumHeight(150)
        describe_widget(
            self.detail,
            "Selected default credential details",
            "Product scope, explanation, safety warning, and official vendor source.",
        )
        layout.addWidget(self.detail, 2)

        values = QGridLayout()
        username_label = QLabel("Username")
        self.username_edit = QLineEdit()
        self.username_edit.setReadOnly(True)
        describe_widget(
            self.username_edit,
            "Selected factory username",
            "Public default username for the selected product scope.",
        )
        username_label.setBuddy(self.username_edit)
        values.addWidget(username_label, 0, 0)
        values.addWidget(self.username_edit, 1, 0)

        password_label = QLabel("Password")
        password_row = QWidget()
        password_layout = QHBoxLayout(password_row)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(4)
        self.password_edit = QLineEdit()
        self.password_edit.setReadOnly(True)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        describe_widget(
            self.password_edit,
            "Selected factory password",
            "Masked public factory password, blank-password label, or device-label guidance.",
        )
        password_layout.addWidget(self.password_edit, 1)
        self.show_password = QToolButton()
        self.show_password.setText("Show")
        self.show_password.setCheckable(True)
        describe_widget(
            self.show_password,
            "Show selected factory password",
            "Reveal or mask the selected public factory password reference.",
        )
        self.show_password.toggled.connect(self._toggle_password)
        password_layout.addWidget(self.show_password)
        password_label.setBuddy(self.password_edit)
        values.addWidget(password_label, 0, 1)
        values.addWidget(password_row, 1, 1)
        layout.addLayout(values)

        actions = QHBoxLayout()
        self.fill_username_button = QPushButton("Fill username")
        describe_widget(
            self.fill_username_button,
            "Fill factory username",
            "Copy only the selected public default username into Quick Connect.",
        )
        self.fill_username_button.clicked.connect(lambda: self._request_fill(False))
        actions.addWidget(self.fill_username_button)
        self.fill_login_button = QPushButton("Fill username & password")
        describe_widget(
            self.fill_login_button,
            "Fill factory username and password",
            "Explicitly copy the selected product-scoped public factory login into Quick "
            "Connect. This never connects automatically.",
        )
        self.fill_login_button.clicked.connect(lambda: self._request_fill(True))
        actions.addWidget(self.fill_login_button)
        layout.addLayout(actions)

        self.search_edit.textChanged.connect(self.refresh)
        self.vendor_combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def selected_entry(self) -> CredentialEntry | None:
        """Return the entry mapped to the selected result row."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 1)
        if item is None:
            return None
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry_id, str):
            return None
        try:
            return self._library.get(entry_id)
        except KeyError:
            return None

    def set_vendor(self, vendor: str) -> None:
        """Synchronize vendor filter where credential references exist."""
        for index in range(self.vendor_combo.count()):
            if self.vendor_combo.itemData(index) == vendor:
                self.vendor_combo.setCurrentIndex(index)
                return
        self.vendor_combo.setCurrentIndex(0)

    def refresh(self, _value: object = None) -> None:
        """Apply filters and preserve selection when possible."""
        current = self.selected_entry()
        current_id = current.id if current else ""
        entries = self._library.search(
            self.search_edit.text(),
            vendor=str(self.vendor_combo.currentData() or ""),
        )
        self.table.setRowCount(len(entries))
        selected_row = -1
        for row, entry in enumerate(entries):
            vendor_item = QTableWidgetItem(entry.vendor)
            product_item = QTableWidgetItem(entry.product)
            product_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            status_item = QTableWidgetItem(entry.password_status)
            status_item.setToolTip(entry.warning)
            self.table.setItem(row, 0, vendor_item)
            self.table.setItem(row, 1, product_item)
            self.table.setItem(row, 2, status_item)
            if entry.id == current_id:
                selected_row = row
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        elif entries:
            self.table.selectRow(0)
        else:
            self.detail.setHtml("<p>No factory references match current filters.</p>")
            self._set_actions_enabled(False)
            self.username_edit.clear()
            self.password_edit.clear()

    def _selection_changed(self) -> None:
        entry = self.selected_entry()
        self._set_actions_enabled(entry is not None)
        if entry is None:
            return
        self.detail.setHtml(
            f"<h3>{html.escape(entry.product)}</h3>"
            f"<p><b>Scope:</b> {html.escape(entry.vendor)} · "
            f"{html.escape(entry.password_status)}</p>"
            f"<p>{html.escape(entry.description)}</p>"
            f"<p><b>Safety:</b> {html.escape(entry.warning)}</p>"
            f'<p><a href="{html.escape(entry.source)}">Official vendor documentation</a></p>'
        )
        self.username_edit.setText(entry.username)
        self.show_password.setChecked(False)
        if entry.password_kind is PasswordKind.STATIC:
            self.password_edit.setPlaceholderText("")
            self.password_edit.setText(entry.password or "")
        elif entry.password_kind is PasswordKind.BLANK:
            self.password_edit.clear()
            self.password_edit.setPlaceholderText("(intentionally blank)")
        else:
            self.password_edit.clear()
            self.password_edit.setPlaceholderText("Read product instructions or device label")
        self.show_password.setEnabled(entry.password_kind is PasswordKind.STATIC)
        self.fill_login_button.setEnabled(entry.can_fill_password)

    def _set_actions_enabled(self, enabled: bool) -> None:
        entry = self.selected_entry()
        self.fill_username_button.setEnabled(enabled)
        self.fill_login_button.setEnabled(enabled and entry is not None and entry.can_fill_password)
        self.show_password.setEnabled(
            enabled and entry is not None and entry.password_kind is PasswordKind.STATIC
        )

    def _toggle_password(self, shown: bool) -> None:
        self.password_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self.show_password.setText("Hide" if shown else "Show")

    def _request_fill(self, include_password: bool) -> None:
        entry = self.selected_entry()
        if entry is not None:
            self.fill_requested.emit(entry, include_password and entry.can_fill_password)
