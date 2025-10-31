from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def _safe_resolve(path: Path) -> Optional[Path]:
    try:
        return path.resolve()
    except Exception:
        return None


def _iter_candidate_paths(config_path: Path, upload_cfg: dict[str, Any]) -> Iterable[Path]:
    """Yield candidate roots that may contain the SkinMap sources."""
    seen: set[str] = set()

    skinmap_root_raw = upload_cfg.get("skinmap_root")
    if skinmap_root_raw:
        skinmap_root = Path(skinmap_root_raw)
        if skinmap_root.is_absolute():
            candidates = [skinmap_root]
        else:
            candidates = [
                config_path.parent / skinmap_root,
                config_path.parent.parent / skinmap_root,
            ]
        for candidate in candidates:
            resolved = _safe_resolve(candidate)
            if resolved is not None and resolved.exists():
                key = str(resolved)
                if key not in seen:
                    seen.add(key)
                    yield resolved

    for parent in [config_path.parent, config_path.parent.parent]:
        resolved = _safe_resolve(parent)
        if resolved is not None and resolved.exists():
            key = str(resolved)
            if key not in seen:
                seen.add(key)
                yield resolved


def _ensure_sys_path(config_path: Path, upload_cfg: dict[str, Any]) -> None:
    for candidate in _iter_candidate_paths(config_path, upload_cfg):
        if str(candidate) not in sys.path:
            sys.path.append(str(candidate))


class LazyCombinedEmbeddingPipeline:
    """Lazily construct the CombinedEmbeddingPipeline on first use."""

    def __init__(self, config: dict[str, Any], config_path: Path, *, device: Optional[str] = None):
        from src.combined_embedder import CombinedEmbeddingPipeline  # Local import to avoid circular deps during build.

        self._config = config
        self._config_path = config_path
        self._device = device
        self._pipeline: CombinedEmbeddingPipeline | None = None
        self._lock = threading.Lock()
        self._load_exc: Exception | None = None
        self._cls = CombinedEmbeddingPipeline

    def _ensure_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        if self._load_exc is not None:
            raise RuntimeError("Upload embedding pipeline failed to initialize.") from self._load_exc
        with self._lock:
            if self._pipeline is None and self._load_exc is None:
                start = time.perf_counter()
                try:
                    logger.info(
                        "Initializing upload embedding pipeline from %s (device=%s)",
                        self._config_path,
                        self._device or "cpu",
                    )
                    self._pipeline = self._cls(
                        config=self._config,
                        config_path=self._config_path,
                        device=self._device,
                    )
                    elapsed = time.perf_counter() - start
                    logger.info(
                        "Upload embedding pipeline ready (took %.1fs)",
                        elapsed,
                    )
                except Exception as exc:  # pragma: no cover - defensive: surfaced to caller
                    self._load_exc = exc
                    logger.exception("Failed to initialize upload embedding pipeline: %s", exc)
                    raise RuntimeError("Upload embedding pipeline failed to initialize.") from exc
        return self._pipeline

    def search_image(self, image_bytes: bytes, k: int = 16):
        return self._ensure_pipeline().search_image(image_bytes, k=k)

    def find_nearest_neighbors(self, vector, k: int = 16):
        return self._ensure_pipeline().find_nearest_neighbors(vector, k=k)

    def embed_bytes(self, data: bytes):
        return self._ensure_pipeline().embed_bytes(data)

    def project_vector(self, vector):
        return self._ensure_pipeline().project_vector(vector)


def create_upload_pipeline(
    config_path: str | Path,
    *,
    device: Optional[str] = None,
    eager: bool = False,
) -> LazyCombinedEmbeddingPipeline | None:
    """
    Prepare a CombinedEmbeddingPipeline for nearest-neighbor lookup.

    Parameters
    ----------
    config_path:
        Path to the embedding_pipeline_config.json file.
    device:
        Torch device string. Defaults to CPU if unset.
    eager:
        When True, instantiate the pipeline immediately; otherwise load lazily
        on the first search.

    Returns
    -------
    LazyCombinedEmbeddingPipeline | None
        A lazily-loaded pipeline wrapper, or None if initialization is not possible.
    """
    path = Path(config_path)
    if not path.exists():
        logger.warning("Upload configuration %s not found; disabling upload search.", path)
        return None

    try:
        with path.open("r") as f:
            upload_cfg = json.load(f)
    except Exception as exc:
        logger.error("Failed to load upload configuration %s: %s", path, exc)
        return None

    _ensure_sys_path(path, upload_cfg)

    try:
        pipeline = LazyCombinedEmbeddingPipeline(upload_cfg, path, device=device)
    except Exception:  # pragma: no cover - LazyCombinedEmbeddingPipeline may raise during import
        return None

    if eager:
        try:
            pipeline._ensure_pipeline()
        except Exception:
            return None

    return pipeline


__all__ = ["create_upload_pipeline", "LazyCombinedEmbeddingPipeline"]
