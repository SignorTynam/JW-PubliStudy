from __future__ import annotations

from PySide6.QtWidgets import QApplication


class Theme:
    SIDEBAR = "#0f172a"
    SIDEBAR_SURFACE = "#172033"
    MAIN_BG = "#f8fafc"
    CARD = "#ffffff"
    BORDER = "#e2e8f0"
    BORDER_STRONG = "#cbd5e1"
    TEXT = "#0f172a"
    TEXT_SECONDARY = "#475569"
    TEXT_MUTED = "#64748b"
    PRIMARY = "#2563eb"
    PRIMARY_HOVER = "#1d4ed8"
    PRIMARY_PRESSED = "#1e40af"
    ACCENT = "#6366f1"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    ERROR = "#dc2626"


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(
        f"""
        * {{
            font-family: "Segoe UI", Arial, sans-serif;
            font-size: 14px;
        }}

        QWidget {{
            background: {Theme.MAIN_BG};
            color: {Theme.TEXT};
        }}

        QMainWindow {{
            background: {Theme.MAIN_BG};
        }}

        QWidget#ContentRoot,
        QWidget#Page,
        QWidget#ChatPanel {{
            background: {Theme.MAIN_BG};
        }}

        QWidget#Sidebar {{
            background: {Theme.SIDEBAR};
            border-right: 1px solid #020617;
        }}

        QLabel#SidebarTitle {{
            background: transparent;
            color: #f8fafc;
            font-size: 20px;
            font-weight: 800;
            padding: 8px 6px 2px 6px;
        }}

        QLabel#SidebarSubtitle,
        QLabel#SidebarAIText {{
            background: transparent;
            color: #cbd5e1;
            font-size: 12px;
        }}

        QLabel#SidebarAIStatus {{
            background: #1e293b;
            color: #e2e8f0;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 11px 12px;
            font-weight: 700;
        }}

        QLabel#SidebarAIStatus[status="ready"] {{
            background: #052e1a;
            color: #bbf7d0;
            border-color: #15803d;
        }}

        QLabel#SidebarAIStatus[status="failed"],
        QLabel#SidebarAIStatus[status="error"] {{
            background: #450a0a;
            color: #fecaca;
            border-color: #b91c1c;
        }}

        QLabel#SidebarAIStatus[status="manual_mode"] {{
            background: #312e81;
            color: #e0e7ff;
            border-color: #6366f1;
        }}

        QLabel#SidebarAIStatus[status="downloading"],
        QLabel#SidebarAIStatus[status="starting"] {{
            background: #422006;
            color: #fed7aa;
            border-color: #c2410c;
        }}

        QPushButton#NavButton {{
            background: transparent;
            color: #cbd5e1;
            border: none;
            border-radius: 12px;
            padding: 12px 14px;
            text-align: left;
            font-weight: 700;
        }}

        QPushButton#NavButton:hover {{
            background: #1e293b;
            color: #ffffff;
        }}

        QPushButton#NavButton[active="true"] {{
            background: {Theme.PRIMARY};
            color: #ffffff;
        }}

        QWidget#TopBar {{
            background: #ffffff;
            border-bottom: 1px solid {Theme.BORDER};
        }}

        QLabel#TopBarTitle {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 17px;
            font-weight: 800;
        }}

        QLabel#TopBarPrivacy {{
            background: #eef2ff;
            color: #3730a3;
            border: 1px solid #c7d2fe;
            border-radius: 999px;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 800;
        }}

        QLabel#PageTitle {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 31px;
            font-weight: 800;
        }}

        QLabel#PageSubtitle,
        QLabel#PlaceholderText,
        QLabel#SettingsDescription {{
            background: transparent;
            color: {Theme.TEXT_SECONDARY};
            font-size: 15px;
            line-height: 1.35;
        }}

        QFrame#HeroCard {{
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, stop: 0 #ffffff, stop: 0.58 #f8fafc, stop: 1 #eef2ff);
            border: 1px solid {Theme.BORDER};
            border-radius: 18px;
        }}

        QLabel#HeroTitle {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 28px;
            font-weight: 800;
        }}

        QLabel#HeroSubtitle {{
            background: transparent;
            color: {Theme.TEXT_SECONDARY};
            font-size: 15px;
        }}

        QFrame#Card,
        QFrame#SectionCard,
        QFrame#SettingsSection,
        QFrame#DetailPanel,
        QFrame#ModelStatus,
        QFrame#ToolbarFrame {{
            background: {Theme.CARD};
            border: 1px solid {Theme.BORDER};
            border-radius: 14px;
        }}

        QFrame#MetricCard {{
            background: {Theme.CARD};
            border: 1px solid {Theme.BORDER};
            border-radius: 14px;
        }}

        QFrame#InfoRow {{
            background: transparent;
            border: none;
        }}

        QLabel#MetricValue {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 24px;
            font-weight: 800;
        }}

        QLabel#MetricLabel {{
            background: transparent;
            color: {Theme.TEXT_MUTED};
            font-size: 13px;
            font-weight: 700;
        }}

        QLabel#CardTitle,
        QLabel#SectionTitle,
        QLabel#DetailTitle {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 17px;
            font-weight: 800;
        }}

        QLabel#CardDescription,
        QLabel#SectionDescription,
        QLabel#DetailMeta {{
            background: transparent;
            color: {Theme.TEXT_SECONDARY};
            font-size: 13px;
        }}

        QLabel#FieldLabel {{
            background: transparent;
            color: {Theme.TEXT};
            font-size: 13px;
            font-weight: 800;
        }}

        QLabel#EmptyState {{
            background: {Theme.CARD};
            color: {Theme.TEXT_SECONDARY};
            border: 1px dashed {Theme.BORDER_STRONG};
            border-radius: 16px;
            padding: 34px;
            font-size: 15px;
        }}

        QLabel#StatusBadge {{
            background: #f1f5f9;
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.BORDER};
            border-radius: 999px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 800;
        }}

        QLabel#StatusBadge[status="ready"],
        QLabel#StatusBadge[status="indexed"],
        QLabel#StatusBadge[status="success"] {{
            background: #dcfce7;
            color: #166534;
            border-color: #86efac;
        }}

        QLabel#StatusBadge[status="error"],
        QLabel#StatusBadge[status="failed"] {{
            background: #fee2e2;
            color: #991b1b;
            border-color: #fecaca;
        }}

        QLabel#StatusBadge[status="warning"],
        QLabel#StatusBadge[status="imported"],
        QLabel#StatusBadge[status="pending_indexing"],
        QLabel#StatusBadge[status="model_missing"],
        QLabel#StatusBadge[status="runtime_missing"] {{
            background: #fef3c7;
            color: #92400e;
            border-color: #fde68a;
        }}

        QLabel#StatusBadge[status="manual_mode"] {{
            background: #e0e7ff;
            color: #3730a3;
            border-color: #c7d2fe;
        }}

        QLabel#PathLabel,
        QLabel#MaintenanceReport,
        QLabel#InlineAlert {{
            background: #f8fafc;
            border: 1px solid {Theme.BORDER};
            border-radius: 12px;
            padding: 10px 12px;
            color: {Theme.TEXT_SECONDARY};
        }}

        QLabel#PrivacyWarning {{
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-radius: 12px;
            padding: 10px 12px;
            color: #92400e;
        }}

        QPushButton#PrimaryButton,
        QPushButton#SecondaryButton,
        QPushButton#DangerButton,
        QPushButton#SearchButton {{
            border-radius: 11px;
            padding: 10px 16px;
            min-height: 20px;
            font-weight: 800;
        }}

        QPushButton#PrimaryButton,
        QPushButton#SearchButton {{
            background: {Theme.PRIMARY};
            color: #ffffff;
            border: 1px solid {Theme.PRIMARY};
        }}

        QPushButton#PrimaryButton:hover,
        QPushButton#SearchButton:hover {{
            background: {Theme.PRIMARY_HOVER};
            border-color: {Theme.PRIMARY_HOVER};
        }}

        QPushButton#PrimaryButton:pressed,
        QPushButton#SearchButton:pressed {{
            background: {Theme.PRIMARY_PRESSED};
            border-color: {Theme.PRIMARY_PRESSED};
        }}

        QPushButton#SecondaryButton {{
            background: #ffffff;
            color: #1e293b;
            border: 1px solid {Theme.BORDER_STRONG};
        }}

        QPushButton#SecondaryButton:hover {{
            background: #f8fafc;
            border-color: #94a3b8;
        }}

        QPushButton#DangerButton {{
            background: #fff7f7;
            color: {Theme.ERROR};
            border: 1px solid #fecaca;
        }}

        QPushButton#DangerButton:hover {{
            background: #fee2e2;
            border-color: #fca5a5;
        }}

        QPushButton:disabled {{
            background: #f1f5f9;
            color: #94a3b8;
            border-color: {Theme.BORDER};
        }}

        QLineEdit,
        QLineEdit#SearchInput,
        QTextEdit,
        QTextEdit#ChatInput,
        QTextEdit#ChunkText,
        QTextBrowser#ChatHistory,
        QComboBox,
        QComboBox#FilterCombo,
        QSpinBox,
        QDoubleSpinBox {{
            background: #ffffff;
            border: 1px solid {Theme.BORDER_STRONG};
            border-radius: 11px;
            padding: 9px 12px;
            color: {Theme.TEXT};
            selection-background-color: #bfdbfe;
        }}

        QLineEdit#SearchInput {{
            padding: 12px 14px;
            font-size: 15px;
        }}

        QTextEdit#ChatInput {{
            border-radius: 16px;
            padding: 13px 14px;
            font-size: 15px;
        }}

        QTextEdit#ChunkText,
        QTextBrowser#ChatHistory {{
            background: #f8fafc;
            border-color: {Theme.BORDER};
            padding: 12px;
        }}

        QLineEdit:focus,
        QLineEdit#SearchInput:focus,
        QTextEdit:focus,
        QTextEdit#ChatInput:focus,
        QComboBox:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus {{
            border: 1px solid {Theme.PRIMARY};
        }}

        QComboBox::drop-down,
        QSpinBox::up-button,
        QSpinBox::down-button,
        QDoubleSpinBox::up-button,
        QDoubleSpinBox::down-button {{
            border: none;
            width: 28px;
        }}

        QTabWidget#StudyTabs::pane {{
            border: none;
            background: {Theme.MAIN_BG};
        }}

        QTabBar::tab {{
            background: #e2e8f0;
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.BORDER_STRONG};
            padding: 10px 18px;
            margin-right: 6px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            font-weight: 800;
        }}

        QTabBar::tab:selected {{
            background: #ffffff;
            color: {Theme.TEXT};
            border-color: {Theme.BORDER};
        }}

        QTableWidget#PublicationsTable,
        QTableWidget#ResultsTable {{
            background: #ffffff;
            border: 1px solid {Theme.BORDER};
            border-radius: 14px;
            gridline-color: #eef2f7;
            alternate-background-color: #f8fafc;
            selection-background-color: #dbeafe;
            selection-color: {Theme.TEXT};
        }}

        QTableWidget#PublicationsTable::item,
        QTableWidget#ResultsTable::item {{
            padding: 10px;
            border-bottom: 1px solid #f1f5f9;
        }}

        QHeaderView::section {{
            background: #f8fafc;
            color: #334155;
            border: none;
            border-bottom: 1px solid {Theme.BORDER};
            padding: 11px 10px;
            font-weight: 800;
        }}

        QProgressBar#AIProgress {{
            background: #e2e8f0;
            border: 1px solid {Theme.BORDER};
            border-radius: 999px;
            height: 17px;
            text-align: center;
            color: {Theme.TEXT};
            font-size: 12px;
            font-weight: 800;
        }}

        QProgressBar#AIProgress::chunk {{
            background: {Theme.PRIMARY};
            border-radius: 999px;
        }}

        QCheckBox {{
            background: transparent;
            color: {Theme.TEXT};
            font-weight: 700;
            spacing: 8px;
        }}

        QDialog,
        QMessageBox {{
            background: {Theme.MAIN_BG};
        }}

        QScrollArea {{
            border: none;
            background: {Theme.MAIN_BG};
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 2px;
        }}

        QScrollBar::handle:vertical {{
            background: #cbd5e1;
            border-radius: 6px;
            min-height: 32px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: #94a3b8;
        }}

        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        """
    )
