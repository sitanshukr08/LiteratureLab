# LiteratureLab

A local academic literature workspace with Gemini/Groq answers, CPU embeddings, hybrid retrieval, and adaptive paragraph/section evidence. It is a final-year project, not a promise of error-free scientific answers.

See the [supplied-paper evaluation](reports/VERITRAIL-EVALUATION.md) for current checks. The [earlier six-paper evaluation](reports/TEST-REPORT.md) is preserved as a historical run.

## Run

After setup, double-click **Start.cmd**, then open **http://127.0.0.1:8765**. Keep the terminal open; Ctrl+C stops it. If a server is already running, use the existing browser tab instead of starting a second copy.

For a fresh installation on Windows with Python 3.12:

```powershell
git clone https://github.com/sitanshukr08/LiteratureLab.git
cd LiteratureLab
powershell -ExecutionPolicy Bypass -File .\Setup.ps1
.\Start.cmd
```

Setup installs the pinned dependencies, downloads the pinned ~67 MB CPU embedding model and the six public research PDFs when missing, and indexes the papers. It does not download an LLM. Set `GEMINI_API_KEY` and/or `GROQ_API_KEY` in `.env`. The tested models are `gemini-3.5-flash-lite` and `openai/gpt-oss-120b`. Restart after changing `.env`. Setup creates `.env` from `.env.example` when missing. Add your own free-tier keys there. `LLM_PROVIDER=auto` enables Gemini then Groq failover; `gemini` or `groq` selects a strict single-provider default. The file is excluded by `.gitignore`; do not copy it into source control or a shared archive.

The Desktop environment is isolated from global Python packages. `requirements.txt` pins the tested dependencies; the resolved environment and security check are recorded in `reports/`. Setup performs a normal dependency installation for another machine. Future provider quotas and package availability may change.

## Use

1. Choose papers in the left library or leave them unselected to search all. Add your own English, text-based PDFs with **Add research papers**.
2. Enter a question. Choose dense, hybrid, or adaptive retrieval. **Inspect retrieval** runs locally without a model API call.
3. **Synthesize** retrieves original evidence and numbered source spans. Draft reported findings and draft logical/design inferences are labeled separately. Both categories need source inspection; the model can misclassify a claim. The selected model selects explicit span indexes; the app copies those original words, validates them, and asks the same provider to review only those cited quotations. Unsupported draft claims are withheld.
4. Click an evidence badge to inspect the passage; **Open source page** opens the original PDF. Page numbers are 1-based PDF pages, which can differ from printed article numbering.
5. Notes are saved locally. **Export note** downloads a Markdown note. Repeating an identical question/corpus/model/strategy uses a clearly marked cached answer, without consuming API quota.
6. The **Evaluation** tab shows recorded measurements. It does not run more API calls automatically.

Public evidence selected from uploaded papers is transmitted to the selected provider. Parsing, vectors and search stay on the laptop. No hosted search tool or paid-provider fallback is used. A free account still has rate and token limits; queueing/retries are bounded and quota failures are shown explicitly. This client cannot change the billing tier of either account, so keep both accounts on their free plans.

## Architecture

`PDF → paper/section/paragraph records → SQLite FTS5 + local BGE vectors → retrieval → structured model claims → literal-span validation → Groq support review → cited research note`

- `literaturelab/core.py`: PDF extraction, immutable document IDs, section windows, vectors, persistence, dense/BM25/RRF retrieval. No OCR or visual table interpretation.
- `literaturelab/synthesis.py`: structured generation, validation, support review, caching and saved notes. Windows curl transport is used because it works with this machine's networking; the key travels through stdin, not process arguments.
- `literaturelab/api.py`: same-origin, loopback FastAPI server and explicit API boundaries.
- `web/`: dependency-free browser interface. Untrusted content is inserted as text, never HTML.
- `demo/`: versioned public PDFs, hashes and the 18 development questions.
- `reports/`: measured evaluation results and live answer records.
- `tests/`: offline regression and API tests; no paid calls.

Hybrid retrieval follows the local-embedding/provenance/rank-fusion approach discussed for CogniShift, with BM25 as the second channel rather than a visual retriever. This is a focused implementation of that approach, not a copy of CogniShift's industrial agent workflows. The RRF algorithm and academic sources remain credited below.

Adaptive retrieval uses real extracted headings, not just chunk size labels. Broad queries retrieve original section windows. Focused queries score coarse section windows and search their child paragraphs, with a small-candidate fallback. Selected or explicitly named papers receive coverage before remaining evidence slots compete. Every strategy has a 1600-word ceiling. These rules are transparent heuristics and have not been established as a novel or universally superior retrieval algorithm.

