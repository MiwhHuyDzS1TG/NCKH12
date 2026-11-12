# CODEX IMPLEMENTATION BRIEF — NCKH12 Speaking Coach / DUET SPEAK

## ROLE AND NON-NEGOTIABLE MISSION

You are acting as a **principal product designer, art director, senior frontend engineer, and Python integration engineer**. This is an **implementation sprint**, not a proposal-only task.

The current NCKH12 Speaking Coach product works, but its UI looks like a basic Streamlit prototype. Your mission is to deliver a **dramatic, unmistakable visual transformation** into a polished, premium, competition-ready speaking assessment web app — while preserving its established UX, functionality, scientific integrity, privacy boundaries, and offline/local workflow.

**The success criterion is visual and experiential, not the number of features or CSS changes.** It must feel like a thoughtfully art-directed EdTech product in the same quality bracket as an excellent contemporary funded product, not like an admin dashboard, a generic template, or Streamlit with gradients.

**Do not stop after planning, generating static mockups, or writing a design document. Implement, run, inspect, test, and deliver the working UI.** Do not ask for styling approval. Make deliberate design decisions and execute them. If a local dependency prevents a particular part from running, deliver everything independently possible and report the precise blocker.

## 0. READ THE ACTUAL PROJECT BEFORE TOUCHING CODE

1. Read `PROJECT_STATE.md` fully, **especially the most recent sections**:
   - `COMPETITION DEMO MVP` (2026-11-07)
   - `COMPETITION FINAL PRODUCT SPRINT` (2026-11-11)
   - `COMPETITION PRODUCT V2 - AUTHORIZED FEEDBACK AND MEDIA WORKSPACE` (2026-11-12)
   - P2.4D and P2.5 freeze/validation constraints.
2. Inspect the real repository: `app.py`, competition UI modules, Python services, the two Product V2 reports, `COMPETITION_FINAL_BUILD_REPORT.md`, `COMPETITION_REHEARSAL.md`, launch scripts, tests, and existing screenshot assets. Do not assume file names beyond those verified in the repo.
3. Map every currently working competition-facing route, state transition, data source, and backend call. Identify student-facing functionality separately from researcher/teacher routes.
4. Take baseline screenshots of the **actual running app**, not an imagined version, and identify the ten biggest visual defects. If screenshots or browser tooling are unavailable, say so explicitly rather than pretending visual review happened.
5. Record a brief baseline and implementation plan in a new `UI_REDESIGN_PLAN.md`, then immediately implement.

> Historical Phase-1 notes about avoiding React applied to the old research-only phase. This explicit task authorizes a **new competition-facing frontend**. It does NOT authorize rewriting DSP/scoring, replacing the Research Console, or weakening scientific/privacy safeguards.

## 1. VISUAL NORTH STAR: "DUET / SPEAK — SPEAKING INTELLIGENCE STUDIO"

**Product identity:** retain the real NCKH12 Speaking Coach identity and scientific context. The public-facing visual lockup may read `DUET / SPEAK`, with a restrained `NCKH12 Speaking Coach` descriptor. Do not rename internal artifacts, models, project IDs, or scientific labels merely to match branding.

**Art direction:** editorial sophistication + audio production studio + optimistic education. Imagine the clarity of a premium creative tool, the polish of an award-worthy SaaS launch, and the seriousness of a speech research instrument. It should feel confident, tactile, expressive, and mature — not cartoonish, cyberpunk, or a wall of cards.

