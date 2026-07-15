from __future__ import annotations

from pathlib import Path

from app.ai.device_detector import ComputeDevice
from app.ai.hardware_profile import ArchitectureInfo, HardwareProfile, hardware_fingerprint


def device(
    vendor: str,
    *,
    device_type: str = "gpu",
    memory_gb: float = 8.0,
    name: str | None = None,
) -> ComputeDevice:
    return ComputeDevice(
        id=f"{device_type}:{vendor}:test",
        device_type=device_type,
        vendor=vendor,
        name=name or f"{vendor.title()} test {device_type.upper()}",
        dedicated_memory_gb=memory_gb,
        potential_backends=("cuda", "vulkan") if vendor == "nvidia" else ("vulkan",),
        detection_source="test",
    )


def profile(
    *,
    native: str = "x86_64",
    process: str | None = None,
    total_ram: float = 16.0,
    available_ram: float = 10.0,
    gpu_devices: tuple[ComputeDevice, ...] = (),
    npu_devices: tuple[ComputeDevice, ...] = (),
    features: frozenset[str] = frozenset({"avx2"}),
    data_dir: Path = Path("."),
) -> HardwareProfile:
    process_arch = process or native
    architecture = ArchitectureInfo(
        native,
        process_arch,
        native != process_arch,
        f"{process_arch}_on_{native}" if native != process_arch else None,
        "test",
    )
    base = HardwareProfile(
        os_name="Windows",
        os_version="11",
        os_build="26100",
        architecture=architecture,
        cpu_vendor="qualcomm" if native == "arm64" else "intel",
        cpu_model="Test CPU",
        logical_cores=12,
        physical_cores=8,
        cpu_features=features,
        total_ram_gb=total_ram,
        available_ram_gb=available_ram,
        free_disk_gb=100.0,
        gpu_devices=gpu_devices,
        npu_devices=npu_devices,
        data_dir=data_dir,
        fingerprint="",
        detection_methods=("test",),
    )
    return HardwareProfile(**{**base.__dict__, "fingerprint": hardware_fingerprint(base)})
