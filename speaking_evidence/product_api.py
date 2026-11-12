"""Same-origin local product adapter for the DUET / SPEAK frontend.

This module only orchestrates existing frozen Product V2 services. It does not
implement scoring, calibration, research selection, or teacher workflows.
"""
from __future__ import annotations

import json
import math
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from speaking_evidence.chatgpt_auth import ChatGPTAuthManager, ChatGPTConnectionError
from speaking_evidence.chatgpt_feedback import attach_automatic_feedback
from speaking_evidence.competition_demo import (
    DEMO_IDS,
    DEMO_ROLES,
    load_demo_cache,
    offline_readiness,
    resolve_demo_video,
    run_live_analysis,
)
from speaking_evidence.json_utils import to_jsonable
from speaking_evidence.media_library import (
    MAX_MEDIA_BYTES,
    MediaLibrary,
    MediaLibraryError,
    create_thumbnail,
    fetch_tiktok_oembed,
)


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "product_dist"
UI_CACHE = ROOT / ".local" / "product_ui"
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_auth_lock = threading.Lock()
_auth_state: dict[str, str | None] = {"state": "IDLE", "message": None}
OVERALL_PRACTICE_VERSION = "nckh12-product-overall-practice-v1"
CRITERION_CONTRACT_VERSION = "nckh12-product-criteria-v1"


class TikTokRequest(BaseModel):
    url: str
    permission_confirmed: bool = False


class ModelRequest(BaseModel):
    slug: str


def _public_error(error: Exception) -> HTTPException:
    if isinstance(error, MediaLibraryError):
        return HTTPException(status_code=400, detail={"code": error.code, "message": error.public_message})
    if isinstance(error, ChatGPTConnectionError):
        return HTTPException(status_code=400, detail={"code": error.code, "message": error.public_message})
    return HTTPException(status_code=500, detail={"code": "operation_failed", "message": "The operation could not be completed safely."})


def _ensure_local(request: Request) -> None:
    client = request.client.host if request.client else None
    if client not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="This product is available only on this computer.")


def _require_presenter(request: Request, x_presenter: str | None) -> None:
    _ensure_local(request)
    if x_presenter != "1":
        raise HTTPException(status_code=403, detail="Presenter mode is required.")


def _safe_media_file(path: Path, allowed_root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(allowed_root.resolve()):
        raise HTTPException(status_code=404, detail="Media is unavailable.")
    return resolved


def _demo_item(pair_id: str) -> dict:
    if pair_id not in DEMO_IDS:
        raise HTTPException(status_code=404, detail="Demo not found.")
    try:
        return load_demo_cache(ROOT, pair_id)
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=409, detail={"code": "stale_demo", "message": "This frozen demo could not be verified."}) from error


def _demo_audio(item: dict) -> Path:
    base = ROOT / "assessment_runs" / "T001_p24_tournament_v1"
    return _safe_media_file(base / item["model_input_ref"], base)


def _feedback(result: dict) -> dict:
    source = result.get("automatic_feedback")
    if isinstance(source, dict):
        chosen = source
        label = "CHATGPT"
    else:
        chosen = result.get("feedback", {})
        label = "DETERMINISTIC"
    return {
        "strength": chosen.get("strength", {"text": "Measured evidence is available."}),
        "focus_next": chosen.get("focus_next", {"text": "Choose one small refinement for the next take."}),
        "try_this": chosen.get("try_this", {"text": "Record one more take and compare the evidence."}),
        "source": label,
    }


