# Media Import and Local Library Report

## Product boundary

Product V2 accepts completed Duet videos for inference through direct upload or a permitted public TikTok link. Every new item is classified as `UNSEEN_USER_MEDIA`, has `research_membership=false`, and remains outside calibration, development, validation, holdout, and teacher-rating artifacts.

The library lives under the user's local application-data directory, outside the repository and outside all research-data paths. Uploaded/downloaded videos, thumbnails, local result files, source URLs, and private feedback caches are ignored by Git.

## TikTok preview and import

TikTok URLs are restricted to `http` or `https`, known TikTok hosts, safe ports, and no embedded credentials. Redirects are followed manually with a small fixed limit, and every hop must remain on a TikTok host.

Preview uses TikTok's official oEmbed endpoint. The UI displays the provider's returned preview only after URL validation. A missing, private, deleted, restricted, or network-unavailable video produces a neutral error and directs the user to upload their own file.

Import requires an unchecked-by-default confirmation: `I own this video or have permission to use it for this assessment.`

The importer uses pinned `yt-dlp==2026.7.4` through a subprocess argument list with no shell, no browser-cookie harvesting, no playlist, short timeout/retry limits, a five-minute duration filter, a 500 MB limit, and strict output-path validation. It does not bypass private videos, authentication, or access controls and makes no watermark-removal claim.

Real public import status is `PENDING_USER_TEST_URL`. Automated network paths are mocked and upload remains the reliable primary fallback.

## Direct upload and Recent Videos

Supported formats are MP4, MOV, MKV, and WebM. The maximum size is 500 MB and maximum duration is five minutes. FFprobe validates readable video metadata before registration. Invalid media is removed from the incoming item directory and never enters the library. SHA-256 input identity prevents uncontrolled duplicates.

The persistent Recent Videos workspace stores friendly title, source badge, import time, duration/resolution, local source/thumbnail locations, Ready/Assessed state, result relationship, and explicit non-research classification. The student-facing card offers Assess, View result when available, and Remove. Machine predictions and research metadata are not displayed before assessment.

## Assessment, removal, and restart behavior

Assess runs the same frozen local competition pipeline and writes analysis only beneath that media item's private directory. Real stage messages are surfaced as the pipeline advances. The saved result can be reopened after an app restart. Optional personalized feedback is attached only after local scoring and cannot change numeric results.

Remove validates that the target is a user-media directory below the library root, rejects demonstration/research media, removes only that item and its analysis, removes feedback cache records tied to its input hash, and updates the registry atomically.

## Offline behavior

Without a network, app launch, Fast Demo, direct upload, metadata/thumbnail creation, Recent Videos, local frozen assessment, saved results, deterministic feedback, and valid cached personalized feedback remain available. New TikTok preview/import and new personalized feedback degrade gracefully.

## Verification and limitations

Automated tests cover valid/invalid URLs, safe redirects, oEmbed, permission, safe subprocess construction, import failure, direct upload, metadata, duplicates, restart persistence, removal protection, and research isolation: **17 passed**. A real local-I/O smoke test also passed for upload, thumbnail, duplicate control, restart persistence, assessed status, and protected removal. External TikTok traffic is mocked.

No real public TikTok URL was supplied in project context, so real import is correctly `PENDING_USER_TEST_URL`, not a fabricated success.
