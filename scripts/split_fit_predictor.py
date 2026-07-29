"""Split the fused bi-encoder model.onnx into a shared encoder + a tiny head.

The trained bi-encoder encodes the resume and JD in two independent towers that
meet once at sigmoid(W.|u-v|+b). Because the towers share the same encoder weights
and neither depends on the other's input, we can carve the graph — with NO retrain
and numerically identical scores — into:

    encoder.onnx : [input_ids, attention_mask] -> embedding   (the shared tower)
    head.onnx    : [emb_resume, emb_jd] -> fit_prob           (Sub/Abs/Gemm/Sigmoid)

Serving then embeds the CV once per search (cache it) and only runs the JD tower +
head per candidate. This script also verifies the split reproduces the original
model's scores before writing anything permanent.

    python -m scripts.split_fit_predictor            # split models/fit-predictor
    python -m scripts.split_fit_predictor --dir X    # a different artifact dir
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnx.utils import extract_model
from tokenizers import Tokenizer

# Tensor names discovered from the fused graph (see the two-tower audit):
_RESUME_EMB = "/Div_output_0"   # L2-normalized resume embedding (u)
_JD_EMB = "/Div_1_output_0"     # L2-normalized JD embedding (v)
_FIT = "fit_prob"
MAX_LEN = 512


def _rename(model: onnx.ModelProto, mapping: dict[str, str]) -> onnx.ModelProto:
    """Rename graph inputs/outputs and every node reference in-place."""
    for vi in list(model.graph.input) + list(model.graph.output):
        if vi.name in mapping:
            vi.name = mapping[vi.name]
    for node in model.graph.node:
        node.input[:] = [mapping.get(i, i) for i in node.input]
        node.output[:] = [mapping.get(o, o) for o in node.output]
    return model


def _encode(tok: Tokenizer, text: str):
    enc = tok.encode(text or "")
    ids = np.asarray([enc.ids], dtype=np.int64)
    mask = np.asarray([enc.attention_mask], dtype=np.int64)
    return ids, mask


def split(artifact_dir: Path) -> None:
    src = artifact_dir / "model.onnx"
    enc_path = artifact_dir / "encoder.onnx"
    head_path = artifact_dir / "head.onnx"
    if not src.exists():
        raise SystemExit(f"missing {src}")

    # Shape inference makes the internal cut tensors addressable by extract_model.
    inferred = artifact_dir / "_model_inferred.onnx"
    onnx.save(onnx.shape_inference.infer_shapes(onnx.load(str(src))), str(inferred))

    # Encoder = the resume tower, renamed to generic input/output names (it is the
    # shared encoder, so it applies to JD tokens too).
    extract_model(str(inferred), str(enc_path),
                  ["resume_input_ids", "resume_attention_mask"], [_RESUME_EMB])
    onnx.save(_rename(onnx.load(str(enc_path)), {
        "resume_input_ids": "input_ids",
        "resume_attention_mask": "attention_mask",
        _RESUME_EMB: "embedding",
    }), str(enc_path))

    # Head = everything from the two embeddings to fit_prob.
    extract_model(str(inferred), str(head_path), [_RESUME_EMB, _JD_EMB], [_FIT])
    onnx.save(_rename(onnx.load(str(head_path)), {
        _RESUME_EMB: "emb_resume",
        _JD_EMB: "emb_jd",
    }), str(head_path))
    inferred.unlink(missing_ok=True)

    _verify(artifact_dir, src, enc_path, head_path)
    print(f"OK — wrote {enc_path.name} ({enc_path.stat().st_size // 1024} KB) "
          f"+ {head_path.name} ({head_path.stat().st_size // 1024} KB)")


def _verify(artifact_dir: Path, src: Path, enc_path: Path, head_path: Path) -> None:
    """Assert the split reproduces the fused model's scores on sample pairs."""
    tok = Tokenizer.from_file(str(artifact_dir / "tokenizer.json"))
    tok.enable_truncation(max_length=MAX_LEN)
    orig = ort.InferenceSession(str(src), providers=["CPUExecutionProvider"])
    enc = ort.InferenceSession(str(enc_path), providers=["CPUExecutionProvider"])
    head = ort.InferenceSession(str(head_path), providers=["CPUExecutionProvider"])

    samples = [
        ("Python ML engineer, PyTorch, RAG, LLM fine-tuning, AWS",
         "We seek an AI Engineer with Python, PyTorch, RAG and LLM experience."),
        ("Frontend React developer, TypeScript, CSS",
         "Seeking a senior civil engineer for bridge construction projects."),
        ("Data scientist, SQL, statistics, experimentation",
         "Data Scientist role: SQL, A/B testing, Python, dashboards."),
    ]
    max_diff = 0.0
    for resume, jd in samples:
        r_ids, r_mask = _encode(tok, resume)
        j_ids, j_mask = _encode(tok, jd)
        want = orig.run([_FIT], {
            "resume_input_ids": r_ids, "resume_attention_mask": r_mask,
            "jd_input_ids": j_ids, "jd_attention_mask": j_mask,
        })[0].reshape(-1)[0]
        u = enc.run(["embedding"], {"input_ids": r_ids, "attention_mask": r_mask})[0]
        v = enc.run(["embedding"], {"input_ids": j_ids, "attention_mask": j_mask})[0]
        got = head.run([_FIT], {"emb_resume": u, "emb_jd": v})[0].reshape(-1)[0]
        max_diff = max(max_diff, abs(float(want) - float(got)))
        print(f"  orig={float(want):.6f}  split={float(got):.6f}  diff={abs(float(want)-float(got)):.2e}")
    assert max_diff < 1e-4, f"split diverges from original (max diff {max_diff:.2e})"
    print(f"verified: max diff {max_diff:.2e} < 1e-4")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="models/fit-predictor")
    args = ap.parse_args()
    split(Path(args.dir))
