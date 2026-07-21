"""Shared resume↔JD fit predictor — inference (Phase 10).

A resume↔JD fit model (SBERT + LoRA) fine-tuned on public resume-JD fit data and
exported to ONNX. Served here with ONNX Runtime — **no PyTorch in production**
(only `onnxruntime` + `tokenizers`, the `[predictor]` extra).

Flag-gated by `MATCH_PREDICTOR_MODEL` (`none` | `v1`). When off, or if the
artifact can't be loaded, `predict_fit()` returns None and the app behaves
exactly as before — so this ships dark and lights up only once a model is
trained (Stage B) and the flag is flipped.

Two ONNX contracts are supported (the training-side export in
scripts/train_match_predictor.py MUST match one of these — it is the source
of truth). The contract in use is detected at load time from the session's
input names, so either artifact can be dropped in without a code change:

    bi-encoder (resume + JD encoded separately):
        inputs : resume_input_ids, resume_attention_mask,
                 jd_input_ids,     jd_attention_mask          (int64, shape [1, seq])
        output : fit_prob                                     (float, shape [1]/[1,1]) in [0,1]

    cross-encoder (resume + JD encoded together as a pair,
                   "[CLS] resume [SEP] jd [SEP]"):
        inputs : input_ids, attention_mask, token_type_ids     (int64, shape [1, seq])
        output : fit_prob                                      (float, shape [1]/[1,1]) in [0,1]

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
_bundle: Optional[tuple] = None   # (onnx InferenceSession, Tokenizer, calibration dict|None, is_cross bool)
_load_failed = False


def is_enabled() -> bool:
    return (settings.match_predictor_model or "none").lower() not in ("", "none")


def _artifact_dir() -> Optional[str]:
    """Local dir holding model.onnx + tokenizer.json. Either an explicit local
    path, or downloaded from the pinned HF Hub repo. None if unconfigured."""
    if settings.match_predictor_path:
        return settings.match_predictor_path
    if settings.match_predictor_repo:
        from huggingface_hub import snapshot_download

        token = settings.hf_token.get_secret_value() if settings.hf_token else None
        return snapshot_download(repo_id=settings.match_predictor_repo, token=token)
    return None


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

    # Detect which ONNX contract this artifact uses from its declared input
    # names: the cross-encoder takes a single pair-encoded (input_ids,
    # attention_mask, token_type_ids); the bi-encoder takes separate
    # resume_*/jd_* pairs. This lets either artifact be dropped in place
    # without a code change.
    input_names = {i.name for i in session.get_inputs()}
    is_cross = "token_type_ids" in input_names or (
        "input_ids" in input_names and "resume_input_ids" not in input_names
    )
    log.info("match_predictor loaded (%s contract)", "cross-encoder" if is_cross else "bi-encoder")
    return session, tok, calib, is_cross


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


def _encode_pair(tok, resume_text: str, jd_text: str):
    """Cross-encoder pair encoding: [CLS] resume [SEP] jd [SEP], with
    token_type_ids 0 on the resume side and 1 on the JD side."""
    import numpy as np

    enc = tok.encode(resume_text or "", jd_text or "")
    ids = np.asarray([enc.ids], dtype=np.int64)
    mask = np.asarray([enc.attention_mask], dtype=np.int64)
    type_ids = np.asarray([enc.type_ids], dtype=np.int64)
    return ids, mask, type_ids


def predict_fit(resume_text: str, jd_text: str) -> Optional[float]:
    """Return a fit probability in [0,1], or None if the feature is off / the
    model is unavailable / inference fails. Synchronous (ONNX CPU) — call via
    asyncio.to_thread from async code. Never raises."""
    if not is_enabled():
        return None
    bundle = _get_bundle()
    if bundle is None:
        return None
    session, tok, calib, is_cross = bundle
    try:
        if is_cross:
            ids, mask, type_ids = _encode_pair(tok, resume_text, jd_text)
            out = session.run(
                ["fit_prob"],
                {
                    "input_ids": ids,
                    "attention_mask": mask,
                    "token_type_ids": type_ids,
                },
            )
        else:
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
