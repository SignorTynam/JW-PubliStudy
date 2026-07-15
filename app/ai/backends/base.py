from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.ai.hardware_profile import HardwareProfile
from app.ai.runtime_catalog import RuntimeResolution
from app.ai.runtime_launch_plan import RuntimeLaunchPlan


@dataclass(frozen=True)
class BackendProbeResult:
    backend_id: str
    detected: bool
    usable: bool
    stable: bool
    reason_code: str
    technical_detail: str = ""
    devices: tuple[str, ...] = ()
    supported_flags: frozenset[str] = frozenset()
    runtime_variant_id: str | None = None
    requires_emulation: bool = False
    experimental: bool = False
    runtime_installed: bool = False
    benchmark_completed: bool = False
    provider_available: bool = False
    model_compatible: bool = True
    generation_tested: bool = False


@dataclass(frozen=True)
class ModelCompatibilityResult:
    compatible: bool
    reason_code: str
    model_format: str


class InferenceBackend(Protocol):
    id: str

    def is_candidate(self, profile: HardwareProfile) -> bool: ...

    def probe(self, profile: HardwareProfile) -> BackendProbeResult: ...

    def resolve_runtime(self, profile: HardwareProfile) -> RuntimeResolution | None: ...

    def validate_model(self, model_path: Path) -> ModelCompatibilityResult: ...

    def build_launch_plan(self, *args, **kwargs) -> RuntimeLaunchPlan: ...

    def health_check(self, endpoint: str) -> bool: ...
