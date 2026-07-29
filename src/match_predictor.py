"""Shared resume↔JD fit predictor — inference (Phase 10).

A resume↔JD fit model (SBERT + LoRA) fine-tuned on public resume-JD fit data and
exported to ONNX. Served here with ONNX Runtime — **no PyTorch in production**
(only `onnxruntime` + `tokenizers`, the `[predictor]` extra).

Flag-gated by `MATCH_PREDICTOR_MODEL` (`none` | `v1`). When off, or if the
artifact can't be loaded, `predict_fit()` returns None and the app behaves
exactly as before — so this ships dark and lights up only once a model is
trained (Stage B) and the flag is flipped.

The shipped artifact is a bi-encoder (resume + JD encoded separately):
    inputs : resume_input_ids, resume_attention_mask,
             jd_input_ids,     jd_attention_mask          (int64, shape [1, seq])
    output : fit_prob                                     (float, shape [1]/[1,1]) in [0,1]

A `tokenizer.json` (HF fast tokenizer) ships alongside `model.onnx`.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from src.utils.config import settings

log = logging.getLogger("resumeagent.match_predictor")

MAX_LEN = 512  # MiniLM's max; must match scripts/train_match_predictor.py
_ARTIFACT = "model.onnx"
_TOKENIZER = "tokenizer.json"

_lock = threading.Lock()
_bundle: Optional[tuple] = None   # (onnx InferenceSession, Tokenizer, calibration dict|None)
_load_failed = False


def is_enabled() -> bool:
    return (settings.match_predictor_model or "none").lower() not in ("", "none")


def _artifact_dir() -> Optional[str]:
    """Local dir holding the baked model.onnx + tokenizer.json, or None if unset."""
    return settings.match_predictor_path or None


def _load() -> Optional[tuple]:
    import json
    import os

    import onnxruntime as ort
    from tokenizers import Tokenizer

    d = _artifact_dir()
    if not d:
        log.warning("match_predictor enabled but no repo/path configured.")
        return None
    session = ort.InferenceSession(os.path.join(d, _ARTIFACT), providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(os.path.join(d, _TOKENIZER))
    tok.enable_truncation(max_length=MAX_LEN)
    calib = None
    cpath = os.path.join(d, "calibration.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            calib = json.load(f)

    log.info("match_predictor loaded (bi-encoder)")
    return session, tok, calib


def _get_bundle() -> Optional[tuple]:
    global _bundle, _load_failed
    if _bundle is not None:
        return _bundle
    if _load_failed:
        return None
    with _lock:
        if _bundle is not None:
            return _bundle
        if _load_failed:
            return None
        try:
            _bundle = _load()
            if _bundle is None:
                _load_failed = True
        except Exception as e:
            log.warning("match_predictor load failed (feature stays off): %s", e)
            _load_failed = True
            return None
    return _bundle


def _encode(tok, text: str):
    """Bi-encoder single-sequence encoding."""
    import numpy as np

    enc = tok.encode(text or "")
    ids = np.asarray([enc.ids], dtype=np.int64)
    mask = np.asarray([enc.attention_mask], dtype=np.int64)
    return ids, mask


def predict_fit(resume_text: str, jd_text: str) -> Optional[float]:
    """Return a fit probability in [0,1], or None if the feature is off / the
    model is unavailable / inference fails. Synchronous (ONNX CPU) — call via
    asyncio.to_thread from async code. Never raises."""
    if not is_enabled():
        return None
    bundle = _get_bundle()
    if bundle is None:
        return None
    session, tok, calib = bundle
    try:
        r_ids, r_mask = _encode(tok, resume_text)
        j_ids, j_mask = _encode(tok, jd_text)
        out = session.run(
            ["fit_prob"],
            {
                "resume_input_ids": r_ids,
                "resume_attention_mask": r_mask,
                "jd_input_ids": j_ids,
                "jd_attention_mask": j_mask,
            },
        )

        from src.match_predictor_calibration import apply_calibration

        prob = float(out[0].reshape(-1)[0])
        return apply_calibration(max(0.0, min(1.0, prob)), calib)
    except Exception as e:
        log.warning("match_predictor inference failed: %s", e)
        return None
