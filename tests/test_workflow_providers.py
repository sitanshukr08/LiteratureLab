import json

import pytest

from literaturelab.core import Corpus
from literaturelab.providers import ProviderError, ProviderRouter
from literaturelab.synthesis import Synthesis
from test_core import FakeEmbedder, pdf_bytes


class FakeProvider:
    def __init__(self, name, *, fail_stage=None, fallback_allowed=False, status=429):
        self.name = name
        self.model = name + '-test-model'
        self.key = 'offline_test_key_12345'
        self.calls = []
        self.fail_stage = fail_stage
        self.fallback_allowed = fallback_allowed
        self.status = status

    def complete(self, messages, schema):
        self.calls.append(schema.__name__)
        if schema.__name__ == self.fail_stage:
            raise ProviderError('Simulated provider failure.', self.status, fallback_allowed=self.fallback_allowed)
        if schema.__name__ == 'Draft':
            source = json.loads(messages[-1]['content'])['sources'][0]
            return {'claims': [{'kind': 'reported', 'text': source['spans'][0]['text'],
                                'evidence': [{'id': source['id'], 'span': 0}]}],
                    'insufficient_evidence': False, 'limitations': []}, {'total_tokens': 30}
        claims = json.loads(messages[-1]['content'])['claims']
        return {'checks': [{'index': c['index'], 'supported': True, 'classification': 'reported',
                            'reason': 'Direct statement in cited source.'} for c in claims]}, {'total_tokens': 10}


@pytest.fixture
def workflow(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'tree.pdf')
    engine = Synthesis(corpus)
    router = ProviderRouter()
    router.preference = 'auto'
    router.providers = {'gemini': FakeProvider('gemini'), 'groq': FakeProvider('groq')}
    engine.provider = router
    return engine, corpus, paper['id']


def stored_counts(corpus):
    with corpus.db() as db:
        return [db.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0] for name in ('history', 'cache')]


def test_review_quota_failure_restarts_generation_and_review_with_fallback(workflow):
    engine, corpus, paper_id = workflow
    primary = engine.provider.providers['gemini']
    primary.fail_stage, primary.fallback_allowed = 'Review', True
    secondary = engine.provider.providers['groq']
    result = engine.ask('how does tree retrieval work', [paper_id], provider='auto')
    assert primary.calls == ['Draft', 'Review']
    assert secondary.calls == ['Draft', 'Review']
    assert result['provider'] == 'groq' and result['model'] == secondary.model
    assert [a['outcome'] for a in result['provider_attempts']] == ['failed', 'completed']
    assert result['claims'] and all(c['support_status'] == 'cited-span-reviewed' for c in result['claims'])
    assert stored_counts(corpus) == [1, 1]
    with corpus.db() as db:
        saved = json.loads(db.execute('SELECT result FROM history').fetchone()[0])
    assert saved['provider'] == 'groq' and saved['model'] == secondary.model


@pytest.mark.parametrize('stage,status', [('Draft', 422), ('Review', 422), ('Draft', 502), ('Review', 502)])
def test_blocked_or_invalid_response_never_tries_another_provider(workflow, stage, status):
    engine, corpus, paper_id = workflow
    primary = engine.provider.providers['gemini']
    primary.fail_stage, primary.status, primary.fallback_allowed = stage, status, False
    with pytest.raises(ProviderError):
        engine.ask('explain the tree thing', [paper_id], provider='auto')
    assert engine.provider.providers['groq'].calls == []
    assert stored_counts(corpus) == [0, 0]


def test_auto_and_manual_provider_cache_are_isolated_with_actual_models(workflow):
    engine, corpus, paper_id = workflow
    primary, secondary = engine.provider.providers.values()
    primary.fail_stage, primary.fallback_allowed = 'Draft', True
    question = 'how does tree retrieval work'
    fallback = engine.ask(question, [paper_id], provider='auto')
    assert fallback['provider'] == 'groq' and not fallback['cached']
    primary.fail_stage = None
    explicit = engine.ask(question, [paper_id], provider='gemini')
    assert explicit['provider'] == 'gemini' and not explicit['cached']
    manual_other = engine.ask(question, [paper_id], provider='groq')
    assert manual_other['provider'] == 'groq' and not manual_other['cached']
    before = [len(primary.calls), len(secondary.calls)]
    cached = engine.ask(question, [paper_id], provider='auto')
    assert cached['cached'] and cached['provider'] == 'groq' and cached['model'] == secondary.model
    assert cached['provider_preference'] == 'auto'
    assert [len(primary.calls), len(secondary.calls)] == before
    assert stored_counts(corpus) == [3, 3]


def test_all_provider_failures_leave_history_and_cache_empty(workflow):
    engine, corpus, paper_id = workflow
    for provider in engine.provider.providers.values():
        provider.fail_stage, provider.fallback_allowed = 'Draft', True
    with pytest.raises(ProviderError):
        engine.ask('what does the method do', [paper_id], provider='auto')
    assert [p.calls for p in engine.provider.providers.values()] == [['Draft'], ['Draft']]
    assert stored_counts(corpus) == [0, 0]


def test_manual_provider_failure_does_not_fallback_even_when_auto_would(workflow):
    engine, corpus, paper_id = workflow
    primary = engine.provider.providers['gemini']
    primary.fail_stage, primary.fallback_allowed = 'Review', True
    with pytest.raises(ProviderError):
        engine.ask('what does the method do', [paper_id], provider='gemini')
    assert engine.provider.providers['groq'].calls == []
    assert stored_counts(corpus) == [0, 0]


def test_review_cannot_relabel_derived_number_as_directly_reported(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    source = 'The new accuracy is 82.6 percent, compared with the previous 62.3 percent. '
    paper = corpus.ingest(pdf_bytes(body=source * 8), 'accuracy.pdf')
    engine = Synthesis(corpus)
    provider = FakeProvider('fake')
    def complete(messages, schema):
        if schema.__name__ == 'Draft':
            first = json.loads(messages[-1]['content'])['sources'][0]
            return {'claims': [{'kind': 'inference', 'text': 'The gain is 20.3 percentage points.',
                                'evidence': [{'id': first['id'], 'span': 0}]}],
                    'insufficient_evidence': False, 'limitations': []}, {}
        return {'checks': [{'index': 0, 'supported': True, 'classification': 'reported',
                            'reason': 'Claim supported.'}]}, {}
    provider.complete = complete
    engine.provider = provider
    result = engine.ask('whats the accuracy gain', [paper['id']])
    assert not any(c['kind'] == 'reported' and '20.3' in c['text'] for c in result['claims'])
