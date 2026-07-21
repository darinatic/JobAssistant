"""Train the shared resume↔JD fit predictor (Phase 10, Stage B) — run on a GPU.

Bi-encoder (SBERT base) + LoRA/PEFT, trained on a public resume-JD fit dataset,
evaluated with AUC/F1, and exported to the ONNX contract that
`src/match_predictor.py` serves:

    inputs : resume_input_ids, resume_attention_mask, jd_input_ids, jd_attention_mask
    output : fit_prob   (sigmoid, [B] in [0,1])

This is the "GPU showcase" deliverable and is meant to run on RunPod, NOT in the
app/CI. Heavy deps (`pip install -e ".[train]"`) are imported inside functions so
importing this module without them fails only at call time.

────────────────────────────────────────────────────────────────────────────
RunPod runbook
────────────────────────────────────────────────────────────────────────────
1. Spin up an A40 / RTX 4090 pod (PyTorch image), SSH in, clone the repo.
2. pip install -e ".[train]"
3. export WANDB_API_KEY=...  HF_TOKEN=...
4. Smoke test on CPU first (1 step, tiny synthetic data):
       python -m scripts.train_match_predictor --smoke
5. Full run + push the ONNX artifact to a PRIVATE HF Hub repo:
       python -m scripts.train_match_predictor \
           --hf-repo <user>/resumeagent-fit-v1 --push --epochs 3
6. Back in the app, set MATCH_PREDICTOR_REPO=<user>/resumeagent-fit-v1,
   HF_TOKEN=..., MATCH_PREDICTOR_MODEL=v1 — the badge lights up.

────────────────────────────────────────────────────────────────────────────
Local GPU (e.g. RTX 3070, 8GB — plenty for MiniLM; HF + W&B both optional)
────────────────────────────────────────────────────────────────────────────
1. pip install -e ".[train]"  then verify CUDA is visible:
       python -c "import torch; print(torch.cuda.is_available())"   # expect True
   If False on Windows, reinstall torch from the CUDA index:
       pip install torch --index-url https://download.pytorch.org/whl/cu121
2. python -m scripts.train_match_predictor --smoke                  # CPU sanity
3. python -m scripts.train_match_predictor --epochs 3 --output-dir artifacts/fit-predictor
4. Serve straight from disk — NO HF Hub needed:
       set MATCH_PREDICTOR_PATH=artifacts/fit-predictor   (PowerShell: $env:MATCH_PREDICTOR_PATH=...)
       set MATCH_PREDICTOR_MODEL=v1
   W&B is optional (set WANDB_API_KEY); without it, metrics log to lightning_logs/ (CSV).
   HF Hub + --push are only needed to share the model or deploy off this machine.

Dataset: defaults to a public (resume, JD, fit-label) corpus on HF. Confirm the
column names + license for whichever dataset you use; map labels to binary
(good fit = 1) via --positive-labels.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

log = logging.getLogger("resumeagent.train")

BASE_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MAX_LEN = 512  # MiniLM's max; must match src/match_predictor.py
DEFAULT_DATASET = "cnamuangtoun/resume-job-description-fit"
# ~3:1 negative:positive ("Good Fit" is ~25%) — upweight positives so the
# sigmoid isn't pushed uniformly low (fixes the v1 "everything scores ~3%").
POS_WEIGHT = 3.0
LORA_R = 8

# Ordinal fit targets: the dataset's three classes mapped to a magnitude in [0,1]
# (Potential Fit is a genuine middle, not a negative). Soft-label regression on
# these replaces the old binary "Good Fit=1, else 0" which capped outputs at ~0.6.
_ORDINAL = {"no fit": 0.0, "potential fit": 0.5, "good fit": 1.0}


def _ordinal_label(v) -> float:
    return _ORDINAL.get(str(v).strip().lower(), 0.0)


# =============================================================================
# Model
# =============================================================================


def _build_module(base_model: str, lr: float, lora_r: int, pos_weight: float):
    """A LightningModule: shared LoRA encoder → mean-pool → [u,v,|u-v|] → 1 logit."""
    import pytorch_lightning as pl
    import torch
    import torch.nn as nn
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModel

    def mean_pool(last_hidden, mask):
        m = mask.unsqueeze(-1).float()
        return (last_hidden * m).sum(1) / m.sum(1).clamp(min=1e-9)

    class FitModule(pl.LightningModule):
        def __init__(self):
            super().__init__()
            encoder = AutoModel.from_pretrained(base_model)
            lora = LoraConfig(r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.1, target_modules=["query", "value"])
            self.encoder = get_peft_model(encoder, lora)
            hidden = encoder.config.hidden_size
            self.head = nn.Linear(3 * hidden, 1)
            # Soft-label regression: targets are ordinal magnitudes {0, 0.5, 1}, so
            # BCE (which accepts soft targets) makes sigmoid(logit) approximate the
            # fit magnitude directly. No pos_weight — Potential Fit is no longer a rare positive.
            self.loss_fn = nn.BCEWithLogitsLoss()
            self._val: list[tuple[float, float]] = []

        def encode(self, ids, mask):
            out = self.encoder(input_ids=ids, attention_mask=mask).last_hidden_state
            return mean_pool(out, mask)

        def forward(self, r_ids, r_mask, j_ids, j_mask):
            u, v = self.encode(r_ids, r_mask), self.encode(j_ids, j_mask)
            feats = torch.cat([u, v, (u - v).abs()], dim=1)
            return self.head(feats).squeeze(-1)

        def training_step(self, batch, _):
            logits = self(batch["r_ids"], batch["r_mask"], batch["j_ids"], batch["j_mask"])
            loss = self.loss_fn(logits, batch["label"])
            self.log("train_loss", loss, prog_bar=True)
            return loss

        def validation_step(self, batch, _):
            logits = self(batch["r_ids"], batch["r_mask"], batch["j_ids"], batch["j_mask"])
            probs = torch.sigmoid(logits)
            for p, y in zip(probs.tolist(), batch["label"].tolist()):
                self._val.append((p, y))

        def on_validation_epoch_end(self):
            from sklearn.metrics import roc_auc_score

            if not self._val:
                return
            probs, ys = zip(*self._val)  # ys are the soft targets 0/0.5/1.0
            mae = sum(abs(p - y) for p, y in self._val) / len(self._val)
            self.log("val_mae", float(mae), prog_bar=True)
            # per-tier mean prediction (drives the "Good ~0.8" success criterion)
            for tier, tv in (("no", 0.0), ("pot", 0.5), ("good", 1.0)):
                ps = [p for p, y in self._val if abs(y - tv) < 1e-6]
                if ps:
                    self.log(f"val_mean_{tier}", float(sum(ps) / len(ps)), prog_bar=False)
            # ranking quality: Good (target 1.0) vs the rest
            bin_y = [1 if abs(y - 1.0) < 1e-6 else 0 for y in ys]
            if 0 < sum(bin_y) < len(bin_y):
                self.log("val_auc", float(roc_auc_score(bin_y, probs)), prog_bar=True)
            self._val.clear()

        def configure_optimizers(self):
            params = [p for p in self.parameters() if p.requires_grad]
            return torch.optim.AdamW(params, lr=lr, weight_decay=0.01)

    return FitModule()


def _build_cross_module(base_model: str, lr: float, lora_r: int, pos_weight: float):
    """Cross-encoder: [CLS] resume [SEP] jd [SEP] through ONE LoRA encoder → [CLS] → 1 logit.
    More accurate for pairwise relevance than the bi-encoder (resume↔jd attend to each other)."""
    import pytorch_lightning as pl
    import torch
    import torch.nn as nn
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModel

    class CrossModule(pl.LightningModule):
        def __init__(self):
            super().__init__()
            encoder = AutoModel.from_pretrained(base_model)
            lora = LoraConfig(r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.1, target_modules=["query", "value"])
            self.encoder = get_peft_model(encoder, lora)
            self.head = nn.Linear(encoder.config.hidden_size, 1)
            self.loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([pos_weight]))
            self._val: list[tuple[float, float]] = []

        def forward(self, input_ids, attention_mask, token_type_ids):
            out = self.encoder(
                input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
            ).last_hidden_state
            return self.head(out[:, 0]).squeeze(-1)  # [CLS] token

        def training_step(self, batch, _):
            logits = self(batch["input_ids"], batch["attention_mask"], batch["token_type_ids"])
            loss = self.loss_fn(logits, batch["label"])
            self.log("train_loss", loss, prog_bar=True)
            return loss

        def validation_step(self, batch, _):
            logits = self(batch["input_ids"], batch["attention_mask"], batch["token_type_ids"])
            probs = torch.sigmoid(logits)
            for p, y in zip(probs.tolist(), batch["label"].tolist()):
                self._val.append((p, y))

        def on_validation_epoch_end(self):
            from sklearn.metrics import f1_score, roc_auc_score

            if self._val:
                probs, ys = zip(*self._val)
                try:
                    self.log("val_auc", float(roc_auc_score(ys, probs)), prog_bar=True)
                    self.log("val_f1", float(f1_score(ys, [p >= 0.5 for p in probs])), prog_bar=True)
                except ValueError:
                    pass
                self._val.clear()

        def configure_optimizers(self):
            params = [p for p in self.parameters() if p.requires_grad]
            return torch.optim.AdamW(params, lr=lr, weight_decay=0.01)

    return CrossModule()


# =============================================================================
# Data
# =============================================================================


def _make_loaders(tokenizer, dataset_name, positive_labels, batch_size, smoke, max_len, arch="biencoder"):
    import torch
    from torch.utils.data import DataLoader, Dataset

    class _DS(Dataset):
        def __init__(self, rows):
            self.rows = rows

        def __len__(self):
            return len(self.rows)

        def __getitem__(self, i):
            return self.rows[i]

    def _label(v) -> float:
        return 1.0 if str(v).strip().lower() in positive_labels else 0.0

    # Bi-encoder trains on ordinal soft labels (0/0.5/1); crossencoder keeps the
    # legacy binary `_label` (reads `positive_labels`) for backward compat.
    _bi_label = _ordinal_label

    def _tok(text):
        enc = tokenizer(text or "", truncation=True, max_length=max_len, padding="max_length")
        return torch.tensor(enc["input_ids"]), torch.tensor(enc["attention_mask"])

    def _to_rows_bi(records, resume_col, jd_col, label_col):
        rows = []
        for r in records:
            r_ids, r_mask = _tok(r[resume_col])
            j_ids, j_mask = _tok(r[jd_col])
            rows.append({"r_ids": r_ids, "r_mask": r_mask, "j_ids": j_ids, "j_mask": j_mask,
                         "label": torch.tensor(_bi_label(r[label_col]))})
        return rows

    def _to_rows_cross(records, resume_col, jd_col, label_col):
        rows = []
        for r in records:
            enc = tokenizer(r[resume_col] or "", r[jd_col] or "",
                            truncation=True, max_length=max_len, padding="max_length")
            tt = enc.get("token_type_ids") or [0] * len(enc["input_ids"])
            rows.append({
                "input_ids": torch.tensor(enc["input_ids"]),
                "attention_mask": torch.tensor(enc["attention_mask"]),
                "token_type_ids": torch.tensor(tt),
                "label": torch.tensor(_label(r[label_col])),
            })
        return rows

    _to_rows = _to_rows_cross if arch == "crossencoder" else _to_rows_bi

    if smoke:
        fake = [{"resume": "python rag llm aws", "jd": "llm engineer python aws", "label": "Good Fit"},
                {"resume": "graphic design photoshop", "jd": "llm engineer python", "label": "No Fit"}] * 8
        rows = _to_rows(fake, "resume", "jd", "label")
        ds = _DS(rows)
        return DataLoader(ds, batch_size=batch_size), DataLoader(ds, batch_size=batch_size)

    from datasets import load_dataset

    ds = load_dataset(dataset_name)
    cols = ds["train"].column_names
    resume_col = next(c for c in cols if "resume" in c.lower())
    jd_col = next(c for c in cols if "job" in c.lower() or "description" in c.lower())
    label_col = next(c for c in cols if "label" in c.lower() or "fit" in c.lower())
    log.info("Columns → resume=%s jd=%s label=%s", resume_col, jd_col, label_col)

    train = _DS(_to_rows(ds["train"], resume_col, jd_col, label_col))
    test_split = "test" if "test" in ds else "validation"
    test = _DS(_to_rows(ds[test_split], resume_col, jd_col, label_col))
    return (DataLoader(train, batch_size=batch_size, shuffle=True),
            DataLoader(test, batch_size=batch_size))


# =============================================================================
# Export (must match src/match_predictor.py's ONNX contract)
# =============================================================================


def _write_calibration(module, test_loader, out_dir: Path) -> None:
    """Fit an isotonic calibration map on held-out (raw_prob, ordinal_target)
    pairs from test_loader and write calibration.json next to model.onnx.
    Best-effort: sklearn is a train-time-only dep, and a failure here must
    never block the ONNX export."""
    import torch

    from src.match_predictor_calibration import fit_calibration

    raw: list[float] = []
    targets: list[float] = []
    module.eval()
    with torch.no_grad():
        for batch in test_loader:
            logits = module(batch["r_ids"], batch["r_mask"], batch["j_ids"], batch["j_mask"])
            probs = torch.sigmoid(logits)
            raw.extend(probs.tolist())
            targets.extend(batch["label"].tolist())

    if not raw:
        log.warning("No held-out predictions collected; skipping calibration.json")
        return

    calib = fit_calibration(raw, targets)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "calibration.json", "w", encoding="utf-8") as f:
        json.dump(calib, f)
    log.info("Wrote calibration.json (%d knots) to %s", len(calib["x"]), out_dir)


def _export_onnx(module, tokenizer, out_dir: Path, arch: str = "biencoder"):
    import torch

    module.eval()
    merged = module.encoder.merge_and_unload()  # fold LoRA into base weights for a plain ONNX
    out_dir.mkdir(parents=True, exist_ok=True)

    if arch == "crossencoder":
        class CrossExport(torch.nn.Module):
            def __init__(self, encoder, head):
                super().__init__()
                self.encoder, self.head = encoder, head

            def forward(self, input_ids, attention_mask, token_type_ids):
                out = self.encoder(
                    input_ids=input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids
                ).last_hidden_state
                return torch.sigmoid(self.head(out[:, 0]).squeeze(-1))

        wrapper = CrossExport(merged, module.head).eval()
        ids = torch.ones(1, 8, dtype=torch.long)
        names = ["input_ids", "attention_mask", "token_type_ids"]
        torch.onnx.export(
            wrapper,
            (ids, ids, torch.zeros(1, 8, dtype=torch.long)),
            str(out_dir / "model.onnx"),
            input_names=names,
            output_names=["fit_prob"],
            dynamic_axes={n: {0: "batch", 1: "seq"} for n in names} | {"fit_prob": {0: "batch"}},
            opset_version=17,
        )
        tokenizer.save_pretrained(str(out_dir))
        log.info("Exported cross-encoder ONNX + tokenizer to %s", out_dir)
        return

    class Export(torch.nn.Module):
        def __init__(self, encoder, head):
            super().__init__()
            self.encoder, self.head = encoder, head

        def _enc(self, ids, mask):
            out = self.encoder(input_ids=ids, attention_mask=mask).last_hidden_state
            m = mask.unsqueeze(-1).float()
            return (out * m).sum(1) / m.sum(1).clamp(min=1e-9)

        def forward(self, resume_input_ids, resume_attention_mask, jd_input_ids, jd_attention_mask):
            u = self._enc(resume_input_ids, resume_attention_mask)
            v = self._enc(jd_input_ids, jd_attention_mask)
            feats = torch.cat([u, v, (u - v).abs()], dim=1)
            return torch.sigmoid(self.head(feats).squeeze(-1))

    wrapper = Export(merged, module.head).eval()
    dummy = torch.ones(1, 8, dtype=torch.long)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = ["resume_input_ids", "resume_attention_mask", "jd_input_ids", "jd_attention_mask"]
    torch.onnx.export(
        wrapper,
        (dummy, dummy, dummy, dummy),
        str(out_dir / "model.onnx"),
        input_names=names,
        output_names=["fit_prob"],
        dynamic_axes={n: {0: "batch", 1: "seq"} for n in names} | {"fit_prob": {0: "batch"}},
        opset_version=17,
    )
    tokenizer.save_pretrained(str(out_dir))  # writes tokenizer.json for the fast tokenizer
    log.info("Exported ONNX + tokenizer to %s", out_dir)


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv
    load_dotenv()  # so WANDB_API_KEY / HF_TOKEN can live in .env like the app's keys
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--base-model", default=BASE_MODEL)
    ap.add_argument("--arch", choices=["biencoder", "crossencoder"], default="biencoder")
    ap.add_argument("--epochs", type=int, default=10, help="max epochs; EarlyStopping usually cuts it sooner")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--max-len", type=int, default=MAX_LEN, help="token truncation (must match serving for the shipped model)")
    ap.add_argument("--lora-r", type=int, default=LORA_R)
    ap.add_argument("--pos-weight", type=float, default=POS_WEIGHT)
    ap.add_argument("--patience", type=int, default=2, help="EarlyStopping patience on val_auc")
    ap.add_argument("--run-name", default=None, help="W&B run name (e.g. v3-512-r8-earlystop)")
    ap.add_argument("--positive-labels", default="good fit,good,fit,1,true")
    ap.add_argument("--output-dir", default="artifacts/fit-predictor")
    ap.add_argument("--hf-repo", default=None)
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="1-step CPU run on synthetic data")
    args = ap.parse_args()

    import pytorch_lightning as pl
    from transformers import AutoTokenizer

    positives = {s.strip().lower() for s in args.positive_labels.split(",")}
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, use_fast=True)
    train_loader, test_loader = _make_loaders(
        tokenizer, args.dataset, positives, args.batch_size, args.smoke, args.max_len, args.arch
    )
    if args.arch == "crossencoder":
        module = _build_cross_module(args.base_model, args.lr, args.lora_r, args.pos_weight)
    else:
        module = _build_module(args.base_model, args.lr, args.lora_r, args.pos_weight)

    config = {
        "arch": args.arch, "base_model": args.base_model, "dataset": args.dataset,
        "max_len": args.max_len, "lora_r": args.lora_r, "pos_weight": args.pos_weight,
        "epochs": args.epochs, "lr": args.lr, "batch_size": args.batch_size,
        "patience": args.patience,
    }

    # W&B if a key is present (hosted/showcase); otherwise log metrics to a local
    # CSV (no account, no extra dep) so local runs still produce loss/AUC curves.
    use_wandb = bool(os.environ.get("WANDB_API_KEY")) and not args.smoke
    logger = False
    if not args.smoke:
        if use_wandb:
            from pytorch_lightning.loggers import WandbLogger
            logger = WandbLogger(project="resumeagent-fit-predictor", name=args.run_name)
        else:
            from pytorch_lightning.loggers import CSVLogger
            logger = CSVLogger("lightning_logs")
        logger.log_hyperparams(config)  # config shows up alongside the metrics

    # Early-stop on val AUC + keep the best checkpoint, so we export the peak
    # weights rather than overfit last-epoch ones. Set --epochs high; ES cuts it.
    callbacks = []
    if not args.smoke:
        from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
        ckpt = ModelCheckpoint(monitor="val_auc", mode="max", save_top_k=1)
        callbacks = [ckpt, EarlyStopping(monitor="val_auc", mode="max", patience=args.patience)]

    trainer = pl.Trainer(
        max_epochs=1 if args.smoke else args.epochs,
        fast_dev_run=args.smoke,
        logger=logger,
        accelerator="auto",
        callbacks=callbacks,
    )
    trainer.fit(module, train_loader, test_loader)
    if not args.smoke:
        best = callbacks[0].best_model_path
        if best:
            log.info("Restoring best-val_auc checkpoint: %s", best)
            import torch
            module.load_state_dict(torch.load(best, weights_only=False)["state_dict"])
        trainer.validate(module, test_loader)

    out_dir = Path(args.output_dir)
    if not args.smoke and args.arch == "biencoder":
        try:
            _write_calibration(module, test_loader, out_dir)
        except Exception as e:
            log.warning("calibration.json generation failed (export continues): %s", e)
    _export_onnx(module, tokenizer, out_dir, args.arch)

    # Version the exported model in W&B (model registry / portfolio). Best-effort.
    if use_wandb:
        try:
            import wandb
            art = wandb.Artifact("fit-predictor", type="model", metadata=config)
            art.add_dir(str(out_dir))
            logger.experiment.log_artifact(art)
            log.info("Logged model artifact to W&B")
        except Exception as e:
            log.warning("W&B artifact log failed: %s", e)

    if args.push and args.hf_repo:
        from huggingface_hub import HfApi
        api = HfApi(token=os.environ.get("HF_TOKEN"))
        api.create_repo(args.hf_repo, private=True, exist_ok=True)
        api.upload_folder(folder_path=str(out_dir), repo_id=args.hf_repo)
        log.info("Pushed artifact to HF Hub: %s", args.hf_repo)

    if use_wandb:
        import wandb
        wandb.finish()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
