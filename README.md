# NCKH12 — Reference-Aware TikTok Duet Speaking Assessment

Local research proof of concept for Grade 10 EFL controlled-reading practice. The system aligns a known TikTok template with a completed Duet, locates learner speech, extracts evidence from the original Duet audio, and prepares development-only speaking assessment calibration.

> **Current status (2026-10-30): functional research prototype, 53/100 competition-ready.** Phase 1 extraction and Phase 2 evidence generation work. The T001 target text, six human ASR references, true small.en/medium.en WER comparison, and selected-backend evidence are complete. The 12-video human speaking-rating queue is still empty, so calibrated criterion scores, learner feedback, and a competition result demo do not yet exist.

This project does **not** claim CEFR, B2, or IELTS validity. Current outputs are development research evidence, not official proficiency results.

## Architecture

```text
Known T001 template + completed student Duet
  → media normalization and template/visual alignment
  → reference audibility and cancellation decision
  → Silero VAD learner timestamps and GREEN/AMBER/RED gate
  → crop learner candidates from the original raw Duet audio
  → faster-whisper transcript + timing/acoustic evidence
  → human reference/rating workflow
  → preliminary controlled-reading calibration (pending ratings)
  → result explanation and feedback (not implemented yet)
```

Cancellation residuals are detection-only. Speaking evidence is always derived from the original completed Duet audio using saved timestamps.

## What currently works

- Phase 1 cohort pipeline: normalization, visual/audio alignment, reference audibility, cancellation selection, VAD, timestamps, diagnostics, and engineering quality gates.
- Fixed 50-development / 18-holdout split; the holdout remains excluded from tuning and Phase 2 work.
- Validated development GREEN audit after P1.4b/P1.4c repair.
- P2.1 evidence engine with raw-Duet provenance, word timestamps, fluency timing evidence, f0/intensity evidence, and explicit uncertainty.
- T001 controlled-reading TaskProfile and human-confirmed 142-word target text.
- Six human verbatim ASR references. Measured micro-WER: small.en `5.51%`, medium.en `7.83%`; small.en is selected and is faster on this sample.
- Versioned 12-video P2.2A rating workflow: 9 GREEN plus 3 low-risk AMBER cases, with AMBER scorability review first.
- Deterministic calibration code and completeness alignment code, gated until enough human ratings exist.
- Local Streamlit research interface and automated tests.

## Not complete yet

- Human Fluency, Intelligibility, and Prosody ratings: `0/12` submitted.
- Development-calibrated 1–5 criterion scores and Overall Controlled-Reading Score.
- Pronunciation-specific engine or validated pronunciation evidence.
- Learner-friendly feedback tied to measured evidence.
- Stable end-to-end competition result screen, export, and presentation package.
- One-time final evaluation on the untouched holdout.

## Installation

Requirements: Windows, Python 3.11 or 3.12, Git, and FFmpeg/FFprobe on `PATH`.

```powershell
python -m pip install -e ".[console,evidence,test]"
```

The ASR models are downloaded by faster-whisper when first used. Keep model caches outside Git.

## Run

```powershell
streamlit run app.py
```

Open these local pages:

- Research console: `http://127.0.0.1:8501/`
- P2.2A human workflow: `http://127.0.0.1:8501/?mode=p22a`

The local console binds to `127.0.0.1`; it is not a cloud deployment.

## Tests

```powershell
python -m pytest -q
python -m compileall -q app.py duet_segmenter duet_speech_lab speaking_evidence
```

Real-media tests are opt-in or skipped when private artifacts are absent. A public clone must not contain student media.

## Directory roles

| Path | Role | Git policy |
| --- | --- | --- |
| `duet_segmenter/` | Phase 1 alignment, cancellation, VAD, gating | Commit |
| `speaking_evidence/` | Phase 2 ASR, evidence, WER, calibration | Commit |
| `duet_speech_lab/`, `app.py` | Local research UI | Commit |
| `tests/`, `scripts/` | Automated checks and local utilities | Commit |
| `data/` | Raw template and student media | **Never commit** |
| `runs/`, `cohort_runs/`, `assessment_runs/` | Generated local artifacts | **Never commit** |
| `human_ground_truth/`, `calibration/`, `task_profiles/` | Private/local research labels and profiles | **Never commit** |

## Privacy and scientific limits

