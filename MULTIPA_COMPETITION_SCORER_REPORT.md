# MultiPA Competition Scorer Report

## Decision

P2.4D evaluated the released [MultiPA](https://github.com/yuwchen/MultiPA) assessment model as a direct, local, pretrained scorer on the same 12 frozen development recordings that already had teacher ratings. MultiPA is described in the [INTERSPEECH 2024 paper](https://www.isca-archive.org/interspeech_2024/chen24c_interspeech.html), and the released checkpoint is hosted in the official [Hugging Face repository](https://huggingface.co/yuwchen/multipa).

The selected competition scorer is criterion-specific:

| Criterion | Current baseline | MultiPA raw | MultiPA calibrated | Winner |
|---|---:|---:|---:|---|
| Pronunciation | ASR-recognition proxy: LOOCV MAE 0.5869, balanced accuracy 0.4286 | fixed 0–10 to 1–5 MAE 0.4553; Spearman 0.4652 | LOOCV MAE 0.4912; balanced accuracy 0.6286; support [3, 4] | **MultiPA Accuracy** |
| Fluency | timing baseline: LOOCV MAE 0.4204, balanced accuracy 0.6250 | fixed 0–10 to 1–5 MAE 0.9061; Spearman 0.4609 | LOOCV MAE 0.4294; balanced accuracy 0.3750; unstable | **NCKH12 timing baseline** |
| Prosody | Praat baseline: LOOCV MAE 0.6927; Spearman 0.1731 | fixed 0–10 to 1–5 MAE 0.5272; Spearman 0.4799 | LOOCV MAE 0.5881; within-one-band 0.8333; Spearman 0.2517 | **MultiPA Prosody** |
| Completeness | deterministic target/ASR alignment | comparison evidence only | not replaced | **NCKH12 ASR-assisted Reading Completeness** |
| Intelligibility | machine mapping unstable | not a MultiPA target in this sprint | not created | **HUMAN_ONLY / MACHINE_UNSTABLE** |

No Overall score was created.

## Frozen method

- The behavior and selection policy were frozen in `p24d_multipa_plan_v1.json` before inference results were inspected.
- Inputs were exactly the 12 frozen rated development IDs. The fixed 18-video holdout and the reserved `D064`, `D043`, `D048` ratings were not read.
- Source invariant: raw completed Duet -> existing Phase-1 learner crop/mask -> raw learner WAV. Cancellation/residual audio was never scored.
- Closed-response target: only the human-confirmed T001 target text. ASR did not invent target words.
- Long recordings were split deterministically at existing word boundaries into 47 chunks, each at most 14.5 seconds. A monotonic target span was assigned to every chunk. The predeclared video aggregation is the unweighted mean; any invalid planned chunk invalidates the video.
- Raw-score MAE uses the single documented mapping `clip(1 + 0.4 * MultiPA, 1, 5)`. The separate NCKH12 mapping is one-dimensional, leave-one-out evaluated and clipped to observed teacher support.
- Promotion used the predeclared P2.4-style MAE/classification or MAE/correlation margin. No alternative aggregation or feature set was selected after seeing teacher agreement.

## Runtime and provenance

- MultiPA Git commit: `a8d83ec1d80f9db60e6d32227cb1c562ee5e6022`.
- Hugging Face revision: `ff1e3c79bfb1d113d887a0b7b05fe2900c095264`.
- Released checkpoint archive SHA-256: `0ed321f7c23bac0ba424b3f37d09be2d4d4ed31e6fc2c1017def0695aa2b90bb`.
- Extracted assessment checkpoint SHA-256: `cc1f02622c763e82f29d7d4d5a073ed45bf9d829013e2c6cc726371fe2d024e8`.
- Official HuBERT Base SHA-256: `1703cf8d2cdc76f8c046f5f6a9bcd224e0e6caf4744cad1a1f4199c32cac8c8d`.
- Isolated environment: Python 3.9.21, fairseq 0.12.2, Torch 2.0.1+cu118, torchaudio 2.0.2+cu118, Transformers 4.30.2, openai-whisper 20231117, spaCy 2.3.9. The environment freeze SHA-256 is `da107f7ff20c819133118857726be481c3b3b4665495543743bc16980616aa7b`.
- Runtime device: NVIDIA CUDA. Model load: 90.36 s. Forty-seven chunk inferences: 506.22 s. Total measured runtime: 596.58 s.
- Validity: 47/47 chunks and 12/12 videos valid; failure rate 0%.
- No NCKH12 neural training or fine-tuning occurred.

The official source is not modified. A thin NCKH12 adapter supplies the confirmed target span, official Whisper-base recognition branch, short raw-audio chunk and released weights to the official feature/model classes.

## Teacher agreement

Teacher support was restricted: Pronunciation {3, 4}, Fluency {4, 5}, Prosody {2, 3, 4, 5}. Raw MultiPA class means moved in the expected direction for Pronunciation (5.647 for level 3 vs 6.011 for level 4) and Fluency (5.946 for level 4 vs 6.312 for level 5). Prosody class means were not fully monotonic, so only the frozen leave-one-out result supports its preliminary selection.

All results are **DEVELOPMENT / PRELIMINARY**. N=12 is too small for a general validity claim, and one teacher supplied restricted-range labels with AI workflow assistance. The three reserved development videos provide the next one-time mini-validation after this scorer freeze. This work is not CEFR, B2 or IELTS validation.

## Cache and fallback

Genuine outputs for four known development demos (`D005`, `D007`, `D015`, `D028`) are cached locally under ignored `.local/multipa/demo_cache/`. Each cache entry stores the raw input hash, all chunk hashes, plan hash, checkpoint hash, raw pretrained scores, calibrated scores and the explicit absence of Overall/fake scores. The detailed 47-chunk outputs, including word Accuracy and word Stress, remain local and untracked.

OOL-LIM was not installed or run. MultiPA produced valid outputs for all 12 videos, so the frozen fallback condition was not met.

## Frozen competition configuration

- Pronunciation: `MultiPA Accuracy -> one-dimensional support-constrained NCKH12 calibration`.
- Fluency: `F0_BASELINE` (existing timing model).
- Prosody: `MultiPA Prosody -> one-dimensional support-constrained NCKH12 calibration`.
- Completeness: `NCKH12 deterministic ASR-assisted Reading Completeness`.
- Intelligibility: `HUMAN_ONLY / MACHINE_UNSTABLE`.
- Overall: none.

Next: the teacher may rate only `D064`, `D043`, and `D048`, once, for independent development mini-validation. Those ratings must not reselect or refit this frozen scorer.