**Visual language:**
- An **editorial, bright, spacious home experience** with striking type, deliberate asymmetry, layered but purposeful composition, and a memorable hero composition built from authentic product UI (video frame, waveforms, transcript, result fragments), not stock photography.
- A **deep midnight assessment workspace** that focuses attention on the uploaded video and the current task. Rich navy surfaces, precise borders, sophisticated accent lighting, and calm clarity.
- A **results story** that combines a sophisticated dark feature panel and beautifully composed warm off-white reading surfaces. Results should read like a personal speaking report rather than an analytics dashboard.
- Use a restrained palette: midnight `#101828`, ink `#152238`, canvas `#F6F5F1`, white `#FFFFFF`, soft mint `#A7F3D0`, muted periwinkle `#A5B4FC`, warm apricot `#FFB98B`. Adjust values slightly after real browser review for accessibility. Avoid random rainbow gradients and excessive glassmorphism.
- Art-directed display typography with a genuinely strong type scale, plus a highly readable UI sans. Choose compatible open-license fonts and **bundle locally** for offline use; no CDN dependency. Crisp typographic hierarchy is more important than decorative shapes.
- Build a consistent radius, spacing, elevation, stroke, and motion system. Deliberate whitespace and negative space. Avoid dozens of identical rounded rectangle KPI cards.
- Use custom SVG/CSS audio motifs, abstract waveform visualizations based on real media/evidence when available, large soft atmospheric shapes, carefully placed media previews, beautiful empty states, and concise iconography. Use real media/evidence or clearly abstract decoration — **never fabricated diagnostic plots or made-up score numbers**.
- Transitions should be responsive, quiet, tactile and intentional: ~180–350 ms for most micro-interactions; honor `prefers-reduced-motion`. No intrusive animation, auto-playing audio, or heavy particle backgrounds.

**Anti-patterns to remove:** Streamlit default chrome, dense forms, cramped columns, generic gray boxes, gratuitous gradients, nested accordions everywhere, tiny type, repetitive KPI tiles, scattered debug labels, default file inputs, and visually undifferentiated primary/secondary actions.

The redesign must be visually original. **Do not simply apply Tailwind colors to the existing DOM. Recompose the presentation layer while preserving the user's effective workflow.**

## 2. FRONTEND / BACKEND ARCHITECTURE

**Preferred solution (strong recommendation):**
- New isolated **React + TypeScript + Vite** competition frontend.
- **Tailwind CSS + shadcn/ui/Radix primitives** for accessible components; custom styling and art direction must dominate the final output.
- **Motion** for subtle interface choreography, **Lucide** for consistent icons.
- Typed API client and schema validation where helpful. Use charts/audio libraries only if they actually improve real evidence visualization.
- A **thin Python FastAPI adapter** (or equivalently light existing-framework adapter if the actual repo shows a safer approach) calling the **existing** pipeline, cache, library, consent, auth and feedback service functions.
- Prefer **one loopback same-origin product server** that serves the built frontend and its `/api/...` endpoints; no public hosting and no mandatory dev server in normal use.
- Preserve the existing Streamlit Research Console and teacher/validation views. They must remain functional and independently launchable.

**Integration constraints:**
- Do NOT copy or reimplement the scorer in TypeScript. The frontend is presentation and orchestration only.
- Do NOT rewrite Phase-1 cancellation/VAD, raw-audio cropping, small.en ASR, MultiPA inference, frozen mappings, feedback eligibility rules, TikTok import security logic, library storage, or artifact validation.
- Keep live analysis running through the existing validated Python path. Expose genuine state and errors; never invent progress percentages or simulated analysis results.
- Keep the old competition UI route as a working fallback until the new product is validated. The legacy `?mode=competition_demo` and presenter-only behavior must not silently break. Provide a clearly documented new entrypoint and adapt `START_COMPETITION_DEMO.bat` **only when** the new packaged path is verified. Preserve a rollback path.
- Honor existing `127.0.0.1` loopback assumptions, Windows launch behavior, same-origin rules, existing OAuth callback/PKCE/state/nonce/DPAPI security, and session boundaries. Inspect current OAuth design before adding a new port/origin; do not break stable host identity to make frontend routing convenient.
- Bundle required frontend assets locally. After a normal install/build, the standard competition flow, local scoring, Fast Demo, recent library and deterministic feedback must work without the internet. Existing optional TikTok import and remote ChatGPT feedback may continue requiring network access.
- No new cloud service, database, analytics beacon, tracker, telemetry, external fonts, or media upload to a third party.
- Prefer the smallest reliable adapter rather than an architectural rewrite. If a chosen integration is demonstrably unsafe, retain the old path and explain the blocked integration. **Do not compromise existing tests for visual goals.**

