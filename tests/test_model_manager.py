import hashlib
import unittest

from app.ai.model_catalog import LocalModelSpec
from app.ai.model_manager import ModelManager


def _spec(sha256: str | None = None) -> LocalModelSpec:
    return LocalModelSpec("test", "Test", "Test", "test.gguf", "https://example.com/test.gguf", sha256, 1, 1, "low", 128, 0.2, 64)


class ModelManagerTest(unittest.TestCase):
    def test_model_paths_and_missing(self) -> None:
        with self.subTest():
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                manager = ModelManager(directory)
                spec = _spec()
                self.assertTrue(manager.models_dir().exists())
                self.assertEqual(manager.get_model_path(spec).name, "test.gguf")
                self.assertFalse(manager.is_model_ready(spec))

    def test_verify_model_without_sha(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            manager = ModelManager(directory)
            spec = _spec()
            path = manager.get_model_path(spec)
            path.write_bytes(b"x" * manager.MIN_PLAUSIBLE_MODEL_BYTES)
            self.assertTrue(manager.verify_model(spec))

    def test_verify_model_bad_sha(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            manager = ModelManager(directory)
            spec = _spec(hashlib.sha256(b"expected").hexdigest())
            path = manager.get_model_path(spec)
            path.write_bytes(b"x" * manager.MIN_PLAUSIBLE_MODEL_BYTES)
            self.assertFalse(manager.verify_model(spec))


if __name__ == "__main__":
    unittest.main()
