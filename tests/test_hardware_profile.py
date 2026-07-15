import unittest
from dataclasses import replace
from unittest.mock import patch

from app.ai.hardware_profile import (
    IMAGE_FILE_MACHINE_AMD64,
    IMAGE_FILE_MACHINE_ARM64,
    IMAGE_FILE_MACHINE_UNKNOWN,
    detect_architecture,
    hardware_fingerprint,
    memory_gb,
    normalize_architecture,
)
from tests.ai_test_helpers import profile


class HardwareProfileTest(unittest.TestCase):
    def test_architecture_aliases(self) -> None:
        self.assertEqual(normalize_architecture("AMD64"), "x86_64")
        self.assertEqual(normalize_architecture("x86_64"), "x86_64")
        self.assertEqual(normalize_architecture("ARM64"), "arm64")
        self.assertEqual(normalize_architecture("aarch64"), "arm64")

    def test_native_x64_process(self) -> None:
        with patch("app.ai.hardware_profile._windows_iswow64process2", return_value=(IMAGE_FILE_MACHINE_UNKNOWN, IMAGE_FILE_MACHINE_AMD64)):
            result = detect_architecture(os_name="Windows", machine="AMD64")
        self.assertEqual((result.native_architecture, result.process_architecture), ("x86_64", "x86_64"))
        self.assertFalse(result.running_under_emulation)

    def test_native_arm64_process(self) -> None:
        with patch("app.ai.hardware_profile._windows_iswow64process2", return_value=(IMAGE_FILE_MACHINE_UNKNOWN, IMAGE_FILE_MACHINE_ARM64)):
            result = detect_architecture(os_name="Windows", machine="ARM64")
        self.assertEqual((result.native_architecture, result.process_architecture), ("arm64", "arm64"))

    def test_x64_process_emulated_on_arm64(self) -> None:
        with patch("app.ai.hardware_profile._windows_iswow64process2", return_value=(IMAGE_FILE_MACHINE_AMD64, IMAGE_FILE_MACHINE_ARM64)):
            result = detect_architecture(os_name="Windows", machine="AMD64")
        self.assertTrue(result.running_under_emulation)
        self.assertEqual(result.emulation_description, "x86_64_on_arm64")

    def test_get_native_system_info_fallback(self) -> None:
        with (
            patch("app.ai.hardware_profile._windows_iswow64process2", return_value=None),
            patch("app.ai.hardware_profile._windows_native_architecture", return_value="arm64"),
        ):
            result = detect_architecture(os_name="Windows", machine="AMD64")
        self.assertEqual(result.detection_method, "get_native_system_info")
        self.assertTrue(result.running_under_emulation)

    def test_environment_fallback(self) -> None:
        with (
            patch("app.ai.hardware_profile._windows_iswow64process2", return_value=None),
            patch("app.ai.hardware_profile._windows_native_architecture", return_value="unknown"),
        ):
            result = detect_architecture(
                os_name="Windows",
                machine="AMD64",
                environ={"PROCESSOR_ARCHITEW6432": "ARM64"},
            )
        self.assertEqual(result.detection_method, "environment")
        self.assertEqual(result.native_architecture, "arm64")

    def test_detection_failure_does_not_raise(self) -> None:
        with (
            patch("app.ai.hardware_profile._windows_iswow64process2", return_value=None),
            patch("app.ai.hardware_profile._windows_native_architecture", return_value="unknown"),
        ):
            result = detect_architecture(os_name="Windows", machine="mystery", environ={})
        self.assertEqual(result.native_architecture, "unknown")

    def test_fingerprint_is_stable_and_architecture_sensitive(self) -> None:
        first = profile(native="x86_64")
        second = replace(first, fingerprint="")
        self.assertEqual(hardware_fingerprint(first), hardware_fingerprint(second))
        arm = replace(first, architecture=replace(first.architecture, native_architecture="arm64"), fingerprint="")
        self.assertNotEqual(hardware_fingerprint(first), hardware_fingerprint(arm))

    def test_memory_failure_returns_safe_zeros(self) -> None:
        with patch("app.ai.hardware_profile.platform.system", return_value="Other"):
            self.assertEqual(memory_gb(), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
