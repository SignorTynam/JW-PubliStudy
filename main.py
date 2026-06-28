from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.i18n import I18n
from app.main_window import MainWindow
from app.settings import AppSettings
from app.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("JW PubliStudy")
    app.setOrganizationName("JW PubliStudy")

    project_root = Path(__file__).resolve().parent
    settings = AppSettings()
    translations = I18n(
        translations_dir=project_root / "resources" / "i18n",
        language=settings.language(),
    )

    apply_theme(app)

    window = MainWindow(translations=translations, settings=settings)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
