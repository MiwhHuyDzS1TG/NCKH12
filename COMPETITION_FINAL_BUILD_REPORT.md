# NCKH12 Competition Final Build Report

## Final product architecture

NCKH12 Speaking Coach remains a local, offline-first Streamlit product with a dedicated `?mode=competition_demo` route. The product layer calls the already-frozen Phase 1 extraction, small.en ASR, NCKH12 Fluency/Completeness evidence and MultiPA Pronunciation/Prosody scorer. It does not duplicate or refit research logic.

```text
Completed Duet
  -> learner timestamps from Phase 1
  -> RAW_CROPPED learner audio
  -> frozen local ASR and criterion scorers
  -> deterministic evidence feedback
  -> optional manually imported GPT wording review
  -> four criterion results, feedback and inspectable evidence
```

## Frozen scorer mapping

| Criterion | Method | Product status |
|---|---|---|
| Pronunciation | calibrated MultiPA Accuracy | Preliminary |
| Fluency | frozen NCKH12 timing/F0 scorer | Usable |
| Prosody | calibrated MultiPA Prosody | Preliminary |
| Reading Completeness | faster-whisper plus target alignment | Usable |
| Intelligibility | no machine score | Human only |
| Overall | not created | Not applicable |

P2.5 ratings were not used for refitting. The MultiPA checkpoint, Fluency mapping, criterion selection and Completeness algorithm are unchanged. The fixed holdout was not opened or processed.

## Target text audit

The source `T001_target_text_v1.json` correctly recorded the template audio, but its confirmed text combined a spoken title with the reading passage. Direct audit of the authoritative template video established:

- around 1-2 seconds, **One Memorable Event** appears alone as the lesson topic/title;
- around 3 seconds, the displayed reading passage begins **One memorable event in my life was my high school graduation**;
- the audio speaks both, which explains why both ASR systems included the title;
- no other word was changed.

`competition_target_profile_v2.json` therefore stores `Topic: One memorable event` separately and excludes only that title from Reading Completeness. The scored passage contains 139 words. This is a target-boundary correction, not a Completeness algorithm change. MultiPA continues to use the exact original v1 closed-response target used by the frozen scorer.

The old competition cache is intentionally obsolete. `competition_demo_cache_v2.json` is bound to the audited target profile hash and recalculates only Reading Completeness with the corrected passage boundary.

## Two-layer feedback architecture

### Layer A: deterministic evidence engine

This layer always works offline. It selects strengths and priorities from real criterion, pause, coverage and word evidence. D043, D064 and D048 now receive different supported fallback feedback rather than the same template. No grammar, vocabulary, confidence, accent, Intelligibility or Overall claim is produced.

### Layer B: manual GPT review

No hidden browser, scraping or unofficial website automation exists. `scripts/export_gpt_review_bundle.py` creates a local bundle containing RAW_CROPPED learner audio, audited target, transcript, machine evidence, a versioned prompt and a provenance manifest. The researcher submits it manually to ChatGPT.

`scripts/import_gpt_review.py` accepts JSON only when video, input, scorer, target and prompt hashes match. It also validates evidence references, supported review words, wording safety and contradiction flags. Imported wording never changes official numeric scores. A missing, malformed or stale review silently falls back to deterministic feedback.

Bundles have been exported locally for D043, D064 and D048 under ignored `runs/competition_gpt_review/`. No review has been fabricated or falsely labeled as ChatGPT-reviewed. At this build point, all three manual reviews remain pending.

## UI hierarchy

- Home uses the existing safe hero visual and two explicit actions: **Try a Demo** and **Assess a Duet**.
- Assessment defaults to D043 as the main presentation case, followed by D064 and D048.
- Results keep the four aligned score cards as the primary visual moment.
- Pronunciation and Prosody visibly retain Preliminary badges.
- Feedback cards appear immediately under the scores, followed by supported words-to-review chips.
- Student evidence shows calibrated criterion results and useful fluency/completeness metrics, not unexplained raw model values.
- Target topic, scored passage and learner transcript are visually separated.
- Raw MultiPA values, exact target hash and feedback provenance appear only in `?presenter=1` technical details.
- How the AI works and Research validation remain collapsed by default.

The design remains a projector-oriented light theme with one cobalt accent, 16 px cards, strong contrast, restrained motion and explicit reduced-motion behavior.

## Fast Demo

Presentation order is D043, D064, D048. Each uses genuine frozen local machine evidence with input, model, scorer and target hashes. Cache validation rejects membership changes, stale scorer files, stale target profiles, changed media, private rating fields, fabricated scores, Intelligibility and Overall.

## Live Analysis

The existing successful pipeline is preserved:

```text
upload -> Phase 1 -> SCORABLE_CLEAN gate -> local ASR -> frozen scorer -> deterministic feedback
```

The title correction affects only Reading Completeness. MultiPA target segmentation remains v1-identical. New uploads do not call ChatGPT and use deterministic feedback unless a future exact hash-bound review exists.

## Offline behavior

Known Fast Demos require no network, Azure, Speechace, Qwen or external LLM API. Live readiness verifies FFmpeg, faster-whisper, Silero VAD and every local MultiPA asset before processing. Manual GPT reviews, once imported, are local JSON artifacts and do not need network at presentation time.

## Failure behavior

- NOT_SCORABLE recordings show no numeric score and receive a simple retry explanation.
- Missing criterion output is labeled unavailable; no number is fabricated.
- Invalid or stale GPT review content is ignored and deterministic feedback remains visible.
- Stack traces, raw reason codes and private paths remain hidden in student mode.

## Validation evidence and limitations

- Pronunciation development MAE: 0.491; mini-validation MAE: 0.436.
- Fluency development MAE: 0.420; mini-validation MAE: 0.513.
- Prosody development MAE: 0.588; mini-validation MAE: 0.703.
- Mini-validation N=3 is descriptive only.
- Pronunciation and Prosody remain preliminary.
- Reading Completeness is ASR-assisted; uncertainty is not a confirmed omission.
- Intelligibility remains human-only.
- No Overall, CEFR, IELTS or standardized proficiency claim is made.

## Startup and presentation flow

Double-click `START_COMPETITION_DEMO.bat`. Use D043 first, show scores and feedback, open evidence, explain the AI stages, then show research validation. Use D064 as a backup consistency case and D048 for a limitation discussion. Full presenter guidance is in `COMPETITION_REHEARSAL.md`.

## Freeze state

`competition_freeze_v1.json` records `COMPETITION_FREEZE_V1`, scorer/checkpoint hashes, target profile and passage hashes, cache hash, prompt hash, demo order, source hashes, startup command and limitations. Scoring and target interpretation must not change after this freeze unless a severe correctness defect is found.

The freeze truthfully records that all three manual GPT reviews are pending. Deterministic feedback keeps the product operational, but the strict requirement that every known demo use an imported GPT review is not complete until those reviews are supplied and validated.

## Final quality assurance

- Fast Demo D043, D064 and D048 load genuine cache-v2 results with distinct deterministic feedback and no network dependency.
- A fresh development-only D064 Live Analysis completed `SCORABLE_CLEAN` with all four supported criteria, no model failure, no machine Intelligibility, no Overall and no holdout processing.
- Targeted competition tests: **16 passed**.
- Full normal suite: **132 passed, 2 skipped**.
- Python compilation and Streamlit AppTest passed.
- Playwright visual QA passed at **1366x768** and **1920x1080** with no horizontal overflow, clipped score cards or clipped feedback cards.
- The only test warning is a non-blocking package-resource deprecation warning from the third-party Silero VAD package.
