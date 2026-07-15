from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from app.ai.auto_configuration import (
    AutomaticConfigurationResult,
    AutomaticConfigurationWorker,
    save_backend_selection,
)
from app.ai.backend_selector import BackendCandidate, BackendSelectionError, BackendSelector
from app.ai.backends.base import BackendProbeResult
from app.ai.download_worker import DownloadWorker
from app.ai.hardware_check import get_hardware_info
from app.ai.hardware_profile import HardwareProfile
from app.ai.model_catalog import LocalModelSpec, get_model, recommend_model
from app.ai.model_manager import ModelManager
from app.ai.resource_planner import ResourcePlan, ResourcePlanner
from app.ai.runtime_catalog import RuntimeResolution
from app.ai.runtime_download_worker import RuntimeDownloadWorker
from app.ai.runtime_launch_plan import BackendCapabilities, RuntimeLaunchPlan
from app.ai.runtime_manager import RuntimeManager
from app.settings import AppSettings


class LocalAISetupService(QObject):
    status_changed = Signal(str)
    step_changed = Signal(str)
    progress_changed = Signal(int)
    error_occurred = Signal(str)
    finished = Signal()

    MAX_FALLBACK_ATTEMPTS = 4

    def __init__(self, settings: AppSettings, model_manager: ModelManager, runtime_manager: RuntimeManager) -> None:
        super().__init__()
        self._settings = settings
        self._model_manager = model_manager
        self._runtime_manager = runtime_manager
        self._download_thread: QThread | None = None
        self._download_worker: DownloadWorker | None = None
        self._runtime_thread: QThread | None = None
        self._runtime_worker: RuntimeStartWorker | None = None
        self._runtime_download_thread: QThread | None = None
        self._runtime_download_worker: RuntimeDownloadWorker | None = None
        self._planning_thread: QThread | None = None
        self._planning_worker: AutomaticConfigurationWorker | None = None
        self._validation_thread: QThread | None = None
        self._validation_worker: BackendValidationWorker | None = None
        self._pending_model_spec: LocalModelSpec | None = None
        self._profile: HardwareProfile | None = None
        self._runtime_resolutions: tuple[RuntimeResolution, ...] = ()
        self._rejected_resolutions: tuple[RuntimeResolution, ...] = ()
        self._resolution_index = 0
        self._fallback_attempts = 0
        self._current_resolution: RuntimeResolution | None = None
        self._current_candidate: BackendCandidate | None = None
        self._current_capabilities = BackendCapabilities()
        self._resource_plan: ResourcePlan | None = None
        self._validated_executable = Path()
        self._automatic_setup = False
        self._cancelled = False
        self._fallback_failures: dict[str, str] = {}
        self._oom_retried_variants: set[str] = set()
        self._cancel_notification_emitted = False

    def recommended_model(self) -> LocalModelSpec:
        info = get_hardware_info(self._model_manager.models_dir().parent)
        return recommend_model(info.total_ram_gb)

    def is_busy(self) -> bool:
        return self._automatic_setup or any(self._thread_is_running(thread) for thread in self._threads())

    @Slot()
    def configure_automatically(self) -> None:
        if self.is_busy():
            return
        if self._settings.ai_use_custom_model() or self._settings.ai_use_custom_runtime():
            self.configure_from_local_files()
            return
        # Preserve the long-standing public hooks used by integrations while
        # the concrete service uses the hardware-aware asynchronous pipeline.
        if self._legacy_hooks_overridden():
            self._configure_legacy_compatibility()
            return
        self._automatic_setup = True
        self._cancelled = False
        self._fallback_attempts = 0
        self._resolution_index = 0
        self._fallback_failures = {}
        self._oom_retried_variants = set()
        self._cancel_notification_emitted = False
        self._current_candidate = None
        self._resource_plan = None
        self._settings.set_ai_mode("auto")
        self._planning_thread = QThread()
        self._planning_worker = AutomaticConfigurationWorker(
            self._model_manager.models_dir().parent,
            experimental_enabled=self._settings.ai_experimental_backends_enabled(),
        )
        worker = self._planning_worker
        thread = self._planning_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status_changed.connect(self._emit_status)
        worker.completed.connect(self._on_automatic_plan_ready)
        worker.failed.connect(self._on_automatic_setup_failed)
        worker.cancelled.connect(self._on_setup_cancelled)
        worker.completed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.cancelled.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _configure_legacy_compatibility(self) -> None:
        self.status_changed.emit("checking_hardware")
        info = get_hardware_info(self._model_manager.models_dir().parent)
        spec = recommend_model(info.total_ram_gb)
        self._settings.set_ai_mode("auto")
        self._settings.set_ai_selected_model_id(spec.id)
        self.status_changed.emit("model_recommended")
        if info.free_disk_gb < spec.size_gb + 1:
            self.error_occurred.emit("disk_space_insufficient")
        elif not self._runtime_manager.is_runtime_available():
            self.download_runtime_then_continue(spec)
        elif not self._model_manager.is_model_ready(spec):
            self.download_model(spec, start_after_download=True)
        else:
            self.start_runtime(spec)

    def _legacy_hooks_overridden(self) -> bool:
        cls = type(self)
        return any(
            getattr(cls, name) is not getattr(LocalAISetupService, name)
            for name in ("download_runtime_then_continue", "download_model", "start_runtime")
        )

    @Slot(object)
    def _on_automatic_plan_ready(self, result: AutomaticConfigurationResult) -> None:
        if self._cancelled:
            return
        self._profile = result.profile
        self._runtime_resolutions = result.resolutions
        self._rejected_resolutions = result.rejected
        self._log_hardware_profile(result.profile)
        for resolution in (*result.resolutions, *result.rejected):
            self._runtime_manager.record_event(
                "candidate",
                f"variant={resolution.variant.id} backend={resolution.variant.backend} "
                f"architecture={resolution.variant.architecture} available={resolution.available} "
                f"emulation={resolution.requires_emulation} reason={resolution.reason_code} asset={resolution.asset_name}",
            )
        self._try_next_runtime_candidate()

    def _try_next_runtime_candidate(self) -> None:
        if self._cancelled:
            return
        if self._fallback_attempts >= self.MAX_FALLBACK_ATTEMPTS or self._resolution_index >= len(self._runtime_resolutions):
            self._finish_with_error("no_usable_backend")
            return
        resolution = self._runtime_resolutions[self._resolution_index]
        self._resolution_index += 1
        self._fallback_attempts += 1
        self._current_resolution = resolution
        self._runtime_manager.record_event(
            "fallback",
            f"attempt={self._fallback_attempts} variant={resolution.variant.id} emulation={resolution.requires_emulation}",
        )
        existing = self._runtime_manager.runtime_variant_path(
            resolution.variant.id,
            resolution.release_tag or "unknown",
        )
        if existing.is_file():
            self._validate_runtime_candidate(existing, resolution)
            return
        self._download_runtime_resolution(resolution)

    def _download_runtime_resolution(self, resolution: RuntimeResolution) -> None:
        self._emit_status("downloading_runtime")
        self._runtime_download_thread = QThread()
        self._runtime_download_worker = RuntimeDownloadWorker(self._runtime_manager, resolution)
        worker = self._runtime_download_worker
        thread = self._runtime_download_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(lambda percent, _done, _total: self.progress_changed.emit(percent))
        worker.status_changed.connect(self._emit_status)
        worker.finished.connect(self._on_runtime_variant_downloaded)
        worker.failed.connect(self._on_runtime_variant_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str)
    def _on_runtime_variant_downloaded(self, runtime_path: str) -> None:
        if not self._cancelled and self._current_resolution is not None:
            self._validate_runtime_candidate(Path(runtime_path), self._current_resolution)

    @Slot(str)
    def _on_runtime_variant_failed(self, error: str) -> None:
        if error == "setup_cancelled" or self._cancelled:
            self._on_setup_cancelled()
            return
        self._reject_current_candidate(error)

    def _validate_runtime_candidate(self, executable: Path, resolution: RuntimeResolution) -> None:
        if self._profile is None:
            self._finish_with_error("hardware_profile_missing")
            return
        self._emit_status("validating_backend")
        self._validation_thread = QThread()
        self._validation_worker = BackendValidationWorker(
            self._runtime_manager,
            self._profile,
            resolution,
            executable,
            experimental_enabled=self._settings.ai_experimental_backends_enabled(),
        )
        worker = self._validation_worker
        thread = self._validation_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(self._on_backend_validated)
        worker.failed.connect(self._reject_current_candidate)
        worker.completed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object, object, str)
    def _on_backend_validated(
        self,
        candidate: BackendCandidate,
        capabilities: BackendCapabilities,
        executable: str,
    ) -> None:
        if self._cancelled or self._profile is None:
            return
        self._current_candidate = candidate
        self._current_capabilities = capabilities
        self._runtime_manager.record_event(
            "selection",
            f"candidate_backend={candidate.backend_id} variant={candidate.runtime_variant_id} "
            f"device={candidate.device_id} score={candidate.score} reasons={','.join(candidate.reasons) or 'none'} "
            f"penalties={','.join(candidate.penalties) or 'none'} flags={','.join(sorted(capabilities.supported_flags)) or 'none'}",
        )
        self._emit_status("optimizing_configuration")
        planner = ResourcePlanner()
        self._resource_plan = planner.plan(
            self._profile,
            candidate,
            optimization_mode=self._settings.ai_optimization_mode(),
        )
        resource = self._resource_plan
        spec = get_model(resource.model_id) or get_model("small")
        if spec is None:
            self._finish_with_error("model_missing")
            return
        self._pending_model_spec = spec
        self._runtime_manager.record_event(
            "resource_plan",
            f"model={resource.model_id} context={resource.context_tokens} max_output={resource.max_output_tokens} "
            f"threads={resource.cpu_threads} gpu_layers={resource.gpu_layers} "
            f"estimated_model_gb={resource.estimated_model_memory_gb} estimated_kv_gb={resource.estimated_kv_cache_gb} "
            f"estimated_overhead_gb={resource.estimated_runtime_overhead_gb} "
            f"estimated_total_gb={resource.estimated_total_memory_gb} reserve_gb={resource.reserved_system_memory_gb} "
            f"reasons={','.join(resource.reason_codes)}",
        )
        if self._profile.free_disk_gb < spec.size_gb + 1:
            self._finish_with_error("disk_space_insufficient")
            return
        # Keep the path emitted by the validation worker; the runtime is not
        # made active until readiness succeeds.
        self._validated_executable = Path(executable)
        if not self._model_manager.is_model_ready(spec):
            self.download_model(spec, start_after_download=True)
            return
        self.start_runtime(spec)

    @Slot(str)
    def _reject_current_candidate(self, error: str) -> None:
        if self._cancelled or error == "setup_cancelled":
            self._on_setup_cancelled()
            return
        resolution = self._current_resolution
        variant_id = resolution.variant.id if resolution else "unknown"
        self._fallback_failures[variant_id] = error
        self._settings.set_ai_last_backend_failure(error)
        self._runtime_manager.record_event(
            "fallback",
            f"rejected_variant={variant_id} error={error} next_attempt={self._fallback_attempts + 1}",
        )
        self._current_candidate = None
        self._resource_plan = None
        self._try_next_runtime_candidate()

    # Legacy downloader remains available for integrations and manual tests.
    def download_runtime_then_continue(self, spec: LocalModelSpec) -> None:
        self._pending_model_spec = spec
        self._runtime_download_thread = QThread()
        self._runtime_download_worker = RuntimeDownloadWorker(self._runtime_manager)
        worker = self._runtime_download_worker
        thread = self._runtime_download_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(lambda percent, _done, _total: self.progress_changed.emit(percent))
        worker.status_changed.connect(self.status_changed.emit)
        worker.finished.connect(self._on_runtime_downloaded)
        worker.failed.connect(self._on_runtime_download_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def download_model(self, spec: LocalModelSpec, start_after_download: bool = False) -> None:
        if not self._automatic_setup:
            self._cancelled = False
            self._cancel_notification_emitted = False
        if self._is_placeholder_url(spec.download_url):
            self._finish_with_error("download_url_placeholder")
            return
        target = self._model_manager.get_model_path(spec)
        self._pending_model_spec = spec
        self._emit_status("download_model")
        self._download_thread = QThread()
        self._download_worker = DownloadWorker(spec.download_url, target, spec.sha256)
        worker = self._download_worker
        thread = self._download_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_changed.connect(lambda percent, _done, _total: self.progress_changed.emit(percent))
        worker.status_changed.connect(self._emit_status)
        worker.failed.connect(self._on_download_failed)
        if start_after_download:
            worker.finished.connect(self._on_model_downloaded_for_start)
        else:
            worker.finished.connect(self._on_model_downloaded_without_start)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str)
    def _on_model_downloaded_for_start(self, _path: str) -> None:
        if not self._cancelled and self._pending_model_spec is not None:
            self.start_runtime(self._pending_model_spec)

    @Slot(str)
    def _on_model_downloaded_without_start(self, _path: str) -> None:
        if not self._cancelled:
            self.finished.emit()

    def _on_runtime_downloaded(self, _runtime_path: str) -> None:
        self.status_changed.emit("runtime_ready")
        spec = self._pending_model_spec
        if spec is None:
            self.finished.emit()
        elif not self._model_manager.is_model_ready(spec):
            self.download_model(spec, start_after_download=True)
        else:
            self.start_runtime(spec)

    def _on_runtime_download_failed(self, error: str) -> None:
        self._finish_with_error(error)

    def start_runtime(self, spec: LocalModelSpec) -> None:
        if not self._automatic_setup:
            self._cancelled = False
            self._cancel_notification_emitted = False
        self._emit_status("starting_runtime")
        if not self._model_manager.is_model_ready(spec):
            self._finish_with_error("model_missing")
            return
        if self._automatic_setup and self._current_candidate and self._resource_plan and self._profile:
            plan = self._build_launch_plan(spec)
            self._start_runtime_worker(plan=plan)
            return
        self._start_runtime_worker(
            model_path=self._model_manager.get_model_path(spec),
            context_tokens=spec.context_tokens,
        )

    def _build_launch_plan(self, spec: LocalModelSpec) -> RuntimeLaunchPlan:
        assert self._profile is not None
        assert self._resource_plan is not None
        assert self._current_candidate is not None
        resolution = self._current_resolution
        executable = self._validated_executable.resolve(strict=False)
        resource = self._resource_plan
        arguments: list[str] = []
        if resource.cpu_threads:
            arguments.extend(("--threads", str(resource.cpu_threads)))
        if resource.gpu_layers is not None:
            arguments.extend(("--n-gpu-layers", str(resource.gpu_layers)))
        if resource.device_id:
            arguments.extend(("--device", resource.device_id))
        return RuntimeLaunchPlan(
            backend_id=resource.backend_id,
            runtime_variant_id=resource.runtime_variant_id,
            executable=executable,
            model_path=self._model_manager.get_model_path(spec),
            host="127.0.0.1",
            port=self._runtime_manager.find_free_port(),
            context_tokens=resource.context_tokens,
            device_id=resource.device_id,
            arguments=tuple(arguments),
            environment={},
            working_directory=executable.parent,
            requires_emulation=bool(resolution and resolution.requires_emulation),
            cpu_threads=resource.cpu_threads,
            gpu_layers=resource.gpu_layers,
            host_architecture=self._profile.architecture.native_architecture,
            executable_architecture=resolution.variant.architecture if resolution else "unknown",
            selection_reasons=(*self._current_candidate.reasons, *resource.reason_codes),
        )

    def start_custom_runtime(self) -> None:
        self._cancelled = False
        self._cancel_notification_emitted = False
        self._emit_status("starting_with_local_files")
        model_path = self._settings.ai_custom_model_path()
        runtime_path = self._settings.ai_custom_runtime_path()
        if not self._settings.ai_use_custom_model() or not self._model_manager.is_custom_model_ready(model_path):
            self._finish_with_error("custom_model_missing")
            return
        if not self._settings.ai_use_custom_runtime() or not Path(runtime_path).is_file():
            self._finish_with_error("custom_runtime_missing")
            return
        self._start_runtime_for_path(Path(model_path), self._settings.ai_selected_context_tokens())

    def configure_from_local_files(self) -> None:
        self._settings.set_ai_mode("auto")
        self.start_custom_runtime()

    def _start_runtime_for_path(self, model_path: Path, context_tokens: int) -> None:
        self._start_runtime_worker(model_path=model_path, context_tokens=context_tokens)

    def _start_runtime_worker(
        self,
        *,
        model_path: Path | None = None,
        context_tokens: int | None = None,
        plan: RuntimeLaunchPlan | None = None,
    ) -> None:
        self._runtime_thread = QThread()
        self._runtime_worker = RuntimeStartWorker(
            self._runtime_manager,
            model_path=model_path,
            context_tokens=context_tokens,
            startup_timeout_seconds=self._settings.ai_startup_timeout_seconds(),
            launch_plan=plan,
        )
        worker = self._runtime_worker
        thread = self._runtime_thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.status_changed.connect(self._emit_status)
        worker.finished.connect(self._on_runtime_started)
        worker.failed.connect(self._on_runtime_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        worker.failed.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_download_failed(self, error: str) -> None:
        if self._cancelled or error == "download_cancelled":
            self._on_setup_cancelled()
        else:
            self._finish_with_error(error)

    def _on_runtime_started(self, endpoint: str) -> None:
        if self._automatic_setup and self._profile and self._resource_plan and self._current_resolution:
            try:
                self._runtime_manager.activate_runtime(
                    self._validated_executable,
                    {
                        "backend_id": self._resource_plan.backend_id,
                        "runtime_variant_id": self._resource_plan.runtime_variant_id,
                        "device_id": self._resource_plan.device_id,
                        "release_tag": self._current_resolution.release_tag,
                        "requires_emulation": self._current_resolution.requires_emulation,
                    },
                )
            except RuntimeError as exc:
                self._reject_current_candidate(str(exc))
                return
            self._persist_successful_selection()
        self._settings.set_ai_runtime_endpoint(endpoint)
        self._settings.set_ai_last_status("ready")
        self._emit_status("ready")
        self._automatic_setup = False
        self.finished.emit()

    def _persist_successful_selection(self) -> None:
        assert self._profile is not None
        assert self._resource_plan is not None
        assert self._current_resolution is not None
        resource = self._resource_plan
        architecture = self._profile.architecture
        self._settings.set_ai_selected_model_id(resource.model_id)
        self._settings.save_ai_backend_selection(
            hardware_fingerprint=self._profile.fingerprint,
            backend_id=resource.backend_id,
            runtime_variant_id=resource.runtime_variant_id,
            device_id=resource.device_id,
            native_architecture=architecture.native_architecture,
            process_architecture=architecture.process_architecture,
            running_under_emulation=self._current_resolution.requires_emulation,
            context_tokens=resource.context_tokens,
            cpu_threads=resource.cpu_threads or 1,
            gpu_layers=resource.gpu_layers,
        )
        rejected = {
            item.variant.id: item.reason_code for item in self._rejected_resolutions
        } | self._fallback_failures
        save_backend_selection(
            self._profile.data_dir,
            {
                "hardware_fingerprint": self._profile.fingerprint,
                "selected_backend": resource.backend_id,
                "selected_runtime_variant": resource.runtime_variant_id,
                "selected_device": resource.device_id,
                "selected_model": resource.model_id,
                "context_tokens": resource.context_tokens,
                "cpu_threads": resource.cpu_threads,
                "gpu_layers": resource.gpu_layers,
                "estimated_total_memory_gb": resource.estimated_total_memory_gb,
                "running_under_emulation": self._current_resolution.requires_emulation,
                "runtime_architecture": self._current_resolution.variant.architecture,
                "fallbacks": [item.variant.id for item in self._runtime_resolutions[self._resolution_index :]],
                "rejected": rejected,
                "reason_codes": list(resource.reason_codes),
            },
        )

    def _on_runtime_failed(self, error: str) -> None:
        if self._cancelled:
            self._on_setup_cancelled()
        elif self._automatic_setup:
            variant_id = self._current_resolution.variant.id if self._current_resolution else "unknown"
            if (
                error == "insufficient_memory"
                and variant_id not in self._oom_retried_variants
                and self._resource_plan is not None
                and self._pending_model_spec is not None
            ):
                self._oom_retried_variants.add(variant_id)
                reduced_context = max(2048, self._resource_plan.context_tokens // 2)
                reduced_gpu_layers = (
                    max(1, self._resource_plan.gpu_layers // 2)
                    if self._resource_plan.gpu_layers is not None
                    else None
                )
                self._resource_plan = replace(
                    self._resource_plan,
                    context_tokens=reduced_context,
                    gpu_layers=reduced_gpu_layers,
                    reason_codes=(*self._resource_plan.reason_codes, "oom_reduced_retry"),
                )
                self._runtime_manager.record_event(
                    "fallback",
                    f"variant={variant_id} retry=memory_reduction context={reduced_context} gpu_layers={reduced_gpu_layers}",
                )
                self.start_runtime(self._pending_model_spec)
                return
            self._reject_current_candidate(error)
        else:
            self._finish_with_error(error)

    def _on_automatic_setup_failed(self, error: str) -> None:
        if not self._cancelled:
            self._finish_with_error(error)

    def _finish_with_error(self, error: str) -> None:
        self._settings.set_ai_last_status("failed")
        self._automatic_setup = False
        self.error_occurred.emit(error)

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True
        if self._planning_worker is not None:
            self._planning_worker.request_cancel()
        if self._validation_worker is not None:
            self._validation_worker.request_cancel()
        if self._runtime_download_worker is not None:
            self._runtime_download_worker.cancel()
        if self._download_worker is not None:
            self._download_worker.cancel()
        if self._runtime_worker is not None:
            self._runtime_worker.request_cancel()
        self._runtime_manager.stop()
        self._on_setup_cancelled()

    def wait_for_shutdown(self, wait_ms: int = 0) -> bool:
        running = [thread for thread in self._threads() if self._thread_is_running(thread)]
        if not running:
            return True
        if wait_ms <= 0:
            return False
        per_thread = max(1, wait_ms // len(running))
        results: list[bool] = []
        for thread in running:
            try:
                results.append(thread.wait(per_thread))
            except RuntimeError:
                results.append(True)
        return all(results)

    @Slot()
    def _on_setup_cancelled(self) -> None:
        if self._cancel_notification_emitted:
            return
        self._cancel_notification_emitted = True
        self._automatic_setup = False
        self._settings.set_ai_last_status("cancelled")
        self.error_occurred.emit("setup_cancelled")

    def _threads(self) -> tuple[QThread | None, ...]:
        return (
            self._planning_thread,
            self._runtime_download_thread,
            self._validation_thread,
            self._download_thread,
            self._runtime_thread,
        )

    def _thread_is_running(self, thread: QThread | None) -> bool:
        if thread is None:
            return False
        try:
            return thread.isRunning()
        except RuntimeError:
            return False

    def _emit_status(self, status: str) -> None:
        self.status_changed.emit(status)
        self.step_changed.emit(status)

    def _log_hardware_profile(self, profile: HardwareProfile) -> None:
        architecture = profile.architecture
        self._runtime_manager.record_event(
            "hardware",
            f"native_architecture={architecture.native_architecture} process_architecture={architecture.process_architecture} "
            f"emulation={architecture.running_under_emulation} detection_method={architecture.detection_method} "
            f"cpu_vendor={profile.cpu_vendor} cpu_model={profile.cpu_model} "
            f"cpu_features={','.join(sorted(profile.cpu_features)) or 'unknown'} "
            f"logical_cores={profile.logical_cores} total_ram_gb={profile.total_ram_gb} "
            f"available_ram_gb={profile.available_ram_gb} methods={','.join(profile.detection_methods)}",
        )
        for device in (*profile.gpu_devices, *profile.npu_devices):
            self._runtime_manager.record_event(
                "hardware_device",
                f"type={device.device_type} vendor={device.vendor} name={device.name} detected={device.device_detected} "
                f"driver_version={device.driver_version or 'unknown'} backend_usable={device.backend_usable} "
                f"potential_backends={','.join(device.potential_backends) or 'none'}",
            )

    def _is_placeholder_url(self, url: str) -> bool:
        try:
            host = urlparse(url).hostname or ""
        except ValueError:
            return True
        return host.lower() in {"example.com", "www.example.com"}


class BackendValidationWorker(QObject):
    completed = Signal(object, object, str)
    failed = Signal(str)

    def __init__(
        self,
        runtime_manager: RuntimeManager,
        profile: HardwareProfile,
        resolution: RuntimeResolution,
        executable: Path,
        *,
        experimental_enabled: bool,
    ) -> None:
        super().__init__()
        self._runtime_manager = runtime_manager
        self._profile = profile
        self._resolution = resolution
        self._executable = Path(executable)
        self._experimental_enabled = experimental_enabled
        self._cancellation_event = threading.Event()

    @Slot()
    def run(self) -> None:
        if self._cancellation_event.is_set():
            self.failed.emit("setup_cancelled")
            return
        validation = self._runtime_manager.validate_runtime_installation(self._executable, use_cache=False)
        if not validation.valid:
            self.failed.emit(validation.error or "runtime_validation_failed")
            return
        capabilities = self._runtime_manager.probe_backend_capabilities(self._executable)
        if self._cancellation_event.is_set():
            self.failed.emit("setup_cancelled")
            return
        variant = self._resolution.variant
        accelerated = variant.backend != "cpu"
        matching_hardware = any(
            device.available and device.vendor in variant.supported_vendors
            for device in self._profile.gpu_devices
        ) if accelerated else True
        memory_verified = any(
            device.available
            and device.vendor in variant.supported_vendors
            and device.dedicated_memory_gb + device.shared_memory_gb >= 1.0
            for device in self._profile.gpu_devices
        ) if accelerated else True
        device_verified = bool(capabilities.available_devices) if accelerated else True
        usable = validation.valid and matching_hardware and memory_verified and device_verified
        if not matching_hardware:
            reason = "device_not_detected"
        elif not memory_verified:
            reason = "gpu_memory_unverified"
        elif not device_verified:
            reason = "device_not_listed_by_runtime"
        else:
            reason = "compatible"
        probe = BackendProbeResult(
            backend_id=f"llama_cpp_{variant.backend}",
            detected=matching_hardware,
            usable=usable,
            stable=validation.valid and (not accelerated or device_verified),
            reason_code=reason,
            technical_detail=f"probe={validation.probe_argument}",
            devices=capabilities.available_devices if accelerated else (),
            supported_flags=capabilities.supported_flags,
            runtime_variant_id=variant.id,
            requires_emulation=self._resolution.requires_emulation,
            experimental=variant.experimental,
            runtime_installed=True,
            provider_available=not accelerated or device_verified,
            model_compatible=variant.model_format == "gguf",
            generation_tested=False,
        )
        try:
            selection = BackendSelector().select(
                self._profile,
                [probe],
                experimental_enabled=self._experimental_enabled,
            )
        except BackendSelectionError as exc:
            self.failed.emit(exc.rejected[0].probe.reason_code if exc.rejected else exc.reason_code)
            return
        self.completed.emit(selection.primary, capabilities, str(self._executable.resolve(strict=False)))

    def request_cancel(self) -> None:
        self._cancellation_event.set()


class RuntimeStartWorker(QObject):
    status_changed = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        runtime_manager: RuntimeManager,
        model_path: Path | None,
        context_tokens: int | None,
        startup_timeout_seconds: int,
        launch_plan: RuntimeLaunchPlan | None = None,
    ) -> None:
        super().__init__()
        self._runtime_manager = runtime_manager
        self._model_path = model_path
        self._context_tokens = context_tokens
        self._startup_timeout_seconds = startup_timeout_seconds
        self._launch_plan = launch_plan
        self._cancellation_event = threading.Event()

    @Slot()
    def run(self) -> None:
        self.status_changed.emit("waiting_for_runtime")
        if self._launch_plan is not None:
            state = self._runtime_manager.start_launch_plan(
                self._launch_plan,
                self._startup_timeout_seconds,
                cancellation_event=self._cancellation_event,
            )
        else:
            if self._model_path is None or self._context_tokens is None:
                self.failed.emit("runtime_launch_plan_missing")
                return
            state = self._runtime_manager.start(
                self._model_path,
                self._context_tokens,
                self._startup_timeout_seconds,
                cancellation_event=self._cancellation_event,
            )
        if state.status == "ready" and state.endpoint_url:
            self.finished.emit(state.endpoint_url)
        else:
            self.failed.emit(state.error or "runtime_start_failed")

    def request_cancel(self) -> None:
        self._cancellation_event.set()
