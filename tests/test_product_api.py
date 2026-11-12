from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from speaking_evidence import product_api
from speaking_evidence.competition_demo import DEMO_IDS, load_demo_cache


ROOT = Path(__file__).resolve().parents[1]


def _all_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key).lower())
            found.update(_all_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_all_keys(item))
    return found


def test_product_bootstrap_preserves_demo_order_and_scientific_scope() -> None:
    with TestClient(product_api.app) as client:
        response = client.get("/api/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert [row["id"] for row in payload["demos"]] == list(DEMO_IDS)
    assert payload["scientific_scope"] == {
        "frozen_research_overall_score": None,
        "machine_intelligibility": None,
        "holdout_processed": False,
        "product_overall_version": product_api.OVERALL_PRACTICE_VERSION,
    }


def test_demo_api_uses_exact_frozen_values_and_hides_private_evidence() -> None:
    source = load_demo_cache(ROOT, "T001-D043", verify_media=False)
    with TestClient(product_api.app) as client:
        response = client.get("/api/demos/T001-D043")
    assert response.status_code == 200
    payload = response.json()
    assert payload["scores"] == source["scores"]
    overall = payload["overall_practice_score"]
    expected_completeness = 1 + 4 * source["completeness"]["coverage"]
    expected = (source["scores"]["pronunciation"] + source["scores"]["fluency"]
                + source["scores"]["prosody"] + expected_completeness) / 4
    assert overall["value"] == round(expected, 4)
    assert overall["display_value"] == round(expected, 1)
    assert overall["status"] == "DESCRIPTIVE_PRODUCT_COMPOSITE"
    assert overall["research_validated"] is False
    assert overall["machine_intelligibility_included"] is False
    assert payload["machine_intelligibility"] is None
    assert payload["holdout_processed"] is False
    keys = _all_keys(payload)
    assert not any(token in key for key in keys for token in (
        "teacher", "human_rating", "validation_rating", "local_path",
        "frozen_hashes", "raw_multipa", "internal_reason",
    ))


def test_result_serializer_drops_internal_failure_and_paths() -> None:
    result = {
        "pair_id": "T001-LIVE",
        "display_name": "Uploaded Duet",
        "status": "PARTIAL",
        "scores": {"fluency": 4.0},
        "criterion_status": {"fluency": "USABLE"},
        "completeness": {"coverage": 0.8},
        "evidence": {
            "fluency": {"speech_rate_wpm": 120.0},
            "raw_multipa": {"private": 1},
            "word_review_prompts": [],
        },
        "feedback": {
            "strength": {"text": "Measured strength."},
            "focus_next": {"text": "Measured focus."},
            "try_this": {"text": "Measured practice."},
        },
        "model_failures": [{
            "public_message": "Pronunciation is unavailable.",
            "internal_reason": "C:/private/model/path",
        }],
        "teacher_ratings": [5],
    }
    payload = product_api._serialize_result(
        result, result_id="result_safe", video_url="/api/media/x/video", audio_url=None)
    rendered = json.dumps(payload)
    assert "private/model" not in rendered
    assert "teacher" not in rendered
    assert "raw_multipa" not in rendered
    assert payload["model_failures"] == [{"public_message": "Pronunciation is unavailable."}]
    assert payload["overall_practice_score"] is None


@pytest.mark.parametrize(("coverage", "expected"), [(1.0, 5.0), (0.5, 3.0), (0.0, 1.0)])
def test_overall_completeness_conversion_has_fixed_endpoints(coverage: float, expected: float) -> None:
    overall = product_api.build_overall_practice_score(
        {"pronunciation": 4.0, "fluency": 4.0, "prosody": 4.0},
        {"coverage": coverage},
    )
    assert overall is not None
    assert overall["inputs"]["reading_completeness"] == expected


def test_overall_is_exact_equal_weight_mean_owned_by_python() -> None:
    overall = product_api.build_overall_practice_score(
        {"pronunciation": 2.0, "fluency": 3.0, "prosody": 4.0},
        {"coverage": 1.0},
    )
    assert overall is not None
    assert overall["value"] == 3.5
    app_source = (ROOT / "product_frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "overall.display_value" in app_source
    assert "1 + 4" not in app_source
    assert "reduce((" not in app_source


def test_overall_requires_all_four_inputs_and_is_absent_when_not_scorable() -> None:
    assert product_api.build_overall_practice_score(
        {"fluency": 4.0, "prosody": 4.0}, {"coverage": 1.0}) is None
    result = {
        "status": "NOT_SCORABLE",
        "scores": {"pronunciation": 4.0, "fluency": 4.0, "prosody": 4.0},
        "completeness": {"coverage": 1.0},
    }
    payload = product_api._serialize_result(
        result, result_id="not_scorable", video_url="/video", audio_url=None)
    assert payload["overall_practice_score"] is None


def test_product_overall_has_no_teacher_p25_holdout_or_intelligibility_dependency() -> None:
    referenced_names = {name.lower() for name in product_api.build_overall_practice_score.__code__.co_names}
    assert not referenced_names.intersection({"teacher", "p25", "holdout", "intelligibility"})


def test_media_serializer_never_exposes_path_url_or_research_membership() -> None:
    payload = product_api._serialize_media({
        "media_id": "media_123",
        "friendly_title": "Practice",
        "source_type": "TIKTOK_LINK",
        "source_url": "https://example.invalid/private",
        "local_path": "C:/private/video.mp4",
        "thumbnail_path": "C:/private/thumb.jpg",
        "research_membership": False,
        "last_result_id": None,
    })
    assert "local_path" not in payload
    assert "source_url" not in payload
    assert payload["research_membership"] is False
    assert payload["data_class"] == "UNSEEN_USER_MEDIA"


def test_presenter_mutation_requires_explicit_local_presenter_header() -> None:
    with TestClient(product_api.app) as client:
        response = client.post("/api/presenter/chatgpt/disconnect")
    assert response.status_code == 403


def test_frozen_files_remain_byte_identical_during_product_adapter_tests() -> None:
    expected = {
        "competition_freeze_v1.json": "0b73719689c9805de741fedb233ef60eb039a8fc220c0e629ea9640b2f47f50d",
        "p24d_multipa_plan_v1.json": "90755aaa169b605c7b9a070ae411dc28366a2b3e568e4daf2e81dc15a4cee1c1",
        "competition_target_profile_v2.json": "e2a4b2f1ee77860bab9a1a075d07bf61a27fe9ab641a71719dc129def1fb9da2",
    }
    for relative, digest in expected.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest


def test_new_launcher_retains_explicit_legacy_rollback() -> None:
    launcher = (ROOT / "START_COMPETITION_DEMO.bat").read_text(encoding="utf-8")
    legacy = (ROOT / "START_COMPETITION_DEMO_LEGACY.bat").read_text(encoding="utf-8")
    assert "start_product_studio.ps1" in launcher
    assert "start_competition_demo.ps1" in legacy
    assert "competition_demo" in (ROOT / "scripts/start_competition_demo.ps1").read_text(encoding="utf-8")
