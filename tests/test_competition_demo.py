import copy
import inspect
import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from speaking_evidence.competition_demo import (
    CACHE_NAME,
    CACHE_VERSION,
    DEMO_IDS,
    StaleDemoCacheError,
    load_demo_cache,
    offline_readiness,
    run_live_analysis,
    validate_demo_cache,
    validate_deterministic_feedback,
    verify_frozen_scorer,
    _write,
    TARGET_PROFILE_NAME,
    TARGET_PROFILE_SHA256,
)
from speaking_evidence.competition_review import (
    PROMPT_SHA256,
    REVIEW_VERSION,
    ReviewValidationError,
    export_review_bundle,
    import_review,
    load_review_feedback,
    scorer_fingerprint,
    selected_feedback,
    validate_review_payload,
)
import speaking_evidence.competition_review as review_module
from speaking_evidence.competition_demo_ui import _score_card


ROOT = Path(__file__).resolve().parents[1]
CACHE = json.loads((ROOT / CACHE_NAME).read_text(encoding="utf-8"))
PRIVATE_DEMO = all((ROOT / path).exists() for path in (
    "cohort_runs/T001_p14/development_manifest_v3.json",
    "cohort_runs/T001_p14/data_split_v2.json",
    "task_profiles/T001_target_text_v1.json",
    "assessment_runs/T001_p24_tournament_v1/validation_inputs_summary.json",
))


def _keys(value):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key).lower())
            found.extend(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_keys(item))
    return found


def test_machine_only_cache_has_exact_demo_membership_and_no_private_ratings():
    assert CACHE["version"] == CACHE_VERSION
    assert tuple(CACHE["demo_ids"]) == DEMO_IDS
    assert tuple(item["pair_id"] for item in CACHE["items"]) == DEMO_IDS
    assert CACHE["refit_performed"] is False
    assert CACHE["holdout_processed"] is False
    assert CACHE["machine_intelligibility"] is None
    assert CACHE["overall_score"] is None
    assert not any(any(token in key for token in ("teacher", "human_rating", "validation_rating"))
                   for key in _keys(CACHE))
    assert tuple(CACHE["demo_ids"]) == ("T001-D043", "T001-D064", "T001-D048")


def test_target_title_audit_is_frozen_and_excluded_only_from_completeness():
    target = json.loads((ROOT / TARGET_PROFILE_NAME).read_text(encoding="utf-8"))
    assert target["classification"] == "TITLE_TOPIC_LABEL"
    assert target["topic"] == "One memorable event"
    assert target["scoring_action"] == "EXCLUDE_TOPIC_FROM_READING_COMPLETENESS"
    assert target["scored_passage"].startswith("One memorable event in my life")
    assert not target["scored_passage"].startswith("One memorable event. One memorable event")
    assert target["scored_word_count"] == 139
    assert CACHE["target_profile_sha256"] == TARGET_PROFILE_SHA256


def test_competition_criteria_are_frozen_and_caveats_are_visible():
    for item in CACHE["items"]:
        assert set(item["scores"]) == {"pronunciation", "fluency", "prosody", "completeness"}
        assert item["criterion_status"] == {
            "pronunciation": "PRELIMINARY",
            "fluency": "USABLE",
            "prosody": "PRELIMINARY",
            "completeness": "USABLE",
        }
        assert item["machine_intelligibility"] is None
        assert item["overall_score"] is None
        assert item["genuine_frozen_inference"] is True
        assert item["fake_or_placeholder_score"] is False
        assert item["holdout"] is False


def test_feedback_is_deterministic_short_and_cites_only_present_evidence():
    forbidden = ("grammar", "vocabulary", "confidence", "native accent", "vietnamese accent")
    for item in CACHE["items"]:
        validate_deterministic_feedback(item)
        feedback = item["feedback"]
        assert feedback["llm_used"] is False
        assert feedback["grammar_or_vocabulary_comment"] is False
        assert feedback["accent_shaming"] is False
        for name in ("strength", "focus_next", "try_this"):
            text = feedback[name]["text"]
            assert len(text.split()) <= 35
            assert not any(term in text.lower() for term in forbidden)


