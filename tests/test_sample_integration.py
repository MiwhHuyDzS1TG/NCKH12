"""Opt-in regression run against the inspected original/Duet pair."""
import os
from pathlib import Path

import pytest

from duet_segmenter.pipeline import load_config, run


@pytest.mark.skipif(os.environ.get("DUET_SAMPLE_INTEGRATION") != "1", reason="set DUET_SAMPLE_INTEGRATION=1 to run FFmpeg/model integration")
def test_supplied_pair(tmp_path):
    root = Path(__file__).parents[1]
    original = root/"ori video.mp4" if (root/"ori video.mp4").exists() else root/"template.mp4"
    duet = root/"video.mp4" if (root/"video.mp4").exists() else root/"main video.mp4"
    result = run(original, duet, tmp_path, load_config())
    assert result["status"] == "ok"
    assert abs(result["alignment_diagnostics"]["b"]+0.6946) < 0.02
    assert min(x["correlation"] for x in result["alignment_diagnostics"]["anchors"] if x["accepted"]) > 0.8
    assert len(result["learner_segments"]) > 0
