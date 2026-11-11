# NCKH12 Competition Rehearsal

## Before the presentation

1. Double-click `START_COMPETITION_DEMO.bat`.
2. Confirm the Home screen opens directly and the hero image is visible.
3. Keep the computer plugged in and close unrelated heavy applications.
4. Use Fast Demo for the judged presentation. It is local, verified and predictable.

## Primary demo: Demo Student B

1. Select **Try a Demo**.
2. Keep **Demo Student B | Main demo | D043** selected.
3. Choose **View genuine results**.
4. Explain that the short processing sequence represents verified local stages, not a cloud call.
5. Introduce the four criteria:
   - Pronunciation: preliminary MultiPA evidence.
   - Fluency: measured timing and continuity evidence.
   - Prosody: preliminary rhythm, stress and intonation evidence.
   - Reading Completeness: ASR-assisted target coverage.
6. Show the three feedback cards and the supported words-to-review chips.
7. Open **See why you received these scores** and explain that ASR uncertainty is not automatically a learner error.
8. Open **How does the AI work?** and describe extraction, pretrained analysis, timing/coverage and development validation.
9. Open **Research validation** and state that N=3 mini-validation is descriptive only.
10. Close with the learning value: the system turns a completed Duet into criterion-level practice guidance while preserving uncertainty.

## Backup examples

- **D064, Demo Student A:** use as a consistency example with strong continuity and no measured long pauses.
- **D048, Demo Student C:** use when judges ask about limitations. It shows why preliminary criteria and evidence review remain visible. Do not call it a failed sample.
- Prefer Fast Demo if live inference timing is risky.

## Presenter mode

Add `&presenter=1` to the competition URL only when technical provenance is needed. Presenter mode can:

- show raw scorer and feedback provenance;
- export the current GPT review bundle;
- validate and import a structured review JSON.

Presenter mode never shows teacher ratings and cannot alter official numeric scores.

## Recovery instructions

### Live model fails

Return to Home and use **Try a Demo**. Known demos do not depend on a new live inference run.

### Recording is NOT_SCORABLE

Explain that the system refuses to fabricate scores when learner speech or audio quality is insufficient. Use a known demo next.

### GPT review is unavailable

Continue normally. The deterministic evidence-based feedback layer is always available offline and the UI does not show a blank state.

### Internet is unavailable

Use Fast Demo. All known demo results, local media verification and feedback fallback work without Internet access.

### Cache validation fails

Do not bypass the guard. Restart the app and use another verified demo. After the presentation, run the cache verification tests before rebuilding anything.

## Final presentation rule

Do not change scorer files, target logic, criterion definitions or validation interpretation after `COMPETITION_FREEZE_V1`. Only documented UI copy or crash fixes are allowed unless a severe correctness bug is found.