## 3. REBUILD THESE REAL PRODUCT SURFACES

### A. HOME — a genuinely memorable first impression
- One exceptionally well-composed, desktop-first hero: strong headline, brief supporting copy, gorgeous UI-derived graphic, and two unmistakable actions: `Try a Demo` and `Assess a Duet`.
- Suggested copy direction (adjust to existing tone): **“Every Duet is a chance to grow.”** / “Turn speaking practice into evidence you can understand.” No guarantees of learning outcomes or scientific validation that do not exist.
- Present the genuine Fast Demo cases in the established presentation order: **D043 first**, then **D064**, then **D048**. Each case is a compelling selection card with real source thumbnail/media if available and neutral descriptive copy. Do not create invented learner personas, achievements, or numeric results.
- Small and elegant path to `Recent Videos`; clear privacy/local-first messaging.
- Make it obvious within three seconds what the app does and where to click. The aesthetic can be bold; the navigation must be effortless.

### B. ASSESSMENT — a video-centric, confidence-inspiring workspace
- Preserve the two existing user paths: local upload and permission-gated **public TikTok import**. Give them beautiful, clear, accessible entry points rather than one confusing mixed form.
- Attractive drag-and-drop uploader with keyboard fallback, valid file feedback, and truthful size/type errors. Video preview should be prominent; import preview uses the existing official TikTok oEmbed handling.
- Keep consent explicit before an import. Never auto-download pasted URLs or bypass existing access restrictions.
- Show genuine analysis state: input accepted, prepared/validated, speech extraction, evidence/scoring, ready — only when backend exposes those real states. If stages cannot be exposed without changing scoring, show a truthful indeterminate activity indicator and status message instead of fake step completion.
- Offline and failure states: invalid file, network unavailable for TikTok, missing model/runtime dependency, unscorable recording, model failure, cancellation/abort where actually supported. No stack traces or system paths in normal UI.
- Offer clear transitions to Results and back to the workspace without data loss where supported.

### C. RESULTS — the signature experience / highest design priority

This page should be the strongest part of the product. Create a compelling visual narrative with:
1. Hero section: `Your speaking snapshot` (or superior copy), subtle task/topic context and source video/learner audio as **actual playback**, not a decoration.
2. Four elegant and distinct criterion modules driven exclusively by saved backend outputs:
   - **Fluency:** usable competition-facing criterion; preserve the frozen 1–5 mapping and preliminary calibration caveats.
   - **Reading Completeness:** deterministic **ASR-assisted** coverage; keep its actual representation/units. Do not invent a 1–5 score if backend returns coverage/percent instead.
   - **Pronunciation:** numeric only if genuine frozen scorer output exists; explicitly **Preliminary / narrow-range**.
   - **Prosody:** numeric only if genuine frozen scorer output exists; explicitly **Preliminary** with its limitations.
3. Never show **Overall**; never invent machine **Intelligibility**. Do not introduce CEFR/B2/IELTS claims. Do not imply all four criteria have equal scientific support.
4. A premium, easy-to-read formative feedback section showing genuinely selected strengths, priorities and next practice advice. Distinguish available personalized ChatGPT wording from deterministic fallback when it matters; don't imply a remote model ran when it didn't.
5. A beautiful expandable `Explore the evidence` section: real scored passage versus learner transcript, supported word chips, timestamp/evidence views, optional true waveform/timeline, source and interpretation caveats. Do not equate ASR differences with confirmed learner errors. Topic/title `One memorable event` is separate from the scored passage and the current `competition_target_profile_v2.json` exclusion must remain intact.
6. A clear path to assess another Duet and view recent results.
7. Research provenance, model hashes, private file paths, raw MultiPA values and technical diagnostics stay hidden from ordinary students and are exposed only by the existing authorized presenter mechanism where appropriate.

Visual hierarchy must show **what matters to the learner first**, evidence second, limitations honestly but not overwhelmingly. Numeric data must be truthful, legible and semantically labeled; use charts only when they communicate actual measured evidence.

