# PROJECT_STATE.md

# Project: Reference-Aware TikTok Duet Speaking Assessment Research System

## 1. Purpose of this file

This file is the technical source of truth for the project.

Codex and any future implementation agent should read this file before making architectural changes.

After every meaningful sprint, update this file with:
- what was implemented;
- measured results;
- decisions made;
- known limitations;
- current phase status;
- next task.

Do not rewrite historical decisions without recording why they changed.

---

# 2. Project goal

Long-term research goal:

Use TikTok Duet as a speaking-practice environment for Grade 10 EFL learners, with AI-assisted formative speaking assessment and feedback.

The research system is NOT intended to record Duets itself.

Workflow:

Student completes TikTok Duet
→ uploads completed Duet
→ system isolates learner speech
→ speaking assessment
→ formative feedback
→ learner practices again

The current engineering priority is NOT pronunciation scoring yet.

The immediate objective is to reliably locate the learner's speech in a completed TikTok Duet.

---

# 3. Simplified project phases

## PHASE 1 — Learner Speech Extraction

Question:

> Where is the learner speaking in the completed Duet?

Input:
- original/template TikTok video;
- completed TikTok Duet.

Canonical output:
- learner speech timestamps;
- confidence/diagnostics;
- overlap candidates.

Main components:
- media normalization;
- template/reference alignment;
- reference cancellation;
- VAD;
- segment post-processing;
- validation;
- Research Console.

Phase 1 must be validated before Phase 2 begins.

---

## PHASE 2 — Speaking Assessment Engine

Question:

> How well did the learner speak?

Potential dimensions:
- pronunciation / accuracy;
- fluency;
- completeness;
- prosody / intonation.

Possible future technologies:
- ASR;
- forced alignment;
- phoneme analysis;
- GOP;
- wav2vec2;
- faster-whisper;
- GOPT / Echoic or related research implementations.

Do not implement this phase before learner speech extraction is sufficiently reliable.

---

## PHASE 3 — Feedback & Learning System

Question:

> How can the system help the learner improve?

Pipeline:

measured speech errors
→ scores / diagnostics
→ understandable formative feedback
→ next practice

LLMs may be used to explain already-measured errors, but must not invent pronunciation scores from transcripts alone.

---

## PHASE 4 — Research Product & Deployment

Question:

> How do we package the validated system for the actual study?

Potential components:
- student upload workflow;
- teacher/researcher dashboard;
- assignment/task management;
- progress history;
- research-data export;
- deployment for the quasi-experimental study.

Do not over-engineer infrastructure before the core research pipeline is validated.

---

# 4. Current phase

CURRENT PHASE:

## PHASE 2 - Speaking Evidence Validation

Current sub-stage:

> P2.2A target text and six human ASR references are confirmed. True WER selected small.en and selected-backend evidence exists for 12 development videos. The 12-video human speaking-rating queue is still 0/12, so calibration, criterion scores, feedback, and the competition result demo remain blocked.

---

# 5. Current best architecture

The current best method is NOT generic two-speaker diarization.

The preferred architecture is:

Original/template video
→ FFmpeg normalization
→ reference alignment
→ aligned reference audio
→ known-reference cancellation against completed Duet
→ learner-dominant residual
→ Silero VAD
→ learner speech timestamps

Important:

The cancelled/residual audio is used for DETECTION only.

The canonical output is TIMESTAMPS.

Any future pronunciation/scoring system should crop audio from the original, unprocessed Duet source audio using those timestamps.

Do not use residual_detection.wav as pronunciation-scoring input.

---

# 6. Why this architecture was chosen

The real sample pair showed that the original/template audio is preserved inside the completed Duet after a stable time offset and amplitude scaling.

This means the task can be treated primarily as a known-reference problem rather than asking a generic diarization model to rediscover both speakers from scratch.

Advantages:
- simpler;
- more deterministic;
- easier to debug;
- cheaper;
- runs locally;
- easier to explain in a research methodology;
- exploits information specific to TikTok Duet;
- does not require speaker identity recognition.

---

# 7. Current implementation status

Implemented in v0.1:

- CLI pipeline;
- FFmpeg media normalization;
- coarse + fine reference alignment;
- alignment diagnostics;
- aligned reference construction;
- linear reference cancellation;
- experimental AEC3 backend;
- Silero VAD;
- learner timestamp extraction;
- overlap-candidate detection;
- outside-template handling;
- JSON outputs;
- learner preview WAV;
- debug plots;
- unit tests;
- optional evaluation framework.

Current CLI pipeline runs successfully on the known original/Duet pair.

---

# 8. Known measured baseline

Known real sample:

Original/template:
- duration ≈ 88.675 s;
- AAC stereo, 44.1 kHz.

Completed Duet:
- duration ≈ 91.347 s;
- AAC stereo, 44.1 kHz.

Normalized processing sample rate:
- 16 kHz mono.

Measured alignment:

- coarse offset ≈ -0.7000 s;
- final offset b = -0.6945625 s;
- time-scale a = 1.0;
- offset variation across accepted anchors = effectively 0 on this sample.

Eight accepted anchor correlations:

- 0.9879
- 0.9939
- 0.9207
- 0.9281
- 0.9438
- 0.9839
- 0.9533
- 0.9845

Interpretation:

Reference alignment is currently very strong on the known sample.

Cancellation:

- selected backend: linear;
- estimated reference gain ≈ 0.34522;
- measured reference suppression ≈ 14.74 dB;
- AEC3 suppression ≈ 2.60 dB on this sample.

Decision:

Automatic mode correctly fell back from AEC3 to linear cancellation.

Runtime on the known sample:
- ≈ 11.64 s.

Current prediction:
- 22 learner intervals;
- 4 possible overlap intervals;
- 0 outside-template detections.

Important:

These are engineering measurements, NOT accuracy measurements.

No completed human ground truth has yet been used to establish true learner precision/recall/F1.

---

# 9. Current provisional validation targets

These are engineering gates, not final scientific claims.

Initial targets:

- learner precision ≥ 0.95;
- learner recall ≥ 0.95;
- learner F1 should be reported;
- original contamination ≤ 0.03;
- median turn-boundary error ≤ 0.25 s;
- false speech outside template ≈ 0.

These thresholds may be revised after evaluation on multiple real Duets.

Do not claim Phase 1 is solved from one video.

---

# 10. Current predicted segments on the known sample

The current v0.1 run produced 22 candidate learner segments.

Do not hard-code them into production logic.

They are test outputs only.

Four intervals are currently flagged as possible overlap:

- approximately 0.000–1.287 s;
- 40.514–40.894 s;
- 52.130–52.990 s;
- 73.698–74.046 s.

These overlap flags have not yet been manually validated.

---

# 11. Important architectural decisions

## Decision A — Do not use stereo channels to separate speakers

The Duet channels are nearly identical mixed audio.

Do not assume:

left audio channel = original speaker
right audio channel = learner

---

## Decision B — pyannote is NOT the primary architecture

Generic speaker diarization may be kept as a research baseline or fallback.

Do not make pyannote mandatory for the core pipeline.

Reason:

The original/template is known and provides much stronger prior information.

---

## Decision C — Active Speaker Detection is a fallback, not v0.1 backbone

LR-ASD or another active-speaker model may be introduced if real validation shows failures involving:
- overlap;
- poor cancellation;
- ambiguous residual speech;
- reference mismatch.

Do not add ASD simply because it is more "AI".

Every new model must solve an observed failure mode.

---

## Decision D — Speech separation is not currently required

Do not introduce generic source separation unless real overlap cases demonstrate that it is necessary.

Potential separation artifacts may damage future pronunciation/prosody analysis.

---

## Decision E — timestamps are canonical

Primary result:

start/end timestamps on the completed Duet timeline.

Generated concatenated WAV files are convenience/debug artifacts only.

---

## Decision F — residual audio is detection-only

Never use cancellation output as the canonical pronunciation-assessment audio.

Always crop future scoring audio from the unprocessed Duet source using predicted learner timestamps.

---

## Decision G — uncertainty must remain visible

The system must not silently pretend uncertain output is correct.

Keep diagnostics such as:
- alignment confidence;
- anchor consistency;
- cancellation suppression;
- overlap candidates;
- warnings.

If alignment/cancellation is unreliable, report it explicitly.

---

# 12. Current known limitations

1. The known pair has a user-reviewed development label set, including a full-video check for completely missed learner turns, but only 41.8% of the timeline has interval labels and accepted learner boundaries derive from baseline predictions. It is not independent complete-timeline ground truth.

2. Only one original/Duet pair has been deeply validated.

3. The baseline has 22 predictions; the leakage-filtered default has 21 after rejecting S001. VAD development tuning can reduce the count to 12 (11 with leakage filtering), but that setting is not a global default and needs multi-video validation.

4. Some overlap candidates may actually be cancellation residue rather than true human overlap.

5. AEC3 performed substantially worse than linear cancellation on the known sample.

6. Generalization across:
   - other templates;
   - other learners;
   - devices;
   - TikTok export/download methods;
   - background noise;
   - quiet speakers;
   - true overlap;
   has not yet been established.

7. Confidence currently reflects detection strength, not calibrated probability that a segment belongs to the learner.

---

# 13. Previous planned sprint (Research Console v0.2, now completed)

## DUET SPEECH LAB — RESEARCH CONSOLE v0.2

Purpose:

Build a local researcher-facing UI around the existing pipeline.

This is NOT the final student application.

Recommended stack:

- Streamlit;
- Plotly;
- Pandas.

The Research Console should allow:

1. choose/upload original template;
2. choose/upload completed Duet;
3. run the existing v0.1 pipeline;
4. display summary diagnostics;
5. inspect an interactive timeline;
6. listen to each predicted learner segment;
7. review/correct segment labels and boundaries;
8. save human ground truth;
9. immediately evaluate predictions;
10. show precision / recall / F1 / contamination / boundary error;
11. retain diagnostic artifacts and run configuration.

Do not duplicate DSP logic inside the UI.

The UI must call the existing Python segmentation modules.

---

# 14. Why the Research Console was selected as the next task

The current bottleneck is no longer basic feasibility.

The current bottleneck is validation speed.

Without a UI, the workflow is:

CLI
→ JSON
→ PNG
→ WAV
→ manual inspection

The Research Console should make it:

Original + Duet
→ Run
→ interactive timeline
→ listen
→ correct
→ evaluate

The UI therefore acts simultaneously as:

- debugger;
- annotation tool;
- evaluation tool;
- experiment tracker;
- technical demo.

This should accelerate Phase 1 rather than distract from it.

---

# 15. Dataset / robustness plan

After the Research Console works, collect additional real Duet pairs.

Near-term target:

- several different original templates;
- multiple learners per template where possible;
- approximately 10–20 Duets as an early robustness set.

Include diverse cases:
- normal speaking;
- quiet speaking;
- fast speaking;
- background noise;
- short pauses;
- true overlap;
- different phones/export methods.

Do not tune the system only against the current single video.

---

# 16. Rules for future Codex work

Before every sprint:

1. Read PROJECT_STATE.md.
2. Preserve working functionality unless the task explicitly requires changing it.
3. Do not jump to a later phase.
4. Do not add a large model without an observed failure mode.
5. Run the known real sample after meaningful changes.
6. Report measured outputs, not "works successfully".
7. Update PROJECT_STATE.md at the end of the sprint.

At the end of each sprint, append/update:

- implementation summary;
- files changed;
- tests;
- real-pair measurements;
- regressions;
- new decisions;
- known limitations;
- next task.

---

# 17. Explicit out-of-scope items right now

Do NOT implement yet:

- Whisper / ASR;
- pronunciation scoring;
- fluency scoring;
- prosody scoring;
- LLM feedback;
- final student UI;
- database;
- authentication;
- cloud deployment;
- TikTok URL downloader;
- React frontend;
- teacher class management.

These belong to later phases.

---

