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
)
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


def test_invalid_score_never_becomes_a_number():
    card = _score_card("Pronunciation", None, "Sound accuracy and clarity", "UNAVAILABLE")
    assert "Unavailable" in card
    assert "/ 5" not in card


def test_live_result_writer_preserves_numpy_measurements_as_plain_json(tmp_path):
    destination = tmp_path / "result.json"
    _write(destination, {"pause_count": np.int64(4), "coverage": np.float64(0.95)})
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "pause_count": 4,
        "coverage": 0.95,
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


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_cache_hash_guard_accepts_current_inputs_and_rejects_stale_cache():
    verified = verify_frozen_scorer(ROOT)
    assert CACHE["frozen_hashes"] == verified
    validate_demo_cache(ROOT, CACHE, verify_media=True)
    stale = copy.deepcopy(CACHE)
    stale["frozen_hashes"]["p24d_plan_sha256"] = "0" * 64
    with pytest.raises(StaleDemoCacheError, match="stale"):
        validate_demo_cache(ROOT, stale, verify_media=False)


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local demo media is not distributed")
def test_all_three_fast_demos_load_and_full_result_page_hides_unsupported_outputs():
    for pair_id in DEMO_IDS:
        assert load_demo_cache(ROOT, pair_id)["pair_id"] == pair_id
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    app.query_params["mode"] = "competition_demo"
    app.run()
    app.button(key="competition_cta").click().run()
    app.button(key="competition_fast_run").click().run()
    assert not app.exception
    rendered = " ".join(str(element.value) for group in
                        (app.title, app.markdown, app.caption, app.info, app.warning, app.error)
                        for element in group)
    assert "Your feedback" in rendered
    assert "Preliminary" in rendered
    assert "Intelligibility" not in rendered
    assert "Overall" not in rendered
    assert "Experiment controls" not in rendered
    assert [expander.label for expander in app.expander] == [
        "See why you received these scores", "How does the AI work?", "Research validation"
    ]


@pytest.mark.skipif(not PRIVATE_DEMO, reason="private local models are not distributed")
def test_offline_demo_assets_are_available_without_remote_services():
    readiness = offline_readiness(ROOT)
    assert readiness["ready"] is True
    assert readiness["checkpoint_hash_verified"] is True
    assert all(readiness["runtime_dependencies"].values())
    assert readiness["remote_services_required"] == []


def test_launcher_opens_dedicated_competition_mode_without_changing_teacher_launcher():
    batch = (ROOT / "START_COMPETITION_DEMO.bat").read_text(encoding="utf-8")
    launcher = (ROOT / "scripts/start_competition_demo.ps1").read_text(encoding="utf-8")
    teacher = (ROOT / "scripts/start_teacher_rating.ps1").read_text(encoding="utf-8")
    assert "start_competition_demo.ps1" in batch
    assert "?mode=competition_demo" in launcher
    assert "?mode=teacher" in teacher
    assert "competition_demo" not in teacher
