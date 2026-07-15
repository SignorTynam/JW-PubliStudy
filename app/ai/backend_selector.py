from __future__ import annotations

from dataclasses import dataclass

from app.ai.backends.base import BackendProbeResult
from app.ai.hardware_profile import HardwareProfile


@dataclass(frozen=True)
class BackendCandidate:
    backend_id: str
    runtime_variant_id: str
    device_id: str | None
    score: int
    reasons: tuple[str, ...]
    penalties: tuple[str, ...]
    probe: BackendProbeResult


@dataclass(frozen=True)
class BackendSelection:
    primary: BackendCandidate
    fallbacks: tuple[BackendCandidate, ...]
    rejected: tuple[BackendCandidate, ...]


class BackendSelectionError(RuntimeError):
    def __init__(self, reason_code: str, rejected: tuple[BackendCandidate, ...] = ()) -> None:
        self.reason_code = reason_code
        self.rejected = rejected
        super().__init__(reason_code)


class BackendSelector:
    INCOMPATIBLE_REASONS = {
        "architecture_mismatch",
        "asset_not_available",
        "device_not_detected",
        "device_not_listed_by_runtime",
        "missing_driver",
        "missing_dll",
        "provider_unavailable",
        "model_format_unsupported",
        "model_incompatible",
        "insufficient_memory",
        "runtime_validation_failed",
        "benchmark_failed",
        "experimental_disabled",
    }

    def select(
        self,
        profile: HardwareProfile,
        probes: list[BackendProbeResult],
        *,
        experimental_enabled: bool = False,
    ) -> BackendSelection:
        accepted: list[BackendCandidate] = []
        rejected: list[BackendCandidate] = []
        seen: set[tuple[str, str]] = set()
        for probe in probes:
            variant_id = probe.runtime_variant_id or "unresolved"
            key = (probe.backend_id, variant_id)
            if key in seen:
                continue
            seen.add(key)
            candidate = self._candidate(profile, probe)
            npu_backend = "npu" in probe.backend_id.lower()
            npu_incomplete = npu_backend and not (
                probe.provider_available and probe.model_compatible and probe.generation_tested and probe.usable
            )
            incompatible = (
                not probe.usable
                or probe.reason_code in self.INCOMPATIBLE_REASONS
                or (probe.experimental and not experimental_enabled)
                or npu_incomplete
            )
            if incompatible:
                rejected.append(candidate)
            else:
                accepted.append(candidate)
        if not accepted:
            raise BackendSelectionError("no_usable_backend", tuple(sorted(rejected, key=lambda item: item.score, reverse=True)))
        ranking = sorted(accepted, key=lambda item: (-item.score, item.backend_id, item.runtime_variant_id))
        return BackendSelection(ranking[0], tuple(ranking[1:]), tuple(sorted(rejected, key=lambda item: item.score, reverse=True)))

    def _candidate(self, profile: HardwareProfile, probe: BackendProbeResult) -> BackendCandidate:
        score = 0
        reasons: list[str] = []
        penalties: list[str] = []
        if not probe.requires_emulation:
            score += 200
            reasons.append("native_architecture")
        else:
            score -= 150
            penalties.append("emulation")
        if probe.usable:
            score += 100
            reasons.append("probe_validated")
        else:
            score -= 120
            penalties.append("probe_failed")
        if probe.devices:
            score += 80
            reasons.append("device_listed_by_runtime")
        if probe.benchmark_completed:
            score += 60
            reasons.append("benchmark_completed")
        if probe.runtime_installed:
            score += 40
            reasons.append("runtime_installed")
        if probe.stable and not probe.experimental:
            score += 30
            reasons.append("stable_backend")
        if probe.experimental:
            score -= 80
            penalties.append("experimental")
        if probe.reason_code == "missing_driver":
            score -= 60
            penalties.append("driver_unverified")
        device_id = probe.devices[0] if probe.devices else None
        return BackendCandidate(
            probe.backend_id,
            probe.runtime_variant_id or "unresolved",
            device_id,
            score,
            tuple(reasons),
            tuple(penalties),
            probe,
        )
