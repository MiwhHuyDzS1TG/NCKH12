from __future__ import annotations

from duet_segmenter.evaluation import evaluate
from duet_segmenter.pipeline import load_config
from duet_segmenter.segments import classify, merge_segments


def test_merge_same_class_only_and_keep_large_pause():
    inputs = [{"start": 0., "end": 0.5, "overlap_candidate": False, "confidence": 0.9},
              {"start": 0.56, "end": 1., "overlap_candidate": False, "confidence": 0.7},
              {"start": 1.05, "end": 1.3, "overlap_candidate": True, "confidence": 0.8},
              {"start": 1.7, "end": 2.0, "overlap_candidate": True, "confidence": 0.8}]
    merged = merge_segments(inputs, 0.1, 0.15)
    assert len(merged) == 3
    assert merged[0]["end"] == 1.
    assert 0.7 < merged[0]["confidence"] < 0.9


def test_overlap_labels_and_outside_template_rejection():
    cfg = load_config()["segments"]
    candidates = [{"start": 0.5, "end": 1.5, "confidence": 0.9},
                  {"start": 3.2, "end": 4.2, "confidence": 0.9}]
    original = [{"start": 1., "end": 1.3}]
    learners, overlaps, outside = classify(candidates, original, 5., 0., 3.5, cfg)
    assert len(learners) == 2
    assert learners[0]["overlap_candidate"] is True
    assert learners[1]["overlap_candidate"] is False
    assert overlaps == [{"start": 1., "end": 1.3, "timeline_state": "OVERLAP_CANDIDATE"}]
    assert outside[0]["timeline_state"] == "OUTSIDE_TEMPLATE"
    assert outside[0]["start"] == 3.62


def test_frame_evaluation_on_labeled_regions():
    cfg = load_config()["evaluation"]
    truth = [{"start": 0., "end": 1., "label": "ORIGINAL"},
             {"start": 1., "end": 2., "label": "LEARNER"},
             {"start": 2., "end": 3., "label": "OVERLAP"},
             {"start": 3., "end": 4., "label": "OUTSIDE_TEMPLATE"}]
    result = evaluate([{"start": 1., "end": 3.}], [], [{"start": 3.5, "end": 4.}], truth, 4., cfg)
    assert result["learner_precision"] == 1.
    assert result["learner_recall"] == 1.
    assert result["original_contamination_rate"] == 0.
    assert result["overlap_recall"] == 1.
    assert abs(result["false_speech_outside_template"]-0.5) < 0.03
    assert result["median_boundary_error_sec"] == 0.
