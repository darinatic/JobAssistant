# syntax=docker/dockerfile:1

# ---------- 1. build the React SPA ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /app/frontend/dist

# ---------- 2. backend (FastAPI + Tectonic + Chromium) ----------
# Trixie (Debian 13, glibc 2.41), NOT bookworm (glibc 2.36): the prebuilt Tectonic
# binary from drop-sh links against glibc >= 2.39, so on bookworm it fails to start
# ("GLIBC_2.39 not found") and every PDF render 500s. Match the OS to the binary.
FROM python:3.12-slim-trixie
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080
WORKDIR /app

# curl (for the tectonic installer) + tectonic's runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates \
      fontconfig libfontconfig1 libssl3 libharfbuzz0b libgraphite2-3 libicu76 \
    && rm -rf /var/lib/apt/lists/*

# Tectonic (LaTeX -> PDF) via the official installer, onto PATH
RUN curl --proto '=https' --tlsv1.2 -fsSL https://drop-sh.fullyjustified.net | sh \
    && mv tectonic /usr/local/bin/tectonic

# Python deps (this also installs the `src` package's requirements).
# `[predictor]` adds onnxruntime + tokenizers for the learned resume<->JD fit model.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install ".[predictor]"

# Patchright Chromium + its OS deps — the in-container fallback for the JobStreet
# scraper (production normally routes it through Browserbase via BROWSERBASE_SCRAPERS).
RUN patchright install-deps chromium && patchright install chromium

# Warm the Tectonic TeX bundle so the first PDF render isn't a cold download.
# NO `|| true`: this doubles as a smoke test — if the binary can't run (e.g. a glibc
# mismatch) or can't fetch the bundle, the BUILD fails here instead of shipping an
# image that 500s on every PDF render.
RUN printf '\\documentclass{article}\\begin{document}warmup\\end{document}' > /tmp/w.tex \
    && tectonic -X compile /tmp/w.tex --outdir /tmp

# The built SPA — FastAPI serves it from the same origin (see api.py static mount).
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8080
# cwd /app is on sys.path so `src` + `frontend/dist` resolve relative to it.
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
