"""OpenTSLM wrapper: per-night HR + SpO₂ narratives.

Module-level singleton with a load-once warmup. Any failure (missing checkpoint,
torch issues, model API drift) returns a structured null so the endpoint can
degrade gracefully and the agent can add a caveat.
"""
from __future__ import annotations
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd

from sleep_pipeline.config import OPENTSLM_ENABLED, OPENTSLM_CHECKPOINT

TARGET_SAMPLES = 256
PROMPT = (
    "Analyze one night of wearable physiology (HR and SpO2, two channels). "
    "In 4-6 sentences describe (1) autonomic stability, (2) restorative deep-sleep signs "
    "from heart-rate dip, (3) any SpO2 disturbances, and (4) one comparative note vs. a "
    "typical adult night. Be concrete about timing."
)

_lock = Lock()
_model = None
_load_error: str | None = None


def _z(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype("float32")
    mu = float(np.nanmean(arr))
    sd = float(np.nanstd(arr))
    if sd < 1e-6:
        return np.zeros_like(arr)
    return (arr - mu) / sd


def _resample_to_target(series: pd.Series, target: int = TARGET_SAMPLES) -> np.ndarray:
    """Coarse downsample to `target` points by bucket-averaging."""
    if series.empty:
        return np.zeros(target, dtype="float32")
    s = series.ffill().bfill()
    arr = s.to_numpy(dtype="float32")
    n = len(arr)
    if n <= target:
        out = np.zeros(target, dtype="float32")
        out[:n] = arr
        return out
    edges = np.linspace(0, n, target + 1, dtype=int)
    return np.array([arr[edges[i] : edges[i + 1]].mean() for i in range(target)], dtype="float32")


def warmup() -> None:
    """Eager-load the model at Flask startup if enabled."""
    if not OPENTSLM_ENABLED:
        return
    try:
        get_model()
    except Exception as e:
        print(f"[opentslm] warmup failed: {e}")


def get_model():
    global _model, _load_error
    if _model is not None:
        return _model
    if _load_error is not None:
        raise RuntimeError(_load_error)
    with _lock:
        if _model is not None:
            return _model
        try:
            from opentslm import OpenTSLM  # type: ignore
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[opentslm] loading {OPENTSLM_CHECKPOINT} on {device} ...")
            _model = OpenTSLM.load_pretrained(OPENTSLM_CHECKPOINT, device=device)
            print("[opentslm] loaded")
            return _model
        except Exception as e:
            _load_error = f"OpenTSLM load failed: {e}"
            raise RuntimeError(_load_error) from e


def _build_batch(hr: np.ndarray, spo2: np.ndarray) -> dict[str, Any]:
    """Construct the single-example batch dict expected by OpenTSLM.generate.

    Mirrors the shape produced by TSQADataset.__getitem__ + the patch-aggregation
    util. Time-series tensor is [C, T].
    """
    import torch
    from opentslm.time_series_datasets.util import (  # type: ignore
        extend_time_series_to_match_patch_size_and_aggregate,
    )
    from opentslm.model_config import PATCH_SIZE  # type: ignore

    ts = torch.from_numpy(np.stack([hr, spo2], axis=0)).float()  # [2, T]
    sample = {
        "time_series": ts,
        "pre_prompt": PROMPT,
        "post_prompt": "",
        "answer": "",
    }
    batch = extend_time_series_to_match_patch_size_and_aggregate([sample], patch_size=PATCH_SIZE)
    return batch


def summarize_night(df: pd.DataFrame, bedtime: str, wake_time: str) -> dict[str, Any]:
    """Return {summary, error}. Either field may be None."""
    if not OPENTSLM_ENABLED:
        return {"summary": None, "error": "OPENTSLM_ENABLED=0"}
    try:
        model = get_model()
    except Exception as e:
        return {"summary": None, "error": str(e)}

    try:
        night = df.loc[bedtime:wake_time]
        hr = _z(_resample_to_target(night["heart_rate_bpm"]))
        spo2 = _z(_resample_to_target(night["spo2_pct"]))
        batch = _build_batch(hr, spo2)
        preds = model.generate(batch, max_new_tokens=256)
        text = preds[0] if isinstance(preds, (list, tuple)) else str(preds)
        return {"summary": text.strip(), "error": None}
    except Exception as e:
        return {"summary": None, "error": f"OpenTSLM generate failed: {e}"}