- Do not upload student video, audio, names, transcripts, ratings, absolute local paths, or model caches.
- Pseudonymous development IDs are engineering identifiers, not proof of anonymization for public data release.
- GREEN/AMBER/RED are engineering gates, not learner achievement levels.
- ASR mistakes are not automatically learner pronunciation or reading mistakes.
- Human calibration is small and development-only; accuracy and generalization must not be overstated.
- The fixed holdout must remain untouched until the scorer and claims are frozen for a final one-time evaluation.
- No license has been declared; this repository is a research snapshot, not a production or certified assessment product.

## Fourteen-day competition plan

1. **Days 1–2:** freeze a privacy-safe Git snapshot and complete all 12 human ratings.
2. **Days 3–4:** fit and inspect preliminary Fluency, Intelligibility, and Completeness mappings; keep Prosody separate if evidence is weak.
3. **Days 5–6:** produce the first transparent 1–5 controlled-reading result with provenance and uncertainty.
4. **Days 7–8:** add a limited, evidence-backed intelligibility/pronunciation presentation without claiming phoneme accuracy.
5. **Days 9–10:** generate rule-based learner feedback from validated evidence only.
6. **Days 11–12:** harden the end-to-end demo, export, error handling, and three representative demo cases.
7. **Days 13–14:** freeze behavior, run regression/smoke checks, decide on one-time holdout evaluation, and prepare slides/architecture/results/limitations.

Realistic 14-day target: **80/100, competition-capable with explicit limitations**. The priority is one complete controlled-reading vertical slice, not unfinished B2/IELTS, open-response, or large-model features.

## Phase 1 cohort gate P1.4

P1.4 adds a same-template cohort workflow for folders such as `data/templates/T001/original.mp4` and `data/duets/T001/`. Choose **Cohort P1.4** in the Streamlit sidebar, build the reusable Template Profile, then run Batch Pre-scan. The profile stores the normalized reference, reference VAD, video fingerprints, media metadata, and template hash once for the entire cohort.

Each Duet is checked in two separate domains. Visual fingerprints locate the template panel and estimate the template-to-Duet timeline without face recognition. Audio features then decide whether the template audio is muted, present, or uncertain. Smart AUTO keeps raw Duet audio for `CLEAN_MUTED`, compares linear cancellation and AEC3 for `REFERENCE_PRESENT`, and sends uncertain cases to review. The residual is detection-only and must never be used for pronunciation scoring.

The batch writes pseudonymous pair rows to `cohort_manifest.json` and `.csv`, per-pair artifacts under `pairs/`, a deterministic development/holdout split, an eight-video calibration queue, and a deterministic Green audit queue. GREEN, AMBER, and RED are engineering triage gates. They become validated only after the calibration examples and every selected Green audit item have human labels. One broken file is recorded as RED while the rest of the cohort continues.

The current command-line equivalent is:

```powershell
python -c "from duet_segmenter.pipeline import load_config; from duet_segmenter.cohort import run_cohort; run_cohort('data/templates/T001/original.mp4', 'data/duets/T001', 'cohort_runs/T001_p14', 'T001', load_config())"
```

Use the dashboard filters to inspect the highest reference-audio score, weakest visual alignment, worst cancellation, leakage, overlap, fragmentation, and unusual learner duration. Human calibration and audit answers are stored separately from immutable per-pair predictions.

## Phase 1 calibration sprint P1.3

`auto` cancellation now compares full-length linear and AEC3 residuals on the same aligned input and saves `backend_comparison.json`. Each predicted interval receives reference-leakage features in `leakage_diagnostics.json`; a conservative multi-feature rule can filter strong leakage while preserving possible true overlap. Silero probabilities are inferred once per run and cached in `vad_probabilities.npz` for fast timestamp tuning.

In the Research Console, **Accept all predicted learner segments** creates an editable review draft. Use the exception actions, **+ Add missed learner interval**, and the full-Duet review checkbox before evaluating Recall/F1. **Optimize VAD** requires saved human ground truth, writes `vad_optimization.json` and `.csv`, and offers preview, apply as a new run, or keep current. Optimization output remains labeled **DEVELOPMENT/PARTIAL GROUND TRUTH** when timeline interval labels are incomplete. No candidate modifies packaged defaults or existing predictions.

