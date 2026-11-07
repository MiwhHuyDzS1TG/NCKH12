# P2.5 Frozen Development Mini-Validation Report

## Scope and leakage guard

This is a one-time, out-of-sample **development** mini-validation on `D064`, `D043`, and `D048`. The P2.4D scorer and its one-dimensional mappings were frozen before these ratings existed. Machine inputs and predictions were created in a stage that did not open the validation rating artifact; the three teacher ratings were read only by the final evaluation stage.

No retraining, recalibration, threshold change, feature change, model reselection, Intelligibility machine score, Overall score or holdout access occurred.

## Per-item results (primary evidence)

| Video | Criterion | Teacher | Machine | Absolute Error |
|---|---|---:|---:|---:|
| D064 | Pronunciation | 4 | 3.7609 | 0.2391 |
| D064 | Fluency | 4 | 4.7100 | 0.7100 |
| D064 | Prosody | 3 | 3.7622 | 0.7622 |
| D043 | Pronunciation | 4 | 3.7950 | 0.2050 |
| D043 | Fluency | 5 | 4.6100 | 0.3900 |
| D043 | Prosody | 4 | 3.9184 | 0.0816 |
| D048 | Pronunciation | 3 | 3.8640 | 0.8640 |
| D048 | Fluency | 4 | 4.4400 | 0.4400 |
| D048 | Prosody | 3 | 4.2644 | 1.2644 |

## Aggregate metrics

Correlations below are descriptive only. With N=3, they do not support significance or stable inference.

| Criterion | Mini MAE | Exact band | Within one band | Pearson | Spearman | Dev LOOCV MAE | Signal | Recommendation |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Pronunciation | 0.4360 | 0.6667 | 1.0000 | -0.9458 | -0.8660 | 0.4912 | GENERALIZATION_SIGNAL_MIXED | KEEP_WITH_CAVEAT |
| Fluency | 0.5133 | 0.6667 | 1.0000 | 0.1480 | 0.0000 | 0.4204 | GENERALIZATION_SIGNAL_POSITIVE | KEEP |
| Prosody | 0.7027 | 0.3333 | 0.6667 | -0.2132 | 0.0000 | 0.5881 | GENERALIZATION_SIGNAL_MIXED | KEEP_WITH_CAVEAT |

## Deterministic completeness and reference-only Intelligibility

| Video | Coverage | Score 1–5 | Matched | Omissions | Insertions | Teacher Intelligibility (reference only) |
|---|---:|---:|---:|---:|---:|---:|
| D064 | 0.9366 | 4.7465 | 133 | 9 | 7 | 4 |
| D043 | 0.9507 | 4.8028 | 135 | 7 | 3 | 5 |
| D048 | 0.9296 | 4.7183 | 132 | 10 | 3 | 4 |

Completeness remains `ASR-assisted Reading Completeness`; ASR differences are not proven learner errors. Intelligibility remains `HUMAN_ONLY / MACHINE_UNSTABLE`.

## Raw MultiPA outputs

| Video | Accuracy | Fluency | Prosody | Total |
|---|---:|---:|---:|---:|
| D064 | 6.4265 | 6.5823 | 6.2330 | 6.2452 |
| D043 | 6.5669 | 6.7469 | 6.4103 | 6.4424 |
| D048 | 6.9169 | 7.1366 | 6.8030 | 6.7861 |

## Competition decision

- **Pronunciation:** `KEEP_WITH_CAVEAT` — `GENERALIZATION_SIGNAL_MIXED`.
- **Fluency:** `KEEP` — `GENERALIZATION_SIGNAL_POSITIVE`.
- **Prosody:** `KEEP_WITH_CAVEAT` — `GENERALIZATION_SIGNAL_MIXED`.
- **Completeness:** `KEEP`.
- **Intelligibility:** `HUMAN_ONLY / MACHINE_UNSTABLE`.
- **Overall:** not created.

These three development cases are extremely small and AI-assisted single-rater labels. The result is a competition-engineering signal, not external validation, CEFR/B2/IELTS evidence, or permission to tune on the three cases.

## Provenance

- Frozen evaluation plan SHA-256: `e75710e13781e154adeacd9683d6afde8a992220fb3c85adcc48e7ffac1c0d54`.
- Frozen prediction artifact SHA-256: `2f4438d86c4226404554dbaa2b033922d450733946d779084f4e585f41a147bf`.
- Validation rating artifact SHA-256: `707d4c33eafaaf54a21c131bff6b1fec09538b06d911b447275fd69ef00ed464`.
- Fixed holdout processed: **NO**.
