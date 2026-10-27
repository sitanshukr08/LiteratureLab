"""Index the six bundled, version-pinned public papers. No LLM calls."""
import json
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literaturelab.core import Corpus

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    corpus = Corpus(ROOT / 'data')
    papers = json.loads((ROOT / 'demo/manifest.json').read_text(encoding='utf-8'))
    for paper in papers:
        aliases = {'rag':['rag'], 'dpr':['dpr'], 'raptor':['raptor'], 'lost':['lost in the middle'],
                   'alce':['alce'], 'hichunk':['hichunk']}[paper['id']]
        raw = (ROOT / 'demo/papers' / (paper['id'] + '.pdf')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != paper['pdf_sha256']:
            raise ValueError('Demo PDF hash differs from the recorded source version: ' + paper['id'])
        result = corpus.ingest(raw, paper['id'] + '.pdf', paper['title'], aliases)
        print(json.dumps({'paper':paper['id'],'duplicate':result['duplicate'],'paragraphs':result['paragraphs'],'sections':result['sections']}), flush=True)
    print('Demo library ready.', flush=True)
