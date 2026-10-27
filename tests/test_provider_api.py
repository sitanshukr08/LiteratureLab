from fastapi.testclient import TestClient

from literaturelab.api import create_app
from literaturelab.core import Corpus
from test_core import FakeEmbedder, pdf_bytes


def test_provider_status_is_public_metadata_only(tmp_path, monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'AQ.test-token-never-expose')
    monkeypatch.setenv('GROQ_API_KEY', 'gsk_never_expose')
    app = create_app(Corpus(tmp_path, FakeEmbedder()))
    client = TestClient(app, base_url='http://localhost')
    status = client.get('/api/status')
    assert status.status_code == 200
    assert {p['name'] for p in status.json()['providers']} == {'gemini', 'groq'}
    assert 'AQ.test-token-never-expose' not in status.text and 'gsk_never_expose' not in status.text


def test_provider_selection_reaches_engine_and_rejects_arbitrary_values(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'paper.pdf')
    app = create_app(corpus)
    calls = []
    def ask(*args, **kwargs):
        calls.append((args, kwargs))
        return {'provider': kwargs['provider']}
    app.state.engine.ask = ask
    client = TestClient(app, base_url='http://localhost')
    result = client.post('/api/ask', json={'question': 'whats this about', 'provider': 'gemini'})
    assert result.status_code == 200 and result.json()['provider'] == 'gemini'
    assert client.post('/api/ask', json={'question': 'hello', 'provider': 'https://evil.example'}).status_code == 422
    assert len(calls) == 1


def test_omitted_provider_preserves_configured_default(tmp_path):
    app = create_app(Corpus(tmp_path, FakeEmbedder()))
    captured = []
    def ask(*args, **kwargs):
        captured.append(kwargs['provider'])
        return {'ok': True}
    app.state.engine.ask = ask
    client = TestClient(app, base_url='http://localhost')
    assert client.post('/api/ask', json={'question': 'explain the method'}).status_code == 200
    assert captured == [None]
