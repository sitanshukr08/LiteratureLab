"""Evaluate a supplied PDF with a frozen question set; live inference requires --live."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from literaturelab.core import Corpus
from literaturelab.synthesis import Synthesis, ProviderError, PROMPT_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper', type=Path, required=True)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--provider', choices=['auto', 'gemini', 'groq'], default='auto')
    parser.add_argument('--ids', nargs='*')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--live', action='store_true', help='Allow hosted provider calls using locally configured credentials.')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/paper-evaluation')
    args = parser.parse_args()
    protocol = json.loads(args.questions.read_text(encoding='utf-8'))
    raw = args.paper.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != protocol['paper_sha256']:
        raise SystemExit('The PDF differs from the source used to prepare the question set.')
    args.output.mkdir(parents=True, exist_ok=True)
    corpus = Corpus(ROOT / 'data')
    started = time.perf_counter()
    paper = corpus.ingest(raw, args.paper.name)
    engine = Synthesis(corpus)
    cases = [q for q in protocol['questions'] if not args.ids or q['id'] in args.ids]
    if args.limit:
        cases = cases[:args.limit]
    metadata = {'created': datetime.now(timezone.utc).isoformat(), 'paper_sha256': digest,
                'question_set_sha256': hashlib.sha256(args.questions.read_bytes()).hexdigest(),
                'question_set_frozen': protocol['freeze_time_utc'], 'paper_id': paper['id'],
                'title': paper['title'], 'pages': paper['pages'], 'paragraphs': paper['paragraphs'],
                'index_policy_version': paper.get('index_policy_version'), 'prompt_version': PROMPT_VERSION,
                'provider_preference': args.provider, 'live': args.live,
                'ingestion_seconds': round(time.perf_counter() - started, 3),
                'scope': protocol['evaluation_kind'], 'cases': []}
    failures = 0
    for case in cases:
        record = {'id': case['id'], 'question': case['question'], 'type': case['type']}
        try:
            if args.live:
                result = engine.ask(case['question'], [paper['id']], refresh=True, provider=args.provider)
                record['result'] = result
                print(json.dumps({'id': case['id'], 'provider': result['provider'], 'model': result['model'],
                                  'claims': len(result['claims']), 'withheld': len(result['rejected_claims']),
                                  'partial': result['insufficient_evidence'], 'seconds': result['duration_seconds']}), flush=True)
            else:
                record['retrieval'] = corpus.search(case['question'], [paper['id']])
                print(json.dumps({'id': case['id'], 'retrieval_only': True}), flush=True)
            failures = 0
        except ProviderError as error:
            record['error'] = str(error)
            record['status'] = error.status
            failures += 1
            print(json.dumps({'id': case['id'], 'error': str(error), 'status': error.status}), flush=True)
        (args.output / f"{case['id']}.json").write_text(json.dumps(record, indent=2), encoding='utf-8')
        metadata['cases'].append({k: v for k, v in record.items() if k != 'result' and k != 'retrieval'})
        (args.output / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        if failures >= 2:
            print('Stopped after two consecutive provider failures; no successful retries selected.', flush=True)
            break


if __name__ == '__main__':
    main()
