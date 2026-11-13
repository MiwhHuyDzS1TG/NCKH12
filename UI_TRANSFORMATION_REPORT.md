# DUET / SPEAK UI Transformation Report

## Outcome

The competition product now ships as a local React application named **DUET / SPEAK - Speaking Intelligence Studio**. It is a new product-experience layer over the existing frozen Python pipeline. The Streamlit competition interface remains available as a rollback, and the research and teacher routes remain unchanged.

## Architecture

- React 19.3.1, TypeScript 5.9.3 and Vite 7.3.8.
- Custom responsive CSS, locally bundled Manrope and Newsreader variable fonts.
- Radix Dialog/Collapsible for focus-safe presenter and evidence interactions.
- Motion for restrained entrances, route state changes and in-view criterion reveals.
- A same-origin FastAPI adapter on `127.0.0.1:8765` calls the existing Product V2 services. It does not copy or replace the scorer.
- `product_dist/` is committed, so normal launch does not require a Vite dev server or an npm command.

The adapter exposes only product-safe fields. It removes paths, raw MultiPA structures, teacher labels and internal errors, and validates that served media remains under an approved local root.

## Visual system

The design direction combines editorial typography, an audio-production studio and optimistic education. Midnight surfaces carry assessment and evidence; a warm canvas supports reading and coaching; mint, periwinkle and apricot encode supporting states; coral is reserved as a signature action accent. Layouts use asymmetric corners, large editorial type, open composition and deliberate full-width sections instead of a repeated dashboard-card grid.

The Home signature image is a decorative audio sculpture created with the built-in image generation tool and stored at `product_frontend/public/assets/duet-speak-audio-sculpture.webp`. It has empty alternative text and `aria-hidden=true`; it is not presented as a learner waveform, diagnostic plot or model output.

## Core experience

- **Home:** two obvious actions, D043/D064/D048 in frozen order, authentic thumbnails, local-privacy story and an editorial hero.
- **Assessment:** upload and permission-gated TikTok import, real indeterminate backend status, frozen demo rail and private Recent Videos continuation.
- **Results:** video and RAW_CROPPED learner audio, Overall Practice Score hero, four differently composed criterion views, prioritized coaching, keyboard-operable evidence, transcript and next actions.
- **Recent Videos:** genuine local thumbnails, source/status metadata, selected-item Assess/View Result routing and protected removal.
- **Presenter:** existing real ChatGPT connection/model status in a focus-managed dialog plus presenter-only provenance on Results.

## Overall Practice Score

`speaking_evidence.product_api` owns formula version `nckh12-product-overall-practice-v1`:

```text
reading_completeness_5 = 1 + 4 * coverage
overall = mean(pronunciation, fluency, prosody, reading_completeness_5)
```

It is returned only when all four inputs are finite and valid. It is null for missing criteria and `NOT_SCORABLE`. React displays the backend result to one decimal place; it does not calculate the score. The product status is `DESCRIPTIVE_PRODUCT_COMPOSITE`; presenter status is `UNVALIDATED_PRODUCT_COMPOSITE`. It is not standardized, research-validated, CEFR, B2, IELTS or teacher-equivalent. Machine Intelligibility remains absent and is not included.

## Functional parity and privacy

Fast Demo, direct upload, local scoring, permission-gated TikTok import, persistent Recent Videos, video/audio playback, four criterion displays, deterministic feedback, optional authorized ChatGPT feedback and presenter controls remain available. New media remains `UNSEEN_USER_MEDIA` outside research membership. No student media, transcript, token, private result, media database or unredacted screenshot is committed.

The real saved-media path was executed through Recent Video -> frozen scoring -> feedback preparation/fallback -> result persistence -> React Results. The prior NumPy `int64` serialization crash did not recur. The genuine result was scientifically partial, so Overall correctly displayed unavailable rather than averaging incomplete criteria.

## Responsive, motion and accessibility QA

The product was inspected at 1920x1080, 1440x900, 1366x768, 768x1024 and 390x844. Automated layout audits found no horizontal overflow or missing image. Mobile uses its own order and single-column criterion story. At 1366x768, the first Results viewport contains the speaking snapshot, Overall and media/audio area.

Browser interaction QA verified keyboard focus, Enter-operated evidence disclosure, dialog focus and Escape close, upload drag state, media hover motion, Results reveal, reduced-motion media query, collapsed transition durations and mobile overflow. Native media controls remain intact. Destructive removal uses the browser's blocking confirmation before the local delete request.

## Visual evidence

Baseline: `ui_evidence/before/`.

Final safe screenshots: `ui_evidence/after/home-1920.png`, `home-1366.png`, `home-mobile.png`, `assessment-1366.png`, `assessment-mobile.png`, `recent-1440.png`, `processing-genuine-1366.png`, `results-d043-1920.png`, `results-d043-1366.png`, `results-d043-mobile.png`, `results-d064-1440.png`, `results-d048-1440.png`, `evidence-expanded-1366.png`, and `presenter-chatgpt-1366.png`.

Demo and private thumbnails, transcript and account label are blurred or hidden in committed evidence. A genuine stable `NOT_SCORABLE` item was not available; no fake result was fabricated solely to create that screenshot.

## Verification and external limitations

Final release verification measured: frontend unit **5 passed**, TypeScript **PASS**, ESLint **PASS**, production build **PASS** (538 modules), focused Python **77 passed**, full Python **193 passed / 2 skipped**, Playwright release regression **8 passed**, compilation **PASS**, and legacy Streamlit coverage **PASS**. The retained warnings are the non-blocking Vite chunk-size advisory and third-party Silero VAD package-resource deprecation. The React, legacy Streamlit and Teacher launch paths remain available. ChatGPT is genuinely authorized on this computer; a real text-only structured feedback request completed and passed the evidence validator without replacing scores. Real TikTok import remains `PENDING_USER_TEST_URL`; no external import success is claimed without a user-supplied authorized URL.

## Rollback

- Final product: double-click `START_NCKH12.bat` and keep its visible backend terminal open.
- Historical/developer React launcher: `START_COMPETITION_DEMO.bat`.
- Legacy product: double-click `START_COMPETITION_DEMO_LEGACY.bat`.
- Teacher: `START_TEACHER_RATING.bat`.
- Research console: existing Streamlit route and launcher behavior remain unchanged.

Removing the React product layer does not require changing the scorer or any research artifact.

## Final release stabilization

The final local release prevents stale-build white screens by serving SPA HTML with `Cache-Control: no-store` while retaining immutable caching only for content-hashed assets. Direct and refreshed D043, D064 and D048 result routes pass at 1920x1080, 1366x768 and 390px with no uncaught browser errors or horizontal overflow. A top-level Error Boundary, validated result contract, explicit loading/not-found/API-error states and media fallbacks ensure a failed subsystem never leaves a featureless page.

The local CSP now permits only the bundled self/data fonts it actually uses, removing the previous browser-console violations. Missing API endpoints and missing static assets remain real 404 responses rather than receiving the SPA document. The primary launcher is `START_NCKH12.bat`; it uses the committed production build, binds only to `127.0.0.1`, waits for release-matched health, opens the browser, and keeps human-readable pipeline events in one visible terminal.

Formal report-ready app-only captures are stored under `ui_evidence/final_release/` with a route, purpose and privacy note for every image. No browser chrome, OAuth identity, private uploaded media, local path, teacher data or holdout material is present.
