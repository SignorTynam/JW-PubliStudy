from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ai.ai_client import AIClient
from app.ai.chat_generation_worker import AIConnectionTestWorker
from app.ai.hardware_check import get_hardware_info
from app.ai.model_catalog import LocalModelSpec, get_model, recommend_model
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager
from app.ai.setup_service import LocalAISetupService
from app.i18n import I18n
from app.paths import AppPaths
from app.services.local_llm_client import is_local_endpoint
from app.services.maintenance_service import IntegrityReport, LibraryStats, MaintenanceResult, MaintenanceService
from app.settings import AppSettings
from app.version import APP_NAME, APP_STAGE, APP_VERSION


class SettingsPage(QWidget):
    language_changed = Signal(str)

    LANGUAGE_OPTIONS = (
        ("it", "settings.language_option.it"),
        ("al", "settings.language_option.al"),
        ("en", "settings.language_option.en"),
    )

    def __init__(
        self,
        translations: I18n,
        settings: AppSettings,
        llm_client: AIClient,
        maintenance_service: MaintenanceService,
        paths: AppPaths,
        model_manager: ModelManager,
        runtime_manager: RuntimeManager,
        ai_setup_service: LocalAISetupService,
    ) -> None:
        super().__init__()
        self._translations = translations
        self._settings = settings
        self._llm_client = llm_client
        self._maintenance_service = maintenance_service
        self._paths = paths
        self._model_manager = model_manager
        self._runtime_manager = runtime_manager
        self._ai_setup_service = ai_setup_service
        self._maintenance_buttons: list[QPushButton] = []
        self._ai_buttons: list[QPushButton] = []
        self._ai_file_buttons: list[QPushButton] = []
        self._recommended_model: LocalModelSpec | None = None
        self._ai_status_message_key = ""
        self._ai_busy = False
        self._startup_elapsed_seconds = 0
        self._connection_thread: QThread | None = None
        self._connection_worker: AIConnectionTestWorker | None = None
        self._startup_timer = QTimer(self)
        self._startup_timer.setInterval(1000)
        self._startup_timer.timeout.connect(self._update_startup_elapsed)

        self.setObjectName("Page")
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(34, 34, 34, 34)
        layout.setSpacing(18)

        self._title = QLabel()
        self._title.setObjectName("PageTitle")
        self._description = QLabel()
        self._description.setObjectName("SettingsDescription")
        self._description.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._description)

        layout.addWidget(self._build_language_section())
        layout.addWidget(self._build_ai_section())
        layout.addWidget(self._build_data_section())
        layout.addWidget(self._build_stats_section())
        layout.addWidget(self._build_maintenance_section())
        layout.addWidget(self._build_about_section())
        layout.addStretch(1)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        self._load_ai_settings()
        self._connect_ai_setup_service()
        self.update_texts()
        self.refresh_stats()

    def update_texts(self) -> None:
        current_language = self._translations.language
        self._title.setText(self._translations.t("settings.title"))
        self._description.setText(self._translations.t("settings.language_description"))

        self._language_section_title.setText(self._translations.t("settings.language_section"))
        self._language_label.setText(self._translations.t("settings.language"))
        self._language_combo.blockSignals(True)
        self._language_combo.clear()
        for language_code, label_key in self.LANGUAGE_OPTIONS:
            self._language_combo.addItem(self._translations.t(label_key), language_code)
        self._language_combo.setCurrentIndex(self._index_for_language(current_language))
        self._language_combo.blockSignals(False)

        self._ai_title.setText(self._translations.t("settings.ai_section"))
        self._ai_description.setText(self._translations.t("settings.ai_description"))
        self._ai_status_title.setText(self._translations.t("settings.ai_status"))
        self._recommended_model_title.setText(self._translations.t("settings.ai_recommended_model"))
        self._installed_model_title.setText(self._translations.t("settings.ai_installed_model"))
        self._required_space_title.setText(self._translations.t("settings.ai_required_space"))
        self._detected_ram_title.setText(self._translations.t("settings.ai_detected_ram"))
        self._optimization_title.setText(self._translations.t("settings.ai_optimization"))
        self._system_title.setText(self._translations.t("settings.ai_system"))
        self._process_title.setText(self._translations.t("settings.ai_process"))
        self._architecture_mode_title.setText(self._translations.t("settings.ai_architecture_mode"))
        self._device_title.setText(self._translations.t("settings.ai_selected_device"))
        self._backend_title.setText(self._translations.t("settings.ai_backend"))
        self._selection_reason_title.setText(self._translations.t("settings.ai_selection_reason"))
        self._fallback_title.setText(self._translations.t("settings.ai_fallback"))
        self._npu_detected_title.setText(self._translations.t("settings.ai_npu_detected"))
        self._npu_status_title.setText(self._translations.t("settings.ai_npu_status"))
        self._optimization_profile_label.setText(self._translations.t("settings.ai_optimization_profile"))
        current_mode = self._settings.ai_optimization_mode()
        self._optimization_profile_combo.blockSignals(True)
        self._optimization_profile_combo.clear()
        for mode in ("automatic", "memory_saver", "performance"):
            self._optimization_profile_combo.addItem(
                self._translations.t(f"settings.ai_optimization_modes.{mode}"),
                mode,
            )
        mode_index = self._optimization_profile_combo.findData(current_mode)
        self._optimization_profile_combo.setCurrentIndex(max(0, mode_index))
        self._optimization_profile_combo.blockSignals(False)
        self._configure_ai_button.setText(self._translations.t("settings.ai_configure_auto"))
        self._recalculate_ai_button.setText(self._translations.t("settings.ai_recalculate"))
        self._hardware_details_button.setText(self._translations.t("settings.ai_hardware_details"))
        self._cancel_ai_setup_button.setText(self._translations.t("settings.ai_cancel_setup"))
        self._download_model_button.setText(self._translations.t("settings.ai_download_model"))
        self._start_ai_button.setText(self._translations.t("settings.ai_start_local"))
        self._test_ai_button.setText(self._translations.t("settings.ai_test"))
        self._local_files_title.setText(self._translations.t("settings.ai_local_files_section"))
        self._local_files_description.setText(self._translations.t("settings.ai_local_files_description"))
        self._selected_local_model_title.setText(self._translations.t("settings.ai_selected_local_model"))
        self._selected_runtime_title.setText(self._translations.t("settings.ai_selected_runtime"))
        self._select_model_button.setText(self._translations.t("settings.ai_select_gguf_model"))
        self._remove_model_button.setText(self._translations.t("settings.ai_remove_selected_model"))
        self._select_runtime_button.setText(self._translations.t("settings.ai_select_runtime"))
        self._remove_runtime_button.setText(self._translations.t("settings.ai_remove_selected_runtime"))
        self._start_with_local_files_button.setText(self._translations.t("settings.ai_start_with_local_files"))
        self._advanced_title.setText(self._translations.t("settings.ai_advanced_section"))
        self._advanced_description.setText(self._translations.t("settings.ai_advanced_description"))
        self._manual_mode_check.setText(self._translations.t("settings.ai_manual_mode"))
        self._ai_privacy.setText(self._privacy_text())
        self._endpoint_label.setText(self._translations.t("settings.ai.endpoint"))
        self._model_label.setText(self._translations.t("settings.ai.model"))
        self._temperature_label.setText(self._translations.t("settings.ai.temperature"))
        self._max_tokens_label.setText(self._translations.t("settings.ai.max_tokens"))
        self._timeout_label.setText(self._translations.t("settings.ai.timeout"))
        self._startup_timeout_label.setText(self._translations.t("settings.ai.startup_timeout"))
        self._startup_timeout_help.setText(self._translations.t("settings.ai.startup_timeout_help"))
        self._startup_timeout_input.setSuffix(f" {self._translations.t('settings.ai.seconds_suffix')}")
        self._retrieval_limit_label.setText(self._translations.t("settings.ai.retrieval_limit"))
        self._save_ai_button.setText(self._translations.t("settings.ai.save"))
        self._reset_ai_button.setText(self._translations.t("settings.ai.reset_defaults"))
        self._test_manual_ai_button.setText(self._translations.t("settings.ai.test_connection"))
        self._show_runtime_logs_button.setText(self._translations.t("settings.ai.show_runtime_logs"))
        self._update_startup_elapsed()

        self._data_title.setText(self._translations.t("settings.data_section"))
        self._data_description.setText(self._translations.t("settings.data_description"))
        self._app_data_label_title.setText(self._translations.t("settings.path.app_data"))
        self._publications_path_label_title.setText(self._translations.t("settings.path.publications"))
        self._index_path_label_title.setText(self._translations.t("settings.path.index"))
        self._metadata_path_label_title.setText(self._translations.t("settings.path.metadata"))
        self._chat_history_path_label_title.setText(self._translations.t("settings.path.chat_history"))
        self._open_app_data_button.setText(self._translations.t("settings.open_app_data"))
        self._open_publications_button.setText(self._translations.t("settings.open_publications"))
        self._open_index_button.setText(self._translations.t("settings.open_index"))

        self._stats_title.setText(self._translations.t("settings.stats_section"))
        self._stats_description.setText(self._translations.t("settings.stats_description"))
        self._refresh_stats_button.setText(self._translations.t("settings.stats.refresh"))

        self._maintenance_title.setText(self._translations.t("settings.maintenance_section"))
        self._maintenance_description.setText(self._translations.t("settings.maintenance_description"))
        self._check_integrity_button.setText(self._translations.t("settings.maintenance.check_integrity"))
        self._rebuild_index_button.setText(self._translations.t("settings.maintenance.rebuild_index"))
        self._reset_index_button.setText(self._translations.t("settings.maintenance.reset_index"))
        self._clear_chat_button.setText(self._translations.t("settings.maintenance.clear_chat_history"))

        self._about_title.setText(self._translations.t("settings.about_section"))
        self._about_app_name.setText(f"{self._translations.t('settings.about.app_name')}: {APP_NAME}")
        self._about_version.setText(f"{self._translations.t('settings.about.version')}: {APP_VERSION}")
        self._about_stage.setText(f"{self._translations.t('settings.about.stage')}: {APP_STAGE}")
        self._about_privacy.setText(self._translations.t("settings.about.local_privacy"))
        self.refresh_stats()

    def refresh_stats(self) -> None:
        self._app_data_path.setText(str(self._paths.app_data_dir))
        self._publications_path.setText(str(self._paths.publications_dir))
        self._index_path.setText(str(self._paths.index_dir))
        self._metadata_path.setText(str(self._paths.metadata_file))
        self._chat_history_path.setText(str(self._paths.chat_history_file))
        self._render_stats(self._maintenance_service.get_library_stats())
        self._ai_privacy.setText(self._privacy_text())
        self._refresh_ai_summary()

    def _build_language_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._language_section_title = self._section_title()
        self._language_label = QLabel()
        self._language_label.setObjectName("FieldLabel")
        self._language_combo = QComboBox()
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self._language_section_title)
        layout.addWidget(self._language_label)
        layout.addWidget(self._language_combo)
        return section

    def _build_ai_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._ai_title = self._section_title()
        self._ai_description = self._section_description()
        layout.addWidget(self._ai_title)
        layout.addWidget(self._ai_description)
        self._ai_status_title, self._ai_status_value = self._summary_row(layout)
        self._ai_status_value.setObjectName("StatusBadge")
        self._recommended_model_title, self._recommended_model_value = self._summary_row(layout)
        self._installed_model_title, self._installed_model_value = self._summary_row(layout)
        self._required_space_title, self._required_space_value = self._summary_row(layout)
        self._detected_ram_title, self._detected_ram_value = self._summary_row(layout)
        self._optimization_title, self._optimization_value = self._summary_row(layout)
        self._system_title, self._system_value = self._summary_row(layout)
        self._process_title, self._process_value = self._summary_row(layout)
        self._architecture_mode_title, self._architecture_mode_value = self._summary_row(layout)
        self._device_title, self._device_value = self._summary_row(layout)
        self._backend_title, self._backend_value = self._summary_row(layout)
        self._selection_reason_title, self._selection_reason_value = self._summary_row(layout)
        self._fallback_title, self._fallback_value = self._summary_row(layout)
        self._npu_detected_title, self._npu_detected_value = self._summary_row(layout)
        self._npu_status_title, self._npu_status_value = self._summary_row(layout)
        optimization_row = QHBoxLayout()
        self._optimization_profile_label = QLabel()
        self._optimization_profile_label.setObjectName("FieldLabel")
        self._optimization_profile_combo = QComboBox()
        self._optimization_profile_combo.currentIndexChanged.connect(self._on_optimization_mode_changed)
        optimization_row.addWidget(self._optimization_profile_label)
        optimization_row.addWidget(self._optimization_profile_combo, 1)
        layout.addLayout(optimization_row)
        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 100)
        self._ai_progress.setValue(0)
        self._ai_progress.setObjectName("AIProgress")
        self._ai_status_message = QLabel()
        self._ai_status_message.setObjectName("MaintenanceReport")
        self._ai_status_message.setWordWrap(True)
        self._ai_elapsed_time = QLabel()
        self._ai_elapsed_time.setObjectName("DetailMeta")
        self._ai_elapsed_time.setVisible(False)
        self._ai_privacy = QLabel()
        self._ai_privacy.setObjectName("PrivacyWarning")
        self._ai_privacy.setWordWrap(True)
        layout.addWidget(self._ai_status_message)
        layout.addWidget(self._ai_elapsed_time)
        layout.addWidget(self._ai_progress)
        primary_buttons = QHBoxLayout()
        secondary_buttons = QHBoxLayout()
        self._configure_ai_button = self._primary_button(self._configure_ai_automatically)
        self._recalculate_ai_button = self._secondary_button(self._configure_ai_automatically)
        self._hardware_details_button = self._secondary_button(self._show_hardware_details)
        self._cancel_ai_setup_button = self._secondary_button(self._cancel_automatic_setup)
        self._cancel_ai_setup_button.setVisible(False)
        self._download_model_button = self._secondary_button(self._download_recommended_model)
        self._start_ai_button = self._secondary_button(self._start_local_ai)
        self._test_ai_button = self._secondary_button(self._test_ai_connection)
        self._ai_buttons = [
            self._configure_ai_button,
            self._recalculate_ai_button,
            self._hardware_details_button,
            self._download_model_button,
            self._start_ai_button,
            self._test_ai_button,
        ]
        primary_buttons.addWidget(self._configure_ai_button)
        primary_buttons.addWidget(self._recalculate_ai_button)
        primary_buttons.addWidget(self._hardware_details_button)
        primary_buttons.addWidget(self._cancel_ai_setup_button)
        secondary_buttons.addWidget(self._download_model_button)
        secondary_buttons.addWidget(self._start_ai_button)
        secondary_buttons.addWidget(self._test_ai_button)
        layout.addLayout(primary_buttons)
        layout.addLayout(secondary_buttons)

        local_files = QFrame()
        local_files.setObjectName("SectionCard")
        local_files_layout = QVBoxLayout(local_files)
        self._local_files_title = self._section_title()
        self._local_files_description = self._section_description()
        local_files_layout.addWidget(self._local_files_title)
        local_files_layout.addWidget(self._local_files_description)
        self._selected_local_model_title, self._selected_local_model_value = self._summary_row(local_files_layout)
        model_buttons = QHBoxLayout()
        self._select_model_button = self._secondary_button(self._select_custom_model)
        self._remove_model_button = self._secondary_button(self._remove_custom_model)
        model_buttons.addWidget(self._select_model_button)
        model_buttons.addWidget(self._remove_model_button)
        local_files_layout.addLayout(model_buttons)
        self._selected_runtime_title, self._selected_runtime_value = self._summary_row(local_files_layout)
        runtime_buttons = QHBoxLayout()
        self._select_runtime_button = self._secondary_button(self._select_custom_runtime)
        self._remove_runtime_button = self._secondary_button(self._remove_custom_runtime)
        self._start_with_local_files_button = self._primary_button(self._start_with_local_files)
        runtime_buttons.addWidget(self._select_runtime_button)
        runtime_buttons.addWidget(self._remove_runtime_button)
        runtime_buttons.addWidget(self._start_with_local_files_button)
        local_files_layout.addLayout(runtime_buttons)
        self._ai_file_buttons = [
            self._select_model_button,
            self._remove_model_button,
            self._select_runtime_button,
            self._remove_runtime_button,
            self._start_with_local_files_button,
        ]
        layout.addWidget(local_files)

        advanced = QFrame()
        advanced.setObjectName("SectionCard")
        advanced_layout = QVBoxLayout(advanced)
        self._advanced_title = self._section_title()
        self._advanced_description = self._section_description()
        self._manual_mode_check = QCheckBox()
        self._manual_mode_check.stateChanged.connect(lambda _state: self._on_manual_mode_changed())
        advanced_layout.addWidget(self._advanced_title)
        advanced_layout.addWidget(self._advanced_description)
        advanced_layout.addWidget(self._manual_mode_check)
        layout.addWidget(self._ai_privacy)
        form = QFormLayout()
        self._endpoint_label = QLabel()
        self._endpoint_input = QLineEdit()
        self._endpoint_input.textChanged.connect(lambda _text: self._ai_privacy.setText(self._privacy_text()))
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
        self._startup_timeout_label = QLabel()
        self._startup_timeout_input = QSpinBox()
        self._startup_timeout_input.setRange(120, 1800)
        self._startup_timeout_input.setSingleStep(30)
        self._startup_timeout_help = self._section_description()
        self._retrieval_limit_label = QLabel()
        self._retrieval_limit_input = QSpinBox()
        self._retrieval_limit_input.setRange(1, 12)
        form.addRow(self._endpoint_label, self._endpoint_input)
        form.addRow(self._model_label, self._model_input)
        form.addRow(self._temperature_label, self._temperature_input)
        form.addRow(self._max_tokens_label, self._max_tokens_input)
        form.addRow(self._timeout_label, self._timeout_input)
        form.addRow(self._startup_timeout_label, self._startup_timeout_input)
        form.addRow("", self._startup_timeout_help)
        form.addRow(self._retrieval_limit_label, self._retrieval_limit_input)
        advanced_layout.addLayout(form)
        advanced_buttons = QHBoxLayout()
        advanced_buttons.addStretch(1)
        self._show_runtime_logs_button = self._secondary_button(self._show_runtime_logs)
        self._reset_ai_button = self._secondary_button(self._reset_ai_settings)
        self._test_manual_ai_button = self._secondary_button(self._test_connection)
        self._save_ai_button = self._primary_button(self._save_ai_settings)
        advanced_buttons.addWidget(self._show_runtime_logs_button)
        advanced_buttons.addWidget(self._reset_ai_button)
        advanced_buttons.addWidget(self._test_manual_ai_button)
        advanced_buttons.addWidget(self._save_ai_button)
        advanced_layout.addLayout(advanced_buttons)
        layout.addWidget(advanced)
        return section

    def _build_data_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._data_title = self._section_title()
        self._data_description = self._section_description()
        layout.addWidget(self._data_title)
        layout.addWidget(self._data_description)
        self._app_data_label_title, self._app_data_path = self._path_row(layout)
        self._publications_path_label_title, self._publications_path = self._path_row(layout)
        self._index_path_label_title, self._index_path = self._path_row(layout)
        self._metadata_path_label_title, self._metadata_path = self._path_row(layout)
        self._chat_history_path_label_title, self._chat_history_path = self._path_row(layout)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._open_app_data_button = self._secondary_button(lambda: self._open_path(self._paths.app_data_dir))
        self._open_publications_button = self._secondary_button(lambda: self._open_path(self._paths.publications_dir))
        self._open_index_button = self._secondary_button(lambda: self._open_path(self._paths.index_dir))
        buttons.addWidget(self._open_app_data_button)
        buttons.addWidget(self._open_publications_button)
        buttons.addWidget(self._open_index_button)
        layout.addLayout(buttons)
        return section

    def _build_stats_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._stats_title = self._section_title()
        self._stats_description = self._section_description()
        self._stats_text = QLabel()
        self._stats_text.setObjectName("DetailMeta")
        self._stats_text.setWordWrap(True)
        self._refresh_stats_button = self._secondary_button(self.refresh_stats)
        layout.addWidget(self._stats_title)
        layout.addWidget(self._stats_description)
        layout.addWidget(self._stats_text)
        layout.addWidget(self._refresh_stats_button)
        return section

    def _build_maintenance_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._maintenance_title = self._section_title()
        self._maintenance_description = self._section_description()
        self._maintenance_report = QLabel()
        self._maintenance_report.setObjectName("MaintenanceReport")
        self._maintenance_report.setWordWrap(True)
        buttons = QHBoxLayout()
        self._check_integrity_button = self._secondary_button(self._check_integrity)
        self._rebuild_index_button = self._secondary_button(self._rebuild_index)
        self._reset_index_button = self._danger_button(self._reset_index)
        self._clear_chat_button = self._danger_button(self._clear_chat_history)
        self._maintenance_buttons = [
            self._check_integrity_button,
            self._rebuild_index_button,
            self._reset_index_button,
            self._clear_chat_button,
        ]
        for button in self._maintenance_buttons:
            buttons.addWidget(button)
        layout.addWidget(self._maintenance_title)
        layout.addWidget(self._maintenance_description)
        layout.addLayout(buttons)
        layout.addWidget(self._maintenance_report)
        return section

    def _build_about_section(self) -> QFrame:
        section = self._section()
        layout = QVBoxLayout(section)
        self._about_title = self._section_title()
        self._about_app_name = QLabel()
        self._about_version = QLabel()
        self._about_stage = QLabel()
        self._about_privacy = self._section_description()
        layout.addWidget(self._about_title)
        layout.addWidget(self._about_app_name)
        layout.addWidget(self._about_version)
        layout.addWidget(self._about_stage)
        layout.addWidget(self._about_privacy)
        return section

    def _load_ai_settings(self) -> None:
        self._manual_mode_check.blockSignals(True)
        self._manual_mode_check.setChecked(self._settings.ai_mode() == "manual")
        self._manual_mode_check.blockSignals(False)
        self._endpoint_input.setText(self._settings.ai_manual_endpoint_url())
        self._model_input.setText(self._settings.ai_manual_model_name())
        self._temperature_input.setValue(self._settings.ai_temperature())
        self._max_tokens_input.setValue(self._settings.ai_max_tokens())
        self._timeout_input.setValue(self._settings.ai_timeout_seconds())
        self._startup_timeout_input.setValue(self._settings.ai_startup_timeout_seconds())
        self._retrieval_limit_input.setValue(self._settings.ai_default_sources_count())
        self._update_advanced_enabled()

    def _save_ai_settings(self) -> None:
        self._persist_ai_settings()
        self._show_message("common.success", "settings.ai.saved")

    def _persist_ai_settings(self) -> None:
        self._settings.set_ai_mode("manual" if self._manual_mode_check.isChecked() else "auto")
        self._settings.set_ai_manual_endpoint_url(self._endpoint_input.text())
        self._settings.set_ai_manual_model_name(self._model_input.text())
        self._settings.set_ai_temperature(self._temperature_input.value())
        self._settings.set_ai_max_tokens(self._max_tokens_input.value())
        self._settings.set_ai_timeout_seconds(self._timeout_input.value())
        self._settings.set_ai_startup_timeout_seconds(self._startup_timeout_input.value())
        self._settings.set_ai_default_sources_count(self._retrieval_limit_input.value())

    def _reset_ai_settings(self) -> None:
        self._settings.reset_llm_defaults()
        self._load_ai_settings()
        self._show_message("common.success", "settings.ai.reset_done")

    def _test_connection(self) -> None:
        self._persist_ai_settings()
        self._start_connection_test()

    def _start_connection_test(self) -> None:
        if self._connection_thread is not None and self._connection_thread.isRunning():
            return
        self._test_manual_ai_button.setEnabled(False)
        self._test_ai_button.setEnabled(False)
        self._connection_thread = QThread(self)
        self._connection_worker = AIConnectionTestWorker(self._llm_client)
        worker = self._connection_worker
        thread = self._connection_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_connection_test_completed)
        worker.completed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._on_connection_test_thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_connection_test_completed(self, ok: bool, _message: str) -> None:
        self._show_message("common.success" if ok else "common.error", "settings.ai.connection_success" if ok else "settings.ai.connection_failed")

    def _on_connection_test_thread_finished(self) -> None:
        self._connection_worker = None
        self._connection_thread = None
        self._update_advanced_enabled()
        self._refresh_ai_summary()

    def _test_ai_connection(self) -> None:
        self._start_connection_test()

    def _configure_ai_automatically(self) -> None:
        self._set_ai_busy(True)
        self._set_progress_determinate(0)
        self._ai_progress.setValue(0)
        self._ai_setup_service.configure_automatically()

    def _download_recommended_model(self) -> None:
        spec = self._recommended_model_or_fallback()
        self._settings.set_ai_selected_model_id(spec.id)
        if self._model_manager.is_model_ready(spec):
            self._set_ai_status_text("settings.ai_status_messages.model_already_downloaded")
            return
        self._set_ai_busy(True)
        self._ai_setup_service.download_model(spec)

    def _start_local_ai(self) -> None:
        spec = self._selected_model_or_fallback()
        self._set_ai_busy(True)
        self._ai_setup_service.start_runtime(spec)

    def _select_custom_model(self) -> None:
        source_file, _ = QFileDialog.getOpenFileName(
            self,
            self._translations.t("settings.ai_select_gguf_model"),
            str(Path.home()),
            self._translations.t("settings.ai_gguf_filter"),
        )
        if not source_file:
            return
        self._set_ai_status_text("settings.ai_status_messages.copying_local_file")
        try:
            target = self._model_manager.import_custom_model(Path(source_file))
        except FileNotFoundError:
            self._set_ai_status_text("settings.ai_model_file_missing")
            return
        except (OSError, ValueError):
            self._set_ai_status_text("settings.ai_invalid_model_file")
            return
        self._settings.set_ai_custom_model_path(str(target))
        self._settings.set_ai_custom_model_display_name(target.stem)
        self._settings.set_ai_use_custom_model(True)
        self._settings.set_ai_mode("auto")
        self._set_ai_status_text("settings.ai_model_selected_success")
        self._refresh_ai_summary()

    def _remove_custom_model(self) -> None:
        self._settings.set_ai_use_custom_model(False)
        self._settings.set_ai_custom_model_path("")
        self._settings.set_ai_custom_model_display_name("")
        self._set_ai_status_text("settings.ai_no_local_model_selected")
        self._refresh_ai_summary()

    def _select_custom_runtime(self) -> None:
        source_file, _ = QFileDialog.getOpenFileName(
            self,
            self._translations.t("settings.ai_select_runtime"),
            str(Path.home()),
            self._translations.t("settings.ai_runtime_filter_windows" if self._is_windows() else "settings.ai_runtime_filter_all"),
        )
        if not source_file:
            return
        self._set_ai_status_text("settings.ai_status_messages.validating_local_runtime")
        try:
            target = self._runtime_manager.import_runtime_executable(Path(source_file))
        except FileNotFoundError:
            self._set_ai_status_text("settings.ai_runtime_file_missing")
            return
        except (OSError, RuntimeError, ValueError):
            self._set_ai_status_text("settings.ai_invalid_runtime_file")
            return
        self._settings.set_ai_custom_runtime_path(str(target))
        self._settings.set_ai_use_custom_runtime(True)
        self._settings.set_ai_mode("auto")
        self._set_ai_status_text("settings.ai_runtime_selected_success")
        self._refresh_ai_summary()

    def _remove_custom_runtime(self) -> None:
        self._settings.set_ai_use_custom_runtime(False)
        self._settings.set_ai_custom_runtime_path("")
        self._set_ai_status_text("settings.ai_no_runtime_selected")
        self._refresh_ai_summary()

    def _start_with_local_files(self) -> None:
        self._set_ai_busy(True)
        self._settings.set_ai_mode("auto")
        self._set_ai_status_text("settings.ai_starting_with_local_files")
        self._ai_setup_service.start_custom_runtime()

    def _connect_ai_setup_service(self) -> None:
        self._ai_setup_service.status_changed.connect(self._on_ai_setup_status)
        self._ai_setup_service.progress_changed.connect(self._ai_progress.setValue)
        self._ai_setup_service.error_occurred.connect(self._on_ai_setup_error)
        self._ai_setup_service.finished.connect(self._on_ai_setup_finished)

    def _on_ai_setup_status(self, code: str) -> None:
        self._set_ai_status_text(f"settings.ai_status_messages.{code}")
        if code in {
            "detecting_hardware",
            "evaluating_backends",
            "selecting_model",
            "validating_backend",
            "optimizing_configuration",
            "starting_runtime",
            "loading_model",
            "waiting_for_runtime",
            "starting_with_local_files",
        }:
            self._set_progress_indeterminate()
            self._start_elapsed_timer()
        elif code in {"download_model", "download_started", "downloading_model", "downloading_runtime", "extracting_runtime"}:
            self._set_progress_determinate(self._ai_progress.value())
        elif code in {"ready", "runtime_ready"}:
            self._set_progress_determinate(100)
            self._stop_elapsed_timer()
        self._refresh_ai_summary()

    def _on_ai_setup_error(self, code: str) -> None:
        self._set_ai_busy(False)
        self._set_progress_determinate(0)
        self._stop_elapsed_timer()
        self._set_ai_error_text(code)
        self._refresh_ai_summary()

    def _on_ai_setup_finished(self) -> None:
        self._set_ai_busy(False)
        self._set_progress_determinate(100)
        self._stop_elapsed_timer()
        self._refresh_ai_summary()

    def _on_manual_mode_changed(self) -> None:
        self._settings.set_ai_mode("manual" if self._manual_mode_check.isChecked() else "auto")
        self._update_advanced_enabled()
        self._refresh_ai_summary()

    def _refresh_ai_summary(self) -> None:
        info = get_hardware_info(self._paths.app_data_dir)
        self._recommended_model = recommend_model(info.total_ram_gb)
        selected = self._selected_model_or_fallback()
        state = self._model_manager.get_custom_model_state(self._settings.ai_custom_model_path()) if self._settings.ai_use_custom_model() else self._model_manager.get_local_state(selected)
        ai_status = self._llm_client.status()
        self._ai_status_value.setText(self._translations.t(f"settings.ai_status_values.{ai_status}"))
        self._ai_status_value.setProperty("status", ai_status)
        self._ai_status_value.style().unpolish(self._ai_status_value)
        self._ai_status_value.style().polish(self._ai_status_value)
        self._recommended_model_value.setText(self._recommended_model.display_name)
        installed_model = self._settings.ai_custom_model_display_name() if self._settings.ai_use_custom_model() and state.verified else selected.display_name
        self._installed_model_value.setText(installed_model if state.verified else self._translations.t("settings.ai_no_model_installed"))
        self._required_space_value.setText(f"{selected.size_gb:.1f} GB")
        self._detected_ram_value.setText(f"{info.total_ram_gb:.1f} GB")
        self._refresh_hardware_summary(info)
        self._selected_local_model_value.setText(self._short_path(self._settings.ai_custom_model_path()) if self._settings.ai_use_custom_model() else self._translations.t("settings.ai_no_local_model_selected"))
        self._selected_runtime_value.setText(self._short_path(self._settings.ai_custom_runtime_path()) if self._settings.ai_use_custom_runtime() else self._translations.t("settings.ai_no_runtime_selected"))
        self._test_ai_button.setEnabled(self._llm_client.is_ready() and not self._ai_busy)
        if not self._ai_status_message_key or self._ai_status_message_key.startswith("settings.ai_status_help."):
            self._set_ai_status_text(f"settings.ai_status_help.{self._llm_client.status()}")

    def _selected_model_or_fallback(self) -> LocalModelSpec:
        return get_model(self._settings.ai_selected_model_id()) or self._recommended_model_or_fallback()

    def _recommended_model_or_fallback(self) -> LocalModelSpec:
        if self._recommended_model is not None:
            return self._recommended_model
        info = get_hardware_info(self._paths.app_data_dir)
        self._recommended_model = recommend_model(info.total_ram_gb)
        return self._recommended_model

    def _refresh_hardware_summary(self, info) -> None:
        profile = self._load_local_json(self._paths.app_data_dir / "ai_hardware_profile.json")
        selection = self._load_local_json(self._paths.app_data_dir / "ai_backend_selection.json")
        architecture = profile.get("architecture") if isinstance(profile.get("architecture"), dict) else {}
        stored_native = self._settings.ai_native_architecture()
        stored_process = self._settings.ai_process_architecture()
        native = str(
            selection.get("native_architecture")
            or architecture.get("native_architecture")
            or (stored_native if stored_native != "unknown" else "")
            or info.architecture
        )
        process = str(
            selection.get("process_architecture")
            or architecture.get("process_architecture")
            or (stored_process if stored_process != "unknown" else "")
            or info.architecture
        )
        process_emulated = bool(architecture.get("running_under_emulation", False))
        runtime_emulated = bool(
            selection.get("running_under_emulation")
            if "running_under_emulation" in selection
            else self._settings.ai_running_under_emulation()
        )
        mode = self._settings.ai_optimization_mode()
        self._optimization_value.setText(self._translations.t(f"settings.ai_optimization_modes.{mode}"))
        os_name = str(profile.get("os_name") or info.os_name)
        os_version = str(profile.get("os_version") or "").strip()
        self._system_value.setText(" ".join(part for part in (os_name, os_version, native.upper()) if part))
        if process_emulated:
            process_text = self._translations.t("settings.ai_process_emulated").format(
                process=process.upper(),
                native=native.upper(),
            )
        elif runtime_emulated:
            runtime_architecture = str(selection.get("runtime_architecture") or "x86_64")
            process_text = self._translations.t("settings.ai_process_native_runtime_emulated").format(
                process=process.upper(),
                runtime=runtime_architecture.upper(),
                native=native.upper(),
            )
        else:
            process_text = self._translations.t("settings.ai_process_native").format(process=process.upper())
        self._process_value.setText(process_text)
        self._architecture_mode_value.setText(
            self._translations.t("settings.ai_emulated" if process_emulated or runtime_emulated else "settings.ai_native")
        )

        backend_id = str(selection.get("selected_backend") or self._settings.ai_backend_id())
        device_id = str(selection.get("selected_device") or self._settings.ai_device_id())
        cpu_model = str(profile.get("cpu_model") or "CPU")
        if backend_id.endswith("_cpu") and not device_id:
            device_text = cpu_model
        else:
            device_text = device_id or self._translations.t("settings.ai_not_selected")
        self._device_value.setText(device_text)
        self._backend_value.setText(
            self._backend_display_name(backend_id) if backend_id else self._translations.t("settings.ai_not_selected")
        )
        reasons = selection.get("reason_codes")
        reason_code = str(reasons[0]) if isinstance(reasons, list) and reasons else "not_calculated"
        reason_text = self._translations.t(f"settings.ai_reason_values.{reason_code}")
        self._selection_reason_value.setText(reason_text if not reason_text.startswith("settings.") else reason_code)
        fallbacks = selection.get("fallbacks")
        if isinstance(fallbacks, list) and fallbacks:
            fallback_text = ", ".join(self._backend_display_name(str(value)) for value in fallbacks)
        else:
            fallback_text = self._translations.t("settings.ai_none")
        self._fallback_value.setText(fallback_text)

        npu_devices = profile.get("npu_devices")
        npu_names = [
            str(item.get("name"))
            for item in npu_devices
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ] if isinstance(npu_devices, list) else []
        if npu_names:
            self._npu_detected_value.setText(", ".join(npu_names))
            self._npu_status_value.setText(self._translations.t("settings.ai_npu_detected_not_usable"))
        else:
            self._npu_detected_value.setText(self._translations.t("settings.ai_not_detected"))
            self._npu_status_value.setText(self._translations.t("settings.ai_npu_not_used"))

    def _backend_display_name(self, value: str) -> str:
        labels = {
            "llama_cpp_cpu": "llama.cpp CPU",
            "llama_cpp_cuda": "llama.cpp CUDA",
            "llama_cpp_vulkan": "llama.cpp Vulkan",
            "llama_cpp_opencl": "llama.cpp OpenCL",
            "llama_cpp_cpu_arm64": "llama.cpp CPU ARM64",
            "llama_cpp_cpu_x86_64_generic": "llama.cpp CPU x64",
            "llama_cpp_cpu_x86_64_avx2": "llama.cpp CPU x64 AVX2",
            "llama_cpp_cuda_x86_64": "llama.cpp CUDA x64",
            "llama_cpp_vulkan_x86_64": "llama.cpp Vulkan x64",
        }
        return labels.get(value, value.replace("_", " "))

    def _on_optimization_mode_changed(self, _index: int) -> None:
        mode = self._optimization_profile_combo.currentData()
        if isinstance(mode, str):
            self._settings.set_ai_optimization_mode(mode)
            self._refresh_ai_summary()

    def _cancel_automatic_setup(self) -> None:
        self._ai_setup_service.cancel()
        self._set_ai_status_text("settings.ai_status_messages.setup_cancelled")

    def _show_hardware_details(self) -> None:
        profile = self._load_local_json(self._paths.app_data_dir / "ai_hardware_profile.json")
        selection = self._load_local_json(self._paths.app_data_dir / "ai_backend_selection.json")
        details = {
            "hardware_profile": profile or {"status": "not_calculated"},
            "backend_selection": selection or {"status": "not_calculated"},
        }
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translations.t("settings.ai_hardware_details_title"))
        dialog.resize(820, 580)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        text.setPlainText(json.dumps(details, indent=2, ensure_ascii=False, sort_keys=True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(text)
        layout.addWidget(buttons)
        dialog.exec()

    def _load_local_json(self, path: Path) -> dict:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _set_ai_busy(self, is_busy: bool) -> None:
        self._ai_busy = is_busy
        for button in [*self._ai_buttons, *self._ai_file_buttons]:
            button.setEnabled(not is_busy)
        self._test_ai_button.setEnabled(not is_busy and self._llm_client.is_ready())
        self._optimization_profile_combo.setEnabled(not is_busy)
        self._cancel_ai_setup_button.setVisible(is_busy)
        self._cancel_ai_setup_button.setEnabled(is_busy)
        if is_busy:
            self._set_ai_status_text("settings.ai_status_messages.busy")
        else:
            self._stop_elapsed_timer()

    def _set_ai_status_text(self, key: str) -> None:
        self._ai_status_message_key = key
        text = self._translations.t(key)
        self._ai_status_message.setText(text if text != key else key.rsplit(".", 1)[-1])

    def _set_ai_error_text(self, code: str) -> None:
        key = f"settings.ai_errors.{code}"
        self._ai_status_message_key = key
        text = self._translations.t(key)
        diagnostic = self._runtime_manager.get_state().diagnostic
        values = {
            "exit_code": diagnostic.exit_code if diagnostic and diagnostic.exit_code is not None else "?",
            "winerror": diagnostic.winerror if diagnostic and diagnostic.winerror is not None else "?",
        }
        try:
            text = text.format(**values)
        except (KeyError, ValueError):
            pass
        self._ai_status_message.setText(text if text != key else code)

    def _update_advanced_enabled(self) -> None:
        is_manual = self._manual_mode_check.isChecked()
        for widget in (
            self._endpoint_label,
            self._endpoint_input,
            self._model_label,
            self._model_input,
            self._temperature_label,
            self._temperature_input,
            self._max_tokens_label,
            self._max_tokens_input,
            self._timeout_label,
            self._timeout_input,
            self._startup_timeout_label,
            self._startup_timeout_input,
            self._startup_timeout_help,
            self._retrieval_limit_label,
            self._retrieval_limit_input,
            self._test_manual_ai_button,
            self._save_ai_button,
        ):
            widget.setVisible(is_manual)
            widget.setEnabled(is_manual)

    def cancel_pending_request(self, wait_ms: int = 0) -> bool:
        setup_stopped = True
        if self._ai_setup_service.is_busy():
            self._ai_setup_service.cancel()
            setup_stopped = self._ai_setup_service.wait_for_shutdown(wait_ms)
        if self._connection_thread is None or not self._connection_thread.isRunning():
            return setup_stopped
        self._llm_client.cancel_active_request()
        connection_stopped = self._connection_thread.wait(wait_ms) if wait_ms > 0 else False
        return setup_stopped and connection_stopped

    def _set_progress_indeterminate(self) -> None:
        self._ai_progress.setRange(0, 0)

    def _set_progress_determinate(self, value: int) -> None:
        self._ai_progress.setRange(0, 100)
        self._ai_progress.setValue(value)

    def _start_elapsed_timer(self) -> None:
        if not self._startup_timer.isActive():
            self._startup_elapsed_seconds = 0
            self._ai_elapsed_time.setVisible(True)
            self._startup_timer.start()
        self._update_startup_elapsed()

    def _stop_elapsed_timer(self) -> None:
        self._startup_timer.stop()
        self._startup_elapsed_seconds = 0
        if hasattr(self, "_ai_elapsed_time"):
            self._ai_elapsed_time.setVisible(False)

    def _update_startup_elapsed(self) -> None:
        minutes, seconds = divmod(self._startup_elapsed_seconds, 60)
        if hasattr(self, "_ai_elapsed_time"):
            self._ai_elapsed_time.setText(
                self._translations.t("settings.ai_elapsed_time").format(
                    time=f"{minutes:02d}:{seconds:02d}"
                )
            )
        self._startup_elapsed_seconds += 1

    def _show_runtime_logs(self) -> None:
        logs = self._runtime_manager.last_runtime_log_text()
        dialog = QDialog(self)
        dialog.setWindowTitle(self._translations.t("settings.ai.runtime_logs_title"))
        dialog.resize(900, 600)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit(dialog)
        text.setReadOnly(True)
        text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        text.setPlainText(logs if logs else self._translations.t("settings.ai.runtime_logs_empty"))
        text.moveCursor(text.textCursor().MoveOperation.End)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(text)
        layout.addWidget(buttons)
        dialog.exec()

    def _short_path(self, value: str) -> str:
        if not value:
            return ""
        path = Path(value)
        return path.name if path.name else value

    def _is_windows(self) -> bool:
        return sys.platform.startswith("win")

    def _check_integrity(self) -> None:
        report = self._maintenance_service.check_integrity()
        self._maintenance_report.setText(self._format_integrity_report(report))

    def _rebuild_index(self) -> None:
        if not self._confirm("settings.maintenance.rebuild_confirm_title", "settings.maintenance.rebuild_confirm_message"):
            return
        self._set_maintenance_busy(True)
        result = self._maintenance_service.rebuild_index()
        self._set_maintenance_busy(False)
        self.refresh_stats()
        self._show_maintenance_result(result, "settings.maintenance.rebuild_success", "settings.maintenance.rebuild_partial", "settings.maintenance.rebuild_failed")

    def _reset_index(self) -> None:
        if not self._confirm("settings.maintenance.reset_confirm_title", "settings.maintenance.reset_confirm_message"):
            return
        result = self._maintenance_service.reset_index()
        self.refresh_stats()
        self._show_message("common.success" if result.success else "common.error", "settings.maintenance.reset_success" if result.success else "settings.maintenance.reset_failed")

    def _clear_chat_history(self) -> None:
        if not self._confirm("settings.maintenance.clear_chat_confirm_title", "settings.maintenance.clear_chat_confirm_message"):
            return
        result = self._maintenance_service.clear_chat_history()
        self.refresh_stats()
        self._show_message(
            "common.success" if result.success else "common.error",
            "settings.maintenance.clear_chat_success" if result.success else "settings.maintenance.clear_chat_failed",
        )

    def _format_integrity_report(self, report: IntegrityReport) -> str:
        if report.ok:
            return self._translations.t("settings.maintenance.integrity_ok")
        lines = [self._translations.t("settings.maintenance.integrity_issues")]
        for issue in report.issues[:12]:
            key = f"settings.integrity.issue.{issue.code}"
            label = self._translations.t(key)
            if issue.publication_title:
                label = f"{label}: {issue.publication_title}"
            lines.append(f"- {label}")
        return "\n".join(lines)

    def _show_maintenance_result(self, result: MaintenanceResult, success_key: str, partial_key: str, failed_key: str) -> None:
        if result.success:
            key = success_key
        elif result.processed_count:
            key = partial_key
        else:
            key = failed_key
        self._show_message("common.success" if result.success else "common.warning", key, processed=result.processed_count, failed=result.failed_count)

    def _render_stats(self, stats: LibraryStats) -> None:
        lines = [
            f"{self._translations.t('settings.stats.total_publications')}: {stats.total_publications}",
            f"{self._translations.t('settings.stats.imported_publications')}: {stats.imported_publications}",
            f"{self._translations.t('settings.stats.indexed_publications')}: {stats.indexed_publications}",
            f"{self._translations.t('settings.stats.error_publications')}: {stats.error_publications}",
            f"{self._translations.t('settings.stats.pending_publications')}: {stats.pending_publications}",
            f"{self._translations.t('settings.stats.total_chunks')}: {stats.total_chunks}",
            f"{self._translations.t('settings.stats.publications_size')}: {self._format_bytes(stats.publications_size_bytes)}",
            f"{self._translations.t('settings.stats.index_size')}: {self._format_bytes(stats.index_size_bytes)}",
            f"{self._translations.t('settings.stats.chat_history_size')}: {self._format_bytes(stats.chat_history_size_bytes)}",
        ]
        self._stats_text.setText("\n".join(lines))

    def _privacy_text(self) -> str:
        if hasattr(self, "_manual_mode_check") and not self._manual_mode_check.isChecked():
            return self._translations.t("settings.ai_privacy_local")
        endpoint = self._endpoint_input.text() if hasattr(self, "_endpoint_input") else self._settings.ai_manual_endpoint_url()
        return self._translations.t("settings.ai_privacy_local" if is_local_endpoint(endpoint) else "settings.ai_privacy_remote_warning")

    def _format_bytes(self, size: int) -> str:
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / (1024 * 1024):.1f} MB"

    def _path_row(self, layout: QVBoxLayout) -> tuple[QLabel, QLabel]:
        title = QLabel()
        title.setObjectName("FieldLabel")
        value = QLabel()
        value.setObjectName("PathLabel")
        value.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(value)
        return title, value

    def _summary_row(self, layout: QVBoxLayout) -> tuple[QLabel, QLabel]:
        row = QHBoxLayout()
        title = QLabel()
        title.setObjectName("FieldLabel")
        value = QLabel()
        value.setObjectName("DetailMeta")
        value.setWordWrap(True)
        row.addWidget(title)
        row.addWidget(value, 1)
        layout.addLayout(row)
        return title, value

    def _section(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("SettingsSection")
        return frame

    def _section_title(self) -> QLabel:
        label = QLabel()
        label.setObjectName("SectionTitle")
        return label

    def _section_description(self) -> QLabel:
        label = QLabel()
        label.setObjectName("SectionDescription")
        label.setWordWrap(True)
        return label

    def _primary_button(self, slot) -> QPushButton:
        button = QPushButton()
        button.setObjectName("PrimaryButton")
        button.clicked.connect(slot)
        return button

    def _secondary_button(self, slot) -> QPushButton:
        button = QPushButton()
        button.setObjectName("SecondaryButton")
        button.clicked.connect(slot)
        return button

    def _danger_button(self, slot) -> QPushButton:
        button = QPushButton()
        button.setObjectName("DangerButton")
        button.clicked.connect(slot)
        return button

    def _open_path(self, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _confirm(self, title_key: str, message_key: str) -> bool:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self._translations.t(title_key))
        dialog.setText(self._translations.t(message_key))
        no_button = dialog.addButton(self._translations.t("common.no"), QMessageBox.ButtonRole.RejectRole)
        yes_button = dialog.addButton(self._translations.t("common.yes"), QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(no_button)
        dialog.exec()
        return dialog.clickedButton() == yes_button

    def _show_message(self, title_key: str, message_key: str, **values: object) -> None:
        dialog = QMessageBox(self)
        dialog.setWindowTitle(self._translations.t(title_key))
        dialog.setText(self._translations.t(message_key).format(**values))
        dialog.addButton(self._translations.t("common.ok"), QMessageBox.ButtonRole.AcceptRole)
        dialog.exec()

    def _set_maintenance_busy(self, is_busy: bool) -> None:
        for button in self._maintenance_buttons:
            button.setEnabled(not is_busy)
        if is_busy:
            self._maintenance_report.setText(self._translations.t("settings.maintenance.busy"))

    def _on_language_changed(self, index: int) -> None:
        language = self._language_combo.itemData(index)
        if isinstance(language, str) and language != self._translations.language:
            self.language_changed.emit(language)

    def _index_for_language(self, language: str) -> int:
        for index, (language_code, _) in enumerate(self.LANGUAGE_OPTIONS):
            if language_code == language:
                return index
        return 0