# 18. Previous immediate task (Research Console v0.2 sprint, completed 2026-09-15)

Build:

## DUET SPEECH LAB — RESEARCH CONSOLE v0.2

Then return the implementation results for review BEFORE proceeding to another major feature.

Required review evidence should include:

- screenshot(s) of UI;
- startup command;
- known-pair runtime;
- whether all current predictions load;
- whether selected-segment audio playback works;
- whether ground-truth editing/export works;
- whether evaluation works;
- tests;
- files changed;
- known limitations.

Do not proceed to Phase 2 until Phase 1 validation is reviewed and accepted.

---

# 19. Research Console v0.2 sprint result (2026-09-15)

## What was implemented

- A local Streamlit researcher console in `app.py`, using Plotly and Pandas around the existing `duet_segmenter` Python API. The independent CLI remains usable.
- Original/Completed Duet selection from workspace MP4s or uploads; Run Analysis calls the existing pipeline with progress updates.
- Prominent status, duration, alignment, anchor, gain, suppression, backend, runtime, segment, overlap, and outside-template cards with visible warnings.
- Interactive Duet-timeline rows for ORIGINAL, PREDICTED_LEARNER, OVERLAP, OUTSIDE_TEMPLATE, and optional RESIDUAL_VAD. Empty diagnostic rows remain visible; hover shows interval data.
- Editable segment review with human labels and corrected boundaries, a quick predicted-segment review mode, audio clips with 0/0.5/1.0 s context from the native-rate, stereo Duet source WAV, and Streamlit's native Duet video player.
- Separate `review.json` and `ground_truth.csv` export plus immediate evaluation through the existing evaluation module. A manual interval editor allows annotating missed learner speech and other timeline states. Partial ground truth is labeled as such, and cannot show a provisional PASS.
- Dated `runs/` folders with copied source videos, exact `config.json`, input SHA-256 hashes, config hash/run ID, and all pipeline artifacts. Streamlit is configured for `127.0.0.1` only.
- Advanced diagnostics retain raw JSON, alignment table, plots, VAD config, warnings, and detection-only residual audio.

## Files changed

- Added: `app.py`, `.streamlit/config.toml`, `duet_speech_lab/__init__.py`, `duet_speech_lab/console.py`, `scripts/browser_smoke.py`, `tests/test_console.py`, `tests/test_console_ui.py`, `tests/test_console_integration.py`.
- Updated: `duet_segmenter/pipeline.py`, `duet_segmenter/result.schema.json`, `pyproject.toml`, `README.md`, `.gitignore`, and this file.
- Generated review evidence: `screenshots/research-console-overview.png`, `screenshots/research-console-timeline.png`, and `screenshots/research-console-review.png`.

## Tests and real-pair measurements

- Unit/UI suite: 16 passed, 2 opt-in sample tests skipped in the ordinary run.
- Opt-in real-pair integration: both the original CLI/pipeline regression and console orchestration passed (2 passed). The isolated Streamlit AppTest changed and reset a config control, clicked quick review, Save, and Evaluate; it displayed Precision/Recall/F1 from synthetic test labels and left predictions unchanged.
- Browser smoke check on `127.0.0.1`: 15 summary cards, all four required timeline rows, 22 learner predictions, 0.5 s context audio from 44.1 kHz stereo Duet source, native video element, and no browser page errors. Clicking Run Analysis created `runs/20260915_232523_main_video`.
- Known-pair UI run: status `ok`; runtime 10.46 s (the earlier v0.1 baseline was about 11.64 s, so this is normal run-to-run variation, not an accuracy or speed claim); final offset -0.6945625 s; accepted anchor correlations 0.9207-0.9939; gain 0.34522; linear reference suppression 14.74 dB; 22 learner intervals; 4 overlap candidates; 0 outside-template detections.
- AEC3 still measured about 2.60 dB on this pair and auto mode visibly used linear fallback. Exact default config hash: `15b612e4328e`.
- No human-labeled ground truth was created for this real pair. Precision/recall/F1 gates remain unmeasured scientifically. Synthetic labels in tests establish UI/evaluation behavior only.

## Bugs, decisions, and limitations

- During visual inspection, an empty OUTSIDE_TEMPLATE row disappeared from Plotly's category axis; invisible category markers fixed it. A 10 ms editor step displayed several timestamps rounded too coarsely; 1 ms steps now display the stored three-decimal times. No v0.1 signal-processing regression was found.
- The reference-aware cancellation/VAD architecture and provisional gates did not change. The only additive pipeline API changes are optional progress callbacks and serialization of Original/Residual VAD intervals for the UI timeline.
- The console is local and research-facing. The native video player does not provide precise synchronized seeking. Run folders copy media and therefore use disk space. Quick review covers predicted intervals only; a complete timeline annotation is needed to measure missed learner turns and true recall.
- Only one real original/Duet pair is deeply inspected. Some of its overlap flags may be cancellation residue, and AEC3 remains less effective than linear cancellation on this sample. Detection confidence is still not calibrated learner-identity probability.

## Current Phase 1 status and recommended next task

Research Console v0.2 is complete and reviewable. Phase 1 learner speech extraction is **not yet validated** against complete human ground truth. The next task is to annotate the full known Duet timeline in the console (including missed turns, original-only speech, overlap, silence, and outro), run the provisional metrics, inspect false positives/negatives, and then repeat on approximately 10-20 diverse Duets before changing the DSP architecture or entering Phase 2.

---

# 20. P1.3 Calibration & Error Control result (completed 2026-09-16)

## Implementation summary

- AUTO cancellation now runs every available backend on the same full aligned input and selects one whole residual; it never splices backend outputs. The deterministic ranking uses reliability, reference suppression, residual/reference similarity, learner-region preservation proxy, false-residual-speech proxy, and a stable linear tie break. The full comparison is saved as `backend_comparison.json` and shown in the console.
- Every predicted interval receives audio-only reference-leakage diagnostics: template overlap ratio, residual/reference waveform correlation, residual/reference log-Mel spectral similarity, local reference suppression, reference VAD activity, mean Silero probability, duration, state, and filter decision. States are `LEARNER_CANDIDATE`, `TRUE_OVERLAP_CANDIDATE`, and `REFERENCE_LEAKAGE_CANDIDATE`.
- The leakage rule is general and multi-feature. It has no segment-ID or timestamp condition, and template VAD activity alone cannot reject a candidate. The default thresholds require waveform correlation >= 0.50, spectral similarity >= 0.60, local suppression <= 0 dB, and template overlap >= 0.30.
- Silero inference is separated from timestamp generation. Probabilities are inferred once per run and stored in `vad_probabilities.npz`; parameter candidates reuse the cache. A regression test confirms cached timestamp generation matches the installed Silero baseline behavior.
- The deterministic coarse-to-fine VAD optimizer requires saved human ground truth, reports development/partial scope, ranks recall and contamination gates before F1/boundary/fragmentation criteria, and saves `vad_optimization.json` plus `vad_optimization.csv`. Preview is temporary; Apply creates a new dated run and does not overwrite defaults or historical predictions.
- Quick Validation supports Accept All as an editable review draft, exception actions (`ACCEPT_LEARNER`, `ORIGINAL_CONTAMINATION`, `TRUE_OVERLAP`, `SILENCE_FALSE_DETECTION`, `NEEDS_BOUNDARY_EDIT`), a persisted full-Duet missed-speech confirmation, and adding missed learner intervals. Human review remains separate from immutable predictions.

## Known-pair engineering measurements

Final verified P1.3 run: `runs/20260916_000304_main_video`.

- final offset b: -0.6945625 s;
- estimated reference gain: 0.3452223;
- selected backend: linear;
- linear suppression: 14.7436 dB;
- runtime: 5.666 s (run-to-run engineering timing, not an accuracy claim);
- output after leakage filtering: 21 learner candidates, 3 overlap candidates, 0 outside-template detections;
- warning: one strong reference-leakage candidate was filtered.

The unchanged-leakage baseline run `runs/20260915_235622_main_video` produced 22 learner candidates, 4 overlap candidates, and no warnings in 9.197 s. All 21 accepted intervals after S001 have exactly the same start/end values as baseline S002-S022.

## AUTO backend comparison on the real pair

- Linear: status `ok`; suppression 14.7436 dB; residual/reference similarity 0.04267; learner-region preservation proxy 0.99999; false-residual-speech proxy 0.14860; 32 confident windows.
- WebRTC AEC3: status `cancellation_unreliable`; suppression 2.5965 dB; residual/reference similarity 0.18798; learner-region preservation proxy 0.88056; false-residual-speech proxy 0.37994; 32 confident windows.
- AUTO selected linear because it passed the reliability gate, removed substantially more reference energy, left less reference-correlated residue, preserved more energy in reference-inactive regions, and had a lower residual-speech proxy. The saved ranking tuple makes the choice deterministic.

## S001 root cause and disposition

Human review identifies S001 (0.000-2.014 s) as Original/template intro speech rather than learner speech. Its diagnostics are:

- template overlap ratio / reference VAD activity: 0.63924;
- residual/reference waveform correlation: 0.62007;
- residual/reference log-Mel spectral similarity: 0.66901;
- local reference suppression: -4.0970 dB;
- mean Silero probability: 0.9486;
- duration: 2.014 s.

High VAD probability says that speech is present, but does not identify the speaker. The simultaneous reference overlap, waveform similarity, spectral similarity, and negative local suppression indicate strong surviving template speech. S001 is therefore classified `REFERENCE_LEAKAGE_CANDIDATE` and filtered. No accepted learner interval was removed: S002-S022 remain with unchanged boundaries and stable IDs.

## VAD optimization

The saved unfiltered development search evaluated 628 unique configurations.

- Baseline: threshold 0.50; minimum speech 250 ms; minimum silence 100 ms; pad 30 ms; merge gap 0.12 s. On reviewed intervals: precision 0.94715, recall 1.00000, F1 0.97286, Original contamination 1.00000, false learner duration 2.02 s, missed learner duration 0 s, boundary error 0 s, 22 fragments.
- Development best: threshold 0.55; minimum speech 250 ms; minimum silence 400 ms; pad 50 ms; merge gap 0.40 s. On reviewed intervals: precision 0.94764, recall 1.00000, F1 0.97312, Original contamination 0.99010, false learner duration 2.00 s, missed learner duration 0 s, boundary error 0.02 s, 12 fragments.

The improvement is minor for classification: false learner duration falls by only 0.02 s, F1 rises by about 0.00026, and S001 remains. The useful change is reduced fragmentation. No VAD-only candidate met both the recall and contamination development targets. This is a **DEVELOPMENT BEST**, not a global best and not a new packaged default.

## Four-scenario comparison

All accuracy values below are `DEVELOPMENT/PARTIAL GROUND TRUTH`. They score reviewed intervals; the researcher confirmed that the full approximately 91-second Duet contains no completely missed learner turn, but only 41.8% of the timeline has interval labels and accepted learner boundaries inherit baseline predictions.

| Scenario | Precision | Recall | F1 | Original contamination | False learner | Missed learner | Boundary error | Segments / fragmentation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Baseline | 0.94715 | 1.00000 | 0.97286 | 1.00000 | 2.02 s | 0 s | 0 s | 22 |
| VAD optimized | 0.94764 | 1.00000 | 0.97312 | 0.99010 | 2.00 s | 0 s | 0.02 s | 12 |
| Leakage filter only | 1.00000 | 1.00000 | 1.00000 | 0.00000 | 0 s | 0 s | 0 s | 21 |
| VAD optimized + leakage | 1.00000 | 1.00000 | 1.00000 | 0.00000 | 0 s | 0 s | 0.02 s | 11 |

These figures are useful for debugging this known pair only. They are not whole-video accuracy estimates and do not establish cross-video reliability.

## Human validation state

