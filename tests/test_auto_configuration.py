import json
import os
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QApplication

from app.ai.auto_configuration import AutomaticConfigurationWorker
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager
from app.ai.setup_service import LocalAISetupService
from app.i18n import I18n
from app.settings import AppSettings
from tests.ai_test_helpers import profile


class ImmediatePlanner(QObject):
    status_changed = Signal(str)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.executed_thread = None
        self.ran = threading.Event()

    @Slot()
    def run(self) -> None:
        self.executed_thread = QThread.currentThread()
        self.ran.set()
        self.failed.emit("test_done")

    def request_cancel(self) -> None:
        self.cancelled.emit()


class AutoConfigurationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_automatic_configuration_worker_emits_intermediate_states(self) -> None:
        with TemporaryDirectory() as directory:
            worker = AutomaticConfigurationWorker(Path(directory))
            statuses = []
            completed = []
            release = {
                "tag_name": "b1",
                "assets": [{
                    "name": "llama-b1-bin-win-cpu-x64.zip",
                    "browser_download_url": "https://example.invalid/runtime.zip",
                }],
            }
            with (
                patch("app.ai.auto_configuration.get_hardware_profile", return_value=profile(data_dir=Path(directory))),
                patch.object(worker, "_load_release_json", return_value=release),
            ):
                worker.status_changed.connect(statuses.append)
                worker.completed.connect(completed.append)
                worker.run()
        self.assertEqual(statuses, ["detecting_hardware", "evaluating_backends", "selecting_model"])
        self.assertEqual(len(completed), 1)

    def test_automatic_configuration_is_dispatched_off_main_thread(self) -> None:
        with TemporaryDirectory() as directory:
            settings = AppSettings("JW PubliStudy Tests", "AsyncPlanner")
            settings.set_ai_use_custom_model(False)
            settings.set_ai_use_custom_runtime(False)
            fake = ImmediatePlanner()
            service = LocalAISetupService(settings, ModelManager(directory), RuntimeManager(directory, settings))
            with patch("app.ai.setup_service.AutomaticConfigurationWorker", return_value=fake):
                service.configure_automatically()
                self.assertTrue(fake.ran.wait(2))
                service._planning_thread.wait(2000)
            self.assertIs(fake.executed_thread, service._planning_thread)
            self.assertIsNot(fake.executed_thread, QThread.currentThread())

    def test_worker_cancellation_is_reported(self) -> None:
        with TemporaryDirectory() as directory:
            worker = AutomaticConfigurationWorker(Path(directory))
            cancelled = []
            worker.cancelled.connect(lambda: cancelled.append(True))
            worker.request_cancel()
            with patch("app.ai.auto_configuration.get_hardware_profile", return_value=profile(data_dir=Path(directory))):
                worker.run()
            self.assertEqual(cancelled, [True])

    def test_translations_expose_hardware_ui_contract(self) -> None:
        root = Path(__file__).resolve().parents[1] / "resources" / "i18n"
        required = (
            "settings.ai_recalculate",
            "settings.ai_hardware_details",
            "settings.ai_native",
            "settings.ai_emulated",
            "settings.ai_npu_detected_not_usable",
            "settings.ai_status_messages.detecting_hardware",
            "settings.ai_status_messages.validating_backend",
        )
        for language in ("it", "en", "al"):
            translations = I18n(root, language)
            for key in required:
                with self.subTest(language=language, key=key):
                    self.assertNotEqual(translations.t(key), key)

    def test_profile_and_selection_files_contain_no_serial_number(self) -> None:
        source = json.dumps(profile().__dict__, default=str).lower()
        self.assertNotIn("serial", source)


if __name__ == "__main__":
    unittest.main()
