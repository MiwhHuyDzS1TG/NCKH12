# DUET / SPEAK UI Transformation Plan

## Baseline

The verified competition product at `?mode=competition_demo` is functional and scientifically careful, but the presentation layer is still a Streamlit application. Baseline screenshots are preserved under `ui_evidence/before/`.

The redesign is interpreted as a premium EdTech competition product with the visual language of an editorial audio studio: optimistic, tactile, calm and scientifically precise. Design dials are `DESIGN_VARIANCE 8`, `MOTION_INTENSITY 6`, and `VISUAL_DENSITY 5`.

### Ten highest-impact visual defects

1. The hero is contained in a generic white card and does not own the viewport.
2. Typography is competent but has no distinct editorial voice or memorable hierarchy.
3. Home relies on three equal feature boxes, creating a template-like rhythm.
4. Assessment looks like a long form rather than a video-centric listening workspace.
5. Upload and TikTok import feel like browser controls, not deliberate product actions.
6. Results begin with a process strip and four equal KPI cards, so every criterion appears equally validated.
7. Feedback is three more equal cards, which weakens the priority of the learner's next action.
8. Source video, learner audio, transcript and evidence feel appended instead of composing one report.
9. Recent Videos lacks the hierarchy and spatial rhythm of a private media library.
10. Mobile works mechanically but does not have its own intentional composition.

## Architecture decision

The new competition surface is an isolated React + TypeScript + Vite single-page application. It uses a custom token and CSS composition layer, Radix primitives for accessible disclosure/dialog behavior, Motion for restrained state and entrance choreography, Phosphor for one coherent icon family, and locally bundled Manrope/Newsreader fonts.

`speaking_evidence.product_api` is a same-origin FastAPI adapter bound to `127.0.0.1`. It calls the existing frozen Python services and never implements scoring. It exposes only public product serializers and validated media endpoints. Research paths, human ratings, raw MultiPA values, local file paths and internal errors are not serialized.

The legacy Streamlit product remains unchanged at `?mode=competition_demo` and is launchable with `START_COMPETITION_DEMO_LEGACY.bat`. Research and teacher routes remain on Streamlit.

## Design system

- Identity: `DUET / SPEAK` with `NCKH12 Speaking Coach` as the scientific descriptor.
- Type: Newsreader for editorial display; Manrope for interaction and evidence text.
- Core palette: midnight `#101828`, ink `#152238`, canvas `#F6F5F1`, mint `#A7F3D0`, periwinkle `#A5B4FC`, apricot `#FFB98B` and one interaction accent, coral `#F26B4F`.
- Shape: asymmetric 4-36 px editorial corners, not universal pills/cards.
- Motion: 180-350 ms interaction feedback plus restrained route-content reveals; all motion collapses under `prefers-reduced-motion`.
- Route themes: bright editorial Home/Library, deep-midnight Assessment, and an intentional report story on Results that moves from a midnight media feature into warm reading surfaces. This is a route-level narrative, not arbitrary theme switching.

## Feature parity and risk matrix

| Product V2 capability | New surface | Existing service reused | Main risk and mitigation |
| --- | --- | --- | --- |
| Fast Demo D043, D064, D048 | Home, Assessment, Results | `competition_demo_cache_v2.json`, `load_demo_cache` | Validate cache and media hashes before every result/media response. |
| Real Duet upload | Assessment | `MediaLibrary.register_upload` | Existing size, type and FFprobe validation remain authoritative. |
| Local frozen assessment | Assessment job + Results | `run_live_analysis` | Background adapter only relays real progress callbacks and safe failures. |
| TikTok preview/import | Assessment | `fetch_tiktok_oembed`, `MediaLibrary.import_tiktok` | Permission stays unchecked by default; no auto-import. |
| Recent Videos | Library | `MediaLibrary` | Serializer omits paths, source URLs and research metadata. |
| Video/audio playback | Results | Validated `FileResponse` endpoints | Every resolved path must remain below its approved media root. |
| Four criteria | Results | Saved backend result | Machine Intelligibility remains absent; each criterion keeps its frozen status. |
| Overall Practice Score | Results hero | Product adapter only | Equal-weight descriptive composite of the four available measures; null unless all four are valid; never written to research artifacts. |
| Deterministic feedback | Results | Existing saved result | Display exactly the selected backend text. |
| ChatGPT feedback/fallback | Post-assessment + presenter controls | `attach_automatic_feedback`, `ChatGPTAuthManager` | Optional failure preserves result; tokens never reach the browser. |
| Presenter connection | Presenter-only dialog | Existing PKCE/DPAPI flow | Local request plus explicit presenter header; no frontend token storage. |
| Research/teacher workflows | Legacy Streamlit | Existing `app.py` routes | No modification to route code or artifacts. |

## Frozen boundary before edits

- `competition_freeze_v1.json`: `0b73719689c9805de741fedb233ef60eb039a8fc220c0e629ea9640b2f47f50d`
- `p24d_multipa_plan_v1.json`: `90755aaa169b605c7b9a070ae411dc28366a2b3e568e4daf2e81dc15a4cee1c1`
- `competition_target_profile_v2.json`: `e2a4b2f1ee77860bab9a1a075d07bf61a27fe9ab641a71719dc129def1fb9da2`

The fixed holdout is not an implementation or test input for this sprint.

## Approved product-only summary

The late product correction adds `Overall Practice Score` only at the API presentation boundary. Python converts Reading Completeness coverage from 0-1 to 1-5, then takes an equal-weight mean with Pronunciation, Fluency and Prosody. React displays the returned one-decimal value and does not reproduce the formula. The status is `DESCRIPTIVE_PRODUCT_COMPOSITE`, the presenter designation is `UNVALIDATED_PRODUCT_COMPOSITE`, and missing input or `NOT_SCORABLE` produces no composite. Intelligibility is excluded.

## Visual QA plan

1. Capture actual Home, Assessment, Results and Recent screens at 1920, 1440, 1366 and 390 px.
2. Check horizontal overflow, clipped controls and failed media images mechanically.
3. Inspect full-page screenshots for hierarchy, rhythm, copy and media prominence.
4. Perform at least one explicit design iteration after review.
5. Commit only sanitized screenshots. Demo thumbnails and video frames are blurred/hidden in version-controlled evidence; unredacted screenshots remain ignored locally.