The known-pair baseline has 22 predictions. With the P1.3 reference-leakage filter, the contaminated first interval is marked `REFERENCE_LEAKAGE_CANDIDATE` and 21 predictions remain. Development metrics for this pair use a user-observed S001 correction and a user confirmation that the whole Duet was checked for missed learner turns. The accepted boundaries are inherited from the baseline predictions, and about 41.8% of the timeline has interval labels; do not interpret the resulting 100% figures as independent full-video accuracy or cross-video reliability.

This local CPU-first proof of concept takes an original/template video and a completed Duet and returns **learner speech timestamps on the Duet timeline**. It aligns the known template, cancels its audio, runs Silero VAD on the detection residual, and preserves overlap candidates. It does not download TikToks, transcribe audio, score pronunciation, or identify speakers with generic diarization.

Use Python 3.11 or 3.12 on Windows and install FFmpeg/FFprobe externally so both commands work on PATH. Install the project with `python -m pip install -e .` (or `python -m pip install -e ".[test]"` for tests). The optional `--backend linear` avoids AEC3; normal `auto` mode measures both available backends on identical aligned audio and selects one full-length residual. AGC and noise suppression are not enabled.

```powershell
duet-segment --original "ori video.mp4" --duet "video.mp4" --output output
# Equivalent:
python -m duet_segmenter --original "ori video.mp4" --duet "video.mp4" --output output
```

The supplied workspace pair has alternate names:

```powershell
python -m duet_segmenter --original "template.mp4" --duet "main video.mp4" --output output
```

`output/result.json` is the full result. `learner_segments.json` is the canonical interval list. `alignment.json`, `backend_comparison.json`, `leakage_diagnostics.json`, `vad_probabilities.npz`, `residual_detection.wav`, `debug_alignment.png`, and `debug_timeline.png` are diagnostics. The Duet MP4 remains untouched, and `duet_source_audio.wav` keeps its native sample rate and channels after PCM decoding. `learner_preview.wav` concatenates crops from that **uncancelled** Duet audio for listening; it is only a convenience artifact. Never use `residual_detection.wav` as pronunciation-scoring input.

`config.yaml` lists experimental, tunable thresholds. Override packaged defaults with `--config config.yaml`; no sample-specific offset is hard-coded. Unreliable alignment or cancellation yields a diagnostic `result.json` with status `alignment_unreliable` or `cancellation_unreliable`, no confident learner segments, and CLI exit code 2. Input/media failures yield exit code 1. A `confidence` field is mean Silero speech probability inside the interval; it is **detection strength**, not a calibrated learner-identity probability.

For quantitative evaluation, add `--ground-truth labels.csv`, with `start,end,label` rows where labels are `ORIGINAL`, `LEARNER`, `OVERLAP`, `SILENCE`, or `OUTSIDE_TEMPLATE`. `evaluation.json` reports frame-level learner precision/recall/F1, original-only contamination, overlap recall, raw VAD speech outside the template, boundary error, and provisional engineering gates. Predictions are never changed by ground truth.

```powershell
python -m pytest -q
$env:DUET_SAMPLE_INTEGRATION="1"
python -m pytest -q tests/test_sample_integration.py
```

The integration test checks that this particular pair estimates an offset near −0.6946 s within ±0.02 s. That expectation is used only in the test. The known pair now has user-reviewed development labels for the S001 correction and accepted predictions; full scientific accuracy still requires independent boundaries and more videos. A future visual active-speaker backend has an interface placeholder. Pyannote and LR-ASD are not installed or used in this pass.

## Research Console v0.2

The optional local researcher interface calls the existing v0.1 pipeline; the CLI remains independent. Install its dependencies with `python -m pip install -e ".[console,test]"`, then start it from the project root:

```powershell
streamlit run app.py
```

The project Streamlit configuration binds the console to `127.0.0.1`, so the local research videos and run artifacts are served only on this machine.

Choose the original/template and completed Duet from workspace videos, or upload both files, then click **Run Analysis**. The page shows measured run cards, warnings, an interactive Plotly timeline, an editable segment table, quick review buttons, native Duet video, and audio clips from `duet_source_audio.wav` with no context, ±0.5 s, or ±1.0 s. The cancelled residual is available only in Advanced / Diagnostics. The sidebar exposes a small set of experimental controls and recent runs.