def build_overall_practice_score(scores: dict, completeness: dict) -> dict | None:
    """Create a descriptive product summary without changing research scores.

    Reading Completeness is converted from its saved 0-1 coverage ratio to the
    existing 1-5 display range. The product composite is available only when
    all four inputs are finite numbers. It is not persisted into research
    artifacts and does not use Intelligibility, ratings, P2.5, or holdout data.
    """
    coverage = completeness.get("coverage") if isinstance(completeness, dict) else None
    values = {
        "pronunciation": scores.get("pronunciation") if isinstance(scores, dict) else None,
        "fluency": scores.get("fluency") if isinstance(scores, dict) else None,
        "prosody": scores.get("prosody") if isinstance(scores, dict) else None,
        "reading_completeness": (1.0 + 4.0 * float(coverage)
                                 if isinstance(coverage, (int, float)) and not isinstance(coverage, bool)
                                 else None),
    }
    if any(not isinstance(value, (int, float)) or isinstance(value, bool)
           or not math.isfinite(float(value)) for value in values.values()):
        return None
    numeric = {key: float(value) for key, value in values.items()}
    if not 0.0 <= float(coverage) <= 1.0 or any(not 1.0 <= value <= 5.0 for value in numeric.values()):
        return None
    raw = sum(numeric.values()) / 4.0
    return {
        "version": OVERALL_PRACTICE_VERSION,
        "value": round(raw, 4),
        "display_value": round(raw, 1),
        "scale_max": 5,
        "status": "DESCRIPTIVE_PRODUCT_COMPOSITE",
        "label": "Overall Practice Score",
        "methodology_note": "Equal-weight mean of Pronunciation, Fluency, Prosody and ASR-assisted Reading Completeness on a 1-5 display scale.",
        "student_note": "A simple summary of the four current assessment measures. It is not a standardized proficiency score.",
        "presenter_designation": "UNVALIDATED_PRODUCT_COMPOSITE",
        "inputs": numeric,
        "machine_intelligibility_included": False,
        "research_validated": False,
    }


def build_criterion_contract(result: dict) -> dict:
    """Normalize criterion presentation once at the product API boundary."""
    scores = result.get("scores", {}) if isinstance(result.get("scores"), dict) else {}
    statuses = (result.get("criterion_status", {})
                if isinstance(result.get("criterion_status"), dict) else {})
    copy = {
        "pronunciation": (
            "Pronunciation", "Sound accuracy and clarity", "Preliminary",
            "Based on a limited development score range.",
        ),
        "fluency": (
            "Fluency", "Flow, continuity and pausing", "Usable criterion", None,
        ),
        "prosody": (
            "Prosody", "Stress, rhythm and intonation", "Preliminary",
            "This measure remains development-stage evidence.",
        ),
    }
    criteria: dict[str, dict] = {}
    for key, (label, description, badge, caveat) in copy.items():
        raw = scores.get(key)
        available = (isinstance(raw, (int, float)) and not isinstance(raw, bool)
                     and math.isfinite(float(raw)) and 1.0 <= float(raw) <= 5.0)
        value = float(raw) if available else None
        criteria[key] = {
            "key": key,
            "label": label,
            "description": description,
            "value": value,
            "display_value": round(value, 1) if value is not None else None,
            "unit": "SCALE_1_5",
            "scale_max": 5,
            "available": available,
            "status": str(statuses.get(key, "UNAVAILABLE")),
            "badge": badge,
            "caveat": caveat,
        }

    completeness = (result.get("completeness", {})
                    if isinstance(result.get("completeness"), dict) else {})
    coverage = completeness.get("coverage")
    available = (isinstance(coverage, (int, float)) and not isinstance(coverage, bool)
                 and math.isfinite(float(coverage)) and 0.0 <= float(coverage) <= 1.0)
    percent = float(coverage) * 100.0 if available else None
    criteria["completeness"] = {
        "key": "completeness",
        "label": "Reading Completeness",
        "description": "Target passage matched by ASR",
        "value": percent,
        "display_value": round(percent) if percent is not None else None,
        "unit": "PERCENT",
        "scale_max": 100,
        "available": available,
        "status": str(statuses.get("completeness", "UNAVAILABLE")),
        "badge": "ASR-assisted coverage",
        "caveat": "ASR differences are not confirmed learner reading errors.",
    }
    return {"version": CRITERION_CONTRACT_VERSION, "items": criteria}


