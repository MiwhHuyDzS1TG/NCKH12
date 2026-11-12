# ChatGPT Automatic Feedback Report

## Scope

NCKH12 Product V2 adds optional automatic, text-only personalized feedback after the frozen local assessment has completed. It does not replace, adjust, or create the official numeric criterion scores. Local deterministic evidence-based feedback remains available at all times.

The implementation follows current official OpenAI guidance:

- [Sign in with ChatGPT](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
- [Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
- [Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)

## Authorization architecture

- Authorization endpoint: `https://auth.openai.com/api/accounts/authorize`
- Token endpoint: `https://auth.openai.com/api/accounts/oauth/token`
- API resource: `https://api.openai.com/v1`
- Initial public client: `dynamic_agent_client`, followed by the issued client identifier.
- Stable host identity: a generated `ext_agent_host_id` is stored outside the repository.
- Requested scopes: `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`.
- Callback: an ephemeral loopback listener bound only to `127.0.0.1`, never `localhost` or a public interface.
- Request protection: PKCE S256, a cryptographically random state, and a cryptographically random nonce.
- Identity verification: RS256 signature, issuer, audience, nonce, expiry, and subject are checked against the published OpenID configuration and JWKS.

The presenter-only setup screen uses the official `Continue with ChatGPT` wording. The human flow is:

1. Click `Continue with ChatGPT`.
2. Approve access in the system browser.
3. Return through the `127.0.0.1` callback.
4. NCKH12 verifies the callback, identity, and granted scopes.
5. NCKH12 discovers the models available to that account.
6. The user may select an available model.
7. The UI reports `Personalized AI feedback enabled`.

Identity connection and plan-usage permission are represented separately. A connected identity without `chatgpt.tokens.use.direct` cannot generate remote feedback and falls back locally.

## Credential storage and security

Credentials are stored outside the repository under the user's local application-data directory. On Windows, the entire profile containing access, refresh, and ID tokens is protected with Windows DPAPI. Atomic owner-only file replacement is used. Tokens, PKCE verifiers, state, and nonce never enter Streamlit session state, result JSON, screenshots, logs, Git, or feedback cache files.

Disconnect attempts token revocation when the provider exposes a revocation endpoint, then deletes the protected local profile. The non-secret issued client mapping and stable host identity remain so a later sign-in does not create unnecessary duplicate registrations.

## Model discovery and Responses API

After authorization, NCKH12 calls the public `GET /v1/models` endpoint, keeps only list-visible models, and persists the user's selected model locally. Feedback uses the public `POST /v1/responses` endpoint with OAuth bearer authorization, `store: false`, `stream: true`, a strict JSON Schema under `text.format`, and acceptance only after a terminal `response.completed` event.

Failed, incomplete, interrupted, malformed, unavailable, permission-denied, and usage-limit responses never affect the frozen score result.

## Text evidence boundary

The outbound payload is built from an explicit allowlist. It may contain the controlled-reading rubric and confirmed target text, learner transcript, four existing supported criterion results, measured timing/recognition/prosody/completeness evidence, supported words to review, and ASR uncertainty warnings.

It excludes audio, video, local paths, source URLs, teacher ratings, validation ratings, split membership, holdout information, private research fields, machine Intelligibility, and Overall. The response validator rejects score overrides, unsupported review words, grammar/vocabulary grading, accent shaming, CEFR/IELTS claims, and unsupported Intelligibility or Overall claims.

## Structured feedback and caching

The strict schema contains a strength, next focus, one practice suggestion, supported review words, supporting observations, uncertainty notes, and contradiction flags. Display conversion is separate from the assessment result. Provenance records that audio/video was not sent and numeric scores were not replaced.

The private cache is outside the repository. Its identity binds the input hash, all frozen scorer hashes, target hash, evidence hash, prompt version, and selected model slug. A mismatch is a cache miss. Cache records contain no credential and no learner transcript. Removing a user-media item also removes feedback records tied to its input hash.

## Fallback and offline behavior

If the account is not connected, plan usage is not granted, no model is available, the network is offline, usage is exhausted, or the response is invalid, the completed local assessment remains unchanged. The UI shows local evidence-based feedback and a neutral notice. A presenter-only internal error code is retained for diagnosis; students do not see secrets, stack traces, or provider internals.

Cached valid personalized feedback may be shown offline because it has already passed all hash and schema checks. New personalized feedback requires a working authorized connection.

## Verification status

- Mocked authorization, JWT verification, refresh, model discovery, streaming, schema, error, cache, and score-boundary tests: **16 passed**.
- Automated tests make no real OpenAI request and consume no ChatGPT plan usage.
- Real account smoke test: `REAL_ACCOUNT_SMOKE_TEST_REQUIRED` / `PENDING_USER_AUTHORIZATION`.
- Real feedback smoke test: `PENDING_USER_AUTHORIZATION`.

These pending human-operated checks are not code failures. They must not be marked successful until a user explicitly completes authorization and runs one permitted non-holdout assessment.
