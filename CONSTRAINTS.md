# Project quality bar

1. Groq only for remote inference. No automatic paid-provider fallback, paid tools, or billing-plan changes. Keep the account on its free plan.
2. Secrets remain backend-only in ignored `.env`. Never include them in source, logs, static resources, screenshots, reports or repository history.
3. No failing automated regression tests in the delivered state. Preserve regressions for observed failures rather than deleting or skipping them to pass.
4. Real browser checks must finish cleanly and distinguish intentional rejected requests from unexpected errors. Test uploads, sources, exports, quota recovery and narrow layouts.
5. Displayed citation IDs resolve to the retrieved original source; cited spans match original text. Missing references or unsupported numerical/threshold assertions are withheld, not silently repaired.
6. Treat source-span validity, LLM support review and scientific entailment as separate properties. Record false acceptances and false rejections. No claim of perfect citation faithfulness or an independent human benchmark.
7. Preserve PDF page provenance and selected-paper coverage; explicitly report coverage missing because of a budget or source gap.
8. Benchmark dense, hybrid and adaptive retrieval on the same questions and ceiling. Report measured times even when the proposed method is slower; paper identity coverage is not semantic relevance.
9. Keep complete development outcomes and identify revised versions/cache hits. Do not cherry-pick one successful answer and present it as repeated-run accuracy.
10. Scope is a single local user with text-based PDFs. OCR, image/table reasoning, multi-user access and hosted deployment need separate work and validation.
