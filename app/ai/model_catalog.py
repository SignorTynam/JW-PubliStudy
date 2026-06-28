from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocalModelSpec:
    id: str
    display_name: str
    description: str
    filename: str
    download_url: str
    sha256: str | None
    size_gb: float
    min_ram_gb: float
    recommended_machine_class: str
    context_tokens: int
    default_temperature: float
    default_max_tokens: int


_MODEL_CATALOG: tuple[LocalModelSpec, ...] = (
    LocalModelSpec(
        id="small",
        display_name="JW PubliStudy Small",
        description="Lightweight local model for PCs with about 8 GB RAM.",
        filename="jw-publistudy-small.gguf",
        download_url="https://example.com/models/jw-publistudy-small.gguf",
        sha256=None,
        size_gb=3.0,
        min_ram_gb=8.0,
        recommended_machine_class="low",
        context_tokens=4096,
        default_temperature=0.2,
        default_max_tokens=800,
    ),
    LocalModelSpec(
        id="medium",
        display_name="JW PubliStudy Medium",
        description="Balanced local model for PCs with about 16 GB RAM.",
        filename="jw-publistudy-medium.gguf",
        download_url="https://example.com/models/jw-publistudy-medium.gguf",
        sha256=None,
        size_gb=6.0,
        min_ram_gb=12.0,
        recommended_machine_class="medium",
        context_tokens=6144,
        default_temperature=0.2,
        default_max_tokens=900,
    ),
    LocalModelSpec(
        id="large",
        display_name="JW PubliStudy Large",
        description="Higher quality local model for PCs with about 32 GB RAM.",
        filename="jw-publistudy-large.gguf",
        download_url="https://example.com/models/jw-publistudy-large.gguf",
        sha256=None,
        size_gb=12.0,
        min_ram_gb=24.0,
        recommended_machine_class="high",
        context_tokens=8192,
        default_temperature=0.2,
        default_max_tokens=1000,
    ),
)


def list_models() -> list[LocalModelSpec]:
    return list(_MODEL_CATALOG)


def get_model(model_id: str) -> LocalModelSpec | None:
    return next((model for model in _MODEL_CATALOG if model.id == model_id), None)


def recommend_model(total_ram_gb: float) -> LocalModelSpec:
    if total_ram_gb >= 24:
        return get_model("large") or _MODEL_CATALOG[0]
    if total_ram_gb >= 12:
        return get_model("medium") or _MODEL_CATALOG[0]
    return get_model("small") or _MODEL_CATALOG[0]

