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
        QLabel#SettingsDescription {
            background: transparent;
            color: #5e6b80;
            font-size: 15px;
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

        QComboBox {
            background: #ffffff;
            border: 1px solid #cfd8e5;
            border-radius: 8px;
            padding: 8px 12px;
            min-width: 220px;
        }

        QComboBox:hover {
            border-color: #8aa4c8;
        }

        QComboBox::drop-down {
            border: none;
            width: 28px;
        }
        """
    )
