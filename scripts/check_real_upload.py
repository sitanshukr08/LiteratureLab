"""Exercise real PDF upload and real CPU embeddings through the API, in an isolated test library."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from literaturelab.api import create_app
from literaturelab.core import Corpus, Embedder

ROOT = Path(__file__).resolve().parents[1]


def main():
    location = ROOT / 'data' / ('upload-check-' + uuid.uuid4().hex[:8])
    corpus = Corpus(location, Embedder(ROOT / 'models/bge'))
    client = TestClient(create_app(corpus), base_url='http://localhost')
    raw = (ROOT / 'demo/papers/rag.pdf').read_bytes()
    started = time.perf_counter()
    response = client.post('/api/papers',files={'file':('real-rag.pdf',raw,'application/pdf')})
    assert response.status_code == 200, response.text
    paper_id = response.json()['id']
    upload_seconds = time.perf_counter() - started
    duplicate = client.post('/api/papers',files={'file':('same-paper.pdf',raw,'application/pdf')})
    assert duplicate.status_code == 200 and duplicate.json()['duplicate']
    search = client.post('/api/search',json={'question':'How do RAG-Sequence and RAG-Token differ?', 'paper_ids':[paper_id], 'strategy':'hybrid'})
    assert search.status_code == 200 and search.json()['evidence']
    served_pdf = client.get(f'/api/papers/{paper_id}/pdf')
    assert served_pdf.status_code == 200 and hashlib.sha256(served_pdf.content).digest() == hashlib.sha256(raw).digest()
    restored = Corpus(location, Embedder(ROOT / 'models/bge'))
    assert restored.papers()[0]['id'] == paper_id
    result = {'created':datetime.now(timezone.utc).isoformat(), 'passed':True,
              'scope':'One real version-pinned RAG PDF uploaded through FastAPI with real CPU BGE embeddings in an isolated library. No Groq calls.',
              'checks':['upload/index','duplicate','hybrid query','exact PDF bytes','persistent reopen'],
              'upload_seconds':round(upload_seconds,3),'paragraphs':response.json()['paragraphs'],
              'search_trace':search.json()['trace']}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/real-upload-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)


if __name__ == '__main__':
    main()