- Human review is persisted separately in `review.json`; `result.json` and `learner_segments.json` remain immutable.
- Baseline review persists S001 as `ORIGINAL` (the UI action is `ORIGINAL_CONTAMINATION`) and S002-S022 as accepted learner intervals.
- The researcher-confirmed full-video check for completely missed learner speech is persisted as `full_video_reviewed_for_missed_speech: true` with provenance text.
- The filtered run keeps the S001 Original interval as a manual ground-truth row because S001 is absent from final predictions.
- Recall/F1 may be displayed under the defined policy after full-video confirmation, but remain labeled development/partial because unlabelled Original/silence regions and prediction-derived boundaries prevent an independent full-timeline accuracy claim.

## Verification

- Complete suite with both opt-in real-pair tests: **22 passed, 0 failed**, with 3 dependency deprecation warnings, in 66.60 s.
- Browser smoke on `127.0.0.1`: console loaded; 21-candidate filtered run displayed; AUTO explanation and diagnostic tables rendered; Quick Validation Accept All and S001 contamination action worked; the persisted full-video checkbox was checked; Add missed learner interval worked; baseline and development-best optimization tables rendered; Preview and Keep Current worked; Apply created `runs/20260916_193547_duet`; the source run hash remained unchanged; no browser page errors occurred.
- Generated screenshots include `screenshots/research-console-overview.png`, `screenshots/research-console-timeline.png`, `screenshots/research-console-review.png`, and `screenshots/p13-optimization-preview.png`.
- Required JSON/CSV/config/manifest/diagnostic-image artifacts were parsed or opened successfully. Every checked manifest config hash matches its saved `config.json`.

## Files added or materially updated in P1.3

- Added: `duet_segmenter/leakage.py`, `duet_segmenter/optimization.py`, `tests/test_calibration.py`, `scripts/p13_browser_smoke.py`.
- Updated: `duet_segmenter/cancellation.py`, `duet_segmenter/vad.py`, `duet_segmenter/pipeline.py`, `duet_segmenter/defaults.yaml`, `duet_segmenter/result.schema.json`, `duet_speech_lab/console.py`, `app.py`, `config.yaml`, `tests/test_console_ui.py`, `tests/test_console_integration.py`, `scripts/browser_smoke.py`, `README.md`, and this file.

## Known limitations and next task

- Only one real Original/Duet pair has development labels. The leakage thresholds and development-best VAD configuration may overfit this pair.
- The 41.8% interval coverage does not independently label all Original, silence, overlap, and boundary frames. The full-video confirmation establishes that no learner interval was completely missed according to the reviewer, but it is not dense full-timeline annotation.
- The preservation and false-residual metrics used in AUTO are audio-only proxies. They are useful for deterministic engineering selection, not calibrated learner-quality measures.
- True-overlap behavior needs examples from additional videos. AEC3 remains unreliable on the known pair.
- Run folders copy input media and use substantial disk space. The console remains local and research-facing.

Next engineering task:

## P1.4 — Multi-video Robustness Validation

Collect approximately 10-20 Original/Duet pairs across several templates, learners, phones/export paths, quiet and fast speech, background noise, short pauses, and true overlap. For each pair, retain the original and completed Duet, review every predicted interval, record contamination/overlap exceptions, confirm whether the entire video was checked for completely missed learner turns, and ideally add dense Original/silence/overlap boundary annotations. Use a fixed P1.3 default configuration first; compare per-video failures before retuning. Do not start Phase 2 or claim general accuracy until this robustness set is evaluated.

---

# 21. P1.4 Cohort Triage, Robustness & Scorability Gate (engineering pass completed 2026-09-16)

## Scope and architecture

- The available same-template cohort contains 68 Duets for template `T001`: 56 MP4 files and 12 MOV files. Reports use deterministic pseudonymous IDs `T001-D001` through `T001-D068`; source paths remain only in the internal source manifest for reproducibility.
- `TemplateProfile` computes the template SHA-256, normalized reference audio, reference VAD, video metadata, and 12 visual fingerprints once. The saved template hash is `586d6e3a52c0029c9bf0e751ad1fa2399b71af4f7359608146cc1b346106caff`.
- Visual alignment compares normalized grayscale/gradient fingerprints on the left and right panels. It performs no face recognition. It removes plain export letterboxing and uses deterministic consensus fitting so repeated first/last frames cannot pull the whole timeline. Accepted anchors must cover at least 70% of the sampled template span.
- Audio audibility is a separate decision based on waveform correlation, GCC-PHAT, speech-band coherence, log-Mel similarity, explained reference energy, and reference-VAD overlap. It emits `CLEAN_MUTED`, `REFERENCE_PRESENT`, or `REFERENCE_PRESENCE_UNCERTAIN`.
- Smart AUTO retains raw Duet audio when the template audio is muted. When template audio is present or uncertain, it compares full-length linear and AEC3 cancellation results using the existing P1.3 cancellation machinery. Cancellation residuals remain detection-only and are never pronunciation-scoring input.
- Each pair receives a first-class scorability status plus a GREEN/AMBER/RED engineering gate. One pair failure does not terminate the batch. Cohort analysis is resumable through a configuration/profile/source signature.

## Final cohort measurements

The full fixed-version run used analysis signature version `P1.4.4-letterbox-normalization-and-visual-consensus` and exact saved config SHA-256 `cd468b40b3dc559b9995886ed1be0cbe9f32316a80c367b58d6f4cedea1a3eab`.

- Cohort: 68 Duets.
- Direct visual alignment: 58/68 (85.3%). Four additional videos used a reliable audio fallback, so 62/68 (91.2%) had a usable alignment. Five were `UNSCORABLE_ALIGNMENT`; one file had no audio stream and was also counted as an alignment/processing failure.
- Audio state: 62 `CLEAN_MUTED`, 2 `REFERENCE_PRESENT`, 3 `REFERENCE_PRESENCE_UNCERTAIN`, and 1 `UNKNOWN` processing failure.
- Selected backend: 62 `NONE`, 4 `LINEAR`, 1 `AEC3`, and 1 `UNSCORABLE` processing failure. The backend totals include cautious cancellation attempts for the three uncertain-audio cases.
- Scorability: 57 `SCORABLE_CLEAN`, 2 `SCORABLE_AFTER_CANCELLATION`, 0 `UNSCORABLE_REFERENCE_OVERLAP`, 6 `UNSCORABLE_ALIGNMENT` (including the processing failure), and 3 `REVIEW_REQUIRED`.
- Quality gate: 29 GREEN, 33 AMBER, and 6 RED.
- Exception-only review queue: all 33 AMBER, all 6 RED, and a deterministic sample of 5 GREEN videos, for 44/68 videos and 97 suspicious intervals. This is an estimated 35.3% reduction in videos requiring review relative to watching all 68. It is a workflow estimate, not an accuracy result.
- The two reference-present cases selected LINEAR and remained scorable after cancellation: suppression was 11.72 dB and 10.22 dB, with residual/reference similarity 0.0261 and 0.0819. Both remain AMBER because possible true-overlap intervals require review.
- The known qualitative fixture is pseudonymous pair `T001-D033`: direct visual score 0.9974, template on the right, `CLEAN_MUTED`, raw Duet path, backend `NONE`, `SCORABLE_CLEAN`, GREEN, 11 learner intervals, and no warnings.
- Full uncached cohort runtime was 368.81 seconds (about 6 minutes 9 seconds); summed per-pair runtime was 365.78 seconds. A subsequent 67-pair cached manifest/hash refresh took 0.23 seconds.

## Failure and review categories

- `UNUSUAL_DURATION`: 30 AMBER videos. The detected learner-speech fraction is outside the conservative gate range and must be spot-checked before changing VAD settings.
- `ALIGNMENT_UNCERTAIN`: 5 RED videos after all available visual/audio checks.
- `REFERENCE_AUDIO_UNCERTAIN`: 3 AMBER videos.
- `POSSIBLE_TRUE_OVERLAP`: 2 AMBER videos.
- `PROCESSING_FAILURE`: 1 RED video with no audio stream.
- Nine processable videos had weak visual alignment; four recovered through reliable audio alignment. The high-score but incomplete-coverage visual case remains blocked, which prevents a good-looking partial match from being treated as whole-video alignment.

## Calibration, Green audit, and holdout

- `calibration_labels.json` contains 8 deterministic representatives spanning low scores, high scores, and decision boundaries. All 8 are still `UNREVIEWED`; audio-state thresholds therefore remain engineering predictions rather than human-calibrated claims.
- The deterministic Green audit uses seed `20260916` and selected `T001-D004`, `T001-D015`, `T001-D032`, `T001-D053`, and `T001-D063`. Zero of five has been reviewed. The Green gate status is `PENDING HUMAN AUDIT`, not passed.
- The post-triage, audio-state-stratified split uses the same fixed seed: 50 development videos and 18 holdout videos (26.5%). No threshold was tuned on the holdout.
- No Phase 2 work, ASR, transcript generation, or pronunciation scoring was added.

## Artifacts and verification

- Cohort artifacts are under `cohort_runs/T001_p14/`: reusable profile, source manifest, JSON/CSV result manifest, exact config, summary, deterministic split, calibration queue, Green audit queue, and 68 pseudonymous pair folders.
- All 67 processable `result.json` files validate against the extended JSON schema, and all artifact paths declared by those results exist. The remaining pair has a parseable `failure.json`. The saved config hash matches the actual `config.json` bytes.
- Full suite with opt-in real-video integrations: **29 passed, 0 failed**, with 3 dependency deprecation warnings, in 49.85 seconds.
- Browser smoke on `127.0.0.1`: 12 cohort metric cards, triage table, one inspected source video, three audio players, the 8-item calibration editor, and the 5-item Green audit editor rendered. Chromium reported no page errors. Screenshot: `screenshots/p14-cohort-dashboard.png`.

## Files added or materially updated in P1.4

- Added: `duet_segmenter/visual.py`, `duet_segmenter/profile.py`, `duet_segmenter/audibility.py`, `duet_segmenter/scorability.py`, `duet_segmenter/smart_pipeline.py`, `duet_segmenter/cohort.py`, `tests/test_p14.py`, and `scripts/p14_browser_smoke.py`.
- Updated: `app.py`, `duet_segmenter/defaults.yaml`, `duet_segmenter/result.schema.json`, `config.yaml`, `pyproject.toml`, `README.md`, and this file.

## Current gate and next task

The P1.4 engineering implementation and complete cohort pre-scan are finished. The scientific gate is still open because the 8 calibration labels and 5 Green audit decisions require human listening/viewing. Do not retune thresholds, use the 18-video holdout, or start Phase 2 yet.

Next task: in the Cohort P1.4 dashboard, review and save the 8 calibration items first, then review all 5 deterministic Green audit items. If calibration exposes a clear detector error, change thresholds only from the 50-video development pool, rerun the fixed pipeline, regenerate the deterministic audit, and evaluate the untouched holdout once. If the Green audit exceeds the 5% failure tolerance, the quality gate fails and the failure categories must be resolved before Phase 2.

---

# 22. P1.4b Human-Calibrated Triage Repair (implemented 2026-09-18)

## Human evidence and historical audit

The eight calibration decisions are complete:

- `T001-D051`, `T001-D048`: template audio muted.
- `T001-D023`, `T001-D006`, `T001-D042`, `T001-D044`, `T001-D036`, `T001-D017`: template audio present.

The original five-item Green audit is preserved in `green_audit.json` and remains failed:

- FAIL: `T001-D004`, because template voice remains audible under learner speech.
- PASS: `T001-D015`; template voice is limited to the intro/non-scoring part.
- PASS: `T001-D032`.
- FAIL: `T001-D053`, because loud background music makes scoring difficult.
- PASS: `T001-D063`.

This exposed three distinct defects: intermittent/weak template audio could be falsely called clean (`D017`, `D004`), background interference could remain GREEN (`D053`), and the original split had already exposed `D006`, `D042`, and `D048` while they were in holdout.

## Holdout repair

