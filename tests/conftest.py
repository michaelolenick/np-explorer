"""Shared test setup. No test ever reaches a real language model: the fallback list is empty here unless a test
sets LLM_FALLBACK_MODELS itself (tests/test_llm_fallback.py does, with httpx.post replaced)."""
import os

import pytest


@pytest.fixture(autouse=True)
def _no_real_fallback_models(monkeypatch):
    if "LLM_FALLBACK_MODELS" not in os.environ:
        monkeypatch.setenv("LLM_FALLBACK_MODELS", "")
    if "LLM_VIA" in os.environ:                       # the .env on a server sets it; tests choose their own
        monkeypatch.delenv("LLM_VIA")


@pytest.fixture
def openrouter_approved(monkeypatch, tmp_path):
    """The owner's yes for OpenRouter (app/openrouter_gate.py) in a temp dir, for tests that stub httpx.post."""
    (tmp_path / "openrouter_ok.txt").write_text("until 2999-01-01")
    monkeypatch.setenv("OPENROUTER_APPROVAL_DIR", str(tmp_path))
