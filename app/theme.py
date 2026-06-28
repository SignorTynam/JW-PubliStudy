from __future__ import annotations

from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            background: #f6f7f9;
            color: #172033;
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 14px;
        }

        QMainWindow {
            background: #f6f7f9;
        }

        QWidget#Sidebar {
            background: #172033;
            border-right: 1px solid #101827;
        }

        QLabel#SidebarTitle {
            background: transparent;
            color: #ffffff;
            font-size: 18px;
            font-weight: 700;
            padding: 8px 12px 18px 12px;
        }

        QPushButton#NavButton {
            background: transparent;
            color: #cbd4e1;
            border: none;
            border-radius: 8px;
            padding: 11px 14px;
            text-align: left;
            font-weight: 600;
        }

        QPushButton#NavButton:hover {
            background: #243149;
            color: #ffffff;
        }

        QPushButton#NavButton[active="true"] {
            background: #e8f0ff;
            color: #183a67;
        }

        QPushButton#PrimaryButton,
        QPushButton#SecondaryButton,
        QPushButton#DangerButton,
        QPushButton#SearchButton {
            border-radius: 8px;
            padding: 10px 16px;
            font-weight: 700;
        }

        QPushButton#PrimaryButton,
        QPushButton#SearchButton {
            background: #1d4f8f;
            color: #ffffff;
            border: 1px solid #1d4f8f;
        }

        QPushButton#PrimaryButton:hover,
        QPushButton#SearchButton:hover {
            background: #183f72;
            border-color: #183f72;
        }

        QPushButton#SecondaryButton {
            background: #ffffff;
            color: #243149;
            border: 1px solid #cfd8e5;
        }

        QPushButton#SecondaryButton:hover {
            background: #eef3f8;
            border-color: #aebbd0;
        }

        QPushButton#DangerButton {
            background: #ffffff;
            color: #b42318;
            border: 1px solid #f0b8b2;
        }

        QPushButton#DangerButton:hover {
            background: #fff1f0;
            border-color: #e78a82;
        }

        QPushButton:disabled {
            background: #edf0f4;
            color: #98a3b3;
            border-color: #d9e0ea;
        }

        QWidget#ContentRoot {
            background: #f6f7f9;
        }

        QWidget#TopBar {
            background: #ffffff;
            border-bottom: 1px solid #e3e7ee;
        }

        QLabel#TopBarTitle {
            background: transparent;
            color: #172033;
            font-size: 16px;
            font-weight: 700;
        }

        QWidget#Page {
            background: #f6f7f9;
        }

        QLabel#PageTitle {
            background: transparent;
            color: #111827;
            font-size: 30px;
            font-weight: 750;
        }

        QLabel#PageSubtitle,
        QLabel#PlaceholderText,
        QLabel#SettingsDescription,
        QLabel#EmptyState {
            background: transparent;
            color: #5e6b80;
            font-size: 15px;
        }

        QLabel#EmptyState {
            padding: 38px;
            border: 1px dashed #c7d1df;
            border-radius: 8px;
            background: #ffffff;
        }

        QWidget#Card {
            background: #ffffff;
            border: 1px solid #e1e6ee;
            border-radius: 8px;
        }

        QLabel#CardTitle {
            background: transparent;
            color: #172033;
            font-size: 16px;
            font-weight: 700;
        }

        QLabel#CardDescription {
            background: transparent;
            color: #66758a;
            font-size: 14px;
        }

        QLabel#FieldLabel {
            background: transparent;
            color: #172033;
            font-weight: 700;
        }

        QWidget#ToolbarFrame {
            background: #ffffff;
            border: 1px solid #e1e6ee;
            border-radius: 8px;
        }

        QComboBox,
        QComboBox#FilterCombo {
            background: #ffffff;
            border: 1px solid #cfd8e5;
            border-radius: 8px;
            padding: 8px 12px;
            min-width: 220px;
        }

        QComboBox#FilterCombo {
            min-width: 150px;
        }

        QComboBox:hover,
        QComboBox#FilterCombo:hover {
            border-color: #8aa4c8;
        }

        QComboBox::drop-down,
        QComboBox#FilterCombo::drop-down {
            border: none;
            width: 28px;
        }

        QLineEdit,
        QLineEdit#SearchInput {
            background: #ffffff;
            border: 1px solid #cfd8e5;
            border-radius: 8px;
            padding: 8px 12px;
        }

        QLineEdit#SearchInput {
            padding: 10px 12px;
            font-size: 15px;
        }

        QLineEdit:focus,
        QLineEdit#SearchInput:focus {
            border-color: #1d4f8f;
        }

        QDialog,
        QMessageBox {
            background: #f6f7f9;
        }

        QTableWidget#PublicationsTable,
        QTableWidget#ResultsTable {
            background: #ffffff;
            border: 1px solid #e1e6ee;
            border-radius: 8px;
            gridline-color: #edf1f6;
            selection-background-color: #dceaff;
            selection-color: #172033;
            alternate-background-color: #f8fafc;
        }

        QTableWidget#PublicationsTable::item,
        QTableWidget#ResultsTable::item {
            padding: 8px;
        }

        QFrame#DetailPanel {
            background: #ffffff;
            border: 1px solid #e1e6ee;
            border-radius: 8px;
        }

        QLabel#DetailTitle {
            background: transparent;
            color: #172033;
            font-size: 17px;
            font-weight: 750;
        }

        QLabel#DetailMeta {
            background: transparent;
            color: #5e6b80;
            font-size: 13px;
        }

        QTextEdit#ChunkText {
            background: #f8fafc;
            border: 1px solid #dbe3ee;
            border-radius: 8px;
            padding: 10px;
            color: #172033;
            font-size: 14px;
        }

        QHeaderView::section {
            background: #eef3f8;
            color: #243149;
            border: none;
            border-bottom: 1px solid #dbe3ee;
            padding: 9px 10px;
            font-weight: 700;
        }
        """
    )
