# Final release screenshot index

These app-only captures use the frozen development demo `T001-D043` or a controlled empty-library state. The demo video region is blurred in report captures so the learner cannot be identified. The images contain no browser chrome, OAuth identity, local paths, uploaded private media, teacher data, holdout data or unrelated desktop content.

| File | Page / route | Purpose |
| --- | --- | --- |
| `01_HOME.png` | Home — `/` | Shows the final DUET / SPEAK identity, primary proposition, demo/assessment actions and signature audio sculpture. |
| `02_ASSESSMENT.png` | Assessment — `/assess` | Shows the upload, TikTok, Recent Videos and frozen-demo entry points in the final studio workspace. |
| `03_RESULTS_D043.png` | Results — `/results/demo/T001-D043` | Primary report figure: the full genuine D043 learner-facing result, including Overall Practice Score, criterion evidence and formative feedback. |
| `04_RESULTS_EVIDENCE.png` | Expanded evidence — `/results/demo/T001-D043` | Shows the genuine scored passage, learner transcript, review prompts and measured fluency evidence. |
| `05_RECENT_VIDEOS.png` | Recent Videos — `/recent` | Shows the safe empty private-library state; the media API was isolated to an empty list so no private uploads appear. |
| `07_MOBILE_RESULTS.png` | Results — `/results/demo/T001-D043` at 390×844 | Demonstrates the responsive learner-facing Results layout on a mobile viewport. |

`06_RESULTS_PARTIAL.png` was intentionally omitted. The genuine PARTIAL smoke used private uploaded media, so it was not captured or committed.

Capture command: from `product_frontend`, run `node scripts/capture_release_screenshots.mjs` while the final local app is healthy on `http://127.0.0.1:8765`.
