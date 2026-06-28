import unittest

from app.ai.runtime_manager import RuntimeManager


class RuntimeManagerTest(unittest.TestCase):
    def test_find_free_port(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            manager = RuntimeManager(directory)
            port = manager.find_free_port()
            self.assertIsInstance(port, int)
            self.assertGreater(port, 0)

    def test_build_command_localhost_only(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = RuntimeManager(root)
            command = manager.build_command(root / "model.gguf", 12345, 4096)
            joined = " ".join(command)
            self.assertIn("127.0.0.1", command)
            self.assertNotIn("0.0.0.0", joined)
            self.assertIn("12345", command)
            self.assertIn(str(root / "model.gguf"), command)


if __name__ == "__main__":
    unittest.main()
