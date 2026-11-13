# NCKH12 Competition Final Release

## What works

The local React product supports Home, Assessment, Recent Videos, all three frozen Fast Demos, direct/refreshable Results routes, local upload, persistent private media, frozen local scoring, deterministic feedback and optional authorized ChatGPT wording. Complete and genuine partial results have both been exercised.

## What is frozen

`COMPETITION_FREEZE_V1`, the P2.4D scorer, MultiPA checkpoint/configuration, Fluency/Pronunciation/Prosody mappings, Reading Completeness method, target profile, development split and P2.5 decision are unchanged. The fixed holdout was not opened or processed. Machine Intelligibility remains absent.

## How to start

Double-click `START_NCKH12.bat`. Keep the backend terminal open. The browser opens only after the local health check passes. Press Ctrl+C in that terminal to stop the backend. `START_COMPETITION_DEMO_LEGACY.bat` remains the Streamlit rollback.

## How scoring works

The existing frozen Python pipeline identifies learner speech in the completed Duet, prepares RAW_CROPPED learner audio, runs local ASR and produces the supported criterion evidence. The React/API layer displays those outputs; it does not recalculate them.

## GPT feedback and offline fallback

When authorized, only allowlisted text evidence is sent for structured wording. Video, audio, private paths, teacher ratings, holdout data and raw private payloads are excluded. The evidence validator must accept the response before it is shown. Any connection, quota, schema or safety failure keeps the scores intact and selects deterministic local feedback. Core demos, upload, scoring, library and deterministic feedback work without Internet.

## What Overall means

Overall Practice Score is an equal-weight product summary of Pronunciation, Fluency, Prosody and ASR-assisted Reading Completeness on the 1-5 display scale. It is shown only when all four inputs exist. It is descriptive, `UNVALIDATED_PRODUCT_COMPOSITE`, not research-validated, CEFR, B2 or IELTS.

## Reliability and privacy

Deep links and refreshes do not reuse stale SPA HTML. Unexpected React exceptions show a recoverable Error Boundary. Missing result/API/media states are explicit. The server binds only to `127.0.0.1`; tokens remain Windows-protected outside Git, paths are omitted from normal API responses, and new media remains `UNSEEN_USER_MEDIA` with `research_membership=false`.

## Known limitations and external pending tests

- Real public TikTok import remains `PENDING_USER_TEST_URL`; no user-authorized URL was supplied.
- Pronunciation and Prosody remain preliminary and narrow-development-range measures.
- Reading Completeness is ASR-assisted; ASR differences are not confirmed learner errors.
- The Vite bundle-size advisory and third-party Silero package-resource deprecation are non-blocking local warnings.

## Verification

Fresh final verification produced 5 passing frontend unit tests, passing TypeScript and ESLint, a 538-module production build, 8 passing Playwright regressions, 77 passing focused Python tests, and 193 passing full-suite tests with 2 deliberate skips. Python compilation and legacy Streamlit coverage passed. A real saved video completed upload, frozen scoring, accepted authorized ChatGPT wording and React Results while the visible terminal showed safe timed stages.

Safe app-only report figures are indexed in `ui_evidence/final_release/README.md`. They cover Home, Assessment, the full D043 Results story, expanded evidence, the controlled empty Recent Videos state and mobile Results. The private genuine PARTIAL smoke was deliberately not captured.

## Release and rollback

Release marker: `competition_final_release.json` (`COMPETITION_FINAL_RELEASE`). The release commit is the commit containing that marker. For rollback, stop the React backend and use `START_COMPETITION_DEMO_LEGACY.bat`; no scorer or research artifact change is required.
