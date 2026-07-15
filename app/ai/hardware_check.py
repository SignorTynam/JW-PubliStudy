from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.ai.hardware_profile import get_hardware_profile, memory_gb


@dataclass(frozen=True)
class HardwareInfo:
    os_name: str
    architecture: str
    total_ram_gb: float
    free_disk_gb: float
    data_dir: Path
    available_ram_gb: float = 0.0


def get_hardware_info(data_dir: Path) -> HardwareInfo:
    profile = get_hardware_profile(data_dir, detect_devices=False)
    return HardwareInfo(
        os_name=profile.os_name,
        architecture=profile.architecture.native_architecture,
        total_ram_gb=profile.total_ram_gb,
        free_disk_gb=profile.free_disk_gb,
        data_dir=profile.data_dir,
        available_ram_gb=profile.available_ram_gb,
    )


def classify_machine(info: HardwareInfo) -> str:
    if info.total_ram_gb >= 24:
        return "high"
    if info.total_ram_gb >= 12:
        return "medium"
    return "low"


def _total_ram_gb() -> float:
    return _memory_gb()[0]


def _memory_gb() -> tuple[float, float]:
    return memory_gb()
