import base64
import copy
import json
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import numpy as np
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from speaking_evidence.chatgpt_auth import (
    PLAN_USAGE_SCOPE,
    AuthorizationAttempt,
    ChatGPTAuthManager,
    CredentialStore,
    authorization_url,
    create_authorization_attempt,
    redact_secrets,
    validate_callback,
    verify_id_token,
)
from speaking_evidence.chatgpt_feedback import (
    AUTO_PROMPT_VERSION,
    AutomaticFeedbackError,
    _canonical,
    attach_automatic_feedback,
    automatic_feedback,
    build_text_evidence,
    cache_identity,
    load_cached_feedback,
    prompt_for,
    stream_structured_feedback,
    validate_feedback,
)
from speaking_evidence.json_utils import to_jsonable


ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "competition_demo_cache_v2.json").read_text(encoding="utf-8"))["items"][0]


def _factory(handler):
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def _profile(model="model-visible"):
    return {
        "issuer": "https://auth.openai.com",
        "subject": "subject",
        "account_label": "Connected account",
        "client_id": "oaiapp_test",
        "ext_agent_host_id": "urn:uuid:test",
        "id_token": "id-secret",
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "expires_at": 4102444800,
        "scopes": [PLAN_USAGE_SCOPE, "openid", "offline_access", "resource.invoke"],
        "selected_model": model,
        "models": [{"slug": model, "display_name": "Visible model"}],
    }


def _feedback_payload(word=None):
    return {
        "strength": "You maintained strong target coverage throughout the reading.",
        "focus_next": "Review the supported practice word while keeping a steady phrase rhythm.",
        "practice_suggestion": "Read one phrase slowly, then repeat it once at your natural pace.",
        "review_words": [word] if word else [],
        "supporting_observations": ["Target coverage was a supported strength."],
        "uncertainty_notes": ["ASR uncertainty is not a confirmed omission."],
        "score_contradiction_flags": [],
    }


def _completed_sse(payload):
    response = {
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(payload)}],
        }]
    }
    event = json.dumps({"type": "response.completed", "response": response})
    return f"data: {event}\n\ndata: [DONE]\n\n".encode()


def test_pkce_state_nonce_loopback_and_plan_scope_are_exact():
    attempt = create_authorization_attempt("urn:uuid:host", 1455)
    assert attempt.redirect_uri == "http://127.0.0.1:1455/auth/callback"
    assert "localhost" not in attempt.redirect_uri
    assert len(attempt.state) >= 32 and len(attempt.nonce) >= 32
    expected = base64.urlsafe_b64encode(__import__("hashlib").sha256(
        attempt.verifier.encode()).digest()).rstrip(b"=").decode()
    assert attempt.challenge == expected
    query = parse_qs(urlparse(authorization_url(attempt)).query)
    assert query["code_challenge_method"] == ["S256"]
    assert PLAN_USAGE_SCOPE in query["scope"][0].split()
    assert query["resource"] == ["https://api.openai.com/v1"]


def test_callback_rejects_state_and_requires_issued_client_id():
    attempt = create_authorization_attempt("urn:uuid:host", 1455)
    with pytest.raises(Exception, match="did not match"):
        validate_callback(attempt, {"state": ["wrong"], "code": ["code"]})
    with pytest.raises(Exception, match="registration did not complete"):
        validate_callback(attempt, {"state": [attempt.state], "code": ["code"]})
    result = validate_callback(attempt, {
        "state": [attempt.state], "code": ["code"], "client_id": ["oaiapp_issued"]
    })
    assert result == {"code": "code", "client_id": "oaiapp_issued"}


def test_credentials_are_protected_outside_repo_and_tokens_are_redacted(tmp_path):
    store = CredentialStore(tmp_path)
    store.save(_profile())
    raw = store.profile_path.read_bytes()
    assert b"access-secret" not in raw
    assert store.load()["access_token"] == "access-secret"
    host = store.host_id()
    assert host.startswith("urn:uuid:") and store.root.is_relative_to(tmp_path)
    text = redact_secrets(
        "Authorization: Bearer access-secret refresh_token=refresh-secret",
        ["access-secret", "refresh-secret"],
    )
    assert "access-secret" not in text and "refresh-secret" not in text
    store.clear()
    assert store.load() is None
    assert store.registration()["client_id"] == "oaiapp_test"


