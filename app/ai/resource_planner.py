from __future__ import annotations

import math
from dataclasses import dataclass

from app.ai.backend_selector import BackendCandidate
from app.ai.hardware_profile import HardwareProfile
from app.ai.model_catalog import LocalModelSpec, get_model, list_models


@dataclass(frozen=True)
class ResourcePlan:
    model_id: str
    backend_id: str
    runtime_variant_id: str
    device_id: str | None
    context_tokens: int
    max_output_tokens: int
    cpu_threads: int | None
    gpu_layers: int | None
    estimated_model_memory_gb: float
    estimated_kv_cache_gb: float
    estimated_runtime_overhead_gb: float
    reserved_system_memory_gb: float
    estimated_total_memory_gb: float
    reason_codes: tuple[str, ...]


class ResourcePlanner:
    def plan(
        self,
        profile: HardwareProfile,
        backend: BackendCandidate,
        *,
        optimization_mode: str = "automatic",
        custom_model_size_gb: float | None = None,
        custom_model_id: str = "custom",
    ) -> ResourcePlan:
        mode = optimization_mode if optimization_mode in {"automatic", "memory_saver", "performance"} else "automatic"
        reserve = self._system_reserve(profile)
        application_reserve = 0.7
        safety_margin = 0.5
        memory_budget = max(0.0, profile.available_ram_gb - reserve - application_reserve - safety_margin)
        reasons: list[str] = [f"optimization_{mode}"]
        if profile.available_ram_gb < 4.0:
            reasons.extend(("memory_pressure", "close_heavy_applications"))
        emulated = backend.probe.requires_emulation
        if emulated:
            reasons.append("emulation_penalty")

        if custom_model_size_gb is not None:
            model = None
            model_id = custom_model_id
            model_size = max(0.1, float(custom_model_size_gb))
            context_cap = 4096
            max_output = 600
        else:
            model = self._choose_catalog_model(profile, memory_budget, mode, emulated)
            model_id = model.id
            model_size = model.size_gb
            context_cap = model.context_tokens
            max_output = model.default_max_tokens

        context_candidates = self._context_candidates(model_id, context_cap, mode)
        chosen_context = context_candidates[-1]
        estimates = self._estimate(model_id, model_size, chosen_context, backend)
        for context in context_candidates:
            candidate_estimates = self._estimate(model_id, model_size, context, backend)
            chosen_context = context
            estimates = candidate_estimates
            if candidate_estimates[-1] <= memory_budget:
                break
        if estimates[-1] > memory_budget:
            reasons.append("available_memory_below_estimate")
        if chosen_context < context_cap:
            reasons.append("context_reduced_for_memory")

        logical = max(1, profile.logical_cores)
        thread_ratio = 0.5 if mode == "memory_saver" else 0.75
        cpu_threads = max(1, min(max(1, logical - 2), math.floor(logical * thread_ratio)))
        accelerated = any(token in backend.backend_id for token in ("cuda", "vulkan", "opencl"))
        gpu_layers = None
        selected_device_id = backend.device_id
        if accelerated and backend.probe.devices and "--n-gpu-layers" in backend.probe.supported_flags:
            gpu_memory = max(
                (device.dedicated_memory_gb + device.shared_memory_gb for device in profile.gpu_devices if device.available),
                default=0.0,
            )
            usable_gpu_memory = max(0.0, gpu_memory - 0.5)
            if usable_gpu_memory > 0.0:
                required_for_full_offload = max(0.1, estimates[0] + estimates[1])
                gpu_layers = max(1, min(99, int(99 * min(1.0, usable_gpu_memory / required_for_full_offload))))
                reasons.append("gpu_offload_within_memory_budget")
            else:
                selected_device_id = None
                reasons.append("gpu_memory_unverified")
        safe_output = min(max_output, 500 if chosen_context <= 2048 else 800)
        if mode == "memory_saver":
            safe_output = min(safe_output, 400)
        return ResourcePlan(
            model_id=model_id,
            backend_id=backend.backend_id,
            runtime_variant_id=backend.runtime_variant_id,
            device_id=selected_device_id,
            context_tokens=chosen_context,
            max_output_tokens=max(160, safe_output),
            cpu_threads=cpu_threads,
            gpu_layers=gpu_layers,
            estimated_model_memory_gb=estimates[0],
            estimated_kv_cache_gb=estimates[1],
            estimated_runtime_overhead_gb=estimates[2],
            reserved_system_memory_gb=reserve + application_reserve + safety_margin,
            estimated_total_memory_gb=estimates[3],
            reason_codes=tuple(reasons),
        )

    def _choose_catalog_model(
        self,
        profile: HardwareProfile,
        memory_budget: float,
        mode: str,
        emulated: bool,
    ) -> LocalModelSpec:
        models = sorted(
            (model for model in list_models() if model.min_ram_gb <= profile.total_ram_gb),
            key=lambda item: item.size_gb,
        )
        if not models:
            models = [get_model("small") or list_models()[0]]
        if mode == "memory_saver" or profile.available_ram_gb < 5.0:
            return get_model("small") or models[0]
        safe: list[LocalModelSpec] = []
        for model in models:
            estimate = self._estimate(model.id, model.size_gb, min(4096, model.context_tokens), None)[-1]
            if estimate <= memory_budget:
                safe.append(model)
        if not safe:
            return get_model("small") or models[0]
        selected = safe[-1]
        if emulated and selected.id != "small":
            selected = safe[max(0, len(safe) - 2)]
        if mode != "performance" and selected.id == "large" and profile.available_ram_gb < 16:
            return get_model("medium") or selected
        return selected

    def _context_candidates(self, model_id: str, cap: int, mode: str) -> list[int]:
        candidates = [value for value in (8192, 6144, 4096, 2048) if value <= cap]
        if not candidates:
            candidates = [2048]
        if mode == "memory_saver":
            return [min(2048, candidates[-1])]
        return candidates

    def _estimate(
        self,
        model_id: str,
        model_size: float,
        context: int,
        backend: BackendCandidate | None,
    ) -> tuple[float, float, float, float]:
        model_memory = max(0.0, model_size * 1.08)
        kv_rate = {"small": 0.00008, "medium": 0.00015, "large": 0.00024}.get(model_id, 0.00015)
        kv_cache = max(0.0, context * kv_rate)
        runtime_overhead = 0.45
        if backend is not None and backend.probe.requires_emulation:
            runtime_overhead += 0.6
        if backend is not None and any(token in backend.backend_id for token in ("cuda", "vulkan", "opencl")):
            runtime_overhead += 0.25
        total = model_memory + kv_cache + runtime_overhead
        return tuple(round(value, 3) for value in (model_memory, kv_cache, runtime_overhead, total))

    def _system_reserve(self, profile: HardwareProfile) -> float:
        if profile.total_ram_gb >= 24:
            return 2.0
        if profile.total_ram_gb >= 12:
            return 1.25
        return 0.75
