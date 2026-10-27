# Final live-answer qualitative audit

Audited 27 October 2026 against the delivered `v4-reported-and-inferred` evaluation. A separate coding-agent pass inspected the retained claims, their selected source spans and the full original-text evidence embedded in each result. This is a qualitative development audit, not independent human evaluation, a held-out benchmark, or a numerical accuracy estimate. No API calls were made for this audit.

**Conclusion:** the system provides inspectable evidence, useful answers on several focused questions, and appropriate abstention on the unavailable laptop measurement. Scientific synthesis still needs human review. In particular, q13 retains an overgeneralized finding that mixes a design recommendation into a claim labeled as reported evidence. Valid citation IDs, copied spans and a model review do not eliminate these errors.

## Case findings

| Case | Assessment |
|---|---|
| q02 — RAG-Sequence versus RAG-Token | The four retained reported claims correctly distinguish one document-latent choice per sequence from per-token document marginalization. The embedded RAG Methods passages establish these mechanisms. This is a useful, sufficiently complete answer to the question; the wording does not imply that only one candidate document is retrieved. |
| q06 — QuALITY gain versus retrieval speed | The retained **inference** correctly calculates 82.6 − 62.3 = 20.3 percentage points from the cited RAPTOR result. The limitation correctly says the supplied evidence does not provide retrieval-speed measurements. The requested distinction would be clearer if it explicitly stated that QA accuracy is a different metric from latency, rather than merely declining a speed comparison. The partial-evidence flag is conservative; it is not a failed arithmetic result. |
| q08 — ALCE citation recall and precision | The reported findings correctly describe collective support from concatenated citations and the irrelevance/removal criterion for precision. The existence-versus-support explanation is now explicitly labeled **inference**, which is appropriate. Recall should be read as joint entailment by the citation set, not a requirement that one individual citation alone entails the statement. The supporting embedded ALCE definitions establish that distinction. This answer substantially addresses the question. |
| q12 — RAPTOR versus HiChunk hierarchy | The retained reported findings broadly match RAPTOR recursive clustering/summarization and HiChunk multilevel chunk points, fixed-size chunks and Auto-Merge. The comparison remains incomplete about RAPTOR's concrete retrieval procedures. Part of the sentence-ID preprocessing detail appears in the full embedded Methodology passage rather than the selected short excerpts. The HiChunk extraction also contains a duplicated mathematical phrase, which makes its citation difficult to read. The limitation appropriately declines a RAPTOR-versus-HiChunk latency ranking; no controlled latency comparison appears in the supplied pack. |
| q13 — Three-paper design synthesis | **Needs correction before treating it as an authoritative synthesis.** The RAPTOR claim calls the observed outcome “retrieval performance,” while the supporting comparisons measure downstream QA/F1 results under particular experimental settings. Its description should name those conditions and metrics. The positional-bias claim is labeled **reported**, but generalizes a specific Llama-2 size experiment to large language models broadly and incorporates an evidence-ordering recommendation into that same claim. The source supports recency bias for the tested smaller model and a U-shaped curve for the tested larger models; it does not establish that evidence should simply be spread evenly for larger models, since middle-position weakness remains. The separately labeled **inference** about combining hierarchical summaries and dense passage retrieval is a plausible design proposal, not a demonstrated best configuration or latency improvement. Its cited excerpts give partial motivation rather than establish every proposed wiring detail. |
| q15 — Dell G15 / RTX 3050 median latency | **Correct abstention.** No retained numerical claim was produced, and the answer explicitly says that the sources do not measure those systems on this laptop. This final result successfully avoids the invented laptop timings observed during the earlier local-model experiment. It does not establish universal abstention reliability. |
| q17 — HiChunk learning rate | The retained reported value, **1e-5**, is supported by the retrieved Experimental Settings passage on PDF page 8. This is answerable in the full-paper retrieval setting. It was unavailable in the earlier deliberately restricted evidence pack, so this final answer must not be scored as a failure to abstain merely because that earlier question was labeled unavailable. |
| q18 — Incomparable quantitative results | **No final v4 answer was returned:** Groq responded with HTTP 429 / `rate_limit_exceeded`. The final behavior for this case is therefore untested, not passed. Any older `live-q18.json` present belongs to a previous development version and is excluded from this audit. |

## Remaining limits

- The final reported/inference labels help separate findings from proposals, but q13 shows that a claim can still be mislabeled or mix both categories.
- The same provider model generates and reviews claims; correlated errors and overly strict rejections remain possible. The deterministic checks address selected failure types, not general scientific entailment.
- Short copied spans can omit a necessary experimental condition even when the complete retrieved passage contains it. Users should open the full evidence and original PDF.
- Repeated use of these development questions informed fixes. They do not establish performance on a disjoint literature corpus or on unseen synthesis tasks.
- The final run returned seven answers and one explicit quota failure. Free-tier throttling is an observed operational constraint, and the unsuccessful q18 request must remain visible in the test report.

## Exact audited result bindings

The result IDs below match the final evaluation record. SHA-256 values bind this audit to the complete JSON files read for the review; subsequent regeneration requires a new audit.

| Case | Result ID | JSON SHA-256 |
|---|---|---|
| q02 | `548b390377604fa78b8e5b8a1edb8df0` | `7d76d3bb0daa1c20f7ff7dd392f3a284ef947e33d5a227571459f1ebe058fea8` |
| q06 | `8a8d055847d347b2a8ca3e91d839ef75` | `477ca5cd36e048a74e8628a50d247df388adc7d99f28c274087c1b9efc5131f5` |
| q08 | `941a551a0ee8454b80ec6430f32e2c45` | `233bb0e26e58fffc80d45b866c3073952505fd94db3ae88c1fa5291bd05b26f2` |
| q12 | `c63117da361c44d1b99b8a22992808aa` | `bcfef66526fc18dbb31605afbc0212150b8ac3d5fea2e1cc97247175a2c02264` |
| q13 | `5ec8d23cbe3241ecab51140a7472c54e` | `a8372c7e59e1a0ab92d90090a0320134249b28addd1ee813e74ceaccb385fa91` |
| q15 | `d1a1fadd16f44a918907f249842de624` | `31503908899a89a00c629878eb98cff01fb25f3827588d62bffab2a61073bd74` |
| q17 | `5d44c82fccdf4c68a307e8cccb57068c` | `0f7e89f49770c73eface3ade6cce50b2893f5bf2e035feb15b9dee58be8356d5` |

The v4 `evaluation.json` is the authority for the failed q18 request; there is no corresponding audited final-result hash.
