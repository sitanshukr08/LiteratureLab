from types import SimpleNamespace
import pytest
from literaturelab.synthesis import validate_claims, Synthesis, ProviderError, expand_references
from literaturelab.core import Corpus
from test_core import FakeEmbedder, pdf_bytes


EVIDENCE = [{'citation_id':'E1', 'id':'paper:p:1', 'paper_id':'paper', 'title':'Study', 'section':'Results',
             'pages':[3], 'text':'The experiment achieved 82.6 percent accuracy on the benchmark.'}]


def claim(quote='82.6 percent accuracy', evidence='E1'):
    return {'text':'The study reports 82.6 percent accuracy.', 'evidence':[{'id':evidence,'quote':quote}]}


def test_invalid_identifiers_or_quotes_are_blocked():
    accepted, rejected = validate_claims([claim(), claim(evidence='E2'), claim(quote='1.5 ms laptop latency')], EVIDENCE)
    assert len(accepted) == 1 and len(rejected) == 2
    assert accepted[0]['evidence'][0]['pages'] == [3]


def test_empty_evidence_claim_and_oversized_quotes_blocked():
    accepted, rejected = validate_claims([{'text':'Claim','evidence':[]}, claim(quote='x')], EVIDENCE)
    assert not accepted and len(rejected) == 2


def test_reported_findings_and_inferences_remain_distinct():
    accepted, _ = validate_claims([dict(claim(),kind='inference'),dict(claim(),kind='reported')], EVIDENCE)
    assert [c['kind'] for c in accepted] == ['inference','reported']


def test_section_citation_locates_page_containing_quote():
    source = dict(EVIDENCE[0], pages=[2,3], spans=[{'text':'The introduction explains the method.', 'pages':[2]},
                  {'text':EVIDENCE[0]['text'],'pages':[3]}])
    accepted, _ = validate_claims([claim()], [source])
    assert accepted[0]['evidence'][0]['pages'] == [3]


def test_span_ids_copy_original_and_reject_unknown_spans():
    claims = [{'text':'A result', 'evidence':[{'id':'E1','span':0}]},
              {'text':'Invented result', 'evidence':[{'id':'E1','span':99}]}]
    expanded = expand_references(claims, EVIDENCE)
    assert expanded[0]['evidence'][0]['quote'] == EVIDENCE[0]['text']
    accepted, rejected = validate_claims(expanded, EVIDENCE)
    assert len(accepted) == 1 and len(rejected) == 1


def test_numerical_claim_requires_source_numbers_or_supported_subtraction():
    source = dict(EVIDENCE[0], text='The new accuracy is 82.6 percent, compared with the previous 62.3 percent.')
    refs = [{'id':'E1','quote':source['text']}]
    accepted, rejected = validate_claims([
        {'kind':'inference','text':'The gain is 20.3 percentage points.', 'evidence':refs},
        {'text':'The experiment has 100 ms latency.', 'evidence':refs}], [source])
    assert len(accepted) == 1 and len(rejected) == 1


def test_uncertain_source_does_not_support_positive_latency_claim():
    source = dict(EVIDENCE[0], text='It is not completely clear how much more time it takes for inference.')
    refs = [{'id':'E1','quote':source['text']}]
    accepted, rejected = validate_claims([{'text':'Its latency remains comparable to the baseline.', 'evidence':refs}], [source])
    assert not accepted and rejected


def test_numeric_threshold_and_metric_cannot_be_invented():
    source = dict(EVIDENCE[0], text='The 13B and 70B models display a U-shaped curve. The system achieved higher QA accuracy.')
    refs = [{'id':'E1','quote':source['text']}]
    accepted, rejected = validate_claims([
        {'text':'All models ≥13B have this curve.', 'evidence':refs},
        {'text':'The system achieved higher retrieval performance.', 'evidence':refs}], [source])
    assert not accepted and len(rejected) == 2


def test_verifier_rejection_is_not_displayed_as_supported(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'test.pdf')
    engine = Synthesis(corpus)
    calls = []
    def provider(messages, schema):
        calls.append(messages)
        if len(calls) == 1:
            quote = engine.corpus.search('tree', [paper['id']])['evidence'][0]['text'].split('.')[0]
            return {'claims':[{'text':'This has lower retrieval latency.', 'evidence':[{'id':'E1','quote':quote}]}],
                    'insufficient_evidence':False,'limitations':[]}, {'total_tokens':50}
        return {'checks':[{'index':0,'supported':False,'reason':'No measured latency in evidence.'}]}, {'total_tokens':20}
    engine.provider = SimpleNamespace(name='fake',model='fake-v1',complete=provider)
    result = engine.ask('tree', [paper['id']])
    assert not result['claims'] and result['insufficient_evidence']
    assert result['rejected_claims'] and len(calls) == 2
    cached = engine.ask('tree', [paper['id']])
    assert cached['cached'] and len(calls) == 2


def test_provider_failure_does_not_create_fake_answer(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'test.pdf')
    engine = Synthesis(corpus)
    def fail(*args): raise ProviderError('Free-tier quota exhausted; retry later.', 429)
    engine.provider = SimpleNamespace(name='fake',model='fake-v1',complete=fail)
    with pytest.raises(ProviderError): engine.ask('What is the method?')