- `data_split.json` is preserved as a historical artifact.
- `data_split_v2.json` uses seed `20260916`, version `P1.4b-v2`, and frozen pre-repair machine strata (`audio_state` x `quality_gate`).
- All 13 human-reviewed IDs are forced into development. None is in the new holdout.
- The new split contains 50 development videos and 18 holdout videos. The holdout IDs are `D001`, `D003`, `D008`, `D011`, `D012`, `D014`, `D018`, `D019`, `D024`, `D025`, `D027`, `D031`, `D033`, `D047`, `D050`, `D055`, `D058`, and `D067` under template `T001`.
- No version-2 holdout media or outcome was opened, recomputed, or used during tuning. Queue generation now receives development rows only, and tests require reviewed IDs and holdout IDs to remain outside human queues.

## Audio-presence detector V2

`measure_reference_presence` now retains window distributions instead of relying only on medians: median, p75, p90, p95, maximum, fractions above strong thresholds, reference-like window count, and longest consecutive run. CLEAN now requires weak evidence both globally and locally. Strong global evidence remains PRESENT; persistent local spectral evidence can also establish PRESENT; ambiguous evidence becomes UNCERTAIN.

On the nine reviewed audibility fixtures:

- False CLEAN: 0.
- False PRESENT: 0.
- UNCERTAIN: 1 (`D004`).
- `D017` changes from CLEAN to PRESENT and is localized to `SCORING_REGION`.
- `D004` changes from CLEAN to UNCERTAIN/UNKNOWN scope and therefore requires review.
- `D036`, `D042`, and `D044` change from UNCERTAIN to PRESENT.
- `D051` and `D048` remain CLEAN, matching human review.

The detector has no file-ID or timestamp exceptions. IDs occur only in the validation artifact as evaluation fixtures.

Reference-like windows are related to learner candidate intervals to emit `NONE`, `INTRO_OR_NONSCORING_ONLY`, `SCORING_REGION`, or `UNKNOWN`. A non-scoring-only result does not automatically reject a video. `D015` remains GREEN, consistent with the human decision that intro-only template audio is acceptable. `D004` remains UNKNOWN rather than receiving an unsupported precise localization.

## Background interference and duration findings

A lightweight audio-quality diagnostic now records RMS percentiles, clipping, learner/background level ratio, spectral flatness, and tonality. The conservative background-interference rule requires three conditions together: loud background, poor learner/background separation, and tonal background.

- `D053`: background RMS p90 `0.05356`, learner/background separation `5.58 dB`, background tonality p90 `0.5225`; it is now `BACKGROUND_INTERFERENCE`, AMBER, and `REVIEW_REQUIRED`.
- PASS comparisons were not flagged: `D015` separation `24.45 dB`, `D032` `17.06 dB`, and `D063` `47.22 dB`.
- Calibration-clean comparisons `D051` and `D048` were also not flagged.

Before repair, 19 development videos were AMBER only because of `UNUSUAL_DURATION`. After repair, 6 remain in that category. No duration threshold was changed because there is no direct human evidence for such a change.

## Development-only rerun and next human task

Only the 50 development videos were recomputed for V2 diagnostics. Before/after development counts:

| Measure | Before | After |
| --- | --- | --- |
| CLEAN / PRESENT / UNCERTAIN / UNKNOWN | 44 / 2 / 3 / 1 | 21 / 8 / 20 / 1 |
| GREEN / AMBER / RED | 21 / 24 / 5 | 10 / 35 / 5 |
| Videos requiring human review | 29 | 40 |

The increased review load is intentional: the current human evidence supports avoiding false CLEAN decisions more strongly than minimizing UNCERTAIN cases.

The historical failed audit remains untouched. `green_audit_v2.json` contains an unlabelled development-GREEN queue of eight videos: `D007`, `D028`, `D030`, `D039`, `D041`, `D046`, `D059`, and `D068`. Four are deterministic borderline/riskier selections and four are deterministic random selections. The dashboard uses the development-only V2 manifest and this versioned queue; it excludes the V2 holdout.

Saved evidence includes `audio_presence_validation.json`, `audio_quality_validation.json`, `development_manifest_v2.json`, and `cohort_summary_v2.json`. Original pair results and original human audit files were not overwritten.

## Verification, files, and limitations

- Standard suite: 30 passed, 2 opt-in integrations skipped.
- Full suite with real-media integrations enabled: 32 passed, 0 failed, with 3 dependency deprecation warnings, in 96.01 seconds.
- Added: `duet_segmenter/quality.py`, `duet_segmenter/p14b.py`, `scripts/p14b_repair.py`, and versioned P1.4b cohort artifacts.
- Updated: `duet_segmenter/audibility.py`, `duet_segmenter/scorability.py`, `duet_segmenter/smart_pipeline.py`, `duet_segmenter/cohort.py`, both YAML configs, the result schema, `app.py`, `tests/test_p14.py`, and this file.

The V2 detector is deliberately conservative: 20/50 development videos are UNCERTAIN and 40/50 require review. `D004` is protected from false CLEAN but its exact contamination scope remains unknown. The new Green audit is prepared but has no human decisions yet. Holdout evaluation, threshold changes beyond this development repair, and Phase 2 remain blocked until that audit is completed and independently reviewed.

---

# 23. P1.4c Low Speech-Level Quality Gate (implemented 2026-09-21)

## Human evidence and development-only repair

The eight-item V2 Green audit is complete: `D007`, `D028`, `D039`, `D041`, `D046`, `D059`, and `D068` are PASS. `D030` is FAIL because the learner is too quiet to judge reliably. The historical V1 PASS for `D015` and V1 FAIL for `D053` remain preserved in their original files.

ChatGPT's P1.4c plan added one conservative low-speech-level check. It requires **all three** measured conditions together: learner-speech median RMS at most `0.012`, whole-video RMS p90 at most `0.020`, and learner/background separation at most `16.0 dB`. The check uses ordinary audio measurements and existing learner candidate intervals; it does not score English or use pair-ID exceptions. A detected weak recording becomes AMBER / REVIEW_REQUIRED with reason `LOW_SPEECH_LEVEL`.

The fixed `data_split_v2.json` was reused. Only its 50 development videos were measured; no V2 holdout media or outcomes were opened. The split hash stayed `cca57f3e7d5ae3918e474f6bf2be05a76b353281633ea190976aeb03911d461b`. Original calibration, V1 audit, and V2 audit hashes also stayed unchanged. Versioned V3 artifacts were written under `cohort_runs/T001_p14/`.

- `D030`: learner-speech median RMS `0.00839`, whole-video RMS p90 `0.01302`, separation `14.54 dB`. It changes from GREEN to AMBER / REVIEW_REQUIRED and receives `LOW_SPEECH_LEVEL`.
- Every human-reviewed PASS comparison remains unflagged by the new rule. `D053` remains AMBER / REVIEW_REQUIRED for background interference.
- Development gate totals change from 10 GREEN / 35 AMBER / 5 RED to 9 GREEN / 36 AMBER / 5 RED. Videos requiring review change from 40 to 41 of 50.
- Current GREEN IDs are `D005`, `D007`, `D015`, `D028`, `D039`, `D041`, `D046`, `D059`, and `D068`. Eight have inherited human PASS decisions. **Only `D005` is unreviewed**, so the V3 Green audit remains pending human validation (8 reviewed, 0 failures so far).

The dashboard selects the V3 development manifest, summary, and audit when present. It can save the remaining V3 audit decision and update the saved summary hash. The V3 quality comparison is in `audio_quality_validation_v3.json`; the full development rows are in `development_manifest_v3.json` and the audit queue is in `green_audit_v3.json`.

No Phase 2, transcript generation, pronunciation scoring, or holdout evaluation was started. ChatGPT must independently review this execution before deciding whether to request the single remaining human audit and any later phase.

---

# 24. P2.1 Speaking Evidence Engine (implemented 2026-09-22)

P1.4c's V3 Green audit is now saved and validated: all nine current development GREEN items are PASS, including the separately reviewed `D005`. The older P1.4c paragraph above describes the earlier pending state and is retained as history. This implementation proceeds under the new P2.1 request; it does not evaluate the fixed V2 holdout.

## Scope and provenance

`speaking_evidence/` provides a development-only, evidence-producing pipeline. It loads only `development_manifest_v3.json`, verifies its IDs exactly match the 50 development IDs in the fixed `data_split_v2.json`, and rejects selected IDs outside that manifest. GREEN is eligible for extraction; AMBER requires review and RED is blocked. The gate demonstration used `T001-D002` (AMBER, unprocessed) and `T001-D016` (RED, unprocessed). No Phase-1 threshold or algorithm changed.

The canonical signal is the original completed Duet media at each development manifest row's `duet_path`. FFmpeg crops that source at turn times, converts to 16 kHz mono PCM16, and zeros audio outside Phase-1 learner candidate intervals. The residual/cancellation audio is rejected as a model input. Each evidence file records a source SHA-256, source metadata, conversion method, Phase-1 manifest and split hashes, and ASR model/runtime metadata. Original media remain unchanged.

An optional manually authored `TaskProfile` supplies ordered task turns, mode, prompt/target text, and scoring dimensions. No human TaskProfile was available for this sample, so Phase-1 learner candidate intervals were grouped by gap into `AUTO_TURN_FALLBACK` turns. Every saved item carries a warning and `LOW_AUTO_TURN_FALLBACK` boundary confidence. These inferred boundaries are a research limitation, not verified task structure.

Faster-whisper `small.en` 1.2.1 on CPU/int8 generates English transcripts with per-word timestamps and probabilities and per-segment log probabilities. Normalization changes whitespace only, preserving ASR wording and learner repetitions. Per-turn and aggregate fluency evidence includes recognized word count, speech/articulation rate, phonation and pause ratios, pause durations, longest pause, run length, and a narrow filled-pause proxy. Parselmouth computes descriptive f0 and intensity statistics with a no-voiced fallback. The pipeline never produces B2/IELTS scores, pronunciation errors, or automated feedback.

## Development sample and sanity checks

The deterministic five-GREEN sample is `T001-D059`, `T001-D007`, `T001-D068`, `T001-D028`, and `T001-D015`, selected across the development duration range. All five completed with saved evidence under `assessment_runs/T001_p2/`. Each produced one fallback turn; ASR returned 139, 136, 134, 130, and 140 words respectively. All five have available f0 evidence. Speech rates were 228.44, 184.53, 167.51, 157.37, and 164.18 recognized words/minute; these are measurements only, and `D059` warrants human listening before interpretation because of its high rate. ASR runtimes were 10.565, 9.460, 12.709, 12.566, and 12.574 seconds respectively on this machine.

Saved-artifact checks passed: word timestamps are ordered and inside each turn, pause/phonation ratios lie in [0, 1], model-input WAV files exist, and each evidence file names `RAW_COMPLETED_DUET` as canonical source. `cohort_summary.json` records the 50/18 split, manifest/split hashes, both gate demonstrations, `holdout_processed=false`, and `no_scores=true`. The fixed holdout media and outcomes were not opened or processed.

The local Streamlit app now has a read-only **Phase 2 Evidence** view of the saved sample, including playback, transcripts, timing data, and warnings. `README.md` documents the command and optional TaskProfile. The standard suite passed: 36 tests, 3 previously opt-in/skip tests. Python compile check passed. No tuning or score calibration was attempted.

## Next research decision

Review several audio/transcript pairs for ASR and automatic turn-boundary plausibility; decide whether to author a human TaskProfile before interpreting turn-specific evidence. ASR mistakes must not be mistaken for learner language mistakes. Phase 2.1 stops at descriptive evidence; scoring, feedback, holdout evaluation, and any model or threshold changes require a separate plan.

---

# 25. P2.1b T001 TaskProfile and ASR Validation (candidate support, 2026-09-22)

## Current status and human checkpoint

