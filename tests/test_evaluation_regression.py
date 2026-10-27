import json
from types import SimpleNamespace

from literaturelab.core import Corpus
from literaturelab.synthesis import ProviderError
from scripts import evaluate
from test_core import FakeEmbedder, pdf_bytes


def test_legacy_evaluator_records_provider_failures_without_crashing(tmp_path, monkeypatch):
    corpus = Corpus(tmp_path / 'data', FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'paper.pdf', aliases=['paper'])
    cases = [{'id': key, 'question': 'explain tree retrieval', 'gold_papers': ['paper']}
             for key in ['q02', 'q06', 'q08', 'q12', 'q13', 'q15', 'q17', 'q18']]
    (tmp_path / 'demo').mkdir()
    (tmp_path / 'demo/questions.json').write_text(json.dumps(cases), encoding='utf-8')
    def fail(*args, **kwargs):
        raise ProviderError('Provider unavailable.', 503)
    engine = SimpleNamespace(ask=fail, last_attempts=[{'provider': 'gemini', 'status': 503}])
    monkeypatch.setattr(evaluate, 'ROOT', tmp_path)
    monkeypatch.setattr(evaluate, 'Corpus', lambda _: corpus)
    monkeypatch.setattr(evaluate, 'Synthesis', lambda _: engine)
    monkeypatch.setattr(evaluate.time, 'sleep', lambda _: None)
    monkeypatch.setattr('sys.argv', ['evaluate.py', '--live'])
    evaluate.main()
    result = json.loads((tmp_path / 'reports/evaluation.json').read_text(encoding='utf-8'))
    assert len(result['live_cases']) == 8
    assert all(row['provider_attempts'] == engine.last_attempts for row in result['live_cases'])
