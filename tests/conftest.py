"""Offline tests must never spend quota or send documents to a real provider."""
import pytest


@pytest.fixture(autouse=True)
def forbid_live_inference(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Live provider transport is forbidden in the offline test suite.')
    monkeypatch.setattr('literaturelab.providers.subprocess.run', blocked)