### D. RECENT VIDEOS — a refined private media library
- Implement a responsive thumbnail/card grid or editorial list based on the real persisted private library.
- Clear recent-item metadata and real status; `Assess`, `View result`, and protected `Remove` actions must work exactly as before. Show meaningful empty/loading/error states.
- Duplicate handling and content hashes stay in backend. Imported/user media remain `UNSEEN_USER_MEDIA`, `research_membership=false`; no way to promote it to research development, ratings, validation or holdout.
- Do not expose local paths, research IDs, private artifacts or teacher outcomes through ordinary UI/API responses.

### E. PRESENTER-ONLY CONNECTION / CONTROLS
- Keep ChatGPT connection and its full OAuth lifecycle **presenter-only**. Build a sophisticated but restrained connection screen that accurately represents connected, disconnected, pending, expired, failed, and fallback states.
- Preserve existing public Sign in with ChatGPT policy and current backend behavior. No fake official partner endorsements, substitute auth flow, front-end token persistence, client secrets, insecure token logging, or background consent.
- Remote request privacy is unchanged: text evidence allowlist only, `store=false` as implemented; never send video/audio, paths, teacher ratings, validation/holdout data, unauthorized source URLs, Intelligibility or Overall. Remote wording may not modify scores.
- The current project's *real* OAuth smoke test and one real authorized feedback generation remain **pending human authorization** until actually completed. Likewise real TikTok import remains pending a user-provided test URL. Do not mark them passed by UI appearance or mocks.

## 4. ENGINEERING / SCIENTIFIC FREEZE — ZERO REGRESSIONS

`COMPETITION_FREEZE_V1` and Product V2 are not design suggestions. They are protection boundaries.

- No training, model replacement, recalibration, new rating, threshold tuning, scoring feature changes, or touching fixed holdout media/outcomes.
- Preserve frozen P2.4D scorer, local MultiPA checkpoint/mappings, Fluency mapping, deterministic Reading Completeness, corrected target boundary, data split, P2.5 outcomes, historical artifacts and input/cache hash verification.
- Existing Fast Demo results are genuine frozen-machine outputs, not hardcoded numbers. Preserve cache validity and reject stale inputs.
- Scoring input remains raw completed Duet -> existing Phase-1 learner intervals -> raw-cropped/masked audio. Never use cancellation residual as scoring input.
- Keep research/teacher interfaces and their blinded/label-segregated behavior unchanged.
- Keep safeguards against data leakage and research/teacher artifact exposure; review API serializers for new endpoints.
- Never silently downgrade errors into success states or claim validation that has not occurred.

## 5. MAKE THE EXPERIENCE FEEL EXPENSIVE, NOT FRAGILE

- Design at **1920×1080, 1440×900, 1366×768, 768px and 390px**. Real responsive composition, no horizontal scrolling, clipped tooltips, dead links, overflowing transcript text or inaccessible dialogs.
- Maintain usable tap targets, focus rings, visible labels, semantic headings, understandable errors, alt text, keyboard access, sufficient contrast and `prefers-reduced-motion` support. Aim for WCAG 2.2 AA where feasible.
- Avoid bulky JavaScript on initial load; use sensible splitting, lazy screens and efficient media preview. Do not embed full videos as giant base64 blobs.
- Use design tokens, reusable typography/layout components, focused CSS, documented component architecture and consistent responsive states.
- Use tasteful skeletons/empty states; never fake loaded analytics or scores.
- Product copy should be clear and student-appropriate, not verbose academic jargon, while labels such as `Preliminary` and `ASR-assisted` retain their scientific meaning.
- Design should remain visually strong without network assets and without a powerful GPU.

## 6. IMPLEMENTATION SEQUENCE — DO THE WORK