## Testing

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\evaluate.py
.venv\Scripts\python.exe scripts\evaluate.py --live --fresh
.venv\Scripts\python.exe scripts\browser_check.py
```

The first command is offline. `scripts/check_real_upload.py` separately verifies one real PDF through the API with actual embeddings. Retrieval evaluation repeats 18 questions with three strategies three times each. `--live --fresh` also sends eight fixed public-literature cases to the configured provider, including cross-paper comparisons, an absent hardware measurement, citation metrics, and incomparable results. It records every result or error; it does not select successful retries as better answers. Cached results are labeled. Browser checks require a running server and an installed Playwright Chromium (`python -m playwright install chromium` if needed).

Paper coverage measures whether a required document appears in retrieved evidence. It is **not** fact recall, citation entailment, or answer accuracy. Section windows and paragraphs differ in size, so comparisons are budget controlled but not identical passage sets. See `reports/TEST-REPORT.md` for the actual run, manual live-answer audit, and limitations. The earlier 18-question OpenScholar set is reused as a development/regression set, not represented as a new held-out benchmark.

## Limits and next research work

LLM support review is fallible, especially when the same model generates and reviews. Literal quotations and valid citations do not alone prove entailment. Unsupported claims can survive both calls; read the originals. Prompts guard against document instructions but cannot guarantee immunity to prompt injection.

PDF headings/reading order use native text and font heuristics. Tables, formulas, scanned pages, multi-column edge cases and malformed section boundaries need inspection. No authored summaries are used as citation evidence. The search loads the small local index into memory; benchmark before scaling to thousands of papers. Free-tier availability is not an uptime guarantee.

For final-year claims, add a larger disjoint corpus, independent human citation labels, genuine held-out questions, retrieval relevance judgments and repeated controlled measurements. Freeze the generator while comparing retrieval strategies, and separate local retrieval time from network, generation and throttling.

## Sources

- [Groq structured outputs](https://console.groq.com/docs/structured-outputs), [rate limits](https://console.groq.com/docs/rate-limits), [models](https://console.groq.com/docs/models).
- [FastEmbed](https://qdrant.github.io/fastembed/), [pinned BGE-small ONNX model](https://huggingface.co/Qdrant/bge-small-en-v1.5-onnx-Q/tree/aa8f8b060edb00e03bfdd08813a2949946c8ba55).
- [Reciprocal rank fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf).
- Exact paper versions, URLs and SHA-256 values are in `demo/manifest.json`. Corpus: RAG, DPR, RAPTOR, Lost in the Middle, ALCE and HiChunk.

## Conversational answers and provider switching

Ask in ordinary English; punctuation is optional. For example, `whats this paper about`, `why cant we just check the final answer`, or `in table 1 how do the numbers compare`. Select a paper if the library contains more than one and you refer to “this paper.” The trace shows a conservative query interpretation; a small spelling map is not a guarantee of understanding every typo or language.

**Answer with** offers Auto, Gemini only and Groq only. Auto tries the configured Gemini model first and restarts the entire draft-and-review workflow on Groq after availability, authentication or quota failure. Safety refusals and unsupported/malformed answers do not trigger a hunt for a more permissive answer. Each research note records its actual provider/model and fallback attempts. An API request omitting `provider` follows `LLM_PROVIDER`; the UI sends its explicit selection.

The reader now resumes at recognized appendices after skipping references. Existing library records need explicit reindexing to gain this coverage. Exact table references and quantitative lookups retrieve nearby original caption/header/data blocks; this helps text-based tables but is not visual table understanding. Overviews prioritize original abstract/introduction/conclusion text. Appendix prompt templates are deprioritized unless the question asks about prompts or instructions.

Each source passage has an explicit span ID. Quotes are copied locally, their original PDF pages resolved, and every clause reviewed against only its cited quotes. Arithmetic stays labeled as inference and is checked again if review changes the classification. These controls can still miss semantic errors or withhold useful answers. No promise of hallucination-free output is made.

## Supplied-paper evaluation

`reports/paper-evaluation/` preserves pilot failures and complete versioned runs for the 43-page VeriTrail paper. The question set was frozen before seeing answers. The first complete run exposed under-answering, invalid span selection and retrieval gaps; it is preserved rather than overwritten. Read each run’s independent accuracy review, not just the number of retained claims. The set is an assistant-authored development evaluation, not independent human validation or a general accuracy estimate.

```powershell
python scripts/evaluate_paper.py --paper path/to/paper.pdf --questions path/to/questions.json
python scripts/evaluate_paper.py --paper path/to/paper.pdf --questions path/to/questions.json --provider auto --live
```

The first command runs retrieval only. `--live` explicitly permits hosted inference. A source hash prevents accidentally evaluating a different PDF. The runner records each case and stops after two consecutive provider failures. Browser generation/error checks are intercepted with a recorded fixture and do not consume model quota; paper answer evaluation uses real APIs.
