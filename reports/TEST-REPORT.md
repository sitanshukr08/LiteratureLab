# LiteratureLab test report

Recorded 27 October 2026 on the user’s Dell G15 / i5-13450HX / approximately 16 GB RAM. CPU parsing and embeddings; Groq GPT-OSS 120B generation/review. No local LLM inference is needed.

**Functional verification and scientific answer quality are separate. This is a working local system, not a validated unattended literature-review system.**

## Verified behavior

- Automated regression/API/provider suite: **29 tests, 0 failures/errors**. Evidence: `unit-tests.xml`. One unsuppressed Starlette/httpx test-client deprecation warning remains.
- Real Edge browser: **14 checks**, clean pass: **True**. Cached final-version synthesis, keyboard access, selected papers, uploads, PDF/citation navigation, export/history, mocked quota recovery, no stale answers and 375px layout checked. Expected 400/429 test rejections are separated from unexpected errors.
- Real PDF through FastAPI with actual BGE embeddings: **True**. Upload/index, duplicate detection, hybrid search, byte-identical PDF serving and persistent reopen. First upload took 29.91 s in an isolated test library.
- Isolated 48-package environment: `pip check` clean. OSV listed no advisory IDs for those package versions at the recorded check. This is not a security certification; see `security-review.md`.
- Key remains in ignored backend `.env`; it is excluded from the local Git commits and source archive. No push or deployment was performed.

## Retrieval measurements

Six version-pinned real papers, 114 PDF pages; 576 paragraphs and 142 original section windows. Eighteen development questions × three repetitions × three strategies = 162 retrieval runs. Shared 1600-word ceiling. Active desktop, small sample, warm embedding model.

| Strategy | Median total retrieval | Sample p95 | Required-paper identity coverage |
|---|---:|---:|---:|
| dense | 15.47 ms | 19.82 ms | 100.0% |
| hybrid | 17.88 ms | 42.9 ms | 100.0% |
| adaptive | 33.45 ms | 53.6 ms | 100.0% |

**Dense search is faster in this small-corpus run. Adaptive retrieval has not demonstrated a speed advantage.** Paper identity coverage does not establish semantic relevance, required-fact recall, or citation support. Adaptive and baseline evidence resolutions differ; the budget is a ceiling, not a claim that every request used identical tokens.

## Final live Groq run

Prompt/policy version: `v4-reported-and-inferred`. Fixed eight-case subset, cache bypassed. **7/8 requests returned**, 1 request errors. Retained 15 claims and withheld 5 draft claims; all retained IDs/spans pass the local validator. Median full answer latency: 12.426s; maximum: 51.931s, including pacing/retries. These timings include network/provider quotas and are not pure inference timings.

0 provider schema-decoding failures were retried before a usable answer existed. Bounded retry is transport recovery, not selection among valid answers. Reported token totals can omit provider attempts that returned no usage metadata.

| Case | Retained claims | Withheld | Insufficient/partial flag | Wall seconds | Error |
|---|---:|---:|---|---:|---|
| q02 | 4 | 0 | False | 3.429 | — |
| q06 | 1 | 1 | True | 3.61 | — |
| q08 | 3 | 0 | False | 12.557 | — |
| q12 | 3 | 2 | True | 51.931 | — |
| q13 | 3 | 2 | True | 51.186 | — |
| q15 | 0 | 0 | True | 8.707 | — |
| q17 | 1 | 0 | False | 12.426 | — |
| q18 | — | — | — | — | Groq free-tier quota reached. Wait for the limit to reset and retry. |

Cases: q02 Sequence/Token mechanism; q06 QA arithmetic versus speed; q08 citation metrics; q12 hierarchy/granularity comparison; q13 cross-paper design synthesis; q15 unavailable Dell/RTX 3050 measurement; q17 HiChunk learning rate; q18 incomparable metrics/baselines.

HiChunk’s learning rate can be found with full-paper retrieval here. It was intentionally unavailable in the earlier supplied-passage OpenScholar test, so those two tasks must not be scored as equivalent abstention tests.

## Quality limits and observed mistakes

The model can still overgeneralize, omit conditions, or refuse valid deductions. Same-model support review produced false acceptances and false rejections during development. Explicit reported/inference labels and local numerical/threshold/metric/uncertainty checks address observed failure classes but do not prove entailment. Inference labels are not empirical validation.

Earlier complete evaluations are retained locally in `reports/development-*`. The first quote-writing workflow changed source wording; later review accepted an improperly cited latency assertion and a result attached to the wrong numerical span. Subsequent versions add stable span indexes, fail-closed local guards and finding/inference separation. No published benchmark accuracy, independent human citation score or perfect reliability is claimed.

See `live-audit-final.md` for the separate source-based assistant audit of the delivered answers. Treat all these questions as development/regression questions; use a larger disjoint corpus and independent human citation labels for academic claims.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest -q --junitxml=reports/unit-tests.xml
.venv\Scripts\python.exe scripts/evaluate.py --live --fresh
.venv\Scripts\python.exe scripts/browser_check.py --synthesize-cached
.venv\Scripts\python.exe scripts/check_real_upload.py
.venv\Scripts\python.exe scripts/write_test_report.py
```

The live command uses the configured Groq account and sends public selected evidence. Keep it on the free plan. The browser command reuses the exact seeded question; other questions are not automatically cached. Free-tier availability and latency are not guaranteed.