1. **Audit** existing app/routes/services and capture baseline behavior. Create a feature parity and risk matrix. Freeze key artifact hashes and relevant known-Demo output snapshots before edits.
2. **Establish** the frontend skeleton, design tokens, typography, reusable component library, local assets and navigation. Create the thinnest secure Python API adapter using existing functions.
3. **Implement** the actual Home and Assessment routes, wire real upload/import permissions, preview, analysis, errors and navigation.
4. **Implement** the Results signature experience using actual saved outputs for D043/D064/D048. Verify every displayed label/value is backend-derived. Wire the actual feedback and evidence expanders.
5. **Implement** the library and presenter-only connection controls, preserving full state and privacy semantics.
6. **Polish visually in the browser**: capture screenshots at the required viewports, inspect composition, refactor poor layouts, spacing, typography, contrast and hierarchy. Make at least one explicit design-improvement iteration after the first screenshot review. Do not declare victory from source code alone.
7. **Verify regression parity**: run relevant frontend tests, Python tests, Streamlit AppTests, Playwright browser flows, and existing real local-media smoke tests when dependencies are available. Do not invoke external live OAuth/TikTok tests without actual user authorization/test URL. No holdout execution.
8. **Package** a reliable one-click local Windows entrypoint for the new competition UI, while retaining the old Streamlit fallback. Verify offline startup and document required local dependencies.
9. **Update** `PROJECT_STATE.md` by appending a dedicated UI transformation sprint record; preserve historical decisions. Include actual file diffs, screenshot paths, tests, measured results, limitations and truthful pending states.

## 7. REQUIRED ACCEPTANCE CRITERIA

**Visual:** Home, Assessment, Results and Recent Videos are clearly a different visual generation from Streamlit. Excellent typographic hierarchy, strong branding, balanced composition, exceptional Results screen, controlled motion and responsive polish. Not merely new colors, a new hero text, or restyled Streamlit widgets.

**Functional:** Fast Demo D043/D064/D048, local upload analysis, source playback, genuine result rendering, deterministic feedback fallback, existing eligible ChatGPT connection/feedback, permission-gated TikTok import, and persistent Recent Videos/Remove behave as before. Clear error states. Research/teacher interfaces remain intact.

**Scientific:** zero scoring semantics or frozen artifact regressions. No invented Overall, Intelligibility, CEFR/B2/IELTS, unsupported pronunciation judgments or demo score claims. `holdout_processed=false` remains truthful.

**Privacy/security:** frontend never introduces media/cloud upload, token exposure, OAuth origin bugs, permissive localhost CORS/CSRF, path leakage, new analytics or research-data contamination. Existing user authorization remains explicit.

**Delivery:** a working locally launchable UI, not mockups. Final report includes a before/after screenshot gallery, actual commands, real test results, hash/behavior parity checks, what changed, known limitations, rollback instructions, and paths to key implementation files.

## 8. DELIVERABLES AND FINAL REPORT

Create or update as appropriate:
- Production-ready competition frontend and its maintainable source.
- Minimal integrated Python API adapter if required.
- New or updated Windows startup script with a verified end-to-end path, preserving the prior launcher/fallback.
- `UI_REDESIGN_PLAN.md` and `UI_TRANSFORMATION_REPORT.md`.
- Version-controlled, **non-sensitive** before/after screenshots for Home, Assessment, Results, library, plus representative narrow/mobile views.
- Automated UI/integration checks and regression tests.
- An appended, accurate UI sprint record in `PROJECT_STATE.md`.

**Your last message must contain:**
1. Summary of the actual implementation, not promises.
2. Design-system / frontend architectural decisions and why they fit the existing repository.
3. Exact startup command/path and where to access the new interface.
4. Screenshot paths and what you inspected/changed after visual review.
5. Feature-parity table covering each Product V2 function.
6. Exact test commands/results and preserved scoring/cache/freeze verification.
7. Remaining issues or manual smoke tests (especially real ChatGPT authorization and real TikTok URL), with no invented pass status.

**Final priority order:** (1) visually exceptional real Results/Home, (2) end-to-end user path and feature parity, (3) scientific/security preservation, (4) robust packaging and regression evidence. These priorities are additive: **none can be sacrificed for another.**

Start by examining the repository and `PROJECT_STATE.md`, then execute the implementation. Be ambitious in design and conservative in research logic.