This is an evidence-validation sprint, not a scoring sprint. A versioned **candidate** T001 TaskProfile was saved at `task_profiles/T001_v1_candidate.json` with `human_confirmed=false`. No confirmed profile exists yet. The current candidate has one `UNKNOWN` response window on the template timeline, **3.75–52.5 s**. No prompt or target text was invented. It must not be used as a human-validated task boundary until the researcher checks the template once in the local **P2.1b Validation** dashboard.

The proposal used only the nine GREEN rows in the fixed 50-video development manifest. Phase-1 learner candidates were mapped from each Duet onto the template timeline using its saved visual alignment. Half-second bins supported by at least five of nine videos were grouped, with at most a one-second gap, then padded 0.25 s before and 0.5 s after. The saved T001 template SHA-256 was checked against the actual original MP4; reference VAD is displayed as context in the UI. This repeated occupancy supports one broad window, not an invented sequence of multiple tasks. Candidate provenance and support counts are saved in the profile. No fixed V2 holdout media or outcomes were opened.

The Streamlit **P2.1b Validation** view plays the template, shows reference speech and the candidate window on a timeline, and allows boundary edits, added/removed turns, turn modes, and optional prompt/target text. The save action requires an explicit human checkbox and writes `task_profiles/T001_v1.json` separately with `human_confirmed=true`, candidate hash, and confirmation time. Merely opening the UI cannot mark the proposal confirmed. After a successful save, the UI invokes the versioned P2.1b sample rerun.

## Prepared downstream workflow

`speaking_evidence/p21b.py` maps human-confirmed template turns to each Duet's raw timeline using saved visual alignment and clips truncated recordings, including D059. The existing Phase-1 learner segments are intersected with each response window; only raw-Duet-derived candidate audio reaches ASR. This preserves turn boundaries so waiting between tasks is excluded from pause measurements. The exact five P2.1 GREEN development IDs are fixed for rerun. Outputs go to `assessment_runs/T001_p21b/`, leaving `assessment_runs/T001_p2/` intact. The rerun is deliberately pending human confirmation.

The P2.1b runner will persist a profile copy, five per-video evidence sets, old-vs-new fluency measurements, sample summary, D059 preliminary diagnosis, and three ASR audit folders (`D028` slower/normal, `D068` medium, `D059` high rate). The UI will show each task turn's audio and original small.en transcript and let the researcher save a verbatim corrected reference; it keeps ASR text/timings/model metadata separately. WER counts substitutions, insertions, deletions, word-count difference, and filler counts while ignoring punctuation and case. Once all three human references exist, the prepared comparison runs medium.en only on their identical saved turn WAV files, compares against those same references, and records runtime, word timing validity, and WER. No WER or backend recommendation is claimed before the human references exist.

D059's previous 139 recognized words occupy 36.51 s, yielding 228.44 words/minute, versus 130–140 words over 44.22–51.16 s for the other four sampled videos. Its median ASR word duration is 0.20 s versus 0.26–0.28 s in the others; mean word probability is 0.88 (not the lowest of five). These observations are consistent with a shorter/faster recording but cannot distinguish actual fast speech, playback speed, and ASR errors without listening and a human transcript. The confirmed TaskProfile rerun will quantify the boundary contribution.

No Phase-1 code, thresholds, speaking scores, feedback, B2/IELTS mapping, or holdout evaluation changed. The standard suite passed **41 tests, 3 skipped**; Python compilation passed. Streamlit AppTest rendered the P2.1b page with template video, timeline, and a save button disabled until the explicit human checkbox is set. The historical P2.1 output still contains 31 files (combined SHA-256 `644513de36fbb9331d0749eb70a2758372b7c92201546b235ad31cef7eaff331`). A real P2.1b five-video ASR rerun and medium.en WER comparison cannot occur before the required human confirmation and three corrected references, respectively.

## Next action

The researcher should open `http://127.0.0.1:8501/?mode=p21b` in the local in-app browser, play the T001 template once, adjust the proposed response window only if needed, and explicitly confirm it. The Streamlit server was started locally on port 8501. Then the system can rerun five development videos and request human transcript corrections on just three; only then is small.en versus medium.en WER measurable.

---

# 26. P2.1b AI-assisted development review (2026-09-22)

The preceding human-confirmation workflow remains available. To reduce researcher effort, a separate AI-reviewed path was added; it never sets `human_confirmed=true` and never treats model text as human ground truth. No holdout video was opened or processed.

## TaskProfile T001

`task_profiles/T001_v2_ai.json` has **one `CONTROLLED_READING` turn, 3.75–52.5 s on the template timeline**, `status=AI_ASSISTED_CONFIRMED`, `model_reviewed=true`, and `human_confirmed=false`. Its source records the candidate hash, development manifest hash, reference VAD hash, review observations, and boundary uncertainty. It leaves prompt and target text empty. The sampled template frames at 0, 3, 6, 10, 15, 20, 25, 30, 35, 40, 45, 50, and 53 s show one scrolling English reading passage, with no alternating questions. A frame at 20 s in each of the nine GREEN development Duets shows the learner beside that same passage. Template reference VAD has ten intervals spanning 0.866–50.430 s with short gaps; development learner occupancy supports one response region. The boundaries remain machine estimates rather than manually checked word boundaries. Visual alignment maps and clips the turn for each recording.

## Five-sample rerun

`assessment_runs/T001_p21b_ai_v2/` is new and leaves historical `assessment_runs/T001_p2/` and the earlier candidate intact. Each sample uses raw Duet audio, existing GREEN Phase-1 candidate intervals, and small.en. The following are descriptive ASR-dependent measurements, not scores:

| Development ID | Old/new ASR words | Old/new active turn s | Old/new speech rate WPM | Old/new pause ratio |
| --- | ---: | ---: | ---: | ---: |
| D059 | 139 / 139 | 36.51 / 36.74 | 228.44 / 227.01 | 0.17 / 0.17 |
| D007 | 136 / 138 | 44.22 / 45.63 | 184.53 / 181.46 | 0.15 / 0.13 |
| D068 | 134 / 134 | 48.00 / 48.78 | 167.51 / 164.81 | 0.20 / 0.21 |
| D028 | 130 / 124 | 49.56 / 48.88 | 157.37 / 152.21 | 0.24 / 0.24 |
| D015 | 140 / 139 | 51.16 / 48.78 | 164.18 / 170.96 | 0.18 / 0.14 |

The complete old/new fluency metrics, including articulation rate, long pauses, and run length, are in `old_vs_new.json`. The AI profile provenance is labeled `AI_REVIEWED_TASK_PROFILE` in all new evidence files.

## ASR audit and D059

On identical saved WAV inputs for D028, D068, and D059, small.en and medium.en differed by **8/127 = 6.30%, 22/131 = 16.79%, and 13/140 = 9.29%** respectively when medium.en is used solely as a pseudo-reference. These rates are **cross-model disagreement, not WER or model accuracy**. Their respective small/medium word counts were 124/127, 134/131, and 139/140. Small/medium runtimes were 32.029/71.029 s, 23.368/91.610 s, and 26.998/68.346 s. `model_comparison_ai.json` has per-video substitutions, insertions, deletions, timings and provenance. A preferred ASR backend cannot be determined from model agreement alone. Human verbatim reference files remain unreviewed.

For D059, the reviewed boundary barely changes speech rate (228.44 to 227.01 WPM). Its Duet is 40.24 s, while visual template-to-Duet scale is 1.00067; both ASR models recover the passage ending, with 139 versus 140 words. This makes faster learner delivery plausible and the task boundary an unlikely main cause. The spoken words and local recognition errors remain uncertain without direct human listening/transcription. See `d059_diagnostic_ai.json`.

## Implementation, checks, and next step

`speaking_evidence/p21b.py` now has a separate `review-ai`, `run-ai`, and `compare-ai` path, while human confirmation and true WER remain gated on actual human review. `speaking_evidence/profile.py` distinguishes AI-reviewed turn provenance. The updated full test suite passed **42 tests, 3 skipped**. The fixed 18-video holdout was not used. No Phase-1 thresholds, proficiency scores, B2/IELTS mapping, or feedback were changed.

Next P2.2-lite presentation slice: show one learner's raw-audio transcript, turn boundary, speech-rate/pause/run-length and pitch evidence, with the source and uncertainty visible. Prepare an *experimental* 1–5 fluency rubric only after specifying its thresholds and having teachers inspect anchor examples; do not present it as a calibrated or official score. For scientific ASR comparison, obtain verbatim human references for D028, D068, and D059 before calculating WER or choosing a backend.

---

# 27. P2.2A Ground Truth and Calibration Sprint (workflow ready 2026-09-23)

P2.2A prepares the minimum human evidence needed for a first controlled-reading calibration. It does not produce a score before human evidence exists. No Phase-1 code changed, and the fixed 18-video holdout was not opened or processed.

## Target text

The T001 template audio was decoded to mono 16 kHz PCM16 and independently transcribed by faster-whisper small.en and medium.en. Both produced the same 142-word text after case/punctuation normalization. The candidate is stored in `task_profiles/T001_target_text_v1.json` with the two model records, preprocessing, template SHA-256, machine text, `confirmed_text=null`, and `human_confirmed=false`. No missing words were invented and visible text was not needed. The P2.2A UI plays the raw template and allows one edit/confirmation. Saving preserves the machine candidate separately from the human-confirmed text.

## Human transcript and rating queues

The six-video verbatim ASR queue is `D028`, `D015`, `D068`, `D007`, `D059`, and `D005`, all from the fixed development split and all GREEN. Their current small.en speech-rate/pause measurements span 153.43?228.64 WPM and pause ratios 0.1354?0.2455; long-pause counts span 1?5. Each record preserves original ASR text, word timestamps, model metadata, raw-Duet-derived audio hash, and a separate empty human reference. The UI pre-fills the machine text but saves the researcher's verbatim edit independently. Grammar and repetitions are never normalized silently.

The twelve-video speaking queue contains all nine current development GREEN cases plus `D009`, `D010`, and `D034`. These three AMBER cases are low-risk candidates: Phase 1 labels them `SCORABLE_CLEAN`, `CLEAN_MUTED`, with no background-interference, low-speech-level, or processing warning; each is AMBER only for `UNUSUAL_DURATION`. The UI requires a human SCORABLE/NOT_SCORABLE decision before ratings for every AMBER. RED is excluded. For scorable videos, the UI shows the raw completed Duet plus raw-Duet-derived learner audio and collects only Fluency, Intelligibility, Prosody (integer 1?5), and an optional note. Human labels are stored in `human_ground_truth/p22a_v1/ratings_v1.json`, separate from all derived evidence.

## ASR comparison, completeness, and calibration code

`speaking_evidence/p22.py` refuses to calculate WER until all six human references are explicitly confirmed. It then runs medium.en on the exact same saved WAV inputs used by small.en, validates word timestamps, reports per-video and aggregate substitutions/insertions/deletions/WER/runtime, and selects a backend only from measured WER plus runtime. Medium must reduce aggregate micro-WER by at least five percentage points to overcome the runtime cost; otherwise small remains selected. This is an engineering model-selection rule, not a proficiency threshold.

After backend selection, the pipeline can generate versioned evidence for the twelve queue items. Confirmed target text is aligned transparently to a human transcript where available and otherwise to the measured selected-backend transcript. Outputs retain target words, learner words, matched sequence, omissions, insertions, coverage, transcript source, and the warning that ASR differences are not proven learner reading errors.

Development calibration requires at least eight scorable human-rated videos and at least three distinct human rating levels. Fluency uses existing pause, long-pause, run-length, rate, and phonation evidence. Intelligibility uses word confidence and segment recognition evidence. Both use a deterministic ridge-linear mapping clipped to 1?5 with leave-one-out MAE because the sample is too small for a complex model. Completeness uses the explicit continuous endpoint mapping `1 + 4 ? sequence coverage`, with no proficiency thresholds and visible transcript provenance. Prosody uses f0/intensity evidence but remains excluded from Overall even if a preliminary mapping fits. Overall Controlled-Reading Score is emitted only when Fluency, Intelligibility, and Completeness are available; it is their unweighted mean. Every result is labeled `DEVELOPMENT / PRELIMINARY CALIBRATION`, `NOT CEFR`, `NOT B2`, and `NOT IELTS`.

