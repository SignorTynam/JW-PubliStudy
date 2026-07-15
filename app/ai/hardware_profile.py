from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Mapping

from app.ai.device_detector import ComputeDevice, DeviceInventory, detect_compute_devices
from app.version import APP_VERSION


ARCHITECTURE_ALIASES = {
    "amd64": "x86_64",
    "x86_64": "x86_64",
    "x64": "x86_64",
    "arm64": "arm64",
    "aarch64": "arm64",
    "arm": "arm32",
    "arm32": "arm32",
    "i386": "x86",
    "i486": "x86",
    "i586": "x86",
    "i686": "x86",
    "x86": "x86",
}

IMAGE_FILE_MACHINE_UNKNOWN = 0x0000
IMAGE_FILE_MACHINE_I386 = 0x014C
IMAGE_FILE_MACHINE_ARM = 0x01C0
IMAGE_FILE_MACHINE_AMD64 = 0x8664
IMAGE_FILE_MACHINE_ARM64 = 0xAA64


@dataclass(frozen=True)
class ArchitectureInfo:
    native_architecture: str
    process_architecture: str
    running_under_emulation: bool
    emulation_description: str | None = None
    detection_method: str = "platform"


@dataclass(frozen=True)
class HardwareProfile:
    os_name: str
    os_version: str
    os_build: str
    architecture: ArchitectureInfo
    cpu_vendor: str
    cpu_model: str
    logical_cores: int
    physical_cores: int | None
    cpu_features: frozenset[str]
    total_ram_gb: float
    available_ram_gb: float
    free_disk_gb: float
    gpu_devices: tuple[ComputeDevice, ...]
    npu_devices: tuple[ComputeDevice, ...]
    data_dir: Path
    fingerprint: str
    detection_methods: tuple[str, ...] = ()


def normalize_architecture(value: str | None) -> str:
    normalized = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    return ARCHITECTURE_ALIASES.get(normalized, "unknown")


def architecture_from_machine_code(value: int) -> str:
    return {
        IMAGE_FILE_MACHINE_I386: "x86",
        IMAGE_FILE_MACHINE_AMD64: "x86_64",
        IMAGE_FILE_MACHINE_ARM: "arm32",
        IMAGE_FILE_MACHINE_ARM64: "arm64",
    }.get(int(value), "unknown")


