from __future__ import annotations

from pathlib import Path

from app.ai.backends.base import BackendProbeResult, ModelCompatibilityResult
from app.ai.hardware_profile import HardwareProfile


class DetectedNpuBackend:
    """Inventory-only NPU backend until a real provider stack is integrated.

    It intentionally cannot build a launch plan. Detection is useful for the
    UI, but does not imply that GGUF, llama.cpp, Windows ML, or a vendor NPU
    execution provider are mutually compatible.
    """

    id = "detected_npu_unavailable"

    def is_candidate(self, profile: HardwareProfile) -> bool:
        return bool(profile.npu_devices)

    def probe(self, profile: HardwareProfile) -> BackendProbeResult:
        devices = tuple(device.id for device in profile.npu_devices if device.available)
        return BackendProbeResult(
            backend_id=self.id,
            detected=bool(devices),
            usable=False,
            stable=False,
            reason_code="provider_unavailable" if devices else "device_not_detected",
            devices=devices,
            provider_available=False,
            model_compatible=False,
            generation_tested=False,
            experimental=True,
        )

    def resolve_runtime(self, _profile: HardwareProfile):
        return None

    def validate_model(self, model_path: Path) -> ModelCompatibilityResult:
        return ModelCompatibilityResult(False, "model_incompatible", Path(model_path).suffix.lower().lstrip("."))

    def build_launch_plan(self, *args, **kwargs):
        raise RuntimeError("npu_provider_unavailable")

    def health_check(self, _endpoint: str) -> bool:
        return False
