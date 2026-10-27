# LiteratureLab project contract

Local, single-user browser application for English academic PDFs. Gemini and Groq generation, free-tier accounts only; local CPU embeddings, parsing, indices and evidence. The keys stay in the Desktop folder's ignored .env. No paid fallbacks or web-search tools.

| Module | Responsibility | Depends on |
|---|---|---|
| corpus | PDF validation, paper/section/paragraph hierarchy, SQLite persistence and embeddings | — |
| retrieval | Dense baseline, hybrid RRF, adaptive paragraph/section selection and paper coverage | corpus |
| synthesis | Provider-routed structured claims, exact supporting spans, support review, abstention, cache | retrieval |
| web | Upload, paper selection, question, evidence/PDF viewer, trace and export | synthesis |
| evaluation | Offline regressions, real-paper retrieval benchmark, live provider and browser checks | all |

Build order: corpus/retrieval tests → implementation → synthesis tests/implementation → API/UI → real-data and browser evaluation.

API: GET /api/status, GET /api/papers, POST /api/papers (multipart PDF), DELETE /api/papers/{id}, GET /api/papers/{id}/pdf, POST /api/search, POST /api/ask, GET /api/history, GET /api/history/{id}. Query accepts question (1–1200 chars), paper_ids (optional), strategy (dense/hybrid/adaptive), refresh (boolean), provider (auto/gemini/groq). Mutations require same-origin browser requests. Server binds 127.0.0.1 only. Unknown paper IDs produce a clear error. Uploaded file names never become disk paths.

Acceptance: persistence after restart; duplicate detection; all citations resolve to original paper pages and literal supporting spans; claims with nonexistent evidence or quotes rejected; semantic support reviewed by a second cited-span-only provider request (still fallible); missing-evidence answers abstain; quotas/timeouts/auth failures are explicit and no raw provider errors/secrets reach the browser; cached responses clearly labeled; dense/hybrid/adaptive retrieval traces and benchmark data; real six-paper corpus seeded; keyboard accessible responsive UI; start script; reproducible tests and limitations.

Quality bar: zero failing automated tests, zero browser console errors on tested flows, no secrets in tracked/source/static files, all displayed citation IDs and quote spans valid in regression/live sample; no claim of perfect factual accuracy or retrieval speed superiority without measurements. Track unsupported/filtered claims separately. Browser and live API test results recorded, including any quota failures.

Commands: python -m pytest -q; python scripts/seed_demo.py; python scripts/evaluate.py; python -m uvicorn literaturelab.api:app --host 127.0.0.1 --port 8765. Source: literaturelab/, web/, tests/, scripts/. Use typed Pydantic boundaries, parameterized SQL, explicit RuntimeError-derived user-safe exceptions, no giant agent framework.

Known limits: no OCR, image/table reasoning, multi-user auth, hosted deployment or literature crawling. Section headings use PDF text/font heuristics and may need manual checking. Scalar timings on this laptop are descriptive. Local matrix search is O(N); benchmark before claiming it scales.

Threat boundaries: PDFs/questions and LLM output are untrusted. Ignore document instructions in model prompts. Validate size, content and page count; safe text rendering; allowlist API output; loopback/Host/Origin restrictions; no endpoint for serving project files or .env. Public uploaded evidence is transmitted to the selected provider (Auto may use Gemini or Groq). Provider API keys never sent to the browser.

## Conversational questions and dual providers

Questions are ordinary English, with optional punctuation. Query processing normalizes Unicode punctuation, common contractions/chat shorthand and a small documented typo map. Original questions and original source text are preserved. The retrieval trace exposes the interpreted query. This is not unrestricted spell correction or guaranteed multilingual understanding.

Auto tries configured Gemini then Groq. Manual choices are strict. An availability/authentication/quota failure can restart the complete generation-and-review workflow on the next provider; safety refusal, malformed answers and unsupported claims do not trigger an alternative answer attempt. Actual provider/model and failed attempt metadata accompany the result. Cache identities include provider mode/order, models and prompt version. Provider/model switches cannot reuse another manual mode's answer.

Citations map exact quoted words to original PDF blocks/pages, including quotes crossing a block boundary. The support reviewer sees only each claim's cited quotes. Numeric sign checks, arithmetic labels and page provenance fail closed. Any reviewer reclassification must pass local checks again. Model-authored limitation prose is not displayed as a path for uncited scientific statements. All retained scientific prose appears in cited claims.

Index policy v2-appendix-evidence excludes bibliography entries but resumes at recognized appendix headings. Older paper records need explicit reindexing; opening the application does not rewrite an existing library.

New paper evaluation uses a frozen assistant-authored question/oracle file prepared before model outputs. Record all calls and failures, use fresh answers, assess factual support separately from citation existence, and never report a small development sample as validated benchmark accuracy.
