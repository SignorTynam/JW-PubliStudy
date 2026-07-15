import json
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.ai.runtime_launch_plan import BackendCapabilities, RuntimeLaunchPlan
from app.ai.runtime_manager import RuntimeManager, RuntimeValidationResult


def launch_plan(root: Path, *, backend: str = "llama_cpp_cpu", arguments: tuple[str, ...] = (), device_id=None):
    return RuntimeLaunchPlan(
        backend_id=backend,
        runtime_variant_id=f"{backend}_x86_64",
        executable=root / "llama-server.exe",
        model_path=root / "model.gguf",
        host="127.0.0.1",
        port=12345,
        context_tokens=4096,
        device_id=device_id,
        arguments=arguments,
        environment={"GGML_TEST": "1"},
        working_directory=root,
        cpu_threads=6,
        gpu_layers=99 if "cpu" not in backend else None,
        host_architecture="x86_64",
        executable_architecture="x86_64",
    )


class RuntimeLaunchPlanTest(unittest.TestCase):
    def test_cpu_plan_keeps_local_base_command(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            command = RuntimeManager(root).build_launch_command(launch_plan(root), BackendCapabilities())
        self.assertIn("127.0.0.1", command)
        self.assertNotIn("0.0.0.0", command)
        self.assertIn("--ctx-size", command)

    def test_cuda_and_vulkan_flags_require_capabilities(self) -> None:
        capabilities = BackendCapabilities(
            True,
            True,
            ("CUDA0", "Vulkan0"),
            frozenset({"--n-gpu-layers", "--device", "--threads"}),
        )
        for backend, device in (("llama_cpp_cuda", "CUDA0"), ("llama_cpp_vulkan", "Vulkan0")):
            with self.subTest(backend=backend), TemporaryDirectory() as directory:
                root = Path(directory)
                plan = launch_plan(
                    root,
                    backend=backend,
                    device_id=device,
                    arguments=("--threads", "6", "--n-gpu-layers", "99", "--device", device),
                )
                command = RuntimeManager(root).build_launch_command(plan, capabilities)
                self.assertIn("--n-gpu-layers", command)
                self.assertIn(device, command)

    def test_unsupported_flag_and_unknown_device_are_not_inserted(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = launch_plan(
                root,
                backend="llama_cpp_vulkan",
                device_id="Missing0",
                arguments=("--invented", "1", "--device", "Missing0"),
            )
            command = RuntimeManager(root).build_launch_command(
                plan,
                BackendCapabilities(True, False, ("Vulkan0",), frozenset({"--device"})),
            )
        self.assertNotIn("--invented", command)
        self.assertNotIn("Missing0", command)

    def test_negative_numeric_value_is_parsed_but_only_for_supported_flag(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = launch_plan(root, arguments=("--threads", "-1"))
            command = RuntimeManager(root).build_launch_command(
                plan,
                BackendCapabilities(supported_flags=frozenset({"--threads"})),
            )
        self.assertEqual(command[-2:], ["--threads", "-1"])

    def test_endpoint_url_argument_is_rejected_with_its_flag(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = launch_plan(root, arguments=("--device", "https://example.invalid/v1/chat/completions"))
            command = RuntimeManager(root).build_launch_command(
                plan,
                BackendCapabilities(True, False, ("https://example.invalid/v1/chat/completions",), frozenset({"--device"})),
            )
        self.assertNotIn("https://example.invalid/v1/chat/completions", command)
        self.assertNotIn("--device", command)

    def test_plan_preserves_cwd_and_environment(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = launch_plan(root)
            self.assertEqual(plan.working_directory, root)
            self.assertEqual(plan.environment, {"GGML_TEST": "1"})

    def test_nonlocal_host_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                RuntimeLaunchPlan(
                    "cpu", "variant", root / "server.exe", root / "model.gguf", "0.0.0.0", 1234, 2048
                )

    def test_side_by_side_variants_do_not_overwrite_each_other(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("bundle/llama-server.exe", b"runtime")
                output.writestr("bundle/dependency.dll", b"dll")
            manager = RuntimeManager(root)

            def valid(executable, *args, **kwargs):
                return RuntimeValidationResult(True, Path(executable), probe_argument="--version")

            with patch.object(manager, "validate_runtime_installation", side_effect=valid):
                x64 = manager.install_runtime_variant_from_zip(archive, "llama_cpp_cpu_x86_64_generic", "b1")
                arm = manager.install_runtime_variant_from_zip(archive, "llama_cpp_cpu_arm64", "b1")
            self.assertTrue(x64.is_file())
            self.assertTrue(arm.is_file())
            self.assertNotEqual(x64.parent, arm.parent)

    def test_failed_replacement_rolls_back_previous_variant(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = RuntimeManager(root)
            target_dir = root / "runtime" / "variant" / "b1"
            target_dir.mkdir(parents=True)
            (target_dir / "llama-server.exe").write_bytes(b"old")
            (target_dir / "marker.txt").write_text("previous", encoding="utf-8")
            archive = root / "runtime.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("bundle/llama-server.exe", b"new")
            validations = [
                RuntimeValidationResult(True, root / "staged.exe"),
                RuntimeValidationResult(False, root / "final.exe", "runtime_incomplete"),
            ]
            with patch.object(manager, "validate_runtime_installation", side_effect=validations):
                with self.assertRaises(RuntimeError):
                    manager.install_runtime_variant_from_zip(archive, "variant", "b1")
            self.assertEqual((target_dir / "marker.txt").read_text(encoding="utf-8"), "previous")

    def test_legacy_runtime_migration_and_active_json(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            manager = RuntimeManager(root)
            legacy = manager.get_runtime_path()
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_bytes(b"legacy")

            def valid(executable, *args, **kwargs):
                return RuntimeValidationResult(True, Path(executable))

            with patch.object(manager, "validate_runtime_installation", side_effect=valid):
                migrated = manager.migrate_legacy_runtime()
                self.assertIsNotNone(migrated)
                manager.activate_runtime(migrated, {"runtime_variant_id": "legacy"})
                discovered = manager.find_runtime_executable()
            payload = json.loads((root / "runtime" / "active.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(payload["executable"]), migrated)
            self.assertEqual(discovered, migrated)


if __name__ == "__main__":
    unittest.main()