## Files, verification, and current stop

- Added: `speaking_evidence/p22.py`, `tests/test_p22.py`, `task_profiles/T001_target_text_v1.json`, `human_ground_truth/p22a_v1/`, `human_ground_truth/T001_target_v1/`, and the raw P2.2A evidence queue under `assessment_runs/T001_p22_calibrated_v01/`.
- Updated: `app.py`, `README.md`, and this file.
- Tests: 50 passed, 3 opt-in tests skipped. Python compilation passed. Streamlit AppTest rendered all four P2.2A tabs with no exception.
- The 12 output pair IDs have no intersection with the 18 fixed holdout IDs. Student media provenance points to `data/duets/T001`; target provenance points to `data/templates/T001/original.mp4`.
- `calibration_summary.json` does not exist because the target, six transcripts, and speaking ratings have not yet been human-confirmed. No WER, ASR backend choice, criterion score, Overall score, B2/IELTS result, or feedback is claimed.

Next action: open `http://127.0.0.1:8501/?mode=p22a`, confirm the target text once, correct the six transcript references, and rate the twelve videos. The UI then exposes measured ASR comparison and development calibration in sequence. Stop before pronunciation-model benchmarking.

## P2.2A human progress checkpoint (2026-09-23)

The researcher completed steps 1 and 2 in the P2.2A UI. `task_profiles/T001_target_text_v1.json` is now `HUMAN_CONFIRMED` with 142 confirmed words. All six ASR reference records (`D005`, `D007`, `D015`, `D028`, `D059`, `D068`) are `HUMAN_CONFIRMED`; their verbatim reference word counts are 134, 136, 138, 133, 141, and 135. The original small.en transcripts and word timings remain stored separately. No speaking ratings have been submitted yet. True small.en/medium.en WER and backend selection remain pending and no calibrated score exists. A one-click local server launcher was added as `MO_P2.2A.cmd`; saved JSON data persists across shutdowns.

---

# CURRENT PROJECT STATUS ? 2026-10-30

## Competition objective

For this audit, 100% means a stable, scientifically honest competition MVP: a completed T001 Duet can go through learner extraction, raw-audio evidence, meaningful controlled-reading criterion scores, understandable result/feedback, and a reproducible demo. It also requires privacy-safe source control, passing tests, explicit limitations, and presentation material. It does not require production hosting, authentication, B2/IELTS certification, open response, Qwen, or publication-grade validation.

## Current position

- **Phase 1 ? MOSTLY COMPLETE: 88%.** The reference-aware cohort pipeline, visual/audio alignment, audibility, cancellation choice, VAD timestamps, P1.4b/P1.4c repair, fixed split, and validated GREEN development audit exist. The main remaining scientific item is a frozen one-time final evaluation on the untouched holdout; Phase 1 should not be rewritten for the competition MVP.
- **Phase 2 ? IN PROGRESS: 46%.** Raw-Duet evidence, T001 TaskProfile, human-confirmed target, six human ASR references, true WER, backend selection, completeness/calibration code, and 12-video selected-backend evidence exist. Human speaking ratings are 0/12, so no defensible criterion score or Overall score exists. Pronunciation-specific evidence is absent.
- **Phase 3 ? NOT STARTED: 0%.** There is no evidence-to-diagnosis or learner-friendly feedback layer.
- **Phase 4 ? EARLY/IN PROGRESS: 35%.** A capable local researcher UI and versioned artifacts exist, but there is no stable outsider-facing score/result page, export, final demo workflow, or competition package.

**CURRENT POSITION:** learner extraction and evidence engineering are substantially complete. The project is now at the human-calibration gate for the first T001 controlled-reading scorer. The largest blockers are 12 human ratings, actual calibrated scores, feedback, and a polished end-to-end demo.

## Competition readiness

| Category | Weight | Earned | Evidence-based assessment |
| --- | ---: | ---: | --- |
| Phase 1 extraction reliability | 18 | 16 | Broad working cohort pipeline and repaired gates; final frozen holdout evaluation still absent. |
| Evidence engine and ASR | 12 | 10 | Raw-Duet provenance, timing/acoustic evidence, six-reference WER, and selected small.en evidence exist. |
| Human ground truth and calibration | 15 | 6 | Target and six transcripts are human-confirmed; speaking ratings are 0/12 and no mapping is fitted. |
| Actual controlled-reading scores/completeness | 15 | 2 | Transparent code exists, but no criterion/Overall score artifact has been generated. |
| Pronunciation/intelligibility evidence | 8 | 3 | Human WER supports ASR quality and recognition confidence exists; no pronunciation-specific implementation. |
| Feedback | 8 | 0 | Not implemented. |
| UI and competition demo | 10 | 6 | Research/annotation UI works; final result screen and outsider demo do not. |
| Validation, stability, privacy, reproducibility | 8 | 7 | 50 tests pass, artifacts are versioned, holdout protected, privacy ignore policy added. |
| Documentation, presentation, GitHub readiness | 6 | 4 | README/status/privacy plan are updated and a safe local Git snapshot is prepared; remote/public presentation assets remain incomplete. |
| **Total** | **100** | **54** | **Functional prototype; not yet competition-capable.** |

**CURRENT COMPETITION READINESS = 54 / 100.** Classification: functional prototype.

Fourteen-day outlook:

- **Best case:** 88/100 ? strong competition-ready vertical slice, tested result/feedback demo, minimal evidence-backed pronunciation presentation, and final validation package.
- **Realistic target:** 80/100 ? competition-capable controlled-reading scorer with explicit limitations, usable feedback, stable demo, and strong documentation.
- **Minimum acceptable target:** 72/100 ? strong prototype with calibrated Fluency/Intelligibility/Completeness, transparent result display, and no overclaim; presentation limitations remain.

## Completed

- P1.4 cohort pipeline, P1.4b audibility/background repair, and P1.4c low-speech-level gate.
- Fixed 50-development / 18-holdout split; all current GREEN development items passed human audit.
- P2.1 raw-Duet speaking evidence with ASR, fluency timing, and acoustic descriptors.
- AI-reviewed T001 controlled-reading TaskProfile with explicit non-human provenance.
- Human-confirmed 142-word T001 target text.
- Six human verbatim ASR references.
- True ASR comparison: small.en micro-WER 5.51% in 172.814 s; medium.en micro-WER 7.83% in 368.447 s. small.en selected from measured results.
- Selected small.en evidence generated for 12 development videos; holdout not processed.
- P2.2A human rating UI, completeness alignment, deterministic calibration code, and score-label safeguards.
- Current audit verification: normal suite **50 passed, 3 skipped**; Python compile and four-tab P2.2A Streamlit AppTest passed. The two opt-in real-media integrations could not start because `ffprobe` is absent from the current machine's `PATH`; both failed at dependency preflight before pipeline processing. This environmental failure is disclosed and must be rerun after FFmpeg/FFprobe is restored. Public-repository privacy rules exclude media, human data, generated audio, and local paths.

## In progress

- Twelve-video human rating queue: 0/12 completed.
- Development calibration code is ready but correctly refuses to emit score artifacts without enough ratings.
- Research UI includes all evidence/annotation workflows but lacks a final competition result experience.
- GitHub preparation has a privacy-safe commit plan; the workspace itself had no `.git` repository or configured GitHub remote at audit start.

## Major blockers before competition

1. Complete the 12 Fluency/Intelligibility/Prosody ratings, including SCORABLE/NOT_SCORABLE decisions for the three AMBER cases.
2. Fit, inspect, and freeze development-only criterion mappings; generate the first real 1?5 score artifacts.
3. Validate completeness behavior against human transcripts and keep ASR uncertainty visible.
4. Add a limited pronunciation/intelligibility presentation or explicitly scope pronunciation out of the score.
5. Implement evidence-backed, learner-friendly feedback without inventing errors.
6. Build a clean result/demo page, export, representative demo cases, and graceful failure paths.
7. Freeze scorer behavior before any one-time holdout evaluation; do not tune on holdout.
8. Prepare architecture/results/limitations/roadmap slides and a rehearsable demo narrative.

## Nice to have

- More teacher raters and inter-rater agreement.
- Additional templates after the T001 vertical slice is stable.
- A stronger pronunciation baseline if it can be added without delaying the demo.
- More polished visual design and richer exports.

## Post-competition

- CEFR/B2 or IELTS mapping, only with appropriate validation.
- Open-response grammar, vocabulary, and coherence assessment.
- Qwen/local LLM explanation layer.
- Production cloud infrastructure, authentication, class management, and TikTok downloading.
- Publication-grade multi-template validation and final quasi-experimental study results.

## 14-day roadmap

| Priority / days | Milestone | Objective and concrete output | Definition of done | Technical work | Human work | Dependency / main risk | Estimated gain |
| --- | --- | --- | --- | --- | --- | --- | ---: |
| P0 ? Days 1?2 | Freeze and finish human ratings | Privacy-safe Git snapshot plus 12 completed rating records | No private media tracked; 12/12 resolved; AMBER scorability saved | Repo audit, tests, backup/version hashes | Researcher rates 12 clips consistently | Human time; rating drift | +4 to +10 |
| P0 ? Days 3?4 | Calibrate criteria | Versioned Fluency, Intelligibility, Completeness mappings and Prosody decision | Mapping artifacts, LOO diagnostics, uncertainty, no arbitrary official claim | Run calibration, inspect coefficients/outliers, freeze config | Review anchors/outliers | Small sample and narrow label variation | +6 |
| P0 ? Days 5?6 | First serious scorer | 1?5 criterion result and transparent Overall where valid | Three required criteria produce reproducible scores with provenance; Prosody separate if weak | Score pipeline, completeness confidence, regression tests | Sanity-check 3?5 examples | ASR-dependent completeness | +7 |
| P1 ? Days 7?8 | Intelligibility/pronunciation slice | Honest word-level recognition/reading evidence and limitation statement | Demo can show why a word/region is uncertain without claiming phoneme accuracy | Add confidence/stability visualization or a small justified baseline | Listen to anchor examples | Scope creep into large pronunciation models | +3 |
| P0 ? Days 9?10 | Feedback layer | Learner-friendly feedback generated only from validated evidence | Every message links to criterion/evidence/confidence; no invented diagnosis | Deterministic feedback rules/templates and tests | Review tone and usefulness | Overclaiming learner errors | +4 |
| P0 ? Days 11?12 | Demo hardening | Outsider-facing upload/select ? evidence ? score ? feedback ? export flow | Three demo cases work without manual file edits; warnings and failures are understandable | Result UI, export, caching, error handling, smoke tests | Rehearse workflow | UI/runtime failure on presentation machine | +4 |
| P0/P1 ? Days 13?14 | Final validation and packaging | Frozen release candidate, optional one-time holdout report, slides and demo script | Tests/smoke pass; behavior frozen; claims match evidence; architecture/results/limits/roadmap ready | Regression run, privacy check, package snapshot | Final claim review and rehearsal | Temptation to tune after holdout; presentation time | +6 |

The gains are not additive guarantees. Achieving all milestones well supports the best-case 88/100; partial completion should target 80/100. One complete controlled-reading vertical slice takes priority over multiple unfinished features.

## Frozen scientific constraints

- Use original raw completed Duet audio for assessment; cancellation residual remains detection-only.
- Keep the fixed holdout untouched until scorer behavior and claims are frozen for a final one-time evaluation.
- Make no CEFR, B2, or IELTS claim.
- Do not treat an ASR mismatch as an automatic pronunciation or learner reading error.
- Do not publish an arbitrary score as validated; keep development/preliminary labels, evidence, uncertainty, and provenance visible.
- Do not upload student/private media, human transcripts, ratings, identifiable filenames, secrets, or local absolute paths to GitHub.

