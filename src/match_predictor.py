"""Shared resume↔JD fit predictor — inference (Phase 10).

A resume↔JD fit model (SBERT + LoRA) fine-tuned on public resume-JD fit data and
exported to ONNX. Served here with ONNX Runtime — **no PyTorch in production**
(only `onnxruntime` + `tokenizers`, the `[predictor]` extra).

Flag-gated by `MATCH_PREDICTOR_MODEL` (`none` | `v1`). When off, or if the
artifact can't be loaded, the predictor returns None and the app behaves exactly
as before — so this ships dark and lights up only once the flag is flipped.

**Two-tower serving (2026-07-30).** The fused bi-encoder was split (losslessly,
`scripts/split_fit_predictor.py`) into a shared encoder + a tiny head:
    encoder.onnx : [input_ids, attention_mask] -> embedding   (the shared tower)
    head.onnx    : [emb_resume, emb_jd]         -> fit_prob    (sigmoid over |u-v|)
So a search embeds the CV **once** (`embed_resume`, cache the vector) and scores
each JD with only the JD tower + head (`score`) — halving the transformer work per
search. `predict_fit` keeps the one-shot (cv, jd) API for non-gated callers.

A `tokenizer.json` (HF fast tokenizer) ships alongside the two graphs.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from src.utils.config import settings

log = logging.getLogger("resumeagent.match_predictor")

MAX_LEN = 512  # MiniLM's max; must match scripts/train_match_predictor.py
_ENCODER = "encoder.onnx"
_HEAD = "head.onnx"
_TOKENIZER = "tokenizer.json"

_lock = threading.Lock()
_bundle: Optional[tuple] = None   # (encoder session, head session, Tokenizer, calibration|None)
_load_failed = False


def is_enabled() -> bool:
    return (settings.match_predictor_model or "none").lower() not in ("", "none")


def _artifact_dir() -> Optional[str]:
    """Local dir holding the baked encoder.onnx + head.onnx + tokenizer.json."""
    return settings.match_predictor_path or None


def _load() -> Optional[tuple]:
    import json
    import os

    import onnxruntime as ort
    from tokenizers import Tokenizer

    d = _artifact_dir()
    if not d:
        log.warning("match_predictor enabled but no path configured.")
        return None
    enc = ort.InferenceSession(os.path.join(d, _ENCODER), providers=["CPUExecutionProvider"])
    head = ort.InferenceSession(os.path.join(d, _HEAD), providers=["CPUExecutionProvider"])
    tok = Tokenizer.from_file(os.path.join(d, _TOKENIZER))
    tok.enable_truncation(max_length=MAX_LEN)
    calib = None
    cpath = os.path.join(d, "calibration.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            calib = json.load(f)

    log.info("match_predictor loaded (two-tower: encoder + head)")
    return enc, head, tok, calib


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
    import numpy as np

    enc = tok.encode(text or "")
    ids = np.asarray([enc.ids], dtype=np.int64)
    mask = np.asarray([enc.attention_mask], dtype=np.int64)
    return ids, mask


def _embed(enc_session, tok, text: str):
    """Run the shared encoder → a single [1, dim] embedding array."""
    ids, mask = _encode(tok, text)
    return enc_session.run(["embedding"], {"input_ids": ids, "attention_mask": mask})[0]


def embed_resume(resume_text: str) -> Optional[Any]:
    """Encode the CV once and return its embedding (reusable across many JDs), or
    None if the feature is off / unavailable. Synchronous (ONNX CPU) — call via
    asyncio.to_thread from async code. Never raises."""
    if not is_enabled():
        return None
    bundle = _get_bundle()
    if bundle is None:
        return None
    enc_session, _head, tok, _calib = bundle
    try:
        return _embed(enc_session, tok, resume_text)
    except Exception as e:
        log.warning("match_predictor embed failed: %s", e)
        return None


def score(resume_emb: Any, jd_text: str) -> Optional[float]:
    """Fit probability in [0,1] for a JD against a pre-computed CV embedding, or
    None if unavailable. Encodes only the JD tower + the tiny head. Never raises."""
    if resume_emb is None or not is_enabled():
        return None
    bundle = _get_bundle()
    if bundle is None:
        return None
    enc_session, head_session, tok, calib = bundle
    try:
        jd_emb = _embed(enc_session, tok, jd_text)
        out = head_session.run(["fit_prob"], {"emb_resume": resume_emb, "emb_jd": jd_emb})

        from src.match_predictor_calibration import apply_calibration

        prob = float(out[0].reshape(-1)[0])
        return apply_calibration(max(0.0, min(1.0, prob)), calib)
    except Exception as e:
        log.warning("match_predictor score failed: %s", e)
        return None


def predict_fit(resume_text: str, jd_text: str) -> Optional[float]:
    """One-shot (cv, jd) → fit probability, for non-gated callers. Embeds both
    towers; the gated search path uses embed_resume + score to reuse the CV."""
    emb = embed_resume(resume_text)
    if emb is None:
        return None
    return score(emb, jd_text)
