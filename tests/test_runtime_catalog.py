import unittest

from app.ai.auto_configuration import order_runtime_resolutions
from app.ai.runtime_catalog import compatible_runtime_variants, resolve_runtime_assets
from tests.ai_test_helpers import device, profile


def release(*names: str) -> dict:
    return {
        "tag_name": "b10021",
        "assets": [
            {"name": name, "browser_download_url": f"https://example.invalid/{name}"}
            for name in names
        ],
    }


ASSETS = (
    "llama-b10021-bin-win-cpu-arm64.zip",
    "llama-b10021-bin-win-cpu-x64.zip",
    "llama-b10021-bin-win-cuda-12.4-x64.zip",
    "llama-b10021-bin-win-vulkan-x64.zip",
    "llama-b10021-bin-win-opencl-adreno-arm64.zip",
    "llama-b10021-bin-win-x86.zip",
    "llama-b10021-source.zip",
)


class RuntimeCatalogTest(unittest.TestCase):
    def test_arm64_prefers_native_cpu_then_x64_emulation(self) -> None:
        resolutions = resolve_runtime_assets(release(*ASSETS), profile(native="arm64", process="arm64", features=frozenset()))
        available = [item for item in resolutions if item.available]
        self.assertEqual(available[0].variant.id, "llama_cpp_cpu_arm64")
        x64 = next(item for item in available if item.variant.id == "llama_cpp_cpu_x86_64_generic")
        self.assertTrue(x64.requires_emulation)

    def test_x64_never_selects_arm64(self) -> None:
        variants = compatible_runtime_variants(profile(native="x86_64"))
        self.assertNotIn("arm64", {variant.architecture for variant, _emulated in variants})

    def test_cuda_excluded_without_nvidia(self) -> None:
        ids = {variant.id for variant, _ in compatible_runtime_variants(profile())}
        self.assertNotIn("llama_cpp_cuda_x86_64", ids)

    def test_cuda_candidate_with_nvidia(self) -> None:
        ids = {variant.id for variant, _ in compatible_runtime_variants(profile(gpu_devices=(device("nvidia"),)))}
        self.assertIn("llama_cpp_cuda_x86_64", ids)

    def test_vulkan_candidates_with_amd_and_intel(self) -> None:
        for vendor in ("amd", "intel"):
            with self.subTest(vendor=vendor):
                ids = {variant.id for variant, _ in compatible_runtime_variants(profile(gpu_devices=(device(vendor),)))}
                self.assertIn("llama_cpp_vulkan_x86_64", ids)

    def test_qualcomm_arm64_cpu_precedes_experimental_gpu(self) -> None:
        resolutions = order_runtime_resolutions(resolve_runtime_assets(
            release(*ASSETS),
            profile(native="arm64", gpu_devices=(device("qualcomm"),), features=frozenset()),
            experimental_enabled=True,
        ))
        native_available = [item for item in resolutions if item.available and not item.requires_emulation]
        self.assertEqual(native_available[0].variant.id, "llama_cpp_cpu_arm64")
        self.assertIn("llama_cpp_cpu_arm64", {item.variant.id for item in native_available})
        self.assertTrue(any(item.variant.experimental for item in native_available))

    def test_missing_asset_has_structured_reason(self) -> None:
        resolutions = resolve_runtime_assets(release(), profile())
        self.assertTrue(resolutions)
        self.assertTrue(all(not item.available and item.reason_code == "asset_not_available" for item in resolutions))

    def test_source_and_x86_assets_are_excluded(self) -> None:
        resolutions = resolve_runtime_assets(release("llama-b10021-source.zip", "llama-b10021-bin-win-x86.zip"), profile())
        self.assertFalse(any(item.available for item in resolutions))

    def test_url_is_only_copied_from_release_metadata(self) -> None:
        resolutions = resolve_runtime_assets(release("llama-b10021-bin-win-cpu-x64.zip"), profile())
        selected = next(item for item in resolutions if item.available)
        self.assertEqual(selected.asset_url, "https://example.invalid/llama-b10021-bin-win-cpu-x64.zip")
        self.assertEqual(selected.release_tag, "b10021")


if __name__ == "__main__":
    unittest.main()