def detect_architecture(
    *,
    os_name: str | None = None,
    machine: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ArchitectureInfo:
    system = (os_name or platform.system()).lower()
    process_fallback = normalize_architecture(machine or platform.machine())
    environment = os.environ if environ is None else environ
    if system == "windows":
        wow64 = _windows_iswow64process2()
        if wow64 is not None:
            process_machine, native_machine = wow64
            native = architecture_from_machine_code(native_machine)
            process = native if process_machine == IMAGE_FILE_MACHINE_UNKNOWN else architecture_from_machine_code(process_machine)
            return _architecture_info(native, process, "iswow64process2")
        native_system = _windows_native_architecture()
        if native_system != "unknown":
            return _architecture_info(native_system, process_fallback, "get_native_system_info")
        native_environment = normalize_architecture(
            environment.get("PROCESSOR_ARCHITEW6432") or environment.get("PROCESSOR_ARCHITECTURE")
        )
        if native_environment != "unknown":
            return _architecture_info(native_environment, process_fallback, "environment")
    return _architecture_info(process_fallback, process_fallback, "platform")


def get_hardware_profile(data_dir: Path, *, detect_devices: bool = True) -> HardwareProfile:
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    architecture = detect_architecture()
    total_ram, available_ram = memory_gb()
    cpu_vendor, cpu_model, cpu_method = _cpu_identity()
    inventory = detect_compute_devices() if detect_devices else DeviceInventory(detection_method="skipped")
    base = HardwareProfile(
        os_name=platform.system() or "unknown",
        os_version=platform.version() or "unknown",
        os_build=_os_build(),
        architecture=architecture,
        cpu_vendor=cpu_vendor,
        cpu_model=cpu_model,
        logical_cores=max(1, os.cpu_count() or 1),
        physical_cores=inventory.physical_cores,
        cpu_features=frozenset(_cpu_features(architecture)),
        total_ram_gb=total_ram,
        available_ram_gb=available_ram,
        free_disk_gb=_free_disk_gb(path),
        gpu_devices=inventory.gpu_devices,
        npu_devices=inventory.npu_devices,
        data_dir=path,
        fingerprint="",
        detection_methods=(architecture.detection_method, cpu_method, inventory.detection_method),
    )
    return replace(base, fingerprint=hardware_fingerprint(base))


def hardware_fingerprint(profile: HardwareProfile) -> str:
    payload = {
        "os": profile.os_name,
        "version": profile.os_version,
        "build": profile.os_build,
        "native_architecture": profile.architecture.native_architecture,
        "process_architecture": profile.architecture.process_architecture,
        "emulation": profile.architecture.running_under_emulation,
        "cpu_vendor": profile.cpu_vendor,
        "cpu_model": profile.cpu_model,
        "cpu_features": sorted(profile.cpu_features),
        "logical_cores": profile.logical_cores,
        "total_ram_gb": round(profile.total_ram_gb, 1),
        "app_version": APP_VERSION,
        "gpu": sorted((device.vendor, device.name.lower(), device.driver_version or "") for device in profile.gpu_devices),
        "npu": sorted((device.vendor, device.name.lower(), device.driver_version or "") for device in profile.npu_devices),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def profile_to_dict(profile: HardwareProfile) -> dict:
    result = asdict(profile)
    result["data_dir"] = str(profile.data_dir)
    result["cpu_features"] = sorted(profile.cpu_features)
    return result


def memory_gb() -> tuple[float, float]:
    if platform.system().lower() == "windows":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return round(status.ullTotalPhys / (1024**3), 1), round(status.ullAvailPhys / (1024**3), 1)
        except (AttributeError, OSError, ValueError):
            pass
    return 0.0, 0.0


def _architecture_info(native: str, process: str, method: str) -> ArchitectureInfo:
    native = native if native in {"x86_64", "arm64", "x86", "arm32"} else "unknown"
    process = process if process in {"x86_64", "arm64", "x86", "arm32"} else "unknown"
    emulated = native != "unknown" and process != "unknown" and native != process
    description = f"{process}_on_{native}" if emulated else None
    return ArchitectureInfo(native, process, emulated, description, method)


def _windows_iswow64process2() -> tuple[int, int] | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        function = kernel32.IsWow64Process2
        process_machine = ctypes.c_ushort(0)
        native_machine = ctypes.c_ushort(0)
        current_process = kernel32.GetCurrentProcess()
        if function(current_process, ctypes.byref(process_machine), ctypes.byref(native_machine)):
            return int(process_machine.value), int(native_machine.value)
    except (AttributeError, OSError, ValueError):
        pass
    return None


def _windows_native_architecture() -> str:
    if not sys.platform.startswith("win"):
        return "unknown"
    try:
        buffer = (ctypes.c_byte * 64)()
        ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(buffer))
        machine = ctypes.c_ushort.from_buffer(buffer).value
        return architecture_from_machine_code(machine)
    except (AttributeError, OSError, ValueError):
        return "unknown"


def _cpu_identity() -> tuple[str, str, str]:
    model = platform.processor().strip() or platform.uname().processor.strip() or "unknown"
    vendor_text = model
    method = "platform"
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                model = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip() or model
                vendor_text = str(winreg.QueryValueEx(key, "VendorIdentifier")[0]).strip() or model
                method = "windows_registry"
        except (ImportError, OSError, ValueError):
            pass
    return _normalize_cpu_vendor(f"{vendor_text} {model}"), model, method


def _normalize_cpu_vendor(value: str) -> str:
    text = value.lower()
    if any(token in text for token in ("genuineintel", "intel")):
        return "intel"
    if any(token in text for token in ("authenticamd", "advanced micro devices", "amd")):
        return "amd"
    if any(token in text for token in ("qualcomm", "snapdragon")):
        return "qualcomm"
    if "apple" in text:
        return "apple"
    if "microsoft" in text:
        return "microsoft"
    return "unknown"


def _cpu_features(architecture: ArchitectureInfo) -> set[str]:
    features: set[str] = set()
    if sys.platform.startswith("win"):
        checks = {39: "avx", 40: "avx2", 41: "avx512"} if architecture.process_architecture == "x86_64" else {19: "neon"}
        for feature_id, name in checks.items():
            try:
                if ctypes.windll.kernel32.IsProcessorFeaturePresent(feature_id):
                    features.add(name)
            except (AttributeError, OSError, ValueError):
                continue
        if "neon" in features:
            features.add("asimd")
        return features
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return features
    for name in ("avx", "avx2", "avx512", "fma", "sse4_2", "neon", "asimd", "dotprod", "i8mm", "sve"):
        if re.search(rf"\b{re.escape(name)}\b", cpuinfo):
            features.add(name)
    return features


def _os_build() -> str:
    if sys.platform.startswith("win"):
        try:
            return str(sys.getwindowsversion().build)
        except (AttributeError, OSError):
            pass
    return platform.release() or "unknown"


def _free_disk_gb(path: Path) -> float:
    try:
        return round(shutil.disk_usage(path).free / (1024**3), 1)
    except OSError:
        return 0.0
