"""Real corpus retrieval diagnostics; optional live Groq generation, retaining every result."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys
import time
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literaturelab.core import Corpus
from literaturelab.synthesis import Synthesis, ProviderError, validate_claims, PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Send public question/evidence passages to Groq.')
    parser.add_argument('--fresh', action='store_true', help='Bypass response cache for every live case.')
    args = parser.parse_args()
    corpus = Corpus(ROOT / 'data')
    cases = json.loads((ROOT / 'demo/questions.json').read_text(encoding='utf-8'))
    report = {'created':datetime.now(timezone.utc).isoformat(), 'prompt_version':PROMPT_VERSION,
              'scope':'Development evaluation on six real papers. Paper coverage is a retrieval diagnostic, not answer accuracy or evidence entailment.',
              'corpus':{'papers':len(corpus.papers()),'paragraphs':sum(n['level']=='paragraph' for n in corpus.nodes()),'sections':sum(n['level']=='section' for n in corpus.nodes())},
              'retrieval_cases':len(cases),'strategies':{},'retrieval_runs':[],
              'retrieval_note':'Same question corpus, 1600-word ceiling, three repetitions. Adaptive section windows differ from baseline paragraphs. Coverage checks paper identity, not whether all required facts were retrieved. No speed superiority claim is made.'}
    corpus.embedder.encode(['Warm-up query'], query=True)
    alias_ids = {alias:p['id'] for p in corpus.papers() for alias in p['aliases'] + [Path(p['filename']).stem]}
    by_case = {}
    for strategy in ['dense','hybrid','adaptive']:
        times, coverage = [], []
        for case in cases:
            question = case['question'].split(' Use only the supplied')[0]
            for repetition in range(3):
                out = corpus.search(question, [], strategy)
                required = {alias_ids[a] for a in case['gold_papers'] if a in alias_ids}
                found = set(out['trace']['covered_papers'])
                covered = len(found & required) / len(required) if required else None
                times.append(out['trace']['total_ms'])
                if covered is not None: coverage.append(covered)
                row = {'case_id':case['id'],'strategy':strategy,'repeat':repetition,
                       'paper_coverage':covered,'evidence_ids':[n['id'] for n in out['evidence']], 'trace':out['trace']}
                report['retrieval_runs'].append(row)
            by_case[case['id']] = case
        report['strategies'][strategy] = {'median_ms':round(statistics.median(times),2),
                                         'p95_ms':round(float(np.percentile(times,95)),2),
                                         'paper_coverage_percent':round(statistics.mean(coverage)*100,1)}
        print(json.dumps({strategy:report['strategies'][strategy]}), flush=True)
    destination = ROOT / 'reports'; destination.mkdir(exist_ok=True)
    output = destination / 'evaluation.json'
    if output.exists():
        previous = json.loads(output.read_text(encoding='utf-8'))
        if previous.get('live_cases') and previous.get('prompt_version') == PROMPT_VERSION:
            report['live_cases'] = previous['live_cases']
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    if args.live:
        engine = Synthesis(corpus)
        live = []
        # Fixed before live generation. Include known failure triggers, not only easy definitions.
        ids = ['q02','q06','q08','q12','q13','q15','q17','q18']
        for case_id in ids:
            case = by_case[case_id]
            question = case['question'].split(' Use only the supplied')[0]
            try:
                result = engine.ask(question, [], 'adaptive', refresh=args.fresh)
                accepted, invalid = validate_claims(result['claims'],result['evidence'])
                (destination / f'live-{case_id}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
                row = {'case_id':case_id,'question':question,'claims':len(result['claims']), 'rejected':len(result['rejected_claims']),
                       'seconds':result['duration_seconds'],'insufficient_evidence':result['insufficient_evidence'],
                       'invalid_citations_or_spans':len(invalid),'cached':result['cached'],'result_id':result['id']}
            except ProviderError as exc:
                row = {'case_id':case_id,'question':question,'error':str(exc), 'provider_diagnostic':engine.provider.last_failure}
            live.append(row)
            report['live_cases'] = live
            output.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(row),flush=True)
            # Pace free-tier calls rather than exhausting request/token limits in a burst.
            time.sleep(12)
    print('Evaluation saved to reports/evaluation.json', flush=True)


if __name__ == '__main__':
    main()
