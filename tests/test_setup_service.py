import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication

from app.ai.model_catalog import list_models
from app.ai.model_manager import ModelManager
from app.ai.runtime_manager import RuntimeManager
from app.ai.setup_service import LocalAISetupService
from app.settings import AppSettings


class TestableSetupService(LocalAISetupService):
    def __init__(self, settings, model_manager, runtime_manager):
        super().__init__(settings, model_manager, runtime_manager)
        self.runtime_download_requested = False
        self.model_download_requested = False
        self.runtime_start_requested = False

    def download_runtime_then_continue(self, spec):
        self.runtime_download_requested = True

    def download_model(self, spec, start_after_download=False):
        self.model_download_requested = True

    def start_runtime(self, spec):
        self.runtime_start_requested = True


class SetupServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_runtime_missing_requests_runtime_download(self) -> None:
        with TemporaryDirectory() as directory:
            settings = AppSettings("JW PubliStudy Tests", "SetupRuntimeMissing")
            settings.set_ai_use_custom_model(False)
            settings.set_ai_use_custom_runtime(False)
            service = TestableSetupService(settings, ModelManager(directory), RuntimeManager(directory, settings))
            service.configure_automatically()
            self.assertTrue(service.runtime_download_requested)

    def test_model_missing_requests_model_download_when_runtime_present(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime" / "llama-server.exe"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"x" * 2048)
            settings = AppSettings("JW PubliStudy Tests", "SetupModelMissing")
            service = TestableSetupService(settings, ModelManager(root), RuntimeManager(root, settings))
            service.configure_automatically()
            self.assertTrue(service.model_download_requested)

    def test_ready_model_and_runtime_starts_runtime(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime" / "llama-server.exe"
            runtime.parent.mkdir(parents=True)
            runtime.write_bytes(b"x" * 2048)
            manager = ModelManager(root)
            for model in list_models():
                manager.get_model_path(model).write_bytes(b"x" * manager.MIN_PLAUSIBLE_MODEL_BYTES)
            settings = AppSettings("JW PubliStudy Tests", "SetupReady")
            service = TestableSetupService(settings, manager, RuntimeManager(root, settings))
            service.configure_automatically()
            self.assertTrue(service.runtime_start_requested)


if __name__ == "__main__":
    unittest.main()
