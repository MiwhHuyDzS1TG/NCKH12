import json
from pathlib import Path

import jsonschema

from duet_segmenter.pipeline import _clean_json


def test_json_schema_sanity():
    schema = json.loads((Path(__file__).parents[1]/"duet_segmenter"/"result.schema.json").read_text())
    result = {
        "status": "ok", "input_metadata": {"original": {}, "duet": {}},
        "alignment_diagnostics": {"coarse_offset_sec": -0.7, "peak_score": 0.4,
                                  "peak_to_background_score": 20., "a": 1., "b": -0.6946, "anchors": []},
        "cancellation_diagnostics": {}, "vad_configuration": {},
        "learner_segments": [{"start": 1., "end": 2., "confidence": 0.9, "overlap_candidate": False}],
        "overlap_candidates": [], "warnings": [], "artifacts": {},
    }
    jsonschema.validate(result, schema)
    assert _clean_json({"bad": float("inf")}) == {"bad": None}
    result["learner_segments"][0]["confidence"] = 1.1
    try:
        jsonschema.validate(result, schema)
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("Out-of-range measured confidence must fail schema validation")
