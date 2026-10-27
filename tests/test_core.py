import hashlib
import numpy as np
import pymupdf
import pytest
from literaturelab.core import Corpus, InputError, rrf


class FakeEmbedder:
    def encode(self, texts, query=False):
        result = []
        for text in texts:
            row = np.zeros(16, dtype=np.float32)
            for word in text.lower().split():
                row[int(hashlib.sha256(word.encode()).hexdigest()[:4], 16) % 16] += 1
            result.append(row / max(np.linalg.norm(row), 1e-8))
        return np.array(result)


def pdf_bytes(title='Tree Retrieval', body=None):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), title, fontsize=20)
    page.insert_text((50, 90), '1 Introduction', fontsize=15)
    text = body or ('Recursive retrieval builds a tree from original passages and section evidence. '
                    'This experiment measures question answering accuracy, not retrieval latency. ')*5
    page.insert_textbox((50, 110, 540, 650), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def corpus(tmp_path):
    return Corpus(tmp_path, FakeEmbedder())


def test_rejects_invalid_or_scanned_pdf(corpus):
    with pytest.raises(InputError): corpus.ingest(b'not a pdf', '../../.env')
    doc = pymupdf.open(); doc.new_page()
    with pytest.raises(InputError): corpus.ingest(doc.tobytes(), 'scan.pdf')
    assert corpus.papers() == []


def test_hierarchy_duplicate_and_persistence(corpus):
    raw = pdf_bytes()
    paper = corpus.ingest(raw, '../../tree.pdf')
    assert '/' not in paper['filename'] and '\\' not in paper['filename']
    assert corpus.ingest(raw, 'copy.pdf')['duplicate']
    assert len(corpus.papers()) == 1
    assert {'paragraph', 'section'} <= {n['level'] for n in corpus.nodes()}
    assert all(n['pages'] == [1] and n['section'] for n in corpus.nodes())
    again = Corpus(corpus.root, FakeEmbedder())
    assert len(again.papers()) == 1


def test_paper_filter_budget_and_no_empty_search(corpus):
    one = corpus.ingest(pdf_bytes(), 'one.pdf')
    two = corpus.ingest(pdf_bytes('Another Paper', 'Distinct unrelated banana fruit agriculture experiment. '*20), 'two.pdf')
    result = corpus.search('Compare the methods and limitations', [one['id']], 'adaptive')
    assert result['evidence']
    assert all(n['paper_id'] == one['id'] for n in result['evidence'])
    assert result['trace']['evidence_words'] <= 1600
    assert result['trace']['resolution'] == 'section'
    with pytest.raises(InputError): corpus.search('query', ['missing'], 'hybrid')
    corpus.delete(two['id'])
    assert len(corpus.papers()) == 1


def test_rrf_retains_both_channels():
    fused = rrf([[1, 2], [3, 2]])
    assert fused[0] == 2 and set(fused) == {1, 2, 3}


def test_comparison_covers_selected_papers(corpus):
    a = corpus.ingest(pdf_bytes(), 'a.pdf')
    b = corpus.ingest(pdf_bytes('Different Study'), 'b.pdf')
    out = corpus.search('Compare these two methods', [a['id'], b['id']], 'adaptive')
    assert set(out['trace']['covered_papers']) == {a['id'], b['id']}


def test_algorithm_steps_are_evidence_not_section_headings(corpus):
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_text((50, 50), 'Retrieval Experiment', fontsize=20)
    page.insert_text((50, 90), '1 Introduction', fontsize=15)
    page.insert_textbox((50, 110, 540, 210), 'The research method evaluates retrieval with original passages and source provenance. '*8, fontsize=11)
    step = '1. Retrieve the most relevant passages using the query embedding and concatenate their original text.'
    page.insert_text((50, 245), step, fontsize=11)
    page.insert_textbox((50, 275, 540, 450), 'The experimental procedure retains page information so readers can inspect evidence. '*8, fontsize=11)
    corpus.ingest(doc.tobytes(), 'method.pdf'); doc.close()
    paragraphs = [n for n in corpus.nodes() if n['level'] == 'paragraph']
    assert any(step in n['text'] for n in paragraphs)
    assert all(n['section'] == '1 Introduction' for n in paragraphs)


def test_numbered_small_capital_subheading_at_body_font_is_preserved(corpus):
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_text((50, 50), 'Retrieval Experiment', fontsize=20)
    page.insert_text((50, 90), '1 Introduction', fontsize=15)
    page.insert_textbox((50, 110, 540, 210), 'The introduction establishes the motivation and evidence needs of the study. '*7, fontsize=11)
    page.insert_text((50, 245), '2.1 RETRIEVAL METHOD', fontsize=11)
    page.insert_textbox((50, 275, 540, 450), 'The experimental procedure retains page information so readers can inspect evidence. '*8, fontsize=11)
    corpus.ingest(doc.tobytes(), 'subsection.pdf'); doc.close()
    assert any(n['section'] == '2.1 RETRIEVAL METHOD' for n in corpus.nodes())


def test_numbered_references_stop_main_body_indexing(corpus):
    doc = pymupdf.open(); page = doc.new_page()
    page.insert_text((50, 50), 'Retrieval Experiment', fontsize=20)
    page.insert_text((50, 90), '1 Introduction', fontsize=15)
    page.insert_textbox((50, 110, 540, 250), 'The research method evaluates retrieval with original passages and source provenance. '*8, fontsize=10)
    page.insert_text((50, 270), '5 References', fontsize=15)
    page.insert_textbox((50, 300, 540, 450), 'Unrelated bibliography entries must never be indexed as original main body findings. '*6, fontsize=11)
    corpus.ingest(doc.tobytes(), 'references.pdf'); doc.close()
    assert all('Unrelated bibliography' not in n['text'] for n in corpus.nodes())


def test_dense_search_does_not_require_lexical_index(corpus):
    corpus.ingest(pdf_bytes(), 'tree.pdf')
    with corpus.db() as db:
        db.execute('DROP TABLE search')
    result = corpus.search('retrieval', strategy='dense')
    assert result['evidence']
    assert result['trace']['lexical_ms'] == 0


def test_selected_paper_outside_global_top_sixty_is_retained(corpus):
    first = corpus.ingest(pdf_bytes(), 'first.pdf')
    second = corpus.ingest(pdf_bytes('Other Study'), 'second.pdf')
    # A large, strongly matched first paper must not crowd the requested second paper out.
    with corpus.db() as db:
        row = db.execute('SELECT metadata,vector FROM nodes WHERE paper_id=? LIMIT 1', (first['id'],)).fetchone()
        import json
        original = json.loads(row[0])
        for i in range(80):
            node = dict(original, id=f'crowd:{i}', text=original['text'] + ' banana')
            db.execute('INSERT INTO nodes VALUES (?,?,?,?)', (node['id'], first['id'], json.dumps(node), row[1]))
    result = corpus.search('retrieval', [first['id'],second['id']], 'dense')
    assert set(result['trace']['covered_papers']) == {first['id'],second['id']}
    assert result['trace']['missing_papers'] == []


def test_section_comparison_reserves_budget_for_each_selected_paper(corpus):
    import json
    ids = [corpus.ingest(pdf_bytes(f'Study Number {i}'), f'study-{i}.pdf')['id'] for i in range(6)]
    with corpus.db() as db:
        for key, metadata in db.execute('SELECT id,metadata FROM nodes').fetchall():
            node = json.loads(metadata)
            if node['level'] == 'section':
                node['text'] = ' '.join(('retrieval evidence '*210).split())
                db.execute('UPDATE nodes SET metadata=? WHERE id=?', (json.dumps(node),key))
    result = corpus.search('Compare the methods', ids, 'adaptive')
    assert set(result['trace']['covered_papers']) == set(ids)
    assert result['trace']['evidence_words'] <= 1600
    assert result['trace']['coverage_truncations']
    assert result['trace']['missing_papers'] == []
