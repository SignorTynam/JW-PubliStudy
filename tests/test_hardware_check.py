from pathlib import Path
import unittest

from app.ai.hardware_check import HardwareInfo, classify_machine


class HardwareCheckTest(unittest.TestCase):
    def test_classify_machine(self) -> None:
        self.assertEqual(classify_machine(HardwareInfo("Windows", "x64", 8, 20, Path("."))), "low")
        self.assertEqual(classify_machine(HardwareInfo("Windows", "x64", 16, 20, Path("."))), "medium")
        self.assertEqual(classify_machine(HardwareInfo("Windows", "x64", 32, 20, Path("."))), "high")


if __name__ == "__main__":
    unittest.main()
