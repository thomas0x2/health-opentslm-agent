"""OpenTSLM wrapper — M4 captioning checkpoint.

The default `OpenTSLM/llama-3.2-1b-m4-sp` checkpoint is trained on the M4
time-series captioning task: given a single normalized series with its mean
and std, generate a free-form natural-language description. We use the
exact prompt template the model was trained on; deviations produce garbage.

For wearable use, we resample each domain's primary channel to 256 points
(M4-friendly length) and call the model once per domain.

Failure modes (missing checkpoint, gated base, torch issues) return a
structured null so the endpoint can degrade gracefully.
"""
from __future__ import annotations
from threading import Lock
from typing import Any, Sequence

import numpy as np
import pandas as pd

from health_pipeline.config import OPENTSLM_ENABLED, OPENTSLM_CHECKPOINT

TARGET_SAMPLES = 256

# Locked to match M4QADataset training format. Do not change.
M4_PRE_PROMPT = "You are an expert in time series analysis."
M4_POST_PROMPT = (
    "Please generate a detailed caption for this time-series, "
    "describing it as accurately as possible."
)


_lock = Lock()
_model = None
_load_error: str | None = None


def _resample_to_target(series: pd.Series, target: int = TARGET_SAMPLES) -> np.ndarray:
    """Bucket-average down to `target` points; ffill/bfill nulls."""
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
    return np.array(
        [arr[edges[i] : edges[i + 1]].mean() for i in range(target)], dtype="float32"
    )


def warmup() -> None:
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


def caption_series(
    values: Sequence[float],
    *,
    channel_label: str | None = None,
    max_new_tokens: int = 256,
) -> dict[str, Any]:
    """Run M4 captioning on one time-series. Returns {summary, error, channel}.

    The series is z-scored internally (M4 expects normalized input with mean/std
    reported in the text descriptor). `channel_label`, if given, is appended to
    the returned dict so the agent can tell what was described.
    """
    if not OPENTSLM_ENABLED:
        return {"summary": None, "error": "OPENTSLM_ENABLED=0", "channel": channel_label}
    try:
        model = get_model()
    except Exception as e:
        return {"summary": None, "error": str(e), "channel": channel_label}

    try:
        from opentslm.prompt.full_prompt import FullPrompt  # type: ignore
        from opentslm.prompt.text_prompt import TextPrompt  # type: ignore
        from opentslm.prompt.text_time_series_prompt import TextTimeSeriesPrompt  # type: ignore

        arr = np.asarray(list(values), dtype="float32")
        if arr.size < 32:
            return {
                "summary": None,
                "error": f"series too short for M4 ({arr.size} samples; need >= 32)",
                "channel": channel_label,
            }
        mean_val = float(arr.mean())
        std_val = float(arr.std()) if arr.std() > 1e-8 else 1.0
        z = ((arr - mean_val) / std_val).tolist()

        prompt = FullPrompt(
            pre_prompt=TextPrompt(M4_PRE_PROMPT),
            text_time_series_prompt_list=[
                TextTimeSeriesPrompt(
                    text=f"This is the time series, it has mean {mean_val:.4f} and std {std_val:.4f}:",
                    time_series=z,
                )
            ],
            post_prompt=TextPrompt(M4_POST_PROMPT),
        )
        text = model.eval_prompt(prompt, max_new_tokens=max_new_tokens, normalize=False)
        return {"summary": (text or "").strip(), "error": None, "channel": channel_label}
    except Exception as e:
        return {"summary": None, "error": f"M4 caption failed: {e}", "channel": channel_label}


def summarize_night(
    df: pd.DataFrame, bedtime: str, wake_time: str
) -> dict[str, Any]:
    """Per-night HR captioning (sleep domain). Returns the same shape as
    caption_series, with `bedtime` added for downstream display."""
    if not OPENTSLM_ENABLED:
        return {"summary": None, "error": "OPENTSLM_ENABLED=0", "channel": "heart_rate_bpm"}
    try:
        night = df.loc[bedtime:wake_time]
        hr = _resample_to_target(night["heart_rate_bpm"].dropna())
        res = caption_series(hr, channel_label="heart_rate_bpm (one night, 256 buckets)")
        res["bedtime"] = bedtime
        return res
    except Exception as e:
        return {
            "summary": None,
            "error": f"summarize_night failed: {e}",
            "channel": "heart_rate_bpm",
            "bedtime": bedtime,
        }
