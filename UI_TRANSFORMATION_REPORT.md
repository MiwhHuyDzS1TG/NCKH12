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

Final verification measured: frontend unit **2 passed**, TypeScript **PASS**, ESLint **PASS**, production build **PASS** (537 modules), targeted Python **71 passed**, full Python **187 passed / 2 skipped**, targeted Streamlit AppTest **46 passed**, compilation **PASS**, and browser visual/interaction QA **PASS**. The only warning is the existing third-party Silero VAD package-resource deprecation. The React, legacy Streamlit and Teacher launchers were started for real and returned healthy local routes. ChatGPT is genuinely authorized on this computer; the real assessment retained deterministic fallback because returned wording failed an existing supported-evidence validator, not because of serialization. Real TikTok import remains `PENDING_USER_TEST_URL`; no external import success is claimed without a user-supplied authorized URL.

## Rollback

- New product: double-click `START_COMPETITION_DEMO.bat`.
- Legacy product: double-click `START_COMPETITION_DEMO_LEGACY.bat`.
- Teacher: `START_TEACHER_RATING.bat`.
- Research console: existing Streamlit route and launcher behavior remain unchanged.

Removing the React product layer does not require changing the scorer or any research artifact.