def test_id_token_signature_issuer_audience_nonce_and_expiry_are_verified():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key().public_numbers()
    header = {"alg": "RS256", "kid": "key-1", "typ": "JWT"}
    claims = {
        "iss": "https://auth.openai.com", "aud": "oaiapp_test", "sub": "subject",
        "nonce": "nonce-value", "exp": int(time.time()) + 600,
    }

    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=").decode()

    signing = f"{encode(header)}.{encode(claims)}"
    signature = private.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
    token = f"{signing}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    jwk = {
        "kty": "RSA", "kid": "key-1",
        "n": base64.urlsafe_b64encode(public.n.to_bytes((public.n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode(),
        "e": base64.urlsafe_b64encode(public.e.to_bytes((public.e.bit_length() + 7) // 8, "big")).rstrip(b"=").decode(),
    }

    def handler(request):
        if "openid-configuration" in str(request.url):
            return httpx.Response(200, json={
                "issuer": "https://auth.openai.com", "jwks_uri": "https://auth.openai.com/jwks"
            })
        return httpx.Response(200, json={"keys": [jwk]})

    with _factory(handler)() as client:
        assert verify_id_token(token, "oaiapp_test", "nonce-value", client)["sub"] == "subject"
        with pytest.raises(Exception, match="identity validation failed"):
            verify_id_token(token, "oaiapp_test", "wrong-nonce", client)


def test_identity_login_without_plan_scope_does_not_enable_inference(tmp_path):
    store = CredentialStore(tmp_path)
    profile = _profile()
    profile["scopes"] = ["openid", "profile", "email"]
    store.save(profile)
    manager = ChatGPTAuthManager(store)
    assert manager.status()["connected"] is True
    assert manager.status()["plan_usage_enabled"] is False
    with pytest.raises(Exception, match="not enabled"):
        manager.access_profile()


def test_expired_or_revoked_session_requires_reauthorization(tmp_path):
    store = CredentialStore(tmp_path)
    profile = _profile()
    profile["expires_at"] = 0
    store.save(profile)
    manager = ChatGPTAuthManager(store, _factory(lambda _request: httpx.Response(
        401, json={"error": {"code": "invalid_grant"}})))
    with pytest.raises(Exception, match="connect ChatGPT again"):
        manager.access_profile()


def test_account_specific_model_discovery_and_selection(tmp_path):
    store = CredentialStore(tmp_path)
    profile = _profile("gone-model")
    store.save(profile)

    def handler(request):
        assert request.headers["Authorization"] == "Bearer access-secret"
        return httpx.Response(200, json={"models": [
            {"slug": "model-a", "display_name": "Model A", "visibility": "list"},
            {"slug": "hidden", "display_name": "Hidden", "visibility": "hidden"},
        ]})

    manager = ChatGPTAuthManager(store, _factory(handler))
    assert manager.discover_models() == [{"slug": "model-a", "display_name": "Model A"}]
    assert manager.status()["selected_model"] == "model-a"
    manager.select_model("model-a")
    with pytest.raises(Exception, match="available"):
        manager.select_model("hidden")


def test_text_evidence_allowlist_contains_no_media_private_labels_or_unsupported_scores():
    evidence = build_text_evidence(DEMO)
    serialized = json.dumps(evidence).lower()
    for forbidden in ("teacher_rating", "validation_rating", "holdout", ".wav", ".mp4",
                      "local_path", "overall_score", "intelligibility_score"):
        assert forbidden not in serialized
    assert set(evidence["criterion_scores"]) == {
        "pronunciation", "fluency", "prosody", "reading_completeness_percent"
    }


def test_successful_streamed_response_uses_public_contract_and_structured_schema():
    evidence = build_text_evidence(DEMO)
    word = evidence["pronunciation_evidence"]["review_words"][0]["word"]

    def handler(request):
        assert request.url == httpx.URL("https://api.openai.com/v1/responses")
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert "audio" not in json.dumps(body).lower()
        return httpx.Response(200, content=_completed_sse(_feedback_payload(word)),
                              headers={"content-type": "text/event-stream"})

    result = stream_structured_feedback("access-secret", "model-a", evidence, _factory(handler))
    assert result["review_words"] == [word]


@pytest.mark.parametrize("status,code", [
    (403, "subscription_sharing_user_not_eligible"),
    (429, "subscription_sharing_usage_limit_exceeded"),
    (503, "subscription_sharing_usage_unavailable"),
])
def test_plan_usage_failures_are_safe_and_coded(status, code):
    def handler(_request):
        return httpx.Response(status, json={"error": {"code": code}})
    with pytest.raises(AutomaticFeedbackError) as caught:
        stream_structured_feedback("secret", "model-a", build_text_evidence(DEMO), _factory(handler))
    assert caught.value.code == code
    assert "secret" not in str(caught.value)


def test_interrupted_failed_and_incomplete_streams_do_not_return_feedback():
    evidence = build_text_evidence(DEMO)
    cases = [
        b"data: {\"type\":\"response.failed\",\"response\":{\"error\":{\"code\":\"failed\"}}}\n\n",
        b"data: {\"type\":\"response.incomplete\"}\n\n",
        b"data: {\"type\":\"response.output_text.delta\",\"delta\":\"{\"}\n\n",
    ]
    for content in cases:
        with pytest.raises(AutomaticFeedbackError):
            stream_structured_feedback(
                "secret", "model-a", evidence,
                _factory(lambda _request, body=content: httpx.Response(200, content=body)),
            )


def test_feedback_rejects_score_override_unsupported_words_and_claims():
    evidence = build_text_evidence(DEMO)
    word = evidence["pronunciation_evidence"]["review_words"][0]["word"]
    valid = _feedback_payload(word)
    validate_feedback(valid, evidence)
    override = copy.deepcopy(valid)
    override["focus_next"] = "Your score should be 5 / 5."
    with pytest.raises(AutomaticFeedbackError):
        validate_feedback(override, evidence)
    unknown = copy.deepcopy(valid)
    unknown["review_words"] = ["invented"]
    with pytest.raises(AutomaticFeedbackError):
        validate_feedback(unknown, evidence)
    claim = copy.deepcopy(valid)
    claim["strength"] = "Your Overall score is strong."
    with pytest.raises(AutomaticFeedbackError):
        validate_feedback(claim, evidence)


def test_feedback_cache_is_hash_isolated_and_stale_artifact_is_rejected(tmp_path):
    store = CredentialStore(tmp_path / "auth")
    store.save(_profile("model-a"))
    manager = ChatGPTAuthManager(store)
    evidence = build_text_evidence(DEMO)
    word = evidence["pronunciation_evidence"]["review_words"][0]["word"]
    calls = {"count": 0}

    def handler(_request):
        calls["count"] += 1
        return httpx.Response(200, content=_completed_sse(_feedback_payload(word)))

    feedback, provenance = automatic_feedback(
        DEMO, manager, tmp_path / "cache", _factory(handler))
    assert feedback["engine"] == "CHATGPT_AUTOMATIC_TEXT_REVIEW_V1"
    assert provenance["cache_hit"] is False and calls["count"] == 1
    _, cached = automatic_feedback(DEMO, manager, tmp_path / "cache", _factory(handler))
    assert cached["cache_hit"] is True and calls["count"] == 1
    changed = copy.deepcopy(DEMO)
    changed["raw_duet_sha256"] = "a" * 64
    assert cache_identity(changed, "model-a") != cache_identity(DEMO, "model-a")
    assert load_cached_feedback(changed, "model-a", tmp_path / "cache") is None


def test_automatic_failure_preserves_scores_and_returns_deterministic_path(tmp_path):
    store = CredentialStore(tmp_path / "auth")
    store.save(_profile("model-a"))
    manager = ChatGPTAuthManager(store)
    original_scores = copy.deepcopy(DEMO["scores"])
    result, code = attach_automatic_feedback(
        DEMO, auth=manager, cache_root=tmp_path / "cache",
        client_factory=_factory(lambda _request: httpx.Response(
            429, json={"error": {"code": "subscription_sharing_usage_limit_exceeded"}})),
    )
    assert code == "subscription_sharing_usage_limit_exceeded"
    assert result["scores"] == original_scores
    assert "automatic_feedback" not in result


def test_nested_numpy_values_have_native_deterministic_canonical_json():
    measured = {
        "integer": np.int64(7),
        "floating32": np.float32(1.5),
        "floating64": np.float64(2.25),
        "bool": np.bool_(True),
        "array": np.array([[1, 2], [3, 4]], dtype=np.int64),
        "nested": [{"tuple": (np.float32(0.5), np.bool_(False))}],
    }
    native = {
        "integer": 7,
        "floating32": 1.5,
        "floating64": 2.25,
        "bool": True,
        "array": [[1, 2], [3, 4]],
        "nested": [{"tuple": [0.5, False]}],
    }
    assert _canonical(measured) == _canonical(native)
    assert json.loads(_canonical(measured)) == native


def _numpy_evidence_result() -> dict:
    result = copy.deepcopy(DEMO)
    result["scores"]["pronunciation"] = np.float64(result["scores"]["pronunciation"])
    result["scores"]["fluency"] = np.float32(4.5)
    result["scores"]["prosody"] = np.float64(result["scores"]["prosody"])
    result["completeness"]["coverage"] = np.float64(result["completeness"]["coverage"])
    result["completeness"]["matched_word_count"] = np.int64(
        result["completeness"]["matched_word_count"])
    result["completeness"]["possible_asr_uncertainty"] = np.array(
        result["completeness"]["possible_asr_uncertainty"], dtype=object)
    fluency = result["evidence"]["fluency"]
    fluency["pause_count"] = np.int64(fluency["pause_count"])
    fluency["long_pause_count"] = np.int64(fluency["long_pause_count"])
    fluency["longest_pause_sec"] = np.float32(fluency["longest_pause_sec"])
    fluency["mean_length_of_run_words"] = np.float64(fluency["mean_length_of_run_words"])
    result["evidence"]["raw_multipa"]["prosody"] = np.float32(
        result["evidence"]["raw_multipa"]["prosody"])
    result["evidence"]["serialization_probe"] = {
        "ok": np.bool_(True), "array": np.array([np.int64(1), np.int64(2)])
    }
    return result


def test_numpy_machine_evidence_cache_identity_and_request_are_json_safe():
    result = _numpy_evidence_result()
    identity = cache_identity(result, "model-a")
    assert identity == cache_identity(to_jsonable(result), "model-a")
    evidence = build_text_evidence(result)
    json.dumps(evidence, allow_nan=False)
    json.dumps(prompt_for(evidence), allow_nan=False)
    assert evidence["criterion_scores"]["fluency"] == 4.5
    assert isinstance(evidence["fluency_evidence"]["pause_count"], int)
    assert isinstance(evidence["completeness_evidence"]["matched_target_words"], int)


def test_numpy_assessment_path_writes_and_reads_feedback_cache_without_score_change(tmp_path):
    store = CredentialStore(tmp_path / "auth")
    store.save(_profile("model-a"))
    manager = ChatGPTAuthManager(store)
    result = _numpy_evidence_result()
    original_scores = copy.deepcopy(result["scores"])
    evidence = build_text_evidence(result)
    word = evidence["pronunciation_evidence"]["review_words"][0]["word"]
    calls = {"count": 0}

    def handler(_request):
        calls["count"] += 1
        return httpx.Response(200, content=_completed_sse(_feedback_payload(word)))

    enriched, error = attach_automatic_feedback(
        result, auth=manager, cache_root=tmp_path / "cache",
        client_factory=_factory(handler),
    )
    assert error is None and calls["count"] == 1
    assert to_jsonable(enriched["scores"]) == to_jsonable(original_scores)
    assert isinstance(enriched["scores"]["fluency"], np.float32)
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) == 1
    json.loads(cache_files[0].read_text(encoding="utf-8"))
    cached = load_cached_feedback(result, "model-a", tmp_path / "cache")
    assert cached is not None
    assert cached[1]["cache_hit"] is False


def test_unexpected_feedback_serialization_failure_preserves_assessment(tmp_path):
    store = CredentialStore(tmp_path / "auth")
    store.save(_profile("model-a"))
    manager = ChatGPTAuthManager(store)
    result = copy.deepcopy(DEMO)
    original_scores = copy.deepcopy(result["scores"])
    result["evidence"]["fluency"]["pause_count"] = object()
    enriched, error = attach_automatic_feedback(
        result, auth=manager, cache_root=tmp_path / "cache",
        client_factory=_factory(lambda _request: pytest.fail("request must not be sent")),
    )
    assert error == "feedback_serialization_failed"
    assert enriched["scores"] == original_scores
    assert enriched["feedback"] == result["feedback"]
    assert "automatic_feedback" not in enriched
