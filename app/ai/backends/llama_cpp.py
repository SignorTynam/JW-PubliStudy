from __future__ import annotations

from pathlib import Path

from app.ai.backends.base import BackendProbeResult, ModelCompatibilityResult
from app.ai.hardware_profile import HardwareProfile
from app.ai.runtime_catalog import RuntimeResolution
from app.ai.runtime_launch_plan import RuntimeLaunchPlan


class _LlamaCppBackend:
    id = "llama_cpp"
    backend = "cpu"
    supported_vendors: tuple[str, ...] = ()

    def __init__(
        self,
        resolution: RuntimeResolution | None = None,
        *,
        supported_flags: frozenset[str] = frozenset(),
        available_devices: tuple[str, ...] = (),
        runtime_validated: bool = False,
    ) -> None:
        self._resolution = resolution
        self._supported_flags = supported_flags
        self._available_devices = available_devices
        self._runtime_validated = runtime_validated

    def is_candidate(self, profile: HardwareProfile) -> bool:
        if self.backend == "cpu":
            return True
        return any(device.available and device.vendor in self.supported_vendors for device in profile.gpu_devices)

    def probe(self, profile: HardwareProfile) -> BackendProbeResult:
        detected = self.is_candidate(profile)
        resolution_available = bool(self._resolution and self._resolution.available)
        accelerated = self.backend != "cpu"
        device_verified = bool(self._available_devices)
        usable = detected and resolution_available and self._runtime_validated and (not accelerated or device_verified)
        if not detected:
            reason = "device_not_detected"
        elif not resolution_available:
            reason = "asset_not_available"
        elif not self._runtime_validated:
            reason = "runtime_validation_failed"
        elif accelerated and not device_verified:
            reason = "device_not_listed_by_runtime"
        else:
            reason = "compatible"
        return BackendProbeResult(
            backend_id=self.id,
            detected=detected,
            usable=usable,
            stable=self.backend == "cpu" or self._runtime_validated,
            reason_code=reason,
            devices=self._available_devices,
            supported_flags=self._supported_flags,
            runtime_variant_id=self._resolution.variant.id if self._resolution else None,
            requires_emulation=self._resolution.requires_emulation if self._resolution else False,
            experimental=self._resolution.variant.experimental if self._resolution else False,
            runtime_installed=self._runtime_validated,
            provider_available=not accelerated or device_verified,
            generation_tested=False,
        )

    def resolve_runtime(self, _profile: HardwareProfile) -> RuntimeResolution | None:
        return self._resolution

    def validate_model(self, model_path: Path) -> ModelCompatibilityResult:
        compatible = Path(model_path).suffix.lower() == ".gguf"
        return ModelCompatibilityResult(compatible, "compatible" if compatible else "model_format_unsupported", "gguf")

    def health_check(self, _endpoint: str) -> bool:
        return False

    def build_launch_plan(
        self,
        *,
        executable: Path,
        model_path: Path,
        port: int,
        context_tokens: int,
        device_id: str | None = None,
        arguments: tuple[str, ...] = (),
        environment: dict[str, str] | None = None,
        requires_emulation: bool = False,
        cpu_threads: int | None = None,
        gpu_layers: int | None = None,
        host_architecture: str = "unknown",
        executable_architecture: str = "unknown",
        selection_reasons: tuple[str, ...] = (),
    ) -> RuntimeLaunchPlan:
        resolution = self._resolution
        return RuntimeLaunchPlan(
            backend_id=self.id,
            runtime_variant_id=resolution.variant.id if resolution else "unresolved",
            executable=Path(executable),
            model_path=Path(model_path),
            host="127.0.0.1",
            port=port,
            context_tokens=context_tokens,
            device_id=device_id,
            arguments=arguments,
            environment=dict(environment or {}),
            working_directory=Path(executable).parent,
            requires_emulation=requires_emulation,
            cpu_threads=cpu_threads,
            gpu_layers=gpu_layers,
            host_architecture=host_architecture,
            executable_architecture=executable_architecture,
            selection_reasons=selection_reasons,
        )


class LlamaCppCpuBackend(_LlamaCppBackend):
    id = "llama_cpp_cpu"
    backend = "cpu"


class LlamaCppCudaBackend(_LlamaCppBackend):
    id = "llama_cpp_cuda"
    backend = "cuda"
    supported_vendors = ("nvidia",)


class LlamaCppVulkanBackend(_LlamaCppBackend):
    id = "llama_cpp_vulkan"
    backend = "vulkan"
    supported_vendors = ("nvidia", "amd", "intel", "qualcomm")
