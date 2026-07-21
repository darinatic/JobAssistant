"""Shared pytest fixtures for the stateless app."""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv(Path(__file__).parent.parent / ".env")
# Keep module imports happy even when tests patch the LLM rather than call it.
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")


@pytest.fixture
def client() -> TestClient:
    from src.api import app

    return TestClient(app)
