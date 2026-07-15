from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BackendCapabilities:
    supports_device_selection: bool = False
    supports_gpu_layers: bool = False
    available_devices: tuple[str, ...] = ()
    supported_flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RuntimeLaunchPlan:
    backend_id: str
    runtime_variant_id: str
    executable: Path
    model_path: Path
    host: str
    port: int
    context_tokens: int
    device_id: str | None = None
    arguments: tuple[str, ...] = ()
    environment: dict[str, str] = field(default_factory=dict)
    working_directory: Path | None = None
    requires_emulation: bool = False
    cpu_threads: int | None = None
    gpu_layers: int | None = None
    host_architecture: str = "unknown"
    executable_architecture: str = "unknown"
    selection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("runtime_host_must_be_local")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("runtime_port_invalid")
        if int(self.context_tokens) < 512:
            raise ValueError("runtime_context_invalid")
        if self.working_directory is None:
            object.__setattr__(self, "working_directory", self.executable.parent)