Each run is saved under `runs/YYYYMMDD_HHMMSS_<safe_name>/` with copied input videos, `config.json`, a config hash in `manifest.json`, all pipeline artifacts, and separate `review.json`, `ground_truth.csv`, and `evaluation.json` when created. Correct start/end values and choose a human review label in the table, or use Quick review for predicted learner intervals. Use the manual ground-truth table to add missed speech or other labeled regions. **Save corrections + ground truth** exports `start,end,label` CSV without changing `result.json` or `learner_segments.json`; **Evaluate** calls the existing evaluation module immediately.

Metrics from incomplete ground truth are explicitly labeled as applying to reviewed intervals only. Until **I reviewed the complete Duet for missed learner speech** is checked, Recall/F1 display **NOT FULLY VERIFIED**. Unlabeled Original and silence regions still limit development metrics after that confirmation. The video uses Streamlit's native player; precise synchronized seeking is a later task.

For a local browser smoke check after startup, run `python scripts/browser_smoke.py`. It checks native-rate audio context, video element, and timeline rows, and writes screenshots under `screenshots/`. Add `--run-analysis` to click the real sample analysis button and create another dated run.

`duet_segmenter.baseline_pyannote.community_one_diarization` is an optional, independent research comparison. Install `pyannote.audio` separately and supply Community-1 model access or a local model directory before calling it. It decodes the Duet with FFmpeg, passes a mono waveform in memory, fixes `num_speakers=2`, and returns its own speaker intervals; it never alters reference-aware timestamps. [Pyannote's documented in-memory waveform input and Community-1 API](https://github.com/pyannote/pyannote-audio) underpin this adapter.

## Phase 2.1 speaking evidence (development only)

Install the optional evidence tools with `python -m pip install -e ".[evidence]"` and ensure FFmpeg is on PATH. From the project root, run `python -m speaking_evidence --sample-size 5`. The command reads the fixed V2 split and V3 **development** manifest, processes five GREEN videos, and writes `assessment_runs/T001_p2/cohort_summary.json` plus per-video evidence, transcripts, fluency, acoustic measurements, and raw-Duet-derived `model_input.wav` files. It refuses AMBER/RED IDs and IDs outside the development manifest. The fixed holdout is excluded.

Open `streamlit run app.py` and choose **Phase 2 Evidence** in the sidebar to read the saved results and listen to each turn. The view does not run a model or edit artifacts. Automatic turn grouping is marked `AUTO_TURN_FALLBACK` because a human TaskProfile is not yet available. An optional JSON TaskProfile can be supplied with `--task-profile path.json`; it needs `task_id`, `template_id`, `version`, `language`, and ordered `turns` with `turn_id`, `start_sec`, `end_sec`, and `mode` (`OPEN_RESPONSE`, `CONTROLLED_READING`, or `UNKNOWN`). Optional turn fields are `prompt_text`, `target_text`, and `scoring_dimensions`.

Word timestamps, pauses, speech rates, and pitch/intensity statistics are descriptive evidence. Whisper can mishear words, and unusual playback speed or audio quality can distort measurements. No B2/IELTS score, pronunciation diagnosis, or automated feedback is produced in this phase.

## P2.1b task and transcript validation

Run `streamlit run app.py` and open `http://127.0.0.1:8501/?mode=p21b` in the local browser. The proposed T001 response window is saved separately in `task_profiles/T001_v1_candidate.json` and is explicitly unconfirmed. Play the T001 template once, adjust the window or add/remove task turns if the template requires it, then check the confirmation box and save. The UI writes the human-confirmed profile to `task_profiles/T001_v1.json` and reruns the same five GREEN development examples into `assessment_runs/T001_p21b/`. It does not alter the earlier `assessment_runs/T001_p2/` results.

The same page then offers a small ASR audit for three videos: D028, D068, and D059. Listen to each saved turn, correct the machine transcript verbatim, and save a human reference. Once all three are checked, run the small.en versus medium.en comparison on those same saved WAV files. WER and model choice remain pending until human reference transcripts exist. No speaking score or feedback is created.

Equivalent command-line steps are `python -m speaking_evidence.p21b propose` (only if no candidate exists), `python -m speaking_evidence.p21b run` (after human confirmation), and `python -m speaking_evidence.p21b compare` (after all three references are saved).

## P2.2A ground truth and preliminary calibration

Open `http://127.0.0.1:8501/?mode=p22a` after starting `streamlit run app.py`. The four tabs guide the researcher through the minimum human work in order:

1. Confirm the single T001 target text proposed independently by small.en and medium.en from the template audio.
2. Listen to six development-only learner clips and correct the verbatim ASR transcript without repairing grammar or repetitions.
3. Rate twelve development videos for Fluency, Intelligibility, and Prosody on the displayed 1–5 rubric. The three low-risk AMBER items require a separate SCORABLE/NOT_SCORABLE decision first.
4. After enough labels exist, compare small.en and medium.en against human transcripts, generate selected-backend evidence, and run deterministic development-only calibration.

Candidate target provenance is in `task_profiles/T001_target_text_v1.json`; human labels are under `human_ground_truth/p22a_v1/`; model mappings are written to `calibration/p22a_v01/`; derived evidence and any preliminary scores go to `assessment_runs/T001_p22_calibrated_v01/`. P2.1 and P2.1b remain unchanged. Completeness stores the matched word sequence, omissions, insertions, and coverage, while warning that ASR differences are not proven reading errors. Any score output is labeled **DEVELOPMENT / PRELIMINARY CALIBRATION**, **NOT CEFR**, **NOT B2**, and **NOT IELTS**.

For tonight's focused teacher workflow, double-click `START_TEACHER_RATING.bat` or open `http://127.0.0.1:8501/?mode=teacher`. The dedicated page hides all machine scores, saves each rating immediately, and advances with **Save & Next**. The separate evidence/result page is `http://127.0.0.1:8501/?mode=p22result`; it displays **WAITING FOR HUMAN CALIBRATION** and no numeric score until the minimum label-count and label-variation gates pass.

## P2.3 pronunciation track preparation

The teacher workflow now records four separate integer criteria: **Fluency**, **Pronunciation**, **Intelligibility**, and **Prosody**. Pronunciation examples/problematic words are optional. The old `ratings_v1.json` remains untouched; `ratings_v2.json` records the new schema and initializes Pronunciation to `null`, never to a fabricated value. The teacher page shows no ASR confidence, WPM, OpenPronounce/GOPT output, or machine score before rating.

The frozen pre-label benchmark plan is `speaking_evidence/specs/pronunciation_benchmark_plan_v1.json`, and the machine-evidence contract is `speaking_evidence/schemas/pronunciation_evidence_v1.schema.json`. Reproduce local pre-rating artifacts with:

```powershell
python scripts/p23_prepare.py
```

Pronunciation input must be the raw completed Duet cropped/masked by Phase-1 learner timestamps. Residual/cancelled audio is rejected. Deterministic target/ASR alignment sends only `MATCHED` words to pronunciation analysis; `OMITTED` words remain Reading Completeness evidence and are not penalized twice. `SUBSTITUTED_OR_UNCERTAIN` remains uncertain rather than becoming an automatic phoneme error.

Baseline A uses existing faster-whisper recognition confidence only as an intelligibility/recognition comparison, not as a true pronunciation model. Candidate B is pinned as optional `openpronounce==0.3.0` (PyPI release commit `8b1e8a3e49eae92756cf7c8335f00f3917f431b8`). It requires FFmpeg, eSpeak NG, and two Wav2Vec2 checkpoints of roughly 1.2 GB each. The core app does not import or require it. On the current Windows machine, the package installed but the SHA-256-verified extracted eSpeak NG 1.52.0 executable failed its runtime probe with Windows exit `3221225477` (`0xC0000005`, access violation), so no OpenPronounce model weights were downloaded and no raw score was accepted. Alignment replacement and GOPT remain unselected for the competition MVP.

### AI-assisted development review

The separate machine-reviewed T001 profile is `task_profiles/T001_v2_ai.json`: one controlled-reading turn at 3.75–52.5 s, with `model_reviewed=true` and `human_confirmed=false`. The completed five-video run is in `assessment_runs/T001_p21b_ai_v2/`. Its D028/D068/D059 small.en versus medium.en comparison reports **pairwise word disagreement only**, not human-reference WER or model accuracy; see `CODEX_P21B_AI_LOG.md` for results and limitations. The older human-confirmation workflow remains available. The CLI adds `review-ai`, `run-ai`, and `compare-ai` commands with explicit `--profile` and `--output-dir` arguments. `review-ai` verifies the fixed nine-GREEN development manifest, template hash, and reference VAD before saving. Its media observations describe the T001 review performed for v2; a future template or cohort change requires a fresh visual review. No holdout or speaking score is involved.
