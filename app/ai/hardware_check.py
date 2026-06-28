from __future__ import annotations

import ctypes
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareInfo:
    os_name: str
    architecture: str
    total_ram_gb: float
    free_disk_gb: float
    data_dir: Path


def get_hardware_info(data_dir: Path) -> HardwareInfo:
    path = Path(data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return HardwareInfo(
        os_name=platform.system() or "unknown",
        architecture=platform.machine() or "unknown",
        total_ram_gb=_total_ram_gb(),
        free_disk_gb=_free_disk_gb(path),
        data_dir=path,
    )


def classify_machine(info: HardwareInfo) -> str:
    if info.total_ram_gb >= 24:
        return "high"
    if info.total_ram_gb >= 12:
        return "medium"
    return "low"


def _total_ram_gb() -> float:
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
                return round(status.ullTotalPhys / (1024**3), 1)
        except (AttributeError, OSError, ValueError):
            pass
    return 0.0


def _free_disk_gb(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return 0.0
    return round(usage.free / (1024**3), 1)

