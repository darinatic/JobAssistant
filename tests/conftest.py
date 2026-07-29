"""Shared pytest fixtures for the stateless app."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).parent.parent / ".env")
# Keep module imports happy even when tests patch the LLM rather than call it.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
# Disable the per-IP rate limiter for the shared app fixture: the TestClient reuses
# one IP, so cumulative guarded-endpoint calls across tests would otherwise trip the
# per-minute cap (429). test_rate_limit.py builds its own app, so it's unaffected.
os.environ["RATE_LIMIT_PER_MIN"] = "0"
os.environ["RATE_LIMIT_PER_DAY"] = "0"


@pytest.fixture
def client() -> TestClient:
    from src.api import app

    return TestClient(app)
