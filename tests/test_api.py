from fastapi.testclient import TestClient
from literaturelab.api import create_app
from literaturelab.core import Corpus
from test_core import FakeEmbedder, pdf_bytes


def client(tmp_path):
    return TestClient(create_app(Corpus(tmp_path, FakeEmbedder())), base_url='http://localhost')


def test_upload_search_pdf_history_and_errors(tmp_path):
    c = client(tmp_path)
    assert c.get('/api/papers').json() == []
    raw = pdf_bytes()
    out = c.post('/api/papers', files={'file':('paper.pdf',raw,'application/pdf')})
    assert out.status_code == 200
    pid = out.json()['id']
    assert c.post('/api/papers', files={'file':('copy.pdf',raw,'application/pdf')}).json()['duplicate']
    search = c.post('/api/search', json={'question':'tree retrieval', 'strategy':'hybrid','paper_ids':[pid]})
    assert search.status_code == 200 and search.json()['evidence']
    assert c.get(f'/api/papers/{pid}/pdf').content.startswith(b'%PDF')
    assert c.get('/api/history').json() == []
    assert c.post('/api/search',json={'question':'','strategy':'fake'}).status_code == 422
    assert c.post('/api/papers', files={'file':('bad.pdf',b'not PDF')}).status_code == 400
    assert c.delete(f'/api/papers/{pid}').status_code == 200
    assert c.get(f'/api/papers/{pid}/pdf').status_code == 404


def test_secrets_not_served_and_cross_origin_mutation_blocked(tmp_path):
    c = client(tmp_path)
    for path in ['/.env','/literaturelab/synthesis.py','/data/library.sqlite3','/api/papers/../.env/pdf']:
        assert c.get(path).status_code == 404
    assert c.post('/api/search',json={'question':'test'},headers={'Origin':'https://evil.example'}).status_code == 403
    assert c.get('/api/status',headers={'Host':'evil.example'}).status_code == 400
    assert c.get('/').headers['x-content-type-options'] == 'nosniff'


def test_streaming_upload_requires_bounded_content_length(tmp_path):
    c = client(tmp_path)
    response = c.post('/api/papers', content=iter([b'unbounded upload']), headers={'Transfer-Encoding':'chunked'})
    assert response.status_code == 411