## Next immediate milestone

Complete the 12-video speaking rating queue in the existing P2.2A UI, then run and inspect the development-only calibration. This is the shortest path from 54/100 to a defensible first controlled-reading score.

---

# P2.2B-PREP — READY FOR HUMAN CALIBRATION (2026-10-30)

This preparation sprint makes the existing development-only scorer ready to run immediately after the teacher completes the 12-video queue. It creates no human labels and no numeric learner score. The fixed 18-video holdout was not opened, processed, or used; only the saved split membership was checked.

## Verified starting state

- Phase 1 source and tests remain operational. The fixed split is still exactly 50 development / 18 holdout, with no overlap.
- P2.1 evidence and the P2.1b AI-assisted T001 TaskProfile exist. The latter retains its explicit AI-assisted/non-human provenance.
- All six human ASR references are `HUMAN_CONFIRMED`.
- The measured six-reference comparison still selects `small.en` (micro-WER 5.51% versus 7.83% for `medium.en`).
- T001 target text is `HUMAN_CONFIRMED` with 142 words.
- Selected-backend evidence exists for all 12 development rating IDs and explicitly records `holdout_processed=false`.
- The human speaking queue is still 0/12. `calibration_summary.json` does not exist; no calibrated score exists.

## Completeness and frozen machine evidence

- `speaking_evidence.p22.generate_completeness_evidence` now requires a human-confirmed target. Without it, the function returns `WAITING_FOR_TARGET_CONFIRMATION` and creates no final completeness evidence.
- Versioned `ASR-assisted Reading Completeness` evidence was prepared for all 12 development videos at `assessment_runs/T001_p22_calibrated_v01/pairs/*/reading_completeness_v1.json`, with target words, learner words, matched sequence, omissions, insertions, coverage, transcript source, and an explicit warning that ASR differences are not proven learner or pronunciation errors. This is evidence, not a score.
- Pre-declared machine features were frozen before human ratings at `calibration/p22b_prep_v01/feature_spec_v1.json`. It contains the seven requested fluency features, ASR word probabilities and fixed low-confidence fraction, available recognition-confidence evidence, and existing Parselmouth f0/intensity/voicing evidence. Recognition stability is explicitly `NOT_AVAILABLE_SINGLE_PASS` rather than invented.
- The feature artifact records `rating_count_read=0`, `holdout_processed=false`, raw completed Duet as the required canonical source, and a source-evidence hash for every development item. Feature selection was not based on teacher labels.

## Calibration and UI readiness

- Calibration is gated on at least eight human-confirmed SCORABLE videos, at least three distinct label levels for each teacher-rated criterion, development-queue IDs only, selected evidence marked non-holdout, and raw completed Duet provenance.
- Before those gates pass, the engine returns `WAITING_FOR_HUMAN_CALIBRATION`, emits an empty score list, and does not write a calibration-score artifact.
- The simple deterministic ridge mapping remains pre-declared. Leave-one-out output now includes MAE, predicted-versus-human rows, within-one-band agreement, and Spearman correlation when defined. No neural model or post-label feature selection is used.
- A focused `Teacher Rating — P2.2A` page shows only raw video/audio, AMBER scorability when needed, three 1–5 teacher ratings, an optional note, `Save & Next`, and persistent X/12 progress. It does not show a machine score.
- `START_TEACHER_RATING.bat` starts the local app and opens `http://127.0.0.1:8501/?mode=teacher`. Ratings are written immediately to the existing JSON path and survive app restarts.
- A separate `Phase 2 Assessment Result` page shows transcript, Fluency/Intelligibility/Completeness/Prosody evidence, and `WAITING FOR HUMAN CALIBRATION` while no calibrated artifact exists. It cannot display a fabricated numeric score. It always shows `DEVELOPMENT / PRELIMINARY CALIBRATION`, `NOT CEFR`, `NOT B2`, and `NOT IELTS`.

## Verification and current gate

- Full normal suite: **56 passed, 3 skipped**.
- Python compilation passed for the modified app and calibration module.
- Tests cover holdout exclusion, no score without human ratings, no placeholder labels, target-confirmation gating, raw completed Duet provenance, non-pronunciation interpretation of ASR mismatch, waiting UI, persistent rating saves, deterministic mapping, and absence of proficiency claims beyond required `NOT ...` disclaimers.
- Competition readiness remains **54/100**. Preparation code does not count as completed human calibration or an actual score.

**Infrastructure status:** ready.

**Calibrated score:** not available.

**Current blocker:** teacher completes the 12-video human rating queue.
**Next action:** after ratings are saved, run development calibration once, inspect its label variation and leave-one-out diagnostics, then review the first real preliminary scores. Do not use holdout or start feedback/pronunciation work in this sprint.

---

# P2.3 PRONUNCIATION TRACK — PREPARED (2026-10-30)

Pronunciation is now a separate controlled-reading criterion. This sprint prepared four-criterion human ground truth and machine-pronunciation benchmarking before any teacher Pronunciation label existed. It did not fit a scorer, create a numeric Pronunciation result, use the fixed holdout, implement feedback, or train/fine-tune a neural model. Competition readiness remains 54/100 until human evidence and real calibrated output exist.

## Human rubric and versioning

The focused `Teacher Rating — P2.2A` page now collects four integer 1–5 criteria:

- **Fluency:** smoothness, continuity, pauses, hesitations, repetitions/self-corrections, and flow; pronunciation is explicitly excluded.
- **Pronunciation:** accuracy and clarity of English words/sounds, including consonants/vowels, final sounds, omitted/misproduced sounds, word pronunciation, and clearly noticeable word stress. A Vietnamese/non-native accent alone must not reduce the rating.
- **Intelligibility:** how easily the learner is understood without the transcript; accent alone must not reduce the rating.
- **Prosody:** rhythm, phrasing, sentence stress, and intonation; it remains separate from Fluency and Pronunciation.

`Pronunciation examples / problematic words` is optional. The teacher page shows no ASR confidence, WPM, pause statistics, OpenPronounce/GOPT output, or machine score. `Save & Next` and X/12 progress remain.

The original private `ratings_v1.json` was hash-checked and left unchanged. A separate `ratings_v2.json` uses schema `P2.3-four-criterion-v2`, retains all previous fields/provenance, adds `pronunciation=null`, `pronunciation_examples=""`, item schema version and rater metadata, and records the source hash. Current human progress remains 0/12 and all 12 Pronunciation values remain null. Re-rating an already confirmed item appends the previous record to history instead of silently deleting it.

## Frozen benchmark plan and evidence contract

`speaking_evidence/specs/pronunciation_benchmark_plan_v1.json` was frozen while ratings were 0/12. It predeclares backend candidates, the raw-audio invariant, target-word policy, calibration gates, metrics, backend-selection priorities and prohibited claims. `speaking_evidence/schemas/pronunciation_evidence_v1.schema.json` defines versioned utterance-, word-, and optional phone-level evidence with backend/model version, runtime, confidence, analyzed coverage and limitations.

All pronunciation input must be `RAW_COMPLETED_DUET` audio cropped/masked with Phase-1 learner timestamps. `residual` and `cancel` filenames/provenance are rejected. Reference-cancellation output remains detection-only.

The deterministic target-vs-selected-ASR edit alignment assigns:

- `MATCHED`: eligible for pronunciation analysis;
- `OMITTED`: Completeness only, never forced into phone alignment or penalized again;
- `INSERTED`: stored separately and excluded from target pronunciation accuracy;
- `SUBSTITUTED_OR_UNCERTAIN`: uncertain, with no automatic exact phoneme diagnosis.

Across the 12 development artifacts, 1,430 of 1,704 target-word instances are `MATCHED`, 107 are `OMITTED`, and 167 are `SUBSTITUTED_OR_UNCERTAIN`; analyzed coverage ranges from 0.6268 to 0.9366. These are ASR-assisted alignment counts, not human pronunciation-error counts.

## Candidate backends and current status

- **Baseline A — faster-whisper recognition proxy:** versioned evidence exists for all 12 development items. It retains mean word probability, fixed low-confidence fraction, target/ASR match coverage and the explicit absence of single-pass recognition stability. It is labeled an Intelligibility/recognition baseline, not a true pronunciation model; every human-calibrated Pronunciation score is null.
- **Candidate B — OpenPronounce:** optional integration is pinned to PyPI `openpronounce==0.3.0`, release commit `8b1e8a3e49eae92756cf7c8335f00f3917f431b8`, with model provenance `facebook/wav2vec2-large-960h` and `facebook/wav2vec2-lv-60-espeak-cv-ft`. The Python package installed. FFmpeg works. The official eSpeak NG 1.52.0 MSI system install returned Windows error 1603; an SHA-256-verified administrative extraction succeeded, but its executable failed the repeatable runtime probe with Windows exit `3221225477` (`0xC0000005`, access violation). Status is `BLOCKED_ESPEAK_NG_RUNTIME_FAILURE`. No model weights were downloaded/loaded, no raw score was accepted, and the optional failure does not affect the core app.
- **Candidate C — alignment:** not selected for this sprint. Existing selected-ASR word timings are sufficient to gate matched words for the first benchmark. WhisperX alignment is the single preferred future option only if measured backend failures show a material need; it must not replace the validated small.en recognizer without evidence.
- **Candidate D — GOPT:** `NOT_SELECTED_FOR_COMPETITION_MVP`. It remains an optional later research benchmark because reproducible GOP/Kaldi/Windows integration cost is disproportionate to the two-week competition MVP.

The OpenPronounce adapter is fail-closed and optional. If dependencies become reliable, it analyzes contiguous `MATCHED` word runs only and can retain raw score, per-word/phone candidate evidence, backend/model versions, runtime, difficult-word candidates and acoustically supported word-final phone candidates. It never treats its raw 0–100 output as ground truth. Unsupported stress/final-sound diagnoses remain unavailable rather than being manufactured.

## Calibration readiness and limits

Pronunciation calibration is prepared but returns `WAITING_FOR_HUMAN_CALIBRATION`. It requires at least eight SCORABLE integer Pronunciation ratings, at least three distinct rating levels, development-queue IDs only, and no holdout. The predeclared small ridge mapping uses leave-one-out validation and reports MAE, within-one-band agreement, Spearman correlation, quadratic weighted kappa when meaningful, predicted-vs-human rows, uncertainty and sample-size limitations. No deep model is trained on 12 videos.

Pronunciation, Intelligibility and Prosody remain separate. A gated relationship function will calculate Pronunciation-vs-Intelligibility Spearman correlation only after all 12 queue items are completed; it will report possible redundancy for later review rather than automatically removing a criterion.

Scientific limitations remain substantial: OpenPronounce is currently blocked on this Windows eSpeak runtime; its Wav2Vec2 models are large and trained mainly on adult/read speech; child speech, Vietnamese-accented speech and noise can create false alarms; ASR-aligned word boundaries are approximate; and 12 development ratings are too small for a stable general claim. No CEFR, B2, IELTS, native-likeness or accent-reduction claim is allowed.

## Verification and next task

- Full normal test suite: **64 passed, 3 skipped**; Python compilation passed.
- Tests enforce the fourth required integer rating, source-schema preservation/history, teacher anchoring protection, development/holdout separation, raw-Duet provenance, residual rejection, omission/double-penalty guard, ASR-uncertainty semantics, construct separation, benchmark-plan/version pins, deterministic baseline rerun, nonfatal optional-backend failure, and prepared LOO/QWK metrics.
- Fixed 18-video holdout media/outcomes were not opened, processed, or used.

**Next task:** the teacher completes 12 four-criterion ratings. Then run development-only pronunciation backend benchmarking/calibration; do not select a final backend or produce a Pronunciation x.x/5 score before those labels exist.

---

# PRE-HUMAN FINAL PREPARATION — COMPLETE (2026-10-31)

