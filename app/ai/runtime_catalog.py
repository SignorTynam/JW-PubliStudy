from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from app.ai.hardware_profile import HardwareProfile


LLAMA_CPP_RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"


@dataclass(frozen=True)
class RuntimeVariant:
    id: str
    family: str
    display_name: str
    os_name: str
    architecture: str
    backend: str
    supported_vendors: tuple[str, ...]
    executable_names: tuple[str, ...]
    release_api_url: str | None
    asset_patterns: tuple[str, ...]
    excluded_asset_patterns: tuple[str, ...]
    required_cpu_features: tuple[str, ...]
    experimental: bool
    model_format: str
    priority: int


@dataclass(frozen=True)
class RuntimeResolution:
    variant: RuntimeVariant
    available: bool
    asset_name: str | None = None
    asset_url: str | None = None
    release_tag: str | None = None
    reason_code: str = "asset_not_available"
    technical_detail: str = ""
    requires_emulation: bool = False


RUNTIME_VARIANTS: tuple[RuntimeVariant, ...] = (
    RuntimeVariant(
        "llama_cpp_cpu_x86_64_generic",
        "llama_cpp",
        "llama.cpp CPU x64",
        "windows",
        "x86_64",
        "cpu",
        (),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-cpu-x64\.zip$",),
        (r"source", r"debug", r"cudart", r"arm64", r"vulkan", r"cuda", r"hip", r"sycl", r"openvino"),
        (),
        False,
        "gguf",
        70,
    ),
    RuntimeVariant(
        "llama_cpp_cpu_x86_64_avx2",
        "llama_cpp",
        "llama.cpp CPU x64 AVX2",
        "windows",
        "x86_64",
        "cpu",
        (),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-(?:cpu-)?avx2-x64\.zip$",),
        (r"source", r"debug", r"cudart", r"arm64"),
        ("avx2",),
        False,
        "gguf",
        75,
    ),
    RuntimeVariant(
        "llama_cpp_cpu_arm64",
        "llama_cpp",
        "llama.cpp CPU ARM64",
        "windows",
        "arm64",
        "cpu",
        (),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-cpu-arm64\.zip$",),
        (r"source", r"debug", r"x64", r"cuda", r"vulkan", r"opencl"),
        (),
        False,
        "gguf",
        80,
    ),
    RuntimeVariant(
        "llama_cpp_cuda_x86_64",
        "llama_cpp",
        "llama.cpp CUDA x64",
        "windows",
        "x86_64",
        "cuda",
        ("nvidia",),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-cuda-[\w.-]+-x64\.zip$",),
        (r"source", r"debug", r"^cudart-"),
        (),
        False,
        "gguf",
        100,
    ),
    RuntimeVariant(
        "llama_cpp_vulkan_x86_64",
        "llama_cpp",
        "llama.cpp Vulkan x64",
        "windows",
        "x86_64",
        "vulkan",
        ("nvidia", "amd", "intel"),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-vulkan-x64\.zip$",),
        (r"source", r"debug", r"arm64"),
        (),
        False,
        "gguf",
        90,
    ),
    RuntimeVariant(
        "llama_cpp_vulkan_arm64",
        "llama_cpp",
        "llama.cpp Vulkan ARM64",
        "windows",
        "arm64",
        "vulkan",
        ("qualcomm",),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-vulkan-arm64\.zip$",),
        (r"source", r"debug", r"x64"),
        (),
        True,
        "gguf",
        85,
    ),
    RuntimeVariant(
        "llama_cpp_opencl_adreno_arm64",
        "llama_cpp",
        "llama.cpp OpenCL Adreno ARM64",
        "windows",
        "arm64",
        "opencl",
        ("qualcomm",),
        ("llama-server.exe",),
        LLAMA_CPP_RELEASE_API,
        (r"llama-.*-bin-win-opencl-adreno-arm64\.zip$",),
        (r"source", r"debug", r"x64"),
        (),
        True,
        "gguf",
        88,
    ),
)


def list_runtime_variants() -> list[RuntimeVariant]:
    return list(RUNTIME_VARIANTS)


def get_runtime_variant(variant_id: str) -> RuntimeVariant | None:
    return next((variant for variant in RUNTIME_VARIANTS if variant.id == variant_id), None)


def compatible_runtime_variants(
    profile: HardwareProfile,
    *,
    experimental_enabled: bool = False,
) -> list[tuple[RuntimeVariant, bool]]:
    native = profile.architecture.native_architecture
    devices = tuple(profile.gpu_devices)
    compatible: list[tuple[RuntimeVariant, bool]] = []
    for variant in RUNTIME_VARIANTS:
        if variant.os_name != profile.os_name.lower():
            continue
        if variant.experimental and not experimental_enabled:
            continue
        requires_emulation = False
        if variant.architecture != native:
            # Windows ARM64 can launch an x64 child through OS emulation even
            # when the Python process itself is native ARM64. This is a
            # fallback only; native candidates are always sorted first.
            if native == "arm64" and variant.architecture == "x86_64":
                requires_emulation = True
            else:
                continue
        if any(feature not in profile.cpu_features for feature in variant.required_cpu_features):
            continue
        if variant.supported_vendors:
            if not any(device.available and device.vendor in variant.supported_vendors for device in devices):
                continue
        compatible.append((variant, requires_emulation))
    return sorted(compatible, key=lambda item: (item[1], -item[0].priority, item[0].id))


def resolve_runtime_assets(
    release_json: dict[str, Any],
    profile: HardwareProfile,
    *,
    experimental_enabled: bool = False,
    variants: Iterable[tuple[RuntimeVariant, bool]] | None = None,
) -> list[RuntimeResolution]:
    tag = str(release_json.get("tag_name") or "").strip() or None
    assets = release_json.get("assets")
    asset_list = [asset for asset in assets if isinstance(asset, dict)] if isinstance(assets, list) else []
    results: list[RuntimeResolution] = []
    candidates = list(variants) if variants is not None else compatible_runtime_variants(profile, experimental_enabled=experimental_enabled)
    for variant, requires_emulation in candidates:
        matches: list[tuple[str, str]] = []
        for asset in asset_list:
            name = str(asset.get("name") or "").strip()
            url = str(asset.get("browser_download_url") or "").strip()
            lowered = name.lower()
            if not name or not url or not lowered.endswith(".zip"):
                continue
            if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in variant.excluded_asset_patterns):
                continue
            if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in variant.asset_patterns):
                matches.append((name, url))
        if not matches:
            results.append(
                RuntimeResolution(
                    variant,
                    False,
                    release_tag=tag,
                    reason_code="asset_not_available",
                    requires_emulation=requires_emulation,
                )
            )
            continue
        name, url = sorted(matches, key=lambda item: item[0].lower())[0]
        results.append(
            RuntimeResolution(
                variant,
                True,
                asset_name=name,
                asset_url=url,
                release_tag=tag,
                reason_code="compatible",
                technical_detail="url_from_release_metadata",
                requires_emulation=requires_emulation,
            )
        )
    return results
