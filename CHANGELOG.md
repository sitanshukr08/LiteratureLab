# Development record

## 0.2.0 — 27 October 2026

- Added Gemini plus strict manual provider selection and complete-workflow Auto failover to Groq. Availability failures can fall back; safety refusals and unsupported answers cannot.
- Added conversational query normalization, appendix indexing, overview context and explicit table-neighbor retrieval.
- Replaced implicit citation positions with printed span IDs. Reviews see only cited quotes; page mapping and reviewer reclassification are revalidated locally.
- Made scientific answer prose more natural while keeping each claim source-linked.
- Added offline transport blocking, provider/cache/API/guardrail regressions and a frozen supplied-paper live evaluation. Earlier incomplete runs remain recorded.


## 0.1.0 — 27 October 2026

Built a local Groq-powered literature workspace with PDF uploads, persistent paper/section/paragraph records, CPU BGE embeddings, dense/BM25/RRF/adaptive retrieval, cited claims, source-page navigation, saved notes, exports, and evaluation views.

### Changes prompted by actual failures

- Explicitly separated reported findings from grounded logical/design inferences after strict source checking caused false abstentions. Both remain source-linked; inference labels do not establish experimental validity.
- Diagnosed Groq HTTP400 `json_validate_failed` responses and added bounded decoding retries, with attempt counts retained. Valid answers are never retried to select a preferred result.

- Initial generated quotes sometimes changed the source wording. Replaced model transcription with stable source-span indexes and client-side copying. Exact span/ID validation remains fail-closed.
- Same-model support review accepted an improperly sourced numerical/timing assertion. Added local numerical, stated-difference, threshold, metric-confusion and source-uncertainty guards. These conservative rules are additional checks, not proof of entailment.
- Algorithm step numbers were mistaken for section headings. Retrieval review added typography and small-capital handling, with real RAPTOR checks. Rebuilt the complete library after the parser fix.
- Global ranking and large sections could omit an explicitly requested paper. Added per-paper candidate fallback, fair evidence budgets and missing-paper/truncation trace fields.
- Dense baseline unnecessarily executed BM25. Removed that work before final performance measurements.
- Missing Content-Length allowed an upload-limit bypass. POST requests now require a bounded declared length; regression test added.
- Unicode decoding depended on the Windows code page. Curl JSON responses now decode explicitly as UTF-8.
- Old system packages caused conflicts and dependency findings. Isolated the environment, updated compatible packages and recorded exact versions/advisory results. Embedding compatibility checked before retaining vectors.
- Old Playwright conflicted with modern Edge's PDF viewer. Updated the driver and completed a clean browser-test shutdown.
- UI errors could leave stale answers, upload text or a hidden error panel. Browser review corrected those states, citation page navigation and workspace accessibility attributes.

The initial and second live evaluations remain in ignored local `reports/development-v1` and `reports/development-v2` directories. The final fixed-set run is `reports/evaluation.json`; the per-answer records remain local. Earlier unsuccessful requests are not presented as passed tests.

- Final independent assistant audit still found overgeneralization in the broad synthesis. The interface and exports therefore explicitly label outputs as drafts; no perfect scientific-reliability claim is made. Final free-tier evaluation retained the HTTP429 failure rather than replacing it with an older answer.

### Review ownership

- Integration owner: generation, API, local grounding checks, real API evaluation, final synchronization and verification.
- Retrieval subagent: heading/parser/ranking/budget regressions; independent read-only live-evidence audit.
- Browser subagent: UI correctness, real Edge flows, quota/error recovery, desktop/mobile visual checks.
- Security subagent: source-boundary review, isolated environment, compatible dependency updates and advisory check.

No external repository was pushed or published. The supplied API key remains only in the ignored Desktop `.env`; test credentials are synthetic. Remaining limitations are recorded in the test report and README.