This sprint recovered and finished the interrupted preparation work without creating human labels or learner scores. The fixed split membership was checked only to enforce development/holdout separation. No holdout media or outcome was opened, processed, or used.

## Teacher workflow hardening

- Direct `?mode=teacher` now exits into the focused `Teacher Rating — P2.2A` route before the Research Console constructs its sidebar. Experiment controls, VAD/cancellation controls, research navigation, transcripts, ASR confidence, timing metrics, machine evidence, and machine scores are absent from the teacher route.
- The page exposes exactly the 12 frozen development queue IDs, raw video/audio, the four 1–5 criteria (Fluency, Pronunciation, Intelligibility, Prosody), optional pronunciation/problem-word examples, AMBER `SCORABLE / NOT_SCORABLE`, `Save & Next`, and persistent X/12 progress. Completed rows reload their saved values and are visibly marked.
- `save_rating` now rejects non-integer/boolean/out-of-range values, preserves the prior row in edit history, writes the private rating file atomically, and creates a timestamped SHA-named snapshot under the ignored `human_ground_truth/p22a_v1/rating_backups/` directory. The UI rereads the saved row before advancing and stops visibly if verification fails.
- Persistence and backup behavior were tested only with isolated temporary fixtures. No production rating was fabricated. Production state remains **0/12** and no production backup exists because no teacher save has occurred yet.
- `START_TEACHER_RATING.bat` delegates to a health-checked PowerShell launcher. A real `--no-browser` smoke run started/reused the local Streamlit server successfully at `http://127.0.0.1:8501/?mode=teacher`.

## Post-rating calibration gate

- `RUN_CALIBRATION_AFTER_RATINGS.bat` and `speaking_evidence.post_rating` provide the one-click post-rating path. The preflight requires the exact four-criterion v2 queue, all 12 rows confirmed, AMBER decisions resolved, at least eight SCORABLE rows, no missing/malformed criterion values, at least three label levels per criterion, a human-confirmed target, prepared completeness/selected-ASR artifacts, development-only evidence, and `RAW_COMPLETED_DUET` provenance.
- The preflight compares queue membership with the frozen 50/18 split but does not open holdout media. Any malformed row, duplicate/unexpected ID, holdout intersection, insufficient SCORABLE count, missing criterion, or insufficient variation stops without creating score artifacts.
- An isolated complete fixture exercised the successful path: it produced five versioned criterion reports, LOO predicted-vs-human rows, MAE, within-one-band agreement, Spearman correlation, QWK when defined, distributions, and sample-size warnings. Pronunciation remained `EVIDENCE_ONLY_BACKEND_PENDING` with a null score.
- The production launcher was run at 0/12 and correctly stopped with explicit reasons. The rating-file hash remained unchanged and `assessment_runs/T001_p22_calibrated_v01/calibration_summary.json` still does not exist.

## Result and Phase 3 preparation

- The read-only Phase 2 result route now forms one coherent development flow: raw learner source/audio, transcript, Fluency evidence/state, Pronunciation evidence/backend-pending state, Intelligibility evidence/state, ASR-assisted Reading Completeness, Prosody evidence/state, Overall waiting/result state, and `FEEDBACK NOT YET GENERATED`.
- Before calibration it shows `WAITING FOR HUMAN CALIBRATION` and no fabricated numeric learner score. After a valid saved calibration summary exists, it reads criterion scores and key evidence automatically. Required labels remain `DEVELOPMENT / PRELIMINARY CALIBRATION`, `NOT CEFR`, `NOT B2`, and `NOT IELTS`.
- `speaking_evidence.feedback_contract` plus `schemas/feedback_input_v1.schema.json` define infrastructure only for a future local adapter. The contract accepts measured development evidence and saved preliminary scores only, requires raw-Duet provenance, forbids invented pronunciation errors and proficiency/accent claims, limits future output structure, and keeps generation at `NOT_YET_GENERATED`. No LLM was installed or run and no feedback was generated.

## Pronunciation and verification

- OpenPronounce remains `BLOCKED_ESPEAK_NG_RUNTIME_FAILURE`. The crashing eSpeak executable was not retried. GOPT and other pronunciation backends were not added. The optional failure remains isolated from Streamlit startup, teacher rating, tests, and the other calibration criteria.
- Targeted suites passed: post-rating/feedback **8 passed**; P2.2/P2.3 **23 passed**; focused P2.2 UI/persistence **15 passed** (overlapping subsets are reported as executed, not summed).
- Full normal suite: **73 passed, 3 skipped**. Python compilation passed for `app.py`, `duet_segmenter`, `duet_speech_lab`, `speaking_evidence`, and `scripts`. Streamlit AppTest covered both direct teacher and waiting-result routes; the launcher health smoke passed.
- `git diff --check` passed apart from informational Windows line-ending notices. Private media, WAVs, ratings, local artifacts, caches, secrets, and models remain ignored.

**Competition readiness:** remains **54/100**. Preparation infrastructure does not count as completed human ground truth or a real calibrated scorer.

**Current blocker:** the external teacher must complete the 12 four-criterion ratings.

**Next action:** after the real queue reaches 12/12, double-click `RUN_CALIBRATION_AFTER_RATINGS.bat`, inspect the development-only reports and first preliminary results, and do not use the holdout or force a Pronunciation score.

# P2.2C — SUPPORT-AWARE CALIBRATION (2026-10-31)

The 12-video development queue is now complete: 12/12 are human-confirmed and SCORABLE. The source `ratings_v2.json` was frozen byte-for-byte before modeling. Its SHA-256 and the frozen snapshot SHA-256 both equal `6ffc1be2661c8ef3fbcf084c2cb4f83cec175d9f1996f20a444cdc6e13005f62`; the raw source labels were not edited. The private frozen snapshot and provenance manifest live under `human_ground_truth/p22a_v1/frozen/p22c_v1/` and remain excluded from Git.

## Observed human-label support

- Fluency: 4 = 8, 5 = 4.
- Pronunciation: 3 = 5, 4 = 7.
- Intelligibility: 4 = 10, 5 = 2.
- Prosody: 2 = 1, 3 = 7, 4 = 3, 5 = 1.

The task is a practiced, preferred-take controlled reading: students could rehearse the passage and submit a take they were satisfied with. Upper-end clustering in Fluency and Intelligibility is therefore a plausible task property, not a defect to repair by changing scores or adding synthetic low labels. This development sample must not be described as representing the full 1–5 speaking-ability continuum.

## Rating provenance and audio-source audit

The accurate label provenance is `HUMAN_REVIEWED_AI_ASSISTED`. The teacher personally listened to/reviewed the recordings and made or accepted the final decisions while using a ChatGPT conversation in the NCKH12 project as assistance. These data are suitable for preliminary development calibration, engineering selection and a competition prototype. They are not an `INDEPENDENT HUMAN GOLD STANDARD`, no inter-rater reliability is claimed, and they are not independent final validation data.

The teacher UI presented the raw completed-Duet video and `raw_learner_audio.wav`. Artifact and code-path tracing across all 12 items classifies the audio source as `RAW_CROPPED`: `prepare_turn_audio` uses ffmpeg to crop mono 16 kHz PCM16 directly from the raw completed Duet and zeros samples outside Phase-1 learner intervals. No cancellation/residual audio enters the teacher-rating path. The masked signal can still contain background/template sound inside learner intervals, but it is not cancellation-processed audio; no raw-audio re-rating is required for this reason.

## Support-aware policy and measured calibration

The previous global requirement for at least three levels in every criterion was replaced by criterion-specific support handling:

- one observed level: evidence only, no supervised calibration;
- two observed levels: regularized binary probability/expected-score model constrained to the observed support;
- three or more levels: small regularized multi-level model constrained to observed support;
- every mapping is evaluated independently with leave-one-out cross-validation;
- no oversampling, duplicated samples, SMOTE, synthetic labels or extrapolation to unobserved human levels is allowed.

Measured development-only results:

- **Fluency — `DEVELOPMENT_PRELIMINARY_RANGE_LIMITED`:** regularized binary logistic expected-score mapping constrained to [4, 5]. LOOCV MAE = 0.4204, classification accuracy = 0.6667, balanced accuracy = 0.6250, Spearman = 0.3073, no majority-class collapse. A preliminary machine Fluency value is allowed only inside [4, 5] and is labeled `DEVELOPMENT / PRELIMINARY / RANGE-LIMITED`.
- **Intelligibility — `MACHINE_CALIBRATION_UNSTABLE`:** exploratory two-level [4, 5] model only. LOOCV MAE = 0.3138, balanced accuracy = 0.5000, Spearman = -0.3239, with majority-class collapse and only two level-5 examples. Human ratings and machine evidence are preserved, but no learner-facing automated Intelligibility score is emitted.
- **Prosody — `MACHINE_CALIBRATION_UNSTABLE`:** four-level regularized model constrained to [2, 5]. LOOCV MAE = 0.6927 and within-one-band agreement = 0.7500, but Spearman = 0.1731, below the frozen stability rule. Prosody remains exploratory and no learner-facing numeric machine score is emitted.
- **Pronunciation — `EVIDENCE_ONLY_BACKEND_PENDING`:** human support {3, 4} is preserved, but the ASR baseline is not treated as a pronunciation model. Exploratory Spearman associations with teacher Pronunciation were 0.1714 for mean word probability, -0.2203 for low-confidence fraction and 0.6131 for target/ASR match coverage; these are recognition/completeness associations, not proof of pronunciation validity or errors. Human Pronunciation versus human Intelligibility Spearman was 0.3780. OpenPronounce remains `BLOCKED_ESPEAK_NG_RUNTIME_FAILURE`; it was not retried and GOPT was not installed.
- **Completeness — `ASR-assisted Reading Completeness`:** existing matched sequence, omissions, insertions and coverage evidence is retained. Current 12-item coverage spans approximately 0.6338–0.9437. ASR differences are not proven learner reading or pronunciation errors, and omitted words are not double-penalized as pronunciation errors.

No Overall score was created. Machine mappings with different validation states, raw human ratings and uncalibrated pronunciation evidence are not averaged into one artificial value. The Assessment Result page now renders a criterion profile: supported criteria can be numeric, unstable criteria remain explicit non-numeric statuses, and Pronunciation remains backend-pending.

## Optional development-only coverage expansion

`calibration/p22a_v01/calibration_coverage_expansion_v1.json` contains an optional deterministic diversity queue selected only from the fixed development split using pre-existing Phase-1 machine evidence. No human score for candidate selection was read. Five, rather than six, additional candidates met the frozen safe eligibility policy: `T001-D006`, `T001-D023`, `T001-D064`, `T001-D043`, and `T001-D048`. The first two require teacher scorability confirmation because they are `SCORABLE_AFTER_CANCELLATION`; rating audio must still use raw completed-Duet crops. No unsafe sixth candidate was added merely to reach a nominal count. This expansion is optional for the range-limited MVP, not a requirement to manufacture lower scores.

## Verification and limits

- Targeted support-aware/calibration/feedback tests: 31 passed.
- Full normal suite: **81 passed, 3 skipped**.
- Python compilation passed for `app.py`, `duet_segmenter`, `duet_speech_lab`, `speaking_evidence`, and `scripts`.
- The original 12 ratings and exact distributions are protected by byte/hash tests.
- Two-level outputs are constrained to observed support; one-level criteria cannot calibrate; severe imbalance can produce `MACHINE_CALIBRATION_UNSTABLE`.
- Expansion selection is deterministic, label-blind and development-only.
- No holdout media or outcomes were opened, processed or used.
- No CEFR, B2 or IELTS claim was introduced.

**Next task:** obtain independent review of the P2.2C criterion reports, then choose either (a) proceed with evidence-grounded Phase-3 work for supported Fluency and Completeness only, or (b) optionally collect the five development coverage-expansion ratings before revisiting unstable criteria. Do not open the holdout or create an Overall/Pronunciation machine score.

