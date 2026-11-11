# NCKH12 Competition Demo MVP Report

## Outcome

The frozen NCKH12 scorer is now presented through a dedicated, student-facing Streamlit experience at `?mode=competition_demo`. The interface is separate from the research and teacher workflows, shows no debug output by default, and supports both instant verified demonstrations and actual local analysis of a newly uploaded completed Duet.

The competition scope remains frozen:

| Criterion | Competition output | Status |
|---|---|---|
| Pronunciation | calibrated MultiPA Accuracy, 1 to 5 | Preliminary |
| Fluency | frozen NCKH12 timing and F0 mapping, 1 to 5 | Usable |
| Prosody | calibrated MultiPA Prosody, 1 to 5 | Preliminary |
| Reading Completeness | ASR-assisted target coverage | Usable |
| Intelligibility | no machine output | Human only |
| Overall | not created | Not applicable |

No model was fitted, retrained, recalibrated or reselected for this demo. The fixed holdout was not opened or processed.

## Architecture

```text
Completed TikTok Duet
        |
        +-- Fast Demo: verify input and frozen hashes -> genuine local cache
        |
        +-- Live Analysis
              -> Phase 1 learner interval extraction
              -> RAW_CROPPED learner audio
              -> local faster-whisper small.en
              -> frozen fluency and completeness mappings
              -> frozen local MultiPA inference
              -> deterministic evidence-based feedback
        |
        -> four criterion cards + evidence explorer + formative feedback
```

The service layer is in `speaking_evidence/competition_demo.py`. It verifies immutable scorer/config hashes, validates the machine-only cache, runs the local live pipeline, and creates feedback from named evidence fields. The presentation layer is in `speaking_evidence/competition_demo_ui.py` and is routed before the research console in `app.py`.

## UI flow

1. **Home** introduces NCKH12 Speaking Coach with one clear call to action.
2. **Assessment** offers:
   - Fast Demo for Demo Student A, B or C, backed by D064, D043 and D048.
   - Live Analysis for an uploaded completed Duet.
3. **Processing** presents four student-friendly stages without logs or technical paths.
4. **Results** shows four score cards, concise feedback, evidence, target/transcript comparison, an AI explanation and research validation.
5. A recording that does not pass the clean scorability gate receives a polished retry message and no numeric score.
6. If MultiPA fails while the remaining evidence is valid, Pronunciation and Prosody are shown as unavailable rather than being fabricated.

The presentation uses a restrained cobalt palette, 16 px card radius, light projector-oriented surfaces, large score typography, responsive four-card layout and reduced-motion support. The generated hero visual is stored at `assets/competition-hero-v1.webp`.

## Genuine Fast Demo cache

`competition_demo_cache_v1.json` contains machine evidence for exactly:

- `T001-D064` as Demo Student A
- `T001-D043` as Demo Student B
- `T001-D048` as Demo Student C

Every item records the raw Duet hash, RAW_CROPPED model-input hash, ASR evidence hash, frozen model versions, criterion scores, evidence references and deterministic feedback. Cache loading rechecks frozen scorer/config hashes and, when local private media is available, rechecks both the RAW_CROPPED input and original development video hashes.

The cache contains no teacher ratings, validation ratings, Intelligibility score or Overall score. A stale or altered cache is rejected instead of displayed.

## Feedback policy

Feedback is fully deterministic and does not use an LLM. Each result contains:

- one measured strength;
- one highest-value next focus supported by the lowest available criterion evidence;
- one concrete practice action.

Every feedback block cites existing evidence fields. Word prompts come only from genuine MultiPA word evidence, are limited to three, and are explicitly described as review prompts rather than confirmed errors. The engine does not comment on grammar, vocabulary, confidence or Vietnamese accent.

## Offline behavior

Fast Demo requires no network and reads only local verified cache and media. Live Analysis requires the following local resources, all verified on this presentation computer:

- frozen MultiPA source, checkpoint, HuBERT and RoBERTa assets;
- local MultiPA Python environment and Whisper cache;
- local faster-whisper `small.en` cache;
- FFmpeg, faster-whisper and Silero VAD runtime dependencies.

No Azure, Speechace, Qwen, external LLM or remote model download is used at presentation time. `offline_readiness()` blocks Live Analysis before upload scoring if a required local asset or runtime dependency is missing.

## Live integration check

A real development-only smoke run was executed through the same `run_live_analysis()` path used by the upload UI, using D064 as a known input. It completed Phase 1 extraction, local ASR, frozen fluency/completeness scoring and frozen MultiPA inference with:

- status: `COMPLETE`;
- scorability: `SCORABLE_CLEAN`;
- model failures: none;
- machine Intelligibility: none;
- Overall: none;
- holdout processed: false.

The run exposed and fixed two integration issues before release: the missing Silero VAD runtime and JSON serialization of NumPy scalar measurements. The latter now has a regression test.

## Visual QA

The browser workflow was exercised with Playwright and visually inspected at 1366 by 768 and 1920 by 1080.

- no horizontal overflow;
- all four score cards remain readable and unclipped;
- feedback cards are unclipped;
- primary actions have projector-safe contrast;
- generated hero artwork renders from a local WebP asset;
- no research console, hashes, model logs, file paths or stack traces appear in the normal competition flow;
- Evidence, AI explanation and Research validation remain collapsed until requested.

Screenshots are kept locally under ignored `screenshots/` and are not committed.

## Generated visual provenance

- final asset: `assets/competition-hero-v1.webp`;
- generation mode: new image, transparent background disabled;
- prompt: `Premium abstract EdTech hero image for a speaking assessment app: a single flowing cobalt-blue speech ribbon transforming into clean white paper layers, subtle audio waveform embossed into one layer, calm modern university research aesthetic, soft daylight, pale cool-gray studio background, restrained blue and silver palette, generous negative space, refined photoreal 3D paper sculpture, no people, no text, no letters, no numbers, no logos, no UI, no gradients that look synthetic, presentation-ready, 16:9 composition`.

## Startup

Double-click `START_COMPETITION_DEMO.bat`. The launcher starts the local app if needed and opens:

```text
http://127.0.0.1:8501/?mode=competition_demo
```

For a rehearsal without opening a browser automatically:

```powershell
.\START_COMPETITION_DEMO.bat --no-browser
```

## Limitations

- Pronunciation and Prosody remain preliminary because development evidence is limited and the frozen mini-validation contains only three items.
- Completeness is ASR-assisted. Unmatched words may reflect ASR uncertainty and are not automatically learner errors.
- Intelligibility remains human only.
- No Overall score, CEFR, B2 or IELTS claim is made.
- The scorer is intended for the controlled T001 reading task, not unrestricted speaking.
- Live analysis is materially slower than Fast Demo because all local inference stages run for real.

## Verification

The final verification covers cache integrity, frozen scorer state, feedback evidence, unavailable/NOT_SCORABLE behavior, route isolation, local assets, launcher isolation, responsive browser QA, Python compilation, Streamlit AppTest and the complete normal test suite.

- complete normal suite: **128 passed, 2 skipped**;
- Python compilation: passed for the app, packages and scripts;
- Playwright visual QA: passed at 1366 by 768 and 1920 by 1080;
- genuine live integration smoke run: passed;
- frozen scorer and cache hash validation: passed.

The only observed warning is a non-blocking `DeprecationWarning` inside Silero VAD's package-resource lookup. It does not change inference output or prevent startup, tests, Fast Demo or Live Analysis.
