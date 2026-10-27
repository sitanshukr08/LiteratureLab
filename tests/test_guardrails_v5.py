import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from literaturelab.core import Corpus, InputError
from literaturelab.synthesis import Reference, Review, Synthesis, validate_claims
from test_core import FakeEmbedder, pdf_bytes


def evidence(text, **extra):
    return dict(citation_id='E1', id='p:1', paper_id='p', title='Study',
                section='Results', pages=[3], text=text, **extra)


def claim(text, quote, kind='reported'):
    return dict(text=text, kind=kind, evidence=[{'id': 'E1', 'quote': quote}])


def test_reference_indexes_and_review_booleans_are_strict():
    with pytest.raises(ValidationError):
        Reference(id='E1', span=True)
    with pytest.raises(ValidationError):
        Reference(id='E1', span=-1)
    with pytest.raises(ValidationError):
        Review(checks=[{'index': 0, 'supported': 'false', 'classification': 'reported', 'reason': 'No.'}])


def test_negative_number_cannot_be_turned_positive():
    quote = 'The measured change was -4.2 percentage points.'
    accepted, rejected = validate_claims([claim('The change was 4.2 percentage points.', quote)], [evidence(quote)])
    assert not accepted and rejected


def test_decimal_without_leading_zero_is_still_checked():
    quote = 'The measured fraction is 0.5 in this experiment.'
    accepted, rejected = validate_claims([claim('The measured fraction is .5.', quote),
                                          claim('The measured fraction is .8.', quote)], [evidence(quote)])
    assert len(accepted) == 1 and len(rejected) == 1


def test_this_paper_requires_selection_when_library_is_ambiguous(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes('First Paper'), 'one.pdf')
    corpus.ingest(pdf_bytes('Second Paper'), 'two.pdf')
    engine = Synthesis(corpus)
    with pytest.raises(InputError, match='Select'):
        engine.ask('whats this paper about')


def test_arithmetic_must_be_labeled_as_interpretation():
    quote = 'Accuracy increased from 62.3 percent to 82.6 percent.'
    text = 'The gain is 20.3 percentage points.'
    accepted, rejected = validate_claims([claim(text, quote), claim(text, quote, 'inference')], [evidence(quote)])
    assert len(accepted) == 1 and accepted[0]['kind'] == 'inference' and len(rejected) == 1


def test_inconsistent_page_provenance_is_rejected_instead_of_using_all_pages():
    quote = 'The study reports an improvement on its test collection.'
    source = evidence(quote, spans=[{'text': 'Unrelated source text.', 'pages': [2]}])
    accepted, rejected = validate_claims([claim('The study reports an improvement.', quote)], [source])
    assert not accepted and rejected


def test_quote_across_original_blocks_resolves_only_its_actual_pages():
    first = 'The retrieval method selects original passages'
    second = 'and preserves their page numbers for source inspection.'
    quote = first + ' ' + second
    source = evidence(quote, spans=[{'text': first, 'pages': [2]}, {'text': second, 'pages': [3]},
                                   {'text': 'Unrelated later discussion.', 'pages': [4]}])
    accepted, _ = validate_claims([claim('Original passages retain their page numbers.', quote)], [source])
    assert accepted[0]['evidence'][0]['pages'] == [2, 3]


def test_reviewer_sees_cited_spans_only_and_no_unverified_limitations_escape(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'test.pdf')
    source = evidence('The study reports 82.6 percent accuracy. It also discusses unrelated deployment advice.')
    corpus.search = lambda *args: {'evidence': [source], 'trace': {'missing_papers': []}}
    requests = []
    def complete(messages, schema):
        requests.append(messages)
        if schema.__name__ == 'Draft':
            packed = json.loads(messages[1]['content'])
            assert packed['sources'][0]['spans'][0] == {'span': 0, 'text': 'The study reports 82.6 percent accuracy.'}
            return {'claims': [{'kind': 'reported', 'text': 'The reported accuracy is 82.6 percent.',
                                'evidence': [{'id': 'E1', 'span': 0}]}],
                    'insufficient_evidence': False, 'limitations': ['It cures every disease.']}, {}
        payload = json.loads(messages[1]['content'])
        assert 'unrelated deployment advice' not in json.dumps(payload)
        return {'checks': [{'index': 0, 'supported': True, 'classification': 'reported', 'reason': 'Direct evidence.'}]}, {}
    engine = Synthesis(corpus)
    engine.provider = SimpleNamespace(name='fake', model='fake-v1', complete=complete)
    result = engine.ask('whats the accuracy')
    assert len(result['claims']) == 1 and len(requests) == 2
    assert 'cures every disease' not in json.dumps(result)


def test_claim_with_uncited_second_sentence_is_withheld(tmp_path):
    corpus = Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'test.pdf')
    quote = 'The study reports 82.6 percent accuracy.'
    source = evidence(quote)
    corpus.search = lambda *args: {'evidence': [source], 'trace': {'missing_papers': []}}
    def complete(messages, schema):
        if schema.__name__ == 'Draft':
            return {'claims': [{'kind': 'reported', 'text': 'Accuracy is 82.6 percent. This also proves deployment is safe.',
                                'evidence': [{'id': 'E1', 'span': 0}]}], 'insufficient_evidence': False, 'limitations': []}, {}
        return {'checks': [{'index': 0, 'supported': False, 'classification': 'unsupported',
                            'reason': 'Safety claim is absent from the cited passage.'}]}, {}
    engine = Synthesis(corpus)
    engine.provider = SimpleNamespace(name='fake', model='fake-v1', complete=complete)
    result = engine.ask('is it accurate and safe')
    assert not result['claims'] and result['rejected_claims'] and result['insufficient_evidence']
