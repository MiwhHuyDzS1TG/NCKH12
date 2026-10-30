# CODEX_P21B_AI_LOG

**STATE:** AI-assisted P2.1b development run complete. No human TaskProfile confirmation or verbatim ASR reference exists. No speaking score was created. The 18-video holdout was not used.

**TASK_PROFILE:** `task_profiles/T001_v2_ai.json` records one `CONTROLLED_READING` turn at **3.75–52.5 s** on the template timeline. `status=AI_ASSISTED_CONFIRMED`, `model_reviewed=true`, `human_confirmed=false`. The versioned source includes candidate, development-manifest, and reference-VAD hashes. Sampled template frames show one scrolling reading passage, and frames from all nine GREEN development Duets show the learner alongside that passage. Template reference VAD spans 0.866–50.430 s in ten near-contiguous intervals. The 0.5 s development occupancy estimate supplies the turn boundaries; no prompt/target text was invented. Boundaries are not human verified and are clipped to each Duet.

**OLD_VS_NEW:** The new run is `assessment_runs/T001_p21b_ai_v2/`; historical P2.1 files remain untouched. All numbers below depend on ASR and are descriptive evidence only.

| Video | Words old→new | Active turn s old→new | Speech rate WPM old→new | Articulation WPM old→new | Pause ratio old→new |
| --- | ---: | ---: | ---: | ---: | ---: |
| D059 | 139→139 | 36.51→36.74 | 228.44→227.01 | 248.87→249.19 | 0.17→0.17 |
| D007 | 136→138 | 44.22→45.63 | 184.53→181.46 | 192.87→195.71 | 0.15→0.13 |
| D068 | 134→134 | 48.00→48.78 | 167.51→164.81 | 180.84→181.27 | 0.20→0.21 |
| D028 | 130→124 | 49.56→48.88 | 157.37→152.21 | 179.14→175.26 | 0.24→0.24 |
| D015 | 140→139 | 51.16→48.78 | 164.18→170.96 | 177.16→183.47 | 0.18→0.14 |

Full pause and run-length values are in `old_vs_new.json`.

**ASR_AUDIT:** small.en and medium.en were run on the same saved turn WAV for D028, D068, D059. With medium.en treated only as a *pseudo-reference*, pairwise word disagreement is **6.30% (8/127), 16.79% (22/131), 9.29% (13/140)**. Small/medium word counts: 124/127, 134/131, 139/140. Small/medium runtimes: 32.029/71.029 s, 23.368/91.610 s, 26.998/68.346 s. These are **not WER**; neither model is verified as ground truth. No backend switch is recommended. `model_comparison_ai.json` contains error counts, model provenance, and matching audio-input references. The human-reference files remain `UNREVIEWED`.

**D059_DIAGNOSIS:** The task boundary changes the rate by only −1.43 WPM. The Duet lasts 40.24 s and its visual template-to-Duet time scale is 1.00067. Both ASR hypotheses cover the ending of the passage and contain 139/140 words. Faster learner delivery is plausible; boundary error and video speedup are not supported as the main explanation by this evidence. Exact words and local ASR errors remain unverified without a human reference. `d059_diagnostic_ai.json` records the measurements and uncertainty.

**FILES_CHANGED:** `speaking_evidence/p21b.py`, `speaking_evidence/profile.py`, `tests/test_p21b.py`, `README.md`, `PROJECT_STATE.md`. New: `task_profiles/T001_v2_ai.json`, `assessment_runs/T001_p21b_ai_v2/`, this log. Existing human-confirmation and WER workflows remain separate.

**TESTS:** `python -m pytest -q -p no:cacheprovider` → **42 passed, 3 skipped**. The five new evidence files and all three medium.en transcripts were generated. Output summary records `holdout_processed=false`, `human_confirmed=false`, and `no_scores=true`.

**LIMITATIONS:** Media was reviewed through sampled video frames, template/reference VAD, Phase-1 learner timelines, and two local ASR models. There was no direct human listening or verbatim transcription. Task boundaries, ASR accuracy, and speaking quality are not scientifically validated. This work does not map CEFR/B2/IELTS or create official points.

**P2.2-LITE NEXT STEP:** Build one presentation-ready learner evidence card from this run: template/learner turn timeline, raw-audio transcript, fluency measures, pitch/intensity plots, and a visible “machine reviewed / uncalibrated” label. Draft any 1–5 fluency rubric as experimental, then ask teachers to review anchor examples before presenting a score as meaningful. Obtain human verbatim references for D028, D068, and D059 before computing WER or selecting an ASR backend.
