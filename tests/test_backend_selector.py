import unittest

from app.ai.backend_selector import BackendSelectionError, BackendSelector
from app.ai.backends.base import BackendProbeResult
from tests.ai_test_helpers import profile


def probe(
    backend: str,
    variant: str,
    *,
    usable: bool = True,
    stable: bool = True,
    devices: tuple[str, ...] = (),
    emulated: bool = False,
    reason: str = "compatible",
    experimental: bool = False,
    provider: bool = True,
    model: bool = True,
    generated: bool = False,
) -> BackendProbeResult:
    return BackendProbeResult(
        backend_id=backend,
        detected=True,
        usable=usable,
        stable=stable,
        reason_code=reason,
        devices=devices,
        runtime_variant_id=variant,
        requires_emulation=emulated,
        experimental=experimental,
        runtime_installed=True,
        provider_available=provider,
        model_compatible=model,
        generation_tested=generated,
    )


class BackendSelectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.selector = BackendSelector()
        self.profile = profile()

    def test_native_validated_wins_over_emulated(self) -> None:
        result = self.selector.select(
            self.profile,
            [probe("llama_cpp_cpu", "emulated", emulated=True), probe("llama_cpp_cpu", "native")],
        )
        self.assertEqual(result.primary.runtime_variant_id, "native")

    def test_cpu_native_wins_when_gpu_is_not_validated(self) -> None:
        result = self.selector.select(
            self.profile,
            [
                probe("llama_cpp_cuda", "cuda", usable=False, stable=False, reason="runtime_validation_failed"),
                probe("llama_cpp_cpu", "cpu"),
            ],
        )
        self.assertEqual(result.primary.backend_id, "llama_cpp_cpu")

    def test_validated_cuda_wins_over_cpu(self) -> None:
        result = self.selector.select(
            self.profile,
            [probe("llama_cpp_cpu", "cpu"), probe("llama_cpp_cuda", "cuda", devices=("CUDA0",))],
        )
        self.assertEqual(result.primary.backend_id, "llama_cpp_cuda")

    def test_cuda_failure_falls_back_to_vulkan_then_cpu(self) -> None:
        result = self.selector.select(
            self.profile,
            [
                probe("llama_cpp_cuda", "cuda", usable=False, reason="missing_driver"),
                probe("llama_cpp_vulkan", "vulkan", devices=("Vulkan0",)),
                probe("llama_cpp_cpu", "cpu"),
            ],
        )
        self.assertEqual(result.primary.backend_id, "llama_cpp_vulkan")
        self.assertEqual(result.fallbacks[0].backend_id, "llama_cpp_cpu")

    def test_vulkan_failure_falls_back_to_cpu(self) -> None:
        result = self.selector.select(
            self.profile,
            [probe("llama_cpp_vulkan", "vk", usable=False, reason="benchmark_failed"), probe("llama_cpp_cpu", "cpu")],
        )
        self.assertEqual(result.primary.backend_id, "llama_cpp_cpu")

    def test_npu_requires_provider_model_and_generation(self) -> None:
        cases = (
            probe("vendor_npu", "npu", provider=False, model=True, generated=True),
            probe("vendor_npu", "npu", provider=True, model=False, generated=True),
            probe("vendor_npu", "npu", provider=True, model=True, generated=False),
        )
        for item in cases:
            with self.subTest(item=item):
                with self.assertRaises(BackendSelectionError):
                    self.selector.select(self.profile, [item], experimental_enabled=True)

    def test_npu_can_only_win_after_complete_probe(self) -> None:
        result = self.selector.select(
            self.profile,
            [probe("vendor_npu", "npu", devices=("NPU0",), provider=True, model=True, generated=True)],
            experimental_enabled=True,
        )
        self.assertEqual(result.primary.backend_id, "vendor_npu")

    def test_experimental_backend_is_disabled_or_penalized(self) -> None:
        experimental = probe("llama_cpp_vulkan", "experimental", devices=("Vulkan0",), experimental=True)
        with self.assertRaises(BackendSelectionError):
            self.selector.select(self.profile, [experimental])
        result = self.selector.select(self.profile, [probe("llama_cpp_cpu", "cpu"), experimental], experimental_enabled=True)
        self.assertEqual(result.primary.backend_id, "llama_cpp_cpu")
        self.assertIn("experimental", result.fallbacks[0].penalties)

    def test_no_candidate_has_structured_error_and_no_duplicates(self) -> None:
        bad = probe("llama_cpp_cuda", "cuda", usable=False, reason="missing_driver")
        with self.assertRaises(BackendSelectionError) as captured:
            self.selector.select(self.profile, [bad, bad])
        self.assertEqual(captured.exception.reason_code, "no_usable_backend")
        self.assertEqual(len(captured.exception.rejected), 1)


if __name__ == "__main__":
    unittest.main()
