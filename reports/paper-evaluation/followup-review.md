# Targeted follow-up answer audit

Two separate targeted development follow-ups; do not merge them into or substitute for the v9 full-run scores.

## guard-v2-followup/vt05.json

Prompt: v9-primary-table-context; guard: v2-purpose-qualification; provider: gemini / gemini-3.5-flash-lite.

Judgment: **partial**. Retained: 2; withheld: 0.

Two retained claims accurately describe evidence-trail contents and provenance on pages 5–6. The earlier unqualified ambiguity-avoidance claim is absent in this fresh answer. The answer still omits sentence-ID assignment/invalid-ID rejection, so it is a safer partial answer, not a full method explanation.

## comparison-followup/vt08.json

Prompt: v10-comparison-completeness; guard: v2-purpose-qualification; provider: gemini / gemini-3.5-flash-lite.

Judgment: **over_abstention**. Retained: 0; withheld: 3.

The generator drafts the correct values and calculates 14.9 percentage points for FABLES+ (and 4.4 for DiverseSumm+), but all three claims are withheld because the cited numeric rows do not establish dataset/metric mappings. No numeric answer reaches the reader. This is strict fail-closed citation checking, not a successful end-to-end arithmetic answer.

## table-context-followup/vt08.json

Prompt: v10-comparison-completeness; guard: v3-original-table-context; provider: gemini / gemini-3.5-flash-lite.

Judgment: **supported**. Retained: 3; withheld: 0.

All three retained claims are correct for Table 1 on PDF page 8. Original caption/header quotations now accompany the numeric rows, resolving the dataset/metric context gap. The answer correctly gives the requested FABLES+ absolute difference of 14.9 percentage points and labels the arithmetic as inference. The extra DiverseSumm+ comparison is unrequested but also correct (4.4 percentage points). This is one targeted successful case, not a replacement for the preserved v9 full-run results.

## Interpretation boundary

The final table-context follow-up validates this single arithmetic answer with its original row, caption and header evidence. It does not convert the earlier v9 12-case run into a successful arithmetic run or establish general citation accuracy. No model calls were made by this audit.
