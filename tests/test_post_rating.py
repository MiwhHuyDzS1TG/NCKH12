import json
from pathlib import Path

from speaking_evidence.p22 import RATING_IDS
from speaking_evidence.post_rating import calibration_preflight, run_after_ratings


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path, completed: bool) -> None:
    holdout = [f"T001-H{i:03d}" for i in range(18)]
    extra_dev = [f"T001-X{i:03d}" for i in range(38)]
    development = list(RATING_IDS) + extra_dev
    _write(root / "cohort_runs/T001_p14/data_split_v2.json",
           {"development": development, "holdout": holdout})
    items = []
    for index, pair_id in enumerate(RATING_IDS):
        level = index % 3 + 2
        items.append({
            "pair_id": pair_id,
            "quality_gate": "AMBER" if pair_id in {"T001-D009", "T001-D010", "T001-D034"} else "GREEN",
            "amber_scorability": "SCORABLE" if pair_id in {"T001-D009", "T001-D010", "T001-D034"}
            else "NOT_REQUIRED",
            "human_confirmed": completed,
            "fluency": level if completed else None,
            "pronunciation": level if completed else None,
            "intelligibility": level if completed else None,
            "prosody": level if completed else None,
        })
        if completed:
            probability = .65 + index * .02
            _write(root / f"assessment_runs/T001_p22_calibrated_v01/pairs/{pair_id}/evidence.json",
                   {"pair_id": pair_id, "scope": "DEVELOPMENT_ONLY", "holdout": False,
                    "audio_provenance": {"canonical_source": "RAW_COMPLETED_DUET"},
                    "aggregate_fluency_evidence": {
                        "pause_ratio": .1 + index * .01,
                        "long_pause_count": index % 4,
                        "longest_pause_sec": .4 + index * .05,
                        "mean_length_of_run_words": 3.0 + index,
                        "speech_rate_wpm": 120.0 + index * 5,
                        "articulation_rate_wpm": 145.0 + index * 4,
                        "phonation_ratio": .9 - index * .01,
                    },
                    "turns": [{
                        "transcript": {
                            "verbatim_transcript": "one two three",
                            "words": [{"text": "one", "probability": probability}],
                            "segments": [{"avg_logprob": -.4 + index * .01,
                                          "no_speech_prob": .05 + index * .005}],
                        },
                        "acoustic": {"f0_range_semitones": 5.0 + index,
                                     "f0_std_semitones": 1.0 + index * .1,
                                     "intensity_std_db": 2.0 + index * .2,
                                     "voiced_fraction": .6 + index * .01},
                    }]})
            _write(root / f"assessment_runs/T001_p22_calibrated_v01/pairs/{pair_id}/reading_completeness_v1.json",
                   {"status": "EVIDENCE_READY_NO_SCORE", "coverage": .75 + index * .01,
                    "matched_sequence": [], "omissions": [], "insertions": [],
                    "warning": "ASR differences are not proven learner errors"})
    _write(root / "human_ground_truth/p22a_v1/ratings_v2.json",
           {"schema_version": "P2.3-four-criterion-v2", "holdout_used": False, "items": items})
    _write(root / "task_profiles/T001_target_text_v1.json",
           {"human_confirmed": True, "confirmed_text": "one two three"})
    _write(root / "assessment_runs/T001_p22_calibrated_v01/selected_backend_evidence_summary.json",
           {"holdout_processed": False})
    _write(root / "assessment_runs/T001_p22_calibrated_v01/reading_completeness_summary_v1.json",
           {"holdout_processed": False, "score_created": False})


def test_preflight_stops_without_all_human_ratings_and_creates_no_score(tmp_path):
    _fixture(tmp_path, completed=False)
    report = calibration_preflight(tmp_path)
    assert report["status"] == "STOPPED"
    assert report["completed_count"] == 0
    assert any("0/12" in reason for reason in report["reasons"])
    result = run_after_ratings(tmp_path)
    assert result["status"] == "STOPPED"
    assert result["calibration_created"] is False
    assert not (tmp_path / "assessment_runs/T001_p22_calibrated_v01/calibration_summary.json").exists()


def test_preflight_accepts_complete_development_only_four_criterion_queue(tmp_path):
    _fixture(tmp_path, completed=True)
    report = calibration_preflight(tmp_path)
    assert report["status"] == "READY_FOR_DEVELOPMENT_CALIBRATION"
    assert report["completed_count"] == 12
    assert report["scorable_count"] == 12
    assert report["holdout_media_processed"] is False
    assert set(report["label_distribution"]) == {
        "fluency", "pronunciation", "intelligibility", "prosody"
    }


def test_complete_fixture_runs_development_calibration_and_keeps_pronunciation_pending(tmp_path):
    _fixture(tmp_path, completed=True)
    result = run_after_ratings(tmp_path)
    assert result["status"] == "DEVELOPMENT_PRELIMINARY_CALIBRATION_COMPLETE"
    assert result["pronunciation_status"] == "EVIDENCE_ONLY_BACKEND_PENDING"
    summary_path = tmp_path / "assessment_runs/T001_p22_calibrated_v01/calibration_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert len(summary["scores"]) == 12
    assert all(row["pronunciation"] is None for row in summary["scores"])
    assert summary["holdout_processed"] is False
    reports = tmp_path / "calibration/p22a_v01/criterion_reports_v01"
    assert {path.name for path in reports.glob("*_calibration_report_v01.json")} == {
        "fluency_calibration_report_v01.json",
        "pronunciation_calibration_report_v01.json",
        "intelligibility_calibration_report_v01.json",
        "prosody_calibration_report_v01.json",
        "completeness_calibration_report_v01.json",
    }


def test_preflight_rejects_holdout_queue_id(tmp_path):
    _fixture(tmp_path, completed=True)
    path = tmp_path / "human_ground_truth/p22a_v1/ratings_v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["items"][0]["pair_id"] = "T001-H000"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = calibration_preflight(tmp_path)
    assert report["status"] == "STOPPED"
    assert any("exactly the frozen 12" in reason for reason in report["reasons"])


def test_preflight_rejects_malformed_completed_human_data(tmp_path):
    _fixture(tmp_path, completed=True)
    path = tmp_path / "human_ground_truth/p22a_v1/ratings_v2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["items"][0]["fluency"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = calibration_preflight(tmp_path)
    assert report["status"] == "STOPPED"
    assert any("invalid/null ratings" in reason for reason in report["reasons"])
