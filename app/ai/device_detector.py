from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ComputeDevice:
    id: str
    device_type: str
    vendor: str
    name: str
    architecture: str | None = None
    dedicated_memory_gb: float = 0.0
    shared_memory_gb: float = 0.0
    potential_backends: tuple[str, ...] = ()
    detection_source: str = "unknown"
    available: bool = True
    device_detected: bool = True
    runtime_available: bool = False
    provider_available: bool = False
    model_compatible: bool = False
    backend_usable: bool = False
    driver_version: str | None = None


@dataclass(frozen=True)
class DeviceInventory:
    gpu_devices: tuple[ComputeDevice, ...] = ()
    npu_devices: tuple[ComputeDevice, ...] = ()
    detection_method: str = "not_available"
    technical_detail: str = ""
    physical_cores: int | None = None


def detect_compute_devices(timeout_seconds: float = 4.0) -> DeviceInventory:
    """Best-effort Windows inventory. Detection never implies backend usability."""
    if not sys.platform.startswith("win"):
        return DeviceInventory(detection_method="unsupported_platform")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        (
            "$ErrorActionPreference='Stop';"
            "$gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion);"
            "$cpu=@(Get-CimInstance Win32_Processor | Select-Object NumberOfCores);"
            "$npu=@(Get-CimInstance Win32_PnPEntity | Where-Object {"
            "$_.Name -match 'NPU|Neural|Hexagon|XDNA|AI Boost'" 
            "} | Select-Object Name,Manufacturer);"
            "@{gpu=$gpu;npu=$npu;cpu=$cpu}|ConvertTo-Json -Depth 4 -Compress"
        ),
    ]
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return DeviceInventory(
            detection_method="powershell_cim_failed",
            technical_detail=type(exc).__name__,
        )
    if completed.returncode != 0:
        return DeviceInventory(
            detection_method="powershell_cim_failed",
            technical_detail=f"exit_code={completed.returncode}",
        )
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return DeviceInventory(detection_method="powershell_cim_invalid_json")
    if not isinstance(payload, dict):
        return DeviceInventory(detection_method="powershell_cim_invalid_json")
    return DeviceInventory(
        gpu_devices=tuple(_gpu_device(item) for item in _items(payload.get("gpu")) if _device_name(item)),
        npu_devices=tuple(_npu_device(item) for item in _items(payload.get("npu")) if _device_name(item)),
        detection_method="powershell_cim",
        physical_cores=_physical_core_count(payload.get("cpu")),
    )


def _gpu_device(value: dict[str, Any]) -> ComputeDevice:
    name = _device_name(value)
    vendor = _device_vendor(name, str(value.get("Manufacturer") or ""))
    useful = "microsoft basic display" not in name.lower()
    potential = {
        "nvidia": ("cuda", "vulkan"),
        "amd": ("vulkan",),
        "intel": ("vulkan", "sycl"),
        "qualcomm": ("opencl", "vulkan"),
    }.get(vendor, ())
    memory_bytes = _nonnegative_int(value.get("AdapterRAM"))
    return ComputeDevice(
        id=_stable_device_id("gpu", vendor, name),
        device_type="gpu",
        vendor=vendor,
        name=name,
        dedicated_memory_gb=round(memory_bytes / (1024**3), 2),
        potential_backends=potential,
        detection_source="powershell_cim",
        available=useful,
        driver_version=str(value.get("DriverVersion") or "").strip() or None,
    )


def _npu_device(value: dict[str, Any]) -> ComputeDevice:
    name = _device_name(value)
    vendor = _device_vendor(name, str(value.get("Manufacturer") or ""))
    return ComputeDevice(
        id=_stable_device_id("npu", vendor, name),
        device_type="npu",
        vendor=vendor,
        name=name,
        potential_backends=(),
        detection_source="powershell_cim",
        available=True,
        backend_usable=False,
    )


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _device_name(value: dict[str, Any]) -> str:
    return str(value.get("Name") or "").strip()


def _device_vendor(name: str, manufacturer: str = "") -> str:
    text = f"{name} {manufacturer}".lower()
    if any(token in text for token in ("nvidia", "geforce", "quadro")):
        return "nvidia"
    if any(token in text for token in ("advanced micro devices", "amd", "radeon", "xdna")):
        return "amd"
    if any(token in text for token in ("intel", "arc", "iris", "ai boost")):
        return "intel"
    if any(token in text for token in ("qualcomm", "adreno", "hexagon", "snapdragon")):
        return "qualcomm"
    if "microsoft" in text:
        return "microsoft"
    return "unknown"


def _stable_device_id(device_type: str, vendor: str, name: str) -> str:
    digest = hashlib.sha256(f"{device_type}|{vendor}|{name.lower()}".encode("utf-8")).hexdigest()[:12]
    return f"{device_type}:{vendor}:{digest}"


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _physical_core_count(value: Any) -> int | None:
    counts = [_nonnegative_int(item.get("NumberOfCores")) for item in _items(value)]
    total = sum(count for count in counts if count > 0)
    return total or None