def _serialize_result(result: dict, *, result_id: str, video_url: str, audio_url: str | None) -> dict:
    failures = [
        {"public_message": str(row.get("public_message", "One criterion is unavailable."))}
        for row in result.get("model_failures", []) if isinstance(row, dict)
    ]
    overall = (None if result.get("status") == "NOT_SCORABLE" else
               build_overall_practice_score(result.get("scores", {}), result.get("completeness", {})))
    payload = {
        "id": result_id,
        "pair_id": result.get("pair_id"),
        "display_name": result.get("display_name", "Completed Duet"),
        "source_mode": result.get("source_mode"),
        "status": result.get("status", "COMPLETE"),
        "target_topic": result.get("target_topic", "One memorable event"),
        "target_text": result.get("target_text", ""),
        "transcript": result.get("transcript", ""),
        "criteria": build_criterion_contract(result),
        "completeness": result.get("completeness", {}),
        "evidence": {
            "fluency": result.get("evidence", {}).get("fluency", {}),
            "word_review_prompts": result.get("evidence", {}).get("word_review_prompts", []),
        },
        "feedback": _feedback(result),
        "media": {"video_url": video_url, "audio_url": audio_url},
        "model_failures": failures,
        "provenance": {
            "source_mode": result.get("source_mode"),
            "canonical_source": result.get("canonical_source", "RAW_COMPLETED_DUET"),
            "audio_source_type": result.get("audio_source_type", "RAW_CROPPED"),
            "genuine_frozen_inference": result.get("genuine_frozen_inference") is True,
            "research_membership": False,
        },
        "machine_intelligibility": None,
        "overall_practice_score": overall,
        "holdout_processed": False,
    }
    if result.get("status") == "NOT_SCORABLE":
        payload["reason_codes"] = [str(value) for value in result.get("reason_codes", [])]
    return to_jsonable(payload)


def _serialize_media(item: dict) -> dict:
    media_id = item["media_id"]
    return {
        "media_id": media_id,
        "friendly_title": item.get("friendly_title", "Completed Duet"),
        "source_type": item.get("source_type", "LOCAL_UPLOAD"),
        "import_timestamp": item.get("import_timestamp"),
        "duration_seconds": item.get("duration_seconds"),
        "resolution": item.get("resolution", {}),
        "processing_state": item.get("processing_state", "READY"),
        "assessment_state": item.get("assessment_state", "NOT_ASSESSED"),
        "has_result": bool(item.get("last_result_id")),
        "thumbnail_url": f"/api/media/{media_id}/thumbnail" if item.get("thumbnail_path") else None,
        "video_url": f"/api/media/{media_id}/video",
        "data_class": "UNSEEN_USER_MEDIA",
        "research_membership": False,
    }


def _write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _assessment_worker(job_id: str, media_id: str) -> None:
    library = MediaLibrary()
    try:
        record = library.get(media_id)
        source = _safe_media_file(Path(record["local_path"]), library.items_root)
        work_dir = library.analysis_dir(media_id)

        def notify(message: str) -> None:
            with _jobs_lock:
                _jobs[job_id].update(state="RUNNING", message=message)

        result = run_live_analysis(ROOT, source, work_dir, progress=notify)
        if result.get("status") != "NOT_SCORABLE":
            enriched, feedback_error = attach_automatic_feedback(result)
            result = enriched
            if feedback_error:
                result["automatic_feedback_error_code"] = feedback_error
        _write_result(work_dir / "result.json", result)
        result_id = f"result_{record['sha256'][:16]}"
        library.mark_assessed(media_id, result_id)
        with _jobs_lock:
            _jobs[job_id].update(state="COMPLETE", message="Assessment ready", result_id=result_id)
    except Exception:
        with _jobs_lock:
            _jobs[job_id].update(
                state="FAILED",
                message="The assessment stopped safely.",
                error="This recording could not be assessed. Your saved video is unchanged.",
            )


