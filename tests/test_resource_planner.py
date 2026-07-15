import unittest

from app.ai.backend_selector import BackendCandidate
from app.ai.backends.base import BackendProbeResult
from app.ai.resource_planner import ResourcePlanner
from tests.ai_test_helpers import device, profile


def candidate(*, backend: str = "llama_cpp_cpu", emulated: bool = False, gpu: bool = False) -> BackendCandidate:
    probe = BackendProbeResult(
        backend_id=backend,
        detected=True,
        usable=True,
        stable=True,
        reason_code="compatible",
        devices=("Vulkan0",) if gpu else (),
        supported_flags=frozenset({"--threads", "--n-gpu-layers", "--device"}),
        runtime_variant_id="variant",
        requires_emulation=emulated,
        runtime_installed=True,
    )
    return BackendCandidate(backend, "variant", probe.devices[0] if probe.devices else None, 100, (), (), probe)


class ResourcePlannerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = ResourcePlanner()

    def test_low_available_memory_chooses_small(self) -> None:
        plan = self.planner.plan(profile(total_ram=16, available_ram=2), candidate())
        self.assertEqual(plan.model_id, "small")
        self.assertIn("memory_pressure", plan.reason_codes)

    def test_sixteen_gb_with_memory_has_safe_plan_not_large(self) -> None:
        plan = self.planner.plan(profile(total_ram=16, available_ram=12), candidate())
        self.assertEqual(plan.model_id, "medium")
        self.assertLess(plan.estimated_total_memory_gb, 12)

    def test_medium_not_selected_when_estimate_exceeds_budget(self) -> None:
        plan = self.planner.plan(profile(total_ram=16, available_ram=5), candidate())
        self.assertEqual(plan.model_id, "small")

    def test_context_is_reduced_under_memory_pressure(self) -> None:
        plan = self.planner.plan(profile(total_ram=16, available_ram=4.5), candidate())
        self.assertLessEqual(plan.context_tokens, 4096)

    def test_windows_reserve_and_estimates_are_nonnegative(self) -> None:
        plan = self.planner.plan(profile(total_ram=8, available_ram=6), candidate())
        self.assertGreater(plan.reserved_system_memory_gb, 0)
        self.assertTrue(all(value >= 0 for value in (
            plan.estimated_model_memory_gb,
            plan.estimated_kv_cache_gb,
            plan.estimated_runtime_overhead_gb,
            plan.estimated_total_memory_gb,
        )))

    def test_emulation_has_memory_penalty(self) -> None:
        native = self.planner.plan(profile(), candidate())
        emulated = self.planner.plan(profile(), candidate(emulated=True))
        self.assertGreater(emulated.estimated_runtime_overhead_gb, native.estimated_runtime_overhead_gb)
        self.assertIn("emulation_penalty", emulated.reason_codes)

    def test_memory_saver_is_lighter_and_performance_stays_bounded(self) -> None:
        saver = self.planner.plan(profile(total_ram=32, available_ram=24), candidate(), optimization_mode="memory_saver")
        performance = self.planner.plan(profile(total_ram=16, available_ram=6), candidate(), optimization_mode="performance")
        self.assertEqual(saver.model_id, "small")
        self.assertLessEqual(performance.estimated_total_memory_gb, 6)

    def test_custom_model_is_supported(self) -> None:
        plan = self.planner.plan(profile(total_ram=16, available_ram=10), candidate(), custom_model_size_gb=3.0)
        self.assertEqual(plan.model_id, "custom")
        self.assertGreater(plan.estimated_model_memory_gb, 3.0)

    def test_gpu_layers_require_flags_device_and_memory(self) -> None:
        plan = self.planner.plan(
            profile(gpu_devices=(device("amd", memory_gb=8),)),
            candidate(backend="llama_cpp_vulkan", gpu=True),
        )
        self.assertIsNotNone(plan.gpu_layers)
        self.assertGreater(plan.gpu_layers or 0, 0)


if __name__ == "__main__":
    unittest.main()
