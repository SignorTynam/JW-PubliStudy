import json
import subprocess
import unittest
from unittest.mock import patch

from app.ai.device_detector import detect_compute_devices


class DeviceDetectorTest(unittest.TestCase):
    def test_gpu_and_npu_detection_does_not_imply_usability(self) -> None:
        payload = {
            "gpu": [{"Name": "NVIDIA GeForce Test", "AdapterRAM": 8 * 1024**3}],
            "npu": [{"Name": "Qualcomm Hexagon NPU", "Manufacturer": "Qualcomm"}],
            "cpu": [{"NumberOfCores": 8}],
        }
        completed = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
        with patch("app.ai.device_detector.sys.platform", "win32"), patch(
            "app.ai.device_detector.subprocess.run", return_value=completed
        ):
            inventory = detect_compute_devices()
        self.assertEqual(inventory.gpu_devices[0].vendor, "nvidia")
        self.assertIn("cuda", inventory.gpu_devices[0].potential_backends)
        self.assertEqual(inventory.npu_devices[0].vendor, "qualcomm")
        self.assertFalse(inventory.npu_devices[0].backend_usable)
        self.assertFalse(inventory.npu_devices[0].provider_available)
        self.assertEqual(inventory.physical_cores, 8)

    def test_powershell_failure_is_best_effort(self) -> None:
        with patch("app.ai.device_detector.sys.platform", "win32"), patch(
            "app.ai.device_detector.subprocess.run", side_effect=OSError("missing")
        ):
            inventory = detect_compute_devices()
        self.assertEqual(inventory.gpu_devices, ())
        self.assertEqual(inventory.detection_method, "powershell_cim_failed")

    def test_non_windows_has_empty_inventory(self) -> None:
        with patch("app.ai.device_detector.sys.platform", "linux"):
            self.assertEqual(detect_compute_devices().detection_method, "unsupported_platform")


if __name__ == "__main__":
    unittest.main()
