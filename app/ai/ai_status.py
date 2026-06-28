from __future__ import annotations


class AIStatus:
    NOT_CONFIGURED = "not_configured"
    MODEL_MISSING = "model_missing"
    RUNTIME_MISSING = "runtime_missing"
    DOWNLOADING = "downloading"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    MANUAL_MODE = "manual_mode"

