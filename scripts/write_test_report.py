"""Build the delivery report from recorded test artifacts; makes no API calls."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from literaturelab.synthesis import validate_claims

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'reports'


def main():
    evaluation = json.loads((REPORTS / 'evaluation.json').read_text())
    browser = json.loads((REPORTS / 'browser-check.json').read_text())
    upload = json.loads((REPORTS / 'real-upload-check.json').read_text())
    suites = ET.parse(REPORTS / 'unit-tests.xml').getroot().findall('.//testsuite')
    tests = sum(int(s.get('tests', 0)) for s in suites)
    failures = sum(int(s.get('failures', 0)) + int(s.get('errors', 0)) for s in suites)
    cases = evaluation.get('live_cases', [])
    durations, rows, retained, withheld, schema_retries = [], [], 0, 0, 0
    for case in cases:
        row = dict(case)
        if not case.get('error'):
            result = json.loads((REPORTS / ('live-' + case['case_id'] + '.json')).read_text())
            assert result['id'] == case['result_id'] and result['prompt_version'] == evaluation['prompt_version']
            _, invalid = validate_claims(result['claims'], result['evidence'])
            assert not invalid, 'Delivered claim violates local grounding validation.'
            row.update(answer_sha256=hashlib.sha256(json.dumps(result['claims'],sort_keys=True).encode()).hexdigest(),
                       reported_findings=sum(c.get('kind') == 'reported' for c in result['claims']),
                       labeled_inferences=sum(c.get('kind') == 'inference' for c in result['claims']))
            retained += len(result['claims']); withheld += len(result['rejected_claims'])
            schema_retries += sum(u.get('schema_failures_retried', 0) for u in result['usage'].values())
            durations.append(case['seconds'])
        rows.append(row)
    errors = sum(bool(c.get('error')) for c in cases)
    summary = {'prompt_version':evaluation['prompt_version'],'automated_tests':tests,'automated_failures':failures,
               'browser_checks':len(browser.get('checks', [])),'browser_passed':browser.get('passed', False),
               'real_pdf_upload_passed':upload['passed'],'live_requested':len(cases),'live_returned':len(cases)-errors,
               'live_errors':errors,'retained_claims':retained,'withheld_draft_claims':withheld,
               'schema_failures_retried':schema_retries,'live_median_seconds':round(statistics.median(durations),3) if durations else None,
               'live_max_seconds':max(durations) if durations else None,
               'semantic_accuracy':'Not established; independent assistant audit is qualitative, not human benchmark accuracy.'}
    (REPORTS / 'delivery-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    fields = sorted({k for row in rows for k in row})
    with (REPORTS / 'live-case-summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    lines = ['# LiteratureLab test report', '', 'Recorded 27 October 2026 on the user’s Dell G15 / i5-13450HX / approximately 16 GB RAM. CPU parsing and embeddings; Groq GPT-OSS 120B generation/review. No local LLM inference is needed.', '',
             '**Functional verification and scientific answer quality are separate. This is a working local prototype, not a validated unattended literature-review system.**', '',
             '## Verified behavior', '',
             f'- Automated regression/API/provider suite: **{tests} tests, {failures} failures/errors**. Evidence: `unit-tests.xml`. One unsuppressed Starlette/httpx test-client deprecation warning remains.',
             f'- Real Edge browser: **{len(browser.get("checks", []))} checks**, clean pass: **{browser.get("passed", False)}**. Cached final-version synthesis, keyboard access, selected papers, uploads, PDF/citation navigation, export/history, mocked quota recovery, no stale answers and 375px layout checked. Expected 400/429 test rejections are separated from unexpected errors.',
             f'- Real PDF through FastAPI with actual BGE embeddings: **{upload["passed"]}**. Upload/index, duplicate detection, hybrid search, byte-identical PDF serving and persistent reopen. First upload took {upload["upload_seconds"]:.2f} s in an isolated test library.',
             '- Isolated 48-package environment: `pip check` clean. OSV listed no advisory IDs for those package versions at the recorded check. This is not a security certification; see `security-review.md`.',
             '- Key remains in ignored backend `.env`; it is excluded from the local Git commits and source archive. No push or deployment was performed.', '',
             '## Retrieval measurements', '',
             f'Six version-pinned real papers, 114 PDF pages; {evaluation["corpus"]["paragraphs"]} paragraphs and {evaluation["corpus"]["sections"]} original section windows. Eighteen development questions × three repetitions × three strategies = 162 retrieval runs. Shared 1600-word ceiling. Active desktop, small sample, warm embedding model.', '',
             '| Strategy | Median total retrieval | Sample p95 | Required-paper identity coverage |', '|---|---:|---:|---:|']
    for name, metric in evaluation['strategies'].items():
        lines.append(f'| {name} | {metric["median_ms"]} ms | {metric["p95_ms"]} ms | {metric["paper_coverage_percent"]}% |')
    lines += ['', '**Dense search is faster in this small-corpus run. Adaptive retrieval has not demonstrated a speed advantage.** Paper identity coverage does not establish semantic relevance, required-fact recall, or citation support. Adaptive and baseline evidence resolutions differ; the budget is a ceiling, not a claim that every request used identical tokens.', '',
              '## Final live Groq run', '',
              f'Prompt/policy version: `{evaluation["prompt_version"]}`. Fixed eight-case subset, cache bypassed. **{len(cases)-errors}/{len(cases)} requests returned**, {errors} request errors. Retained {retained} claims and withheld {withheld} draft claims; all retained IDs/spans pass the local validator. Median full answer latency: {summary["live_median_seconds"]}s; maximum: {summary["live_max_seconds"]}s, including pacing/retries. These timings include network/provider quotas and are not pure inference timings.', '',
              f'{schema_retries} provider schema-decoding failures were retried before a usable answer existed. Bounded retry is transport recovery, not selection among valid answers. Reported token totals can omit provider attempts that returned no usage metadata.', '',
              '| Case | Retained claims | Withheld | Insufficient/partial flag | Wall seconds | Error |', '|---|---:|---:|---|---:|---|']
    for case in cases:
        lines.append(f'| {case["case_id"]} | {case.get("claims", "—")} | {case.get("rejected", "—")} | {case.get("insufficient_evidence", "—")} | {case.get("seconds", "—")} | {case.get("error", "—")} |')
    lines += ['', 'Cases: q02 Sequence/Token mechanism; q06 QA arithmetic versus speed; q08 citation metrics; q12 hierarchy/granularity comparison; q13 cross-paper design synthesis; q15 unavailable Dell/RTX 3050 measurement; q17 HiChunk learning rate; q18 incomparable metrics/baselines.', '',
              'HiChunk’s learning rate can be found with full-paper retrieval here. It was intentionally unavailable in the earlier supplied-passage OpenScholar test, so those two tasks must not be scored as equivalent abstention tests.', '',
              '## Quality limits and observed mistakes', '',
              'The model can still overgeneralize, omit conditions, or refuse valid deductions. Same-model support review produced false acceptances and false rejections during development. Explicit reported/inference labels and local numerical/threshold/metric/uncertainty checks address observed failure classes but do not prove entailment. Inference labels are not empirical validation.', '',
              'Earlier complete evaluations are retained locally in `reports/development-*`. The first quote-writing workflow changed source wording; later review accepted an improperly cited latency assertion and a result attached to the wrong numerical span. Subsequent versions add stable span indexes, fail-closed local guards and finding/inference separation. No published benchmark accuracy, independent human citation score or perfect reliability is claimed.', '',
              'See `live-audit-final.md` for the separate source-based assistant audit of the delivered answers. Treat all these questions as development/regression questions; use a larger disjoint corpus and independent human citation labels for academic claims.', '',
              '## Reproduce', '', '```powershell', r'.venv\Scripts\python.exe -m pytest -q --junitxml=reports/unit-tests.xml', r'.venv\Scripts\python.exe scripts/evaluate.py --live --fresh', r'.venv\Scripts\python.exe scripts/browser_check.py --synthesize-cached', r'.venv\Scripts\python.exe scripts/check_real_upload.py', r'.venv\Scripts\python.exe scripts/write_test_report.py', '```', '',
              'The live command uses the configured Groq account and sends public selected evidence. Keep it on the free plan. The browser command reuses the exact seeded question; other questions are not automatically cached. Free-tier availability and latency are not guaranteed.']
    (REPORTS / 'TEST-REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__ == '__main__':
    main()
