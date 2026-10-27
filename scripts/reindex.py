"""Rebuild the full current library safely after a parser change. Stop the server first."""
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from contextlib import closing
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literaturelab.core import Corpus

ROOT = Path(__file__).resolve().parents[1]


def main():
    current = Corpus(ROOT / 'data')
    papers = current.papers()
    if not papers:
        print('Library is empty; nothing to rebuild.'); return
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = ROOT / 'data/backups' / (stamp + '.sqlite3')
    backup.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(ROOT / 'data/library.sqlite3')) as old, closing(sqlite3.connect(backup)) as saved:
        old.backup(saved)
    fresh = Corpus(ROOT / 'data' / ('rebuild-' + stamp), current.embedder)
    for paper in papers:
        raw = (ROOT / 'data/pdfs' / (paper['id'] + '.pdf')).read_bytes()
        result = fresh.ingest(raw, paper['filename'], paper['title'], paper['aliases'])
        print(json.dumps({'paper':paper['filename'],'paragraphs':result['paragraphs'],'sections':result['sections']}),flush=True)
    with current.db() as old, fresh.db() as new:
        notes = old.execute('SELECT id,created,result FROM history').fetchall()
        new.executemany('INSERT INTO history VALUES (?,?,?)', notes)
    if {p['id'] for p in fresh.papers()} != {p['id'] for p in papers}:
        raise RuntimeError('Rebuilt paper identity mismatch; original database kept.')
    (fresh.root / 'library.sqlite3').replace(ROOT / 'data/library.sqlite3')
    print('Index replaced atomically. Historic notes and original PDF files preserved; response cache invalidated.',flush=True)


if __name__ == '__main__':
    main()
