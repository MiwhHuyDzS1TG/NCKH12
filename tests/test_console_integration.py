"""Opt-in end-to-end Research Console orchestration on the known pair."""
import os
from pathlib import Path

import pytest

from duet_segmenter.pipeline import load_config
from duet_speech_lab.console import audio_clip_bytes, execute_analysis, review_dataframe, save_review


@pytest.mark.skipif(os.environ.get("DUET_SAMPLE_INTEGRATION") != "1", reason="requires installed FFmpeg and sample media")
def test_console_known_pair(tmp_path):
    root = Path(__file__).parents[1]
    run_dir, result = execute_analysis(root/"template.mp4", root/"main video.mp4", load_config(), tmp_path)
    assert result["status"] == "ok"
    assert len(result["learner_segments"]) == 21
    assert len(result["reference_leakage_candidates"]) == 1
    assert result["reference_leakage_candidates"][0]["segment_id"] == "S001"
    assert len(result["original_vad_segments"]) > 0
    assert len(result["residual_vad_segments"]) > 0
    assert (run_dir/"config.json").is_file()
    assert (run_dir/"inputs"/"original.mp4").is_file()
    assert (run_dir/"inputs"/"duet.mp4").is_file()
    assert len(review_dataframe(result)) == 21
    assert review_dataframe(result).iloc[0]["segment_id"] == "S002"
    first = result["learner_segments"][0]
    clip, _, _, sr, channels = audio_clip_bytes(run_dir/"duet_source_audio.wav", first["start"], first["end"])
    assert len(clip) > 100 and sr == 44_100 and channels == 2