def test_live_path_calls_real_local_pipeline_and_contains_no_fitting_or_rating_access():
    source = inspect.getsource(run_live_analysis)
    assert "run_profiled(" in source
    assert "FasterWhisperBackend" in source
    assert "_run_live_multipa" in source
    assert "fit(" not in source
    assert "train(" not in source
    assert "RATINGS_PATH" not in source
    assert "development_validation_ratings" not in source
    assert "holdout_processed\": False" in source
    assert "frozen_multipa_target" in source
    assert "segment_closed_response(transcript[\"words\"], frozen_multipa_target)" in source


def test_invalid_score_never_becomes_a_number():
    card = _score_card("Pronunciation", None, "Sound accuracy and clarity", "UNAVAILABLE")
    assert "Unavailable" in card
    assert "/ 5" not in card


def test_live_result_writer_preserves_numpy_measurements_as_plain_json(tmp_path):
    destination = tmp_path / "result.json"
    _write(destination, {
        "pause_count": np.int64(4),
        "coverage": np.float64(0.95),
        "usable": np.bool_(True),
        "nested": [{"values": np.array([1.5, 2.5], dtype=np.float32)}],
    })
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "pause_count": 4,
        "coverage": 0.95,
        "usable": True,
        "nested": [{"values": [1.5, 2.5]}],
    }


def test_not_scorable_state_blocks_score_dashboard():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.session_state["competition_view"] = "results"
    app.session_state["competition_result"] = {
        "status": "NOT_SCORABLE", "scores": {}, "machine_intelligibility": None,
        "overall_score": None,
    }
    app.run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.info, app.warning, app.error)
                        for element in group)
    assert "We couldn't assess this recording reliably." in rendered
    assert "Assessment completed" not in rendered
    assert "Sound accuracy and clarity" not in rendered
    assert "Your feedback" not in rendered


def test_results_ui_survives_automatic_feedback_serialization_fallback():
    result = copy.deepcopy(CACHE["items"][0])
    expected_scores = copy.deepcopy(result["scores"])
    result["feedback_notice"] = (
        "Personalized feedback was unavailable. Local evidence-based feedback is shown instead."
    )
    result["automatic_feedback_error_code"] = "feedback_serialization_failed"
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.session_state["competition_view"] = "results"
    app.session_state["competition_result"] = result
    app.run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.info, app.warning, app.error)
                        for element in group)
    assert "Your feedback" in rendered
    assert "Local evidence-based feedback is shown instead." in rendered
    assert app.session_state["competition_result"]["scores"] == expected_scores


def test_competition_landing_isolated_from_research_console():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "Turn a Duet into useful speaking feedback." in rendered
    assert "Experiment controls" not in rendered
    assert "Research Console" not in rendered
    assert "Config hash" not in rendered
    assert "CUDA" not in rendered and "FFmpeg" not in rendered


