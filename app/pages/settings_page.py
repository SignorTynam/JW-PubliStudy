from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import I18n
from app.services.local_llm_client import LocalLLMClient
from app.settings import AppSettings


class SettingsPage(QWidget):
    language_changed = Signal(str)

    LANGUAGE_OPTIONS = (
        ("it", "settings.language_option.it"),
        ("al", "settings.language_option.al"),
        ("en", "settings.language_option.en"),
    )

    def __init__(self, translations: I18n, settings: AppSettings, llm_client: LocalLLMClient) -> None:
        super().__init__()
        self._translations = translations
        self._settings = settings
        self._llm_client = llm_client

        self.setObjectName("Page")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(18)

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        layout.addWidget(self._title)

        self._description = QLabel()
        self._description.setObjectName("SettingsDescription")
        self._description.setWordWrap(True)
        layout.addWidget(self._description)

        self._language_label = QLabel()
        self._language_label.setObjectName("FieldLabel")
        layout.addWidget(self._language_label)

        self._language_combo = QComboBox()
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self._language_combo)

        ai_section = QFrame()
        ai_section.setObjectName("SettingsSection")
        ai_layout = QVBoxLayout(ai_section)
        ai_layout.setContentsMargins(18, 18, 18, 18)
        ai_layout.setSpacing(12)

        self._ai_title = QLabel()
        self._ai_title.setObjectName("SectionTitle")
        self._ai_description = QLabel()
        self._ai_description.setObjectName("SectionDescription")
        self._ai_description.setWordWrap(True)
        ai_layout.addWidget(self._ai_title)
        ai_layout.addWidget(self._ai_description)

        form = QFormLayout()
        form.setSpacing(12)
        self._endpoint_label = QLabel()
        self._endpoint_input = QLineEdit()
        self._model_label = QLabel()
        self._model_input = QLineEdit()
        self._temperature_label = QLabel()
        self._temperature_input = QDoubleSpinBox()
        self._temperature_input.setRange(0.0, 1.0)
        self._temperature_input.setSingleStep(0.1)
        self._temperature_input.setDecimals(2)
        self._max_tokens_label = QLabel()
        self._max_tokens_input = QSpinBox()
        self._max_tokens_input.setRange(128, 4096)
        self._timeout_label = QLabel()
        self._timeout_input = QSpinBox()
        self._timeout_input.setRange(10, 300)
        self._retrieval_limit_label = QLabel()
        self._retrieval_limit_input = QSpinBox()
        self._retrieval_limit_input.setRange(1, 12)

        form.addRow(self._endpoint_label, self._endpoint_input)
        form.addRow(self._model_label, self._model_input)
        form.addRow(self._temperature_label, self._temperature_input)
        form.addRow(self._max_tokens_label, self._max_tokens_input)
        form.addRow(self._timeout_label, self._timeout_input)
        form.addRow(self._retrieval_limit_label, self._retrieval_limit_input)
        ai_layout.addLayout(form)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)
        self._save_ai_button = QPushButton()
        self._save_ai_button.setObjectName("PrimaryButton")
        self._save_ai_button.clicked.connect(self._save_ai_settings)
        self._reset_ai_button = QPushButton()
        self._reset_ai_button.setObjectName("SecondaryButton")
        self._reset_ai_button.clicked.connect(self._reset_ai_settings)
        self._test_ai_button = QPushButton()
        self._test_ai_button.setObjectName("SecondaryButton")
        self._test_ai_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self._reset_ai_button)
        button_layout.addWidget(self._test_ai_button)
        button_layout.addWidget(self._save_ai_button)
        ai_layout.addLayout(button_layout)
        layout.addWidget(ai_section)
        layout.addStretch(1)

        self._load_ai_settings()
        self.update_texts()

    def update_texts(self) -> None:
        current_language = self._translations.language
        self._title.setText(self._translations.t("settings.title"))
        self._description.setText(self._translations.t("settings.language_description"))
        self._language_label.setText(self._translations.t("settings.language"))
        self._ai_title.setText(self._translations.t("settings.ai_section"))
        self._ai_description.setText(self._translations.t("settings.ai_description"))
        self._endpoint_label.setText(self._translations.t("settings.ai.endpoint"))
        self._model_label.setText(self._translations.t("settings.ai.model"))
        self._temperature_label.setText(self._translations.t("settings.ai.temperature"))
        self._max_tokens_label.setText(self._translations.t("settings.ai.max_tokens"))
        self._timeout_label.setText(self._translations.t("settings.ai.timeout"))
        self._retrieval_limit_label.setText(self._translations.t("settings.ai.retrieval_limit"))
        self._save_ai_button.setText(self._translations.t("settings.ai.save"))
        self._reset_ai_button.setText(self._translations.t("settings.ai.reset_defaults"))
        self._test_ai_button.setText(self._translations.t("settings.ai.test_connection"))

        self._language_combo.blockSignals(True)
        self._language_combo.clear()
        for language_code, label_key in self.LANGUAGE_OPTIONS:
            self._language_combo.addItem(self._translations.t(label_key), language_code)
        self._language_combo.setCurrentIndex(self._index_for_language(current_language))
        self._language_combo.blockSignals(False)

    def _load_ai_settings(self) -> None:
        self._endpoint_input.setText(self._settings.llm_endpoint_url())
        self._model_input.setText(self._settings.llm_model())
        self._temperature_input.setValue(self._settings.llm_temperature())
        self._max_tokens_input.setValue(self._settings.llm_max_tokens())
        self._timeout_input.setValue(self._settings.llm_timeout_seconds())
        self._retrieval_limit_input.setValue(self._settings.retrieval_limit())

    def _save_ai_settings(self) -> None:
        self._persist_ai_settings()
        self._show_message("common.success", "settings.ai.saved")

    def _persist_ai_settings(self) -> None:
        self._settings.set_llm_endpoint_url(self._endpoint_input.text())
        self._settings.set_llm_model(self._model_input.text())
        self._settings.set_llm_temperature(self._temperature_input.value())
        self._settings.set_llm_max_tokens(self._max_tokens_input.value())
        self._settings.set_llm_timeout_seconds(self._timeout_input.value())
        self._settings.set_retrieval_limit(self._retrieval_limit_input.value())

    def _reset_ai_settings(self) -> None:
        self._settings.reset_llm_defaults()
        self._load_ai_settings()
        self._show_message("common.success", "settings.ai.reset_done")

    def _test_connection(self) -> None:
        self._persist_ai_settings()
        ok = self._llm_client.test_connection(self._settings.llm_config())
        self._show_message(
            "common.success" if ok else "common.error",
            "settings.ai.connection_success" if ok else "settings.ai.connection_failed",
        )

    def _show_message(self, title_key: str, message_key: str) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self._translations.t(title_key))
        dialog.setText(self._translations.t(message_key))
        dialog.addButton(self._translations.t("common.ok"), QMessageBox.ButtonRole.AcceptRole)
        dialog.exec()

    def _on_language_changed(self, index: int) -> None:
        language = self._language_combo.itemData(index)
        if isinstance(language, str) and language != self._translations.language:
            self.language_changed.emit(language)

    def _index_for_language(self, language: str) -> int:
        for index, (language_code, _) in enumerate(self.LANGUAGE_OPTIONS):
            if language_code == language:
                return index
        return 0