def create_app() -> FastAPI:
    app = FastAPI(title="DUET / SPEAK local product API", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        _ensure_local(request)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "public, max-age=3600"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https://*.tiktokcdn.com https://*.tiktok.com; media-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
        return response

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "product": "DUET / SPEAK"}

    @app.get("/api/bootstrap")
    def bootstrap() -> dict:
        library = MediaLibrary()
        auth = ChatGPTAuthManager().status()
        demos = []
        for pair_id in DEMO_IDS:
            item = _demo_item(pair_id)
            demos.append({
                "id": pair_id,
                "short_id": pair_id.removeprefix("T001-"),
                "display_name": item["display_name"],
                "role": DEMO_ROLES[pair_id],
                "thumbnail_url": f"/api/demos/{pair_id}/thumbnail",
            })
        return {
            "product": "DUET / SPEAK",
            "descriptor": "NCKH12 Speaking Coach",
            "demos": demos,
            "offline_ready": offline_readiness(ROOT)["ready"],
            "recent_count": len(library.list_recent()),
            "chatgpt": auth,
            "scientific_scope": {
                "frozen_research_overall_score": None,
                "machine_intelligibility": None,
                "holdout_processed": False,
                "product_overall_version": OVERALL_PRACTICE_VERSION,
            },
        }

    @app.get("/api/demos/{pair_id}")
    def demo_result(pair_id: str) -> dict:
        item = _demo_item(pair_id)
        return _serialize_result(item, result_id=pair_id, video_url=f"/api/demos/{pair_id}/video", audio_url=f"/api/demos/{pair_id}/audio")

    @app.get("/api/demos/{pair_id}/video")
    def demo_video(pair_id: str):
        item = _demo_item(pair_id)
        path = resolve_demo_video(ROOT, pair_id, item["raw_duet_sha256"])
        return FileResponse(path)

    @app.get("/api/demos/{pair_id}/audio")
    def demo_audio(pair_id: str):
        return FileResponse(_demo_audio(_demo_item(pair_id)), media_type="audio/wav")

    @app.get("/api/demos/{pair_id}/thumbnail")
    def demo_thumbnail(pair_id: str):
        item = _demo_item(pair_id)
        path = UI_CACHE / "demo_thumbnails" / f"{pair_id}.jpg"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            video = resolve_demo_video(ROOT, pair_id, item["raw_duet_sha256"])
            if not create_thumbnail(video, path):
                raise HTTPException(status_code=404, detail="Thumbnail is unavailable.")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/media")
    def recent_media() -> dict:
        return {"items": [_serialize_media(row) for row in MediaLibrary().list_recent()]}

    @app.post("/api/media/upload")
    async def upload_media(file: UploadFile = File(...)) -> dict:
        payload = await file.read(MAX_MEDIA_BYTES + 1)
        if len(payload) > MAX_MEDIA_BYTES:
            raise HTTPException(status_code=413, detail={"code": "file_too_large", "message": "Use a video smaller than 500 MB."})
        try:
            item, created = MediaLibrary().register_upload(file.filename or "completed-duet.mp4", payload)
            return {"item": _serialize_media(item), "created": created}
        except Exception as error:
            raise _public_error(error) from error

    @app.post("/api/tiktok/preview")
    def tiktok_preview(body: TikTokRequest) -> dict:
        try:
            return to_jsonable(fetch_tiktok_oembed(body.url))
        except Exception as error:
            raise _public_error(error) from error

    @app.post("/api/tiktok/import")
    def tiktok_import(body: TikTokRequest) -> dict:
        try:
            item, created = MediaLibrary().import_tiktok(body.url, body.permission_confirmed)
            return {"item": _serialize_media(item), "created": created}
        except Exception as error:
            raise _public_error(error) from error

    @app.post("/api/media/{media_id}/assess")
    def assess_media(media_id: str) -> dict:
        library = MediaLibrary()
        try:
            library.get(media_id)
        except Exception as error:
            raise _public_error(error) from error
        job_id = f"job_{uuid.uuid4().hex}"
        job = {"job_id": job_id, "media_id": media_id, "state": "QUEUED", "message": "Assessment queued"}
        with _jobs_lock:
            _jobs[job_id] = job
        threading.Thread(target=_assessment_worker, args=(job_id, media_id), daemon=True).start()
        return deepcopy(job)

    @app.get("/api/jobs/{job_id}")
    def job_state(job_id: str) -> dict:
        with _jobs_lock:
            job = deepcopy(_jobs.get(job_id))
        if not job:
            raise HTTPException(status_code=404, detail="Assessment job not found.")
        return job

    @app.get("/api/media/{media_id}/result")
    def media_result(media_id: str) -> dict:
        library = MediaLibrary()
        try:
            record = library.get(media_id)
            path = _safe_media_file(library.analysis_dir(media_id) / "result.json", library.items_root)
            result = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            raise _public_error(error) from error
        if result.get("raw_duet_sha256") != record.get("sha256"):
            raise HTTPException(status_code=409, detail="The saved result no longer matches this video.")
        audio = library.analysis_dir(media_id) / "raw_learner_audio.wav"
        audio_url = f"/api/media/{media_id}/audio" if audio.is_file() else None
        return _serialize_result(result, result_id=record.get("last_result_id") or media_id, video_url=f"/api/media/{media_id}/video", audio_url=audio_url)

    @app.get("/api/media/{media_id}/video")
    def media_video(media_id: str):
        library = MediaLibrary()
        try:
            record = library.get(media_id)
            return FileResponse(_safe_media_file(Path(record["local_path"]), library.items_root))
        except Exception as error:
            raise _public_error(error) from error

    @app.get("/api/media/{media_id}/audio")
    def media_audio(media_id: str):
        library = MediaLibrary()
        try:
            path = _safe_media_file(library.analysis_dir(media_id) / "raw_learner_audio.wav", library.items_root)
            return FileResponse(path, media_type="audio/wav")
        except Exception as error:
            raise _public_error(error) from error

    @app.get("/api/media/{media_id}/thumbnail")
    def media_thumbnail(media_id: str):
        library = MediaLibrary()
        try:
            record = library.get(media_id)
            if not record.get("thumbnail_path"):
                raise MediaLibraryError("thumbnail_missing", "Thumbnail is unavailable.")
            return FileResponse(_safe_media_file(Path(record["thumbnail_path"]), library.items_root), media_type="image/jpeg")
        except Exception as error:
            raise _public_error(error) from error

    @app.delete("/api/media/{media_id}")
    def delete_media(media_id: str) -> dict:
        try:
            MediaLibrary().remove(media_id)
            return {"removed": True}
        except Exception as error:
            raise _public_error(error) from error

    @app.post("/api/presenter/chatgpt/connect")
    def connect_chatgpt(request: Request, x_presenter: str | None = Header(default=None)) -> dict:
        _require_presenter(request, x_presenter)
        with _auth_lock:
            if _auth_state["state"] == "PENDING":
                return deepcopy(_auth_state)
            _auth_state.update(state="PENDING", message="Waiting for secure browser authorization")

        def worker() -> None:
            try:
                ChatGPTAuthManager().sign_in()
                with _auth_lock:
                    _auth_state.update(state="CONNECTED", message="Personalized feedback is enabled")
            except ChatGPTConnectionError as error:
                with _auth_lock:
                    _auth_state.update(state="FAILED", message=error.public_message)

        threading.Thread(target=worker, daemon=True).start()
        return deepcopy(_auth_state)

    @app.post("/api/presenter/chatgpt/disconnect")
    def disconnect_chatgpt(request: Request, x_presenter: str | None = Header(default=None)) -> dict:
        _require_presenter(request, x_presenter)
        ChatGPTAuthManager().disconnect()
        return {"connected": False}

    @app.post("/api/presenter/chatgpt/model")
    def select_chatgpt_model(body: ModelRequest, request: Request, x_presenter: str | None = Header(default=None)) -> dict:
        _require_presenter(request, x_presenter)
        try:
            ChatGPTAuthManager().select_model(body.slug)
            return {"selected_model": body.slug}
        except Exception as error:
            raise _public_error(error) from error

    if FRONTEND.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            candidate = (FRONTEND / full_path).resolve()
            if full_path and candidate.is_file() and candidate.is_relative_to(FRONTEND.resolve()):
                return FileResponse(candidate)
            return FileResponse(FRONTEND / "index.html")

    return app


app = create_app()
