from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata

import numpy as np
import pymupdf


class InputError(ValueError):
    pass


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def rrf(rankings, k=60):
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0) + 1 / (k + rank)
    return sorted(scores, key=lambda item: (-scores[item], str(item)))


class Embedder:
    def __init__(self, path):
        self.path = path
        self.model = None
        self.lock = threading.Lock()

    def encode(self, texts, query=False):
        with self.lock:
            if self.model is None:
                from fastembed import TextEmbedding
                if not (self.path / 'model_optimized.onnx').exists():
                    raise InputError('Embedding model is missing. Run Setup.ps1 first.')
                self.model = TextEmbedding('BAAI/bge-small-en-v1.5', specific_model_path=str(self.path),
                                          local_files_only=True, providers=['CPUExecutionProvider'], threads=4)
            method = self.model.query_embed if query else self.model.embed
            rows = np.asarray(list(method(texts)), dtype=np.float32)
            return rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-8)


class Corpus:
    def __init__(self, root, embedder=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'pdfs').mkdir(exist_ok=True)
        self.embedder = embedder or Embedder(self.root.parent / 'models/bge')
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS papers(id TEXT PRIMARY KEY, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, paper_id TEXT NOT NULL, metadata TEXT NOT NULL, vector BLOB NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(id UNINDEXED, text, title, section);
                CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY, created TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, result TEXT NOT NULL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / 'library.sqlite3', timeout=30)
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def papers(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT metadata FROM papers ORDER BY rowid')]

    def nodes(self):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT metadata FROM nodes ORDER BY rowid')]

    def ingest(self, raw, filename, title=None, aliases=None):
        if len(raw) > 20 * 1024**2 or not raw.startswith(b'%PDF-'):
            raise InputError('Upload a valid PDF smaller than 20 MB.')
        digest = hashlib.sha256(raw).hexdigest()
        paper_id = digest[:16]
        with self.lock:
            existing = next((p for p in self.papers() if p['id'] == paper_id), None)
            if existing:
                return dict(existing, duplicate=True)
            try:
                doc = pymupdf.open(stream=raw, filetype='pdf')
            except Exception as exc:
                raise InputError('This PDF could not be opened.') from exc
            try:
                if doc.needs_pass or len(doc) > 200:
                    raise InputError('Use an unencrypted PDF with at most 200 pages.')
                records, heading, sizes, title_lines = [], 'Front matter', [], []
                for page in doc:
                    for block in page.get_text('dict')['blocks']:
                        for line in block.get('lines', []):
                            for span in line['spans']:
                                if len(span['text'].strip()) > 5:
                                    sizes.extend([round(span['size'], 1)] * min(40, len(span['text'])))
                if not sizes:
                    raise InputError('No searchable text found. Scanned PDFs require OCR, which is not enabled.')
                body_size = Counter(sizes).most_common(1)[0][0]
                references = False
                for page_index, page in enumerate(doc):
                    for block in page.get_text('dict')['blocks']:
                        lines = block.get('lines', [])
                        text = '\n'.join(''.join(s['text'] for s in line['spans']) for line in lines)
                        text = normalize(re.sub(r'(?<=\w)-\s*\n(?=\w)', '', text))
                        if not text:
                            continue
                        font = max((s['size'] for line in lines for s in line['spans']), default=0)
                        if page_index == 0 and font >= body_size + 2 and 8 < len(text) < 230 and not text.lower().startswith('arxiv:'):
                            title_lines.append((font, text))
                        # Numbering alone also matches algorithm steps. Require heading typography
                        # for numbered titles so original procedural evidence is not discarded.
                        heading_label = re.sub(r'^\d+(?:\.\d+)*[.\s]+', '', text).strip()
                        heading_name = heading_label.lower()
                        bold = any(s.get('flags', 0) & 16 for line in lines for s in line['spans'])
                        is_heading = (len(text.split()) <= 18 and len(text) < 180 and
                                      (heading_name in {'abstract', 'introduction', 'conclusion', 'conclusions', 'references', 'limitations', 'discussion'} or
                                       (bool(re.match(r'^\d+(?:\.\d+)*[.\s]+[A-Z]', text)) and
                                        not text.endswith(('.', ';', ':')) and (font > body_size + 0.2 or bold or heading_label.isupper())) or
                                       (font > body_size + 1.5 and page_index > 0)))
                        if is_heading:
                            if heading_name == 'references':
                                references = True
                            heading = text
                            continue
                        if references or len(text.split()) < 12:
                            continue
                        words = text.split()
                        for offset in range(0, len(words), 140):
                            part = ' '.join(words[offset:offset + 160])
                            if len(part.split()) < 12:
                                continue
                            records.append({'paper_id': paper_id, 'level': 'paragraph', 'section': heading,
                                            'pages': [page_index + 1], 'text': part, 'bbox': list(block['bbox'])})
                if sum(len(r['text'].split()) for r in records) < 70:
                    raise InputError('Too little readable text. This system needs text-based academic PDFs.')
                filename = Path(filename.replace('\\', '/')).name[:180] or 'paper.pdf'
                extracted_title = max(title_lines, default=(0, filename), key=lambda item: item[0])[1]
                paper = {'id': paper_id, 'title': title or extracted_title, 'filename': filename, 'pages': len(doc),
                         'sha256': digest, 'aliases': aliases or [Path(filename).stem.lower()],
                         'paragraphs': len(records), 'sections': len({r['section'] for r in records})}
                section_groups = {}
                for i, record in enumerate(records):
                    record.update(id=f'{paper_id}:p:{i}', title=paper['title'])
                    section_groups.setdefault(record['section'], []).append(record)
                parents = []
                for section, children in section_groups.items():
                    batch, words = [], 0
                    for child in children:
                        if batch and words + len(child['text'].split()) > 420:
                            parents.append(self._parent(paper, section, batch, len(parents)))
                            batch, words = [], 0
                        batch.append(child); words += len(child['text'].split())
                    if batch:
                        parents.append(self._parent(paper, section, batch, len(parents)))
                nodes = records + parents
                vectors = self.embedder.encode([f"{n['title']} / {n['section']}\n{n['text']}" for n in nodes])
                pdf_path = self.root / 'pdfs' / f'{paper_id}.pdf'
                pdf_path.write_bytes(raw)
                with self.db() as db:
                    db.execute('INSERT INTO papers VALUES (?,?)', (paper_id, json.dumps(paper)))
                    db.executemany('INSERT INTO nodes VALUES (?,?,?,?)', [(n['id'], paper_id, json.dumps(n), v.tobytes()) for n, v in zip(nodes, vectors)])
                    db.executemany('INSERT INTO search(id,text,title,section) VALUES (?,?,?,?)', [(n['id'], n['text'], n['title'], n['section']) for n in nodes])
                return dict(paper, duplicate=False)
            finally:
                doc.close()

    @staticmethod
    def _parent(paper, section, children, index):
        parent_id = f"{paper['id']}:s:{index}"
        for child in children:
            child['parent_id'] = parent_id
        return {'id': parent_id, 'paper_id': paper['id'], 'title': paper['title'], 'level': 'section',
                'section': section, 'pages': sorted({p for c in children for p in c['pages']}),
                'text': ' '.join(c['text'] for c in children), 'children': [c['id'] for c in children],
                'spans': [{'text':c['text'], 'pages':c['pages'], 'node_id':c['id']} for c in children]}

    def delete(self, paper_id):
        with self.lock, self.db() as db:
            if not db.execute('SELECT 1 FROM papers WHERE id=?', (paper_id,)).fetchone():
                raise InputError('Paper not found.')
            db.execute('DELETE FROM search WHERE id IN (SELECT id FROM nodes WHERE paper_id=?)', (paper_id,))
            db.execute('DELETE FROM nodes WHERE paper_id=?', (paper_id,))
            db.execute('DELETE FROM papers WHERE id=?', (paper_id,))
            db.execute('DELETE FROM cache')
            # Keep past research notes, but source PDFs removed by the user are no longer accessible.
            (self.root / 'pdfs' / f'{paper_id}.pdf').unlink(missing_ok=True)

    def search(self, question, paper_ids=None, strategy='adaptive'):
        started = time.perf_counter()
        if strategy not in {'dense', 'hybrid', 'adaptive'}:
            raise InputError('Unknown retrieval strategy.')
        papers = self.papers()
        known = {p['id'] for p in papers}
        if paper_ids and not set(paper_ids) <= known:
            raise InputError('One or more selected papers no longer exist.')
        if not papers:
            raise InputError('Upload at least one paper first.')
        target = set(paper_ids or [])
        if not target:
            target = {p['id'] for p in papers if any(re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', question.lower()) for alias in p['aliases'] if len(alias) >= 3)}
        allowed = target or known
        broad = bool(re.search(r'compar|synthesi|overview|summari|limitations|across|methods', question, re.I))
        resolution = 'section' if strategy == 'adaptive' and broad else 'paragraph'
        with self.db() as db:
            rows = db.execute('SELECT metadata,vector FROM nodes ORDER BY rowid').fetchall()
            nodes = [json.loads(row[0]) for row in rows]
            vectors = np.vstack([np.frombuffer(row[1], dtype=np.float32) for row in rows])
            embedding_start = time.perf_counter()
            query = self.embedder.encode([question], query=True)[0]
            embedding_ms = (time.perf_counter() - embedding_start) * 1000
            candidates = [i for i, n in enumerate(nodes) if n['paper_id'] in allowed and n['level'] == resolution]
            coarse_count, fallback = 0, None
            if strategy == 'adaptive' and not broad:
                coarse = [i for i, n in enumerate(nodes) if n['paper_id'] in allowed and n['level'] == 'section']
                coarse_count = len(coarse)
                coarse_rank = sorted(coarse, key=lambda i: -float(vectors[i] @ query))
                best = []
                for pid in allowed:
                    best.extend([i for i in coarse_rank if nodes[i]['paper_id'] == pid][:3])
                parents = {nodes[i]['id'] for i in best}
                narrowed = [i for i in candidates if nodes[i].get('parent_id') in parents]
                if len(narrowed) >= 8:
                    candidates = narrowed
                else:
                    fallback = 'Small coarse candidate set; searched all eligible paragraphs.'
            dense_start = time.perf_counter()
            dense_all = sorted(candidates, key=lambda i: -float(vectors[i] @ query))
            dense = dense_all[:60]
            dense_ms = (time.perf_counter() - dense_start) * 1000
            lexical_start = time.perf_counter()
            terms = list(dict.fromkeys(re.findall(r'\w+', question.lower())))[:45]
            stop = {'the','what','how','and','are','was','for','with','from','that','this','does','which','can','use','only','supplied','evidence'}
            match = ' OR '.join('"' + t + '"' for t in terms if t not in stop and len(t) > 1)
            candidate_set = set(candidates)
            indices = {n['id']: i for i, n in enumerate(nodes) if i in candidate_set}
            lexical = []
            if strategy != 'dense' and match and indices:
                eligible = list(indices)
                placeholders = ','.join('?' for _ in eligible)
                lexical = [indices[r[0]] for r in db.execute(
                    f'SELECT id FROM search WHERE search MATCH ? AND id IN ({placeholders}) ORDER BY bm25(search,0,1,2,2) LIMIT 60',
                    [match, *eligible])]
            lexical_ms = (time.perf_counter() - lexical_start) * 1000 if strategy != 'dense' else 0.0
        ranked = dense if strategy == 'dense' else rrf([dense, lexical])
        selected, used, excerpts, truncations = [], 0, {}, []
        def add(index, allowance=None):
            nonlocal used
            node = nodes[index]
            words = node['text'].split()
            excerpt = ' '.join(words[:allowance]) if allowance and len(words) > allowance else node['text']
            count = len(excerpt.split())
            if index not in selected and used + count <= 1600:
                selected.append(index); used += count; excerpts[index] = excerpt
                if len(words) > count:
                    truncations.append(node['id'])
        # Explicitly requested papers each get evidence before remaining slots compete.
        if target:
            for pid in sorted(target):
                match_index = next((i for i in ranked if nodes[i]['paper_id'] == pid), None)
                if match_index is None:
                    match_index = next((i for i in dense_all if nodes[i]['paper_id'] == pid), None)
                if match_index is not None:
                    # Reserve a fair share before adding extra passages. The bounded excerpt
                    # remains contiguous original text, with the full source kept on disk.
                    add(match_index, max(1, 1600 // len(target)))
        for index in ranked:
            if len(selected) >= (6 if resolution == 'section' else 10):
                break
            add(index)
        evidence = [dict(nodes[i], text=excerpts[i], citation_id=f'E{j + 1}', dense_rank=dense_all.index(i) + 1 if i in dense_all else None,
                         lexical_rank=lexical.index(i) + 1 if i in lexical else None) for j, i in enumerate(selected)]
        return {'evidence': evidence, 'trace': {'strategy': strategy, 'resolution': resolution,
                'reason': 'Broad question: original section windows.' if resolution == 'section' else 'Focused question: original paragraphs.',
                'total_nodes': len(nodes), 'coarse_vectors_scored': coarse_count, 'fine_vectors_scored': len(candidates),
                'requested_papers': sorted(target), 'covered_papers': sorted({n['paper_id'] for n in evidence}),
                'missing_papers': sorted(target - {n['paper_id'] for n in evidence}),
                'coverage_truncations': truncations,
                'evidence_words': used, 'fallback': fallback, 'embedding_ms': round(embedding_ms, 2),
                'dense_ms': round(dense_ms, 2), 'lexical_ms': round(lexical_ms, 2),
                'total_ms': round((time.perf_counter() - started) * 1000, 2)}}
