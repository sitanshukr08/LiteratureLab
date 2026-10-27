# LiteratureLab project contract

Local, single-user browser application for English academic PDFs. Groq generation, free-tier account only; local CPU embeddings, parsing, indices and evidence. The key stays in the Desktop folder's ignored .env. No paid fallbacks or web-search tools.

| Module | Responsibility | Depends on |
|---|---|---|
| corpus | PDF validation, paper/section/paragraph hierarchy, SQLite persistence and embeddings | — |
| retrieval | Dense baseline, hybrid RRF, adaptive paragraph/section selection and paper coverage | corpus |
| synthesis | Groq structured claims, exact supporting spans, support review, abstention, cache | retrieval |
| web | Upload, paper selection, question, evidence/PDF viewer, trace and export | synthesis |
| evaluation | Offline regressions, real-paper retrieval benchmark, live Groq and browser checks | all |

Build order: corpus/retrieval tests → implementation → synthesis tests/implementation → API/UI → real-data and browser evaluation.

API: GET /api/status, GET /api/papers, POST /api/papers (multipart PDF), DELETE /api/papers/{id}, GET /api/papers/{id}/pdf, POST /api/search, POST /api/ask, GET /api/history, GET /api/history/{id}. Query accepts question (1–1200 chars), paper_ids (optional), strategy (dense/hybrid/adaptive), refresh (boolean). Mutations require same-origin browser requests. Server binds 127.0.0.1 only. Unknown paper IDs produce a clear error. Uploaded file names never become disk paths.

Acceptance: persistence after restart; duplicate detection; all citations resolve to original paper pages and literal supporting spans; claims with nonexistent evidence or quotes rejected; semantic support reviewed by a second Groq request (still fallible); missing-evidence answers abstain; quotas/timeouts/auth failures are explicit and no raw provider errors/secrets reach the browser; cached responses clearly labeled; dense/hybrid/adaptive retrieval traces and benchmark data; real six-paper corpus seeded; keyboard accessible responsive UI; start script; reproducible tests and limitations.

Quality bar: zero failing automated tests, zero browser console errors on tested flows, no secrets in tracked/source/static files, all displayed citation IDs and quote spans valid in regression/live sample; no claim of perfect factual accuracy or retrieval speed superiority without measurements. Track unsupported/filtered claims separately. Browser and live API test results recorded, including any quota failures.

Commands: python -m pytest -q; python scripts/seed_demo.py; python scripts/evaluate.py; python -m uvicorn literaturelab.api:app --host 127.0.0.1 --port 8765. Source: literaturelab/, web/, tests/, scripts/. Use typed Pydantic boundaries, parameterized SQL, explicit RuntimeError-derived user-safe exceptions, no giant agent framework.

Known limits: no OCR, image/table reasoning, multi-user auth, hosted deployment or literature crawling. Section headings use PDF text/font heuristics and may need manual checking. Scalar timings on this laptop are descriptive. Local matrix search is O(N); benchmark before claiming it scales.

Threat boundaries: PDFs/questions and LLM output are untrusted. Ignore document instructions in model prompts. Validate size, content and page count; safe text rendering; allowlist API output; loopback/Host/Origin restrictions; no endpoint for serving project files or .env. Public uploaded evidence is transmitted to Groq. Provider API key never sent to the browser.