def test_assessment_workspace_has_tiktok_upload_recent_and_empty_state(tmp_path, monkeypatch):
    monkeypatch.setenv("NCKH12_APP_DATA", str(tmp_path / "app-data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.run()
    app.button(key="competition_upload_cta").click().run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "Assessment workspace" in rendered
    assert "Recent videos" in rendered
    assert "No recent videos yet" in rendered
    assert any(widget.label == "TikTok video URL" for widget in app.text_input)
    assert any(widget.label == "Choose video" for widget in app.file_uploader)
    assert "Experiment controls" not in rendered


def test_presenter_assessment_exposes_discreet_chatgpt_settings_only(tmp_path, monkeypatch):
    monkeypatch.setenv("NCKH12_APP_DATA", str(tmp_path / "app-data"))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.query_params["presenter"] = "1"
    app.run()
    app.button(key="competition_upload_cta").click().run()
    assert not app.exception
    assert "Personalized feedback settings" in [row.label for row in app.expander]
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "Local evidence-based feedback is still available." in rendered
    assert "access_token" not in rendered and "refresh_token" not in rendered


def test_recent_video_card_shows_source_duration_status_and_actions(tmp_path, monkeypatch):
    app_data = tmp_path / "app-data"
    library = app_data / "media_library"
    item = library / "items" / "media_fixture"
    item.mkdir(parents=True)
    source = item / "source.mp4"
    source.write_bytes(b"test-fixture-only")
    registry = {
        "schema_version": "nckh12-user-media-v1",
        "items": [{
            "schema_version": "nckh12-user-media-v1",
            "media_id": "media_fixture",
            "friendly_title": "My completed Duet",
            "original_filename": "duet.mp4",
            "source_type": "LOCAL_UPLOAD",
            "source_url": None,
            "import_timestamp": "2026-11-12T00:00:00+00:00",
            "local_path": str(source),
            "sha256": "a" * 64,
            "duration_seconds": 42.0,
            "resolution": {"width": 1080, "height": 1920},
            "thumbnail_path": None,
            "processing_state": "READY",
            "assessment_state": "ASSESSED",
            "last_result_id": "result_fixture",
            "data_class": "UNSEEN_USER_MEDIA",
            "research_membership": False,
        }],
    }
    (library / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setenv("NCKH12_APP_DATA", str(app_data))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    app.query_params["mode"] = "competition_demo"
    app.run()
    app.button(key="competition_upload_cta").click().run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "My completed Duet" in rendered
    assert "Upload" in rendered and "42 sec" in rendered and "Assessed" in rendered
    assert app.button(key="media_assess_media_fixture").label == "Assess"
    assert app.button(key="media_result_media_fixture").label == "View result"
    assert app.button(key="media_remove_media_fixture").label == "Remove"


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_cache_hash_guard_accepts_current_inputs_and_rejects_stale_cache():
    verified = verify_frozen_scorer(ROOT)
    assert CACHE["frozen_hashes"] == verified
    validate_demo_cache(ROOT, CACHE, verify_media=True)
    stale = copy.deepcopy(CACHE)
    stale["frozen_hashes"]["p24d_plan_sha256"] = "0" * 64
    with pytest.raises(StaleDemoCacheError, match="stale"):
        validate_demo_cache(ROOT, stale, verify_media=False)
    stale_target = copy.deepcopy(CACHE)
    stale_target["target_profile_sha256"] = "0" * 64
    with pytest.raises(StaleDemoCacheError, match="target profile"):
        validate_demo_cache(ROOT, stale_target, verify_media=False)


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_all_three_fast_demos_load_and_full_result_page_hides_unsupported_outputs():
    for pair_id in DEMO_IDS:
        assert load_demo_cache(ROOT, pair_id)["pair_id"] == pair_id
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    app.query_params["mode"] = "competition_demo"
    app.run()
    app.button(key="competition_demo_cta").click().run()
    app.button(key="competition_fast_run").click().run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "Your feedback" in rendered
    assert "Preliminary" in rendered
    assert "Intelligibility" not in rendered
    assert "Overall" not in rendered
    assert "Raw MultiPA" not in rendered
    assert "Model context score" not in rendered
    assert "Topic: One memorable event" in rendered
    assert "Experiment controls" not in rendered
    assert [expander.label for expander in app.expander] == [
        "See why you received these scores", "How does the AI work?", "Research validation"
    ]


def _valid_review_payload(item, manifest):
    word = item["evidence"]["word_review_prompts"][0]["word"]
    return {
        "review_version": REVIEW_VERSION,
        "video_id": item["pair_id"],
        "video_input_sha256": item["model_input_sha256"],
        "scorer_fingerprint": scorer_fingerprint(item),
        "target_profile_sha256": TARGET_PROFILE_SHA256,
        "review_prompt_sha256": PROMPT_SHA256,
        "review_source": "CHATGPT_MANUAL_REVIEW",
        "review_timestamp_utc": "2026-11-11T12:00:00+07:00",
        "strength": "Your reading maintained clear coverage across the passage.",
        "focus_next": f"Review {word} as a supported practice prompt, not a confirmed error.",
        "practice_suggestion": f"Say {word} in a phrase, then repeat its full sentence at a natural pace.",
        "review_words": [word],
        "supporting_observations": [{
            "text": "The selected word has lower relative pronunciation evidence.",
            "evidence_refs": ["pronunciation_evidence.word_review_prompts.0.accuracy_evidence"],
        }],
        "uncertainty_notes": ["ASR uncertainty is not a confirmed omission."],
        "score_contradiction_flags": [],
        "safe_for_student_display": True,
    }


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_review_bundle_is_machine_only_and_manual(tmp_path):
    destination = export_review_bundle(ROOT, "T001-D043", tmp_path / "bundle")
    manifest = json.loads((destination / "bundle_manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((destination / "machine_evidence.json").read_text(encoding="utf-8"))
    assert manifest["teacher_ratings_included"] is False
    assert manifest["validation_labels_included"] is False
    assert manifest["holdout_included"] is False
    assert manifest["chatgpt_automation_used"] is False
    assert evidence["machine_intelligibility"] is None
    assert evidence["overall_score"] is None
    assert (destination / "learner_audio.wav").is_file()
    assert not any("rating" in key for key in _keys(evidence))


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_review_import_is_hash_bound_cannot_override_scores_and_falls_back(tmp_path, monkeypatch):
    item = load_demo_cache(ROOT, "T001-D043")
    payload = _valid_review_payload(item, {})
    validate_review_payload(ROOT, item["pair_id"], copy.deepcopy(payload))
    source = tmp_path / "review.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(review_module, "REVIEW_STORE", str(tmp_path / "imported"))
    destination = import_review(ROOT, source)
    assert destination.is_file()
    reviewed = load_review_feedback(ROOT, item)
    assert reviewed is not None
    feedback, provenance = reviewed
    assert feedback["engine"] == "GPT_REVIEWED_PERSONALIZED_FEEDBACK_V1"
    assert provenance["feedback_source"] == "GPT_REVIEWED_IMPORTED"
    assert item["scores"] == load_demo_cache(ROOT, "T001-D043")["scores"]

    stale = copy.deepcopy(payload)
    stale["scorer_fingerprint"] = "0" * 64
    with pytest.raises(ReviewValidationError, match="provenance"):
        validate_review_payload(ROOT, item["pair_id"], stale)
    override = copy.deepcopy(payload)
    override["focus_next"] = "Your score is 5 / 5."
    with pytest.raises(ReviewValidationError, match="replace a score"):
        validate_review_payload(ROOT, item["pair_id"], override)
    unsupported = copy.deepcopy(payload)
    unsupported["supporting_observations"][0]["evidence_refs"] = ["invented.phoneme.error"]
    with pytest.raises(ReviewValidationError, match="missing evidence"):
        validate_review_payload(ROOT, item["pair_id"], unsupported)

    monkeypatch.setattr(review_module, "REVIEW_STORE", str(tmp_path / "missing"))
    fallback, fallback_provenance = selected_feedback(ROOT, item)
    assert fallback["engine"] == "DETERMINISTIC_MEASURED_EVIDENCE_V1"
    assert fallback_provenance["feedback_source"] == "DETERMINISTIC_FALLBACK"


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_presenter_mode_exposes_provenance_without_teacher_data():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    app.query_params["mode"] = "competition_demo"
    app.query_params["presenter"] = "1"
    app.run()
    app.button(key="competition_demo_cta").click().run()
    app.button(key="competition_fast_run").click().run()
    assert not app.exception
    labels = [expander.label for expander in app.expander]
    assert "Technical details" in labels
    assert "Presenter tools" in labels
    rendered = " ".join(str(element.value) for group in
                        (app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "teacher rating" not in rendered.lower()


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local models are not distributed")
def test_offline_demo_assets_are_available_without_remote_services():
    readiness = offline_readiness(ROOT)
    assert readiness["ready"] is True
    assert readiness["checkpoint_hash_verified"] is True
    assert all(readiness["runtime_dependencies"].values())
    assert readiness["remote_services_required"] == []


def test_launcher_opens_new_product_and_preserves_legacy_and_teacher_launchers():
    batch = (ROOT / "START_COMPETITION_DEMO.bat").read_text(encoding="utf-8")
    product = (ROOT / "scripts/start_product_studio.ps1").read_text(encoding="utf-8")
    legacy_batch = (ROOT / "START_COMPETITION_DEMO_LEGACY.bat").read_text(encoding="utf-8")
    legacy = (ROOT / "scripts/start_competition_demo.ps1").read_text(encoding="utf-8")
    teacher = (ROOT / "scripts/start_teacher_rating.ps1").read_text(encoding="utf-8")
    assert "start_product_studio.ps1" in batch
    assert "127.0.0.1:8765" in product
    assert "start_competition_demo.ps1" in legacy_batch
    assert "?mode=competition_demo" in legacy
    assert "?mode=teacher" in teacher
    assert "competition_demo" not in teacher
