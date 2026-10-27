import pytest
from literaturelab import core
from test_core import FakeEmbedder, pdf_bytes


@pytest.mark.parametrize('formal,casual', [
    ("What is this paper about?", "  WHATS this   paper about  "),
    ("Can you explain the retrieval method?", "can u explain the retrival method??"),
    ("What are its limitations?", "what’re its limitations"),
])
def test_normal_question_forms_have_equivalent_search_interpretations(formal, casual):
    assert core.normalize_question(formal) == core.normalize_question(casual)


@pytest.mark.parametrize('question', [
    'whats this paper about',
    'can u explain this paper in simple words',
    'how is the tree method different from normal retrieval',
    'what are the good and bad parts of this approach',
    'give me the big picture',
    'what are its weaknesses',
])
def test_casual_overview_and_comparison_questions_use_broad_evidence(tmp_path, question):
    corpus = core.Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'tree.pdf')
    result = corpus.search(question, [paper['id']])
    assert result['trace']['resolution'] == 'section'
    assert result['trace']['interpreted_query'] == core.normalize_question(question)
    assert result['trace']['routing_reason']


def test_punctuation_and_shorthand_do_not_change_retrieved_source_text(tmp_path):
    corpus = core.Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'tree.pdf')
    formal = corpus.search('Can you explain the retrieval method?', [paper['id']], 'hybrid')
    casual = corpus.search('can u explain the retrival method??', [paper['id']], 'hybrid')
    assert [n['id'] for n in formal['evidence']] == [n['id'] for n in casual['evidence']]
    assert [n['text'] for n in formal['evidence']] == [n['text'] for n in casual['evidence']]


def test_question_normalization_preserves_technical_identifiers_and_numeric_signs():
    question = 'does GPT-OSS-120B beat BGE-small-en-v1.5 at -0.5 with 1e-5 and >=13B'
    interpreted = core.normalize_question(question)
    for token in ['gpt-oss-120b','bge-small-en-v1.5','-0.5','1e-5','>=13b']:
        assert token in interpreted
    assert core.normalize_question("it doesn’t prove a speed gain") == 'it does not prove a speed gain'
    assert 'retrieval' in core.normalize_question('what does retrival do')
    assert 'hallucination' in core.normalize_question('what causes halluciantion')
    assert 'unrecognisedtechnicalterm' in core.normalize_question('unrecognisedtechnicalterm')


def test_casual_words_do_not_dominate_keyword_channel(tmp_path):
    corpus = core.Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'tree.pdf')
    result = corpus.search('hey please could u tell me about the retrieval method', [paper['id']], 'hybrid')
    assert result['evidence']
    assert result['trace']['query_terms'] == ['retrieval','method']


@pytest.mark.parametrize('question', ['  ', '???', 'a' * 1201])
def test_empty_or_unbounded_question_rejected_at_retrieval_boundary(tmp_path, question):
    corpus = core.Corpus(tmp_path, FakeEmbedder())
    corpus.ingest(pdf_bytes(), 'tree.pdf')
    with pytest.raises(core.InputError):
        corpus.search(question)
def test_overview_prioritizes_original_abstract_over_appendix_instructions(tmp_path):
    from test_core import pdf_bytes, FakeEmbedder
    from literaturelab.core import Corpus
    import json
    corpus = Corpus(tmp_path, FakeEmbedder())
    paper = corpus.ingest(pdf_bytes(), 'overview.pdf')
    with corpus.db() as db:
        row = db.execute("SELECT id,metadata FROM nodes WHERE paper_id=? AND json_extract(metadata,'$.level')='section' LIMIT 1", (paper['id'],)).fetchone()
        node = json.loads(row[1]);node['section'] = 'ABSTRACT';node['text'] = 'The abstract describes the research problem and the method used to evaluate source grounded answers.'
        db.execute('UPDATE nodes SET metadata=? WHERE id=?', (json.dumps(node), row[0]))
    out = corpus.search('whats this paper about explain it like im new to this', [paper['id']])
    assert out['evidence'][0]['section'] == 'ABSTRACT'
    assert out['trace']['structural_prior'] == 'overview'

