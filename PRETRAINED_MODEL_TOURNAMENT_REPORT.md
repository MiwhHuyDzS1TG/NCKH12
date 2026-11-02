# PRETRAINED MODEL TOURNAMENT REPORT

Scope: development-only P2.4 tournament. No holdout media or outcome was used.

Frozen plan SHA-256: `28b2e4ef7c17214c202e09bcc1a5c01c7cecc309a81881c86dec21b81886836a`

All NCKH12 metrics below are measured locally. Published external benchmark values were used only to predeclare candidates and are not reported as NCKH12 results.

## Engineering provenance

- `WHISPERX_INSTALL_ATTEMPT_1`: dependency-resolution loop; terminated safely; main environment unaffected.
- Final isolated alignment environment: `whisperx==3.8.6`, `torch==2.8.0+cpu`, `transformers==4.57.6`; dependency check passed.
- Main environment remained `torch==2.11.0` (CPU-only), `transformers==5.17.0`, `ctranslate2==4.8.1`.
- RTX 3050 4 GB and one CTranslate2 CUDA device were detected, but the frozen CPU/int8 policy was retained for reproducibility. Peak VRAM was 0 for measured candidates.
- The first small.en materialization attempt hit Windows symlink privilege error 1314. The exact frozen revision was then materialized without symlinks and benchmarked successfully; challengers were not rerun.

## ASR

All candidates used CPU, int8, identical audio, normalization and decoding settings.

| model | micro-WER | mean WER | median WER | S / D / I | six-ref runtime (s) | peak RAM (bytes) | failures | selected | status |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| ASR_A_SMALL_EN | 0.0502 | 0.0502 | 0.0599 | 25 / 2 / 14 | 159.1649 | 905220096 | 0 | YES | EVIDENCE_READY |
| ASR_B_DISTIL_LARGE_V3 | 0.0869 | 0.0871 | 0.0875 | 52 / 2 / 17 | 739.4688 | 1841238016 | 0 | NO | EVIDENCE_READY |
| ASR_C_LARGE_V3_TURBO | 0.0881 | 0.0883 | 0.0945 | 53 / 2 / 17 | 765.7995 | 1951686656 | 0 | NO | EVIDENCE_READY |

Selected: `ASR_A_SMALL_EN` — BASELINE_RETAINED_BY_FROZEN_RULE.

## Alignment

WhisperX status: `WHISPERX_FLUENCY_EVIDENCE_COMPLETE`. Canonical transcription was not replaced.
Mean absolute timing delta where positionally comparable: start=0.1898s, end=0.1199s.
Both current and WhisperX-derived Fluency evidence are preserved.

## SSL-FT-PRON pretrained evidence

| candidate | official subpath | weight bytes | status | device | peak RAM (bytes) | item runtime (s) | direct score | failure/resource note |
|---|---|---:|---|---|---:|---:|---|---|
| APA_1_WAV2VEC2_LARGE_GENERAL | wav2vec2/general/01_wav2vec2-large | 1261781352 | BACKEND_UNAVAILABLE | n/a | n/a | n/a | NO | WINDOWS_ACCESS_VIOLATION_0xC0000005_DURING_STRICT_CHECKPOINT_LOAD |
| APA_2_HUBERT_XLARGE_LS960_FT_CTC | hubert/ctc/09_hubert-xlarge-ls960-ft | 3850258896 | BACKEND_UNAVAILABLE_RESOURCE_LIMIT | n/a | n/a | n/a | NO | FROZEN_RESOURCE_GATE_WEIGHT_EXCEEDS_2GB |
| APA_2F_HUBERT_BASE_LS960_GENERAL | hubert/general/07_hubert-base-ls960 | 377524352 | EMBEDDING_EXTRACTION_COMPLETE | cpu | 1286836224 | 261.1884872998344 | NO | n/a |

The released General/Freeze checkpoint state contains an official four-output training head, but the documented packaged encoder loading path does not provide a sufficiently clear standalone score-inference contract for this tournament. For the successful HuBERT-base fallback, the full wrapper state was loaded with `strict=True`; only its fine-tuned encoder was used. Outputs are therefore labeled `PRETRAINED_EMBEDDING_FEATURE`, never direct pronunciation scores. Mean pooling follows the official method; PCA was fitted without human labels and frozen.

## Fluency

| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |
|---|---|---:|---:|---:|---:|---:|---:|---|
| F0_BASELINE | DEVELOPMENT_PRELIMINARY_RANGE_LIMITED | 0.4204 | 0.6250 | n/a | 0.3073 | 7 | 0.5833 | YES |
| F1_WHISPERX | DEVELOPMENT_PRELIMINARY_RANGE_LIMITED | 0.4031 | 0.5625 | n/a | 0.3073 | 7 | 0.5833 | NO |
| F2_APA1 | BACKEND_UNAVAILABLE | n/a | n/a | n/a | n/a | 0 | n/a | NO |
| F2_APA2F | MACHINE_CALIBRATION_UNSTABLE | 0.5301 | 0.4375 | n/a | -0.8193 | 2 | 0.1667 | NO |
| F3_HYBRID | BACKEND_UNAVAILABLE | n/a | n/a | n/a | n/a | 0 | n/a | NO |

Winner: `F0_BASELINE` — BASELINE_RETAINED_BY_DEFAULT.
Predictions remain constrained to observed human support [4,5].

## Pronunciation

| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |
|---|---|---:|---:|---:|---:|---:|---:|---|
| P0_ASR_RECOGNITION | MACHINE_CALIBRATION_UNSTABLE | 0.5869 | 0.4286 | n/a | n/a | 3 | 0.2500 | YES |
| P1_APA1 | BACKEND_UNAVAILABLE | n/a | n/a | n/a | n/a | 0 | n/a | NO |
| P2_APA2F | MACHINE_CALIBRATION_UNSTABLE | 0.5816 | 0.2143 | n/a | n/a | 2 | 0.1667 | NO |

Winner: `P0_ASR_RECOGNITION` — BASELINE_RETAINED_BY_DEFAULT.
Scores remain constrained to [3,4]. No phoneme-level diagnostic claim is made.

## Intelligibility

| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |
|---|---|---:|---:|---:|---:|---:|---:|---|
| I0_SINGLE_ASR | MACHINE_CALIBRATION_UNSTABLE | 0.3138 | 0.5000 | n/a | n/a | 5 | 0.4167 | YES |
| I1_MULTI_ASR | MACHINE_CALIBRATION_UNSTABLE | 0.4214 | 0.3500 | n/a | n/a | 6 | 0.5000 | NO |
| I2_MULTI_ASR_MINIMAL | MACHINE_CALIBRATION_UNSTABLE | 0.4298 | 0.5500 | n/a | n/a | 3 | 0.2500 | NO |

Winner/status: `I0_SINGLE_ASR` / `MACHINE_CALIBRATION_UNSTABLE`.
ASR disagreement is recognition-stability evidence, not a pronunciation error.

## Prosody

| candidate | status | LOOCV MAE | balanced accuracy | within-one | Spearman | features | features/N | selected |
|---|---|---:|---:|---:|---:|---:|---:|---|
| R0_PRAAT | MACHINE_CALIBRATION_UNSTABLE | 0.6927 | n/a | 0.7500 | 0.1731 | 4 | 0.3333 | YES |
| R1_APA1 | BACKEND_UNAVAILABLE | n/a | n/a | n/a | n/a | 0 | n/a | NO |
| R1_APA2F | MACHINE_CALIBRATION_UNSTABLE | 0.7803 | n/a | 0.7500 | -0.5821 | 2 | 0.1667 | NO |
| R2_HYBRID | BACKEND_UNAVAILABLE | n/a | n/a | n/a | n/a | 0 | n/a | NO |

Winner/status: `R0_PRAAT` / `MACHINE_CALIBRATION_UNSTABLE`.

## Reading Completeness

The deterministic ASR-assisted method is retained. Backend comparison:

| ASR backend | mean coverage | matched | omissions | insertions | uncertain substitutions |
|---|---:|---:|---:|---:|---:|
| ASR_A_SMALL_EN | 0.8597 | 1465 | 239 | 182 | 165 |
| ASR_B_DISTIL_LARGE_V3 | 0.8727 | 1487 | 217 | 163 | 148 |
| ASR_C_LARGE_V3_TURBO | 0.8926 | 1521 | 183 | 130 | 118 |

Differences between ASR backends are not proven learner errors.

## Frozen five-video validation plan

Reserved IDs: `D006, D023, D064, D043, D048`. Machine evidence is prepared, but no future human validation rating was read for model selection. Winners are frozen before those ratings are collected.

## Safety and limitations

- DEVELOPMENT / PRELIMINARY only.
- NOT CEFR, NOT B2, NOT IELTS.
- N=12 model-selection sample with restricted human ranges.
- Feature/N ratios above 0.25 are explicitly flagged as methodologically unsafe; such candidates cannot be promoted on a marginal metric difference.
- No large speech model was fine-tuned on NCKH12.
- No Overall score was generated.
- Fixed 18-video holdout untouched.
