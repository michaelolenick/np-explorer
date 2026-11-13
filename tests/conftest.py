"""Shared test setup. No test ever reaches a real language model: the fallback list is empty here unless a test
sets LLM_FALLBACK_MODELS itself (tests/test_llm_fallback.py does, with httpx.post replaced)."""
import os

import pytest


@pytest.fixture(autouse=True)
def _no_real_fallback_models(monkeypatch):
    if "LLM_FALLBACK_MODELS" not in os.environ:
        monkeypatch.setenv("LLM_FALLBACK_MODELS", "")
