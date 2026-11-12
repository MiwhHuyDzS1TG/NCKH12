"""Private local media library for competition/user inference only."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from speaking_evidence.chatgpt_auth import app_data_root
from speaking_evidence.json_utils import to_jsonable


MEDIA_SCHEMA_VERSION = "nckh12-user-media-v1"
TIKTOK_IMPORTER_VERSION = "yt-dlp-2026.7.4"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
MAX_MEDIA_BYTES = 500 * 1024 * 1024
MAX_DURATION_SECONDS = 300.0
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com",
                "vm.tiktok.com", "vt.tiktok.com"}


class MediaLibraryError(RuntimeError):
    def __init__(self, code: str, public_message: str):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_title(filename: str) -> str:
    stem = Path(filename).stem
    clean = re.sub(r"[^A-Za-z0-9 _.-]+", " ", stem)
    clean = re.sub(r"\s+", " ", clean).strip(" ._-")
    return (clean or "Completed Duet")[:80]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False,
                                    indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)


def is_tiktok_host(host: str | None) -> bool:
    value = (host or "").lower().rstrip(".")
    return value in TIKTOK_HOSTS or value.endswith(".tiktok.com")


def validate_tiktok_url(url: str) -> str:
    try:
        parsed = urlparse(url.strip())
    except ValueError as exc:
        raise MediaLibraryError("invalid_url", "Enter a valid public TikTok video link.") from exc
    if parsed.scheme not in {"http", "https"} or not is_tiktok_host(parsed.hostname):
        raise MediaLibraryError("unsupported_url", "Enter a public TikTok video link.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MediaLibraryError("unsafe_url", "This TikTok link cannot be used safely.") from exc
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        raise MediaLibraryError("unsafe_url", "This TikTok link cannot be used safely.")
    return parsed.geturl()


def resolve_tiktok_url(url: str, client: httpx.Client | None = None,
                       max_redirects: int = 5) -> str:
    current = validate_tiktok_url(url)
    owned = client is None
    session = client or httpx.Client(follow_redirects=False)
    try:
        for _ in range(max_redirects + 1):
            response = session.get(current, headers={"Range": "bytes=0-0"}, timeout=12)
            if response.status_code not in {301, 302, 303, 307, 308}:
                return validate_tiktok_url(str(response.url))
            location = response.headers.get("location")
            if not location:
                raise MediaLibraryError("link_resolution_failed",
                                        "This TikTok link could not be resolved.")
            current = validate_tiktok_url(urljoin(current, location))
        raise MediaLibraryError("too_many_redirects", "This TikTok link could not be resolved.")
    except httpx.HTTPError as exc:
        raise MediaLibraryError("network_unavailable",
                                "TikTok preview is unavailable. You can upload your video instead.") from exc
    finally:
        if owned:
            session.close()


def fetch_tiktok_oembed(url: str, client: httpx.Client | None = None) -> dict:
    resolved = resolve_tiktok_url(url, client=client)
    owned = client is None
    session = client or httpx.Client()
    try:
        response = session.get("https://www.tiktok.com/oembed", params={"url": resolved}, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise MediaLibraryError(
            "preview_unavailable",
            "This TikTok video could not be previewed. It may be deleted, private, or restricted.",
        ) from exc
    finally:
        if owned:
            session.close()
    if not isinstance(payload.get("html"), str):
        raise MediaLibraryError("preview_unavailable", "This TikTok video could not be previewed.")
    return {
        "resolved_url": resolved,
        "title": str(payload.get("title") or "TikTok Duet")[:120],
        "author_name": str(payload.get("author_name") or "")[:80],
        "thumbnail_url": payload.get("thumbnail_url"),
        "html": payload["html"],
        "provider_name": "TikTok",
    }


def probe_media(path: Path) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=width,height", "-select_streams", "v:0",
        "-of", "json", str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True,
                                   timeout=20)
        payload = json.loads(completed.stdout)
        stream = (payload.get("streams") or [{}])[0]
        duration = float(payload.get("format", {}).get("duration", 0))
        width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError, IndexError) as exc:
        raise MediaLibraryError("invalid_video", "This file is not a readable video.") from exc
    if duration <= 0 or duration > MAX_DURATION_SECONDS:
        raise MediaLibraryError("duration_not_supported",
                                "Use a completed Duet that is five minutes or shorter.")
    return {"duration_seconds": round(duration, 3), "width": width, "height": height}


def create_thumbnail(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-ss", "1", "-i", str(source), "-frames:v", "1",
        "-vf", "scale=640:-2", "-q:v", "3", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30)
        return destination.is_file()
    except (OSError, subprocess.SubprocessError):
        return False


class MediaLibrary:
    def __init__(self, root: Path | None = None):
        self.root = (root or (app_data_root() / "media_library")).resolve()
        self.items_root = self.root / "items"
        self.registry_path = self.root / "registry.json"

    def _load(self) -> dict:
        if not self.registry_path.is_file():
            return {"schema_version": MEDIA_SCHEMA_VERSION, "items": []}
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != MEDIA_SCHEMA_VERSION or not isinstance(payload.get("items"), list):
            raise MediaLibraryError("invalid_media_registry", "The local video library could not be read.")
        return payload

    def _save(self, payload: dict) -> None:
        _atomic_json(self.registry_path, payload)

    def list_recent(self) -> list[dict]:
        return sorted(self._load()["items"], key=lambda row: row["import_timestamp"], reverse=True)

    def get(self, media_id: str) -> dict:
        try:
            return next(row for row in self._load()["items"] if row["media_id"] == media_id)
        except StopIteration as exc:
            raise MediaLibraryError("media_not_found", "This local video is no longer available.") from exc

    def register_upload(self, filename: str, payload: bytes,
                        source_type: str = "LOCAL_UPLOAD", source_url: str | None = None,
                        title: str | None = None) -> tuple[dict, bool]:
        if source_type not in {"LOCAL_UPLOAD", "TIKTOK_LINK"}:
            raise MediaLibraryError("invalid_source_type", "This video source is not supported.")
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise MediaLibraryError("unsupported_format", "Upload an MP4, MOV, MKV, or WebM video.")
        if not payload or len(payload) > MAX_MEDIA_BYTES:
            raise MediaLibraryError("file_size_not_supported", "Use a video smaller than 500 MB.")
        digest = _sha256(payload)
        registry = self._load()
        duplicate = next((row for row in registry["items"] if row["sha256"] == digest), None)
        if duplicate:
            return duplicate, False
        media_id = f"media_{digest[:16]}"
        item_dir = (self.items_root / media_id).resolve()
        if not item_dir.is_relative_to(self.items_root.resolve()):
            raise MediaLibraryError("unsafe_media_path", "The local video could not be saved safely.")
        item_dir.mkdir(parents=True, exist_ok=False)
        source = item_dir / f"source{suffix}"
        source.write_bytes(payload)
        try:
            metadata = probe_media(source)
        except Exception:
            shutil.rmtree(item_dir, ignore_errors=True)
            raise
        thumbnail = item_dir / "thumbnail.jpg"
        thumbnail_ready = create_thumbnail(source, thumbnail)
        record = {
            "schema_version": MEDIA_SCHEMA_VERSION,
            "media_id": media_id,
            "friendly_title": (title or _safe_title(filename))[:120],
            "original_filename": Path(filename).name[:160],
            "source_type": source_type,
            "source_url": source_url if source_type == "TIKTOK_LINK" else None,
            "import_timestamp": _now(),
            "local_path": str(source),
            "sha256": digest,
            "duration_seconds": metadata["duration_seconds"],
            "resolution": {"width": metadata["width"], "height": metadata["height"]},
            "thumbnail_path": str(thumbnail) if thumbnail_ready else None,
            "processing_state": "READY",
            "assessment_state": "NOT_ASSESSED",
            "last_result_id": None,
            "data_class": "UNSEEN_USER_MEDIA",
            "research_membership": False,
        }
        registry["items"].append(record)
        self._save(registry)
        return record, True

    def analysis_dir(self, media_id: str) -> Path:
        record = self.get(media_id)
        directory = (Path(record["local_path"]).parent / "analysis").resolve()
        if not directory.is_relative_to(self.items_root.resolve()):
            raise MediaLibraryError("unsafe_media_path", "The local assessment path is unsafe.")
        return directory

    def mark_assessed(self, media_id: str, result_id: str, state: str = "ASSESSED") -> dict:
        payload = self._load()
        record = next((row for row in payload["items"] if row["media_id"] == media_id), None)
        if not record:
            raise MediaLibraryError("media_not_found", "This local video is no longer available.")
        record["assessment_state"] = state
        record["last_result_id"] = result_id
        record["processing_state"] = "READY"
        self._save(payload)
        return record

    def remove(self, media_id: str) -> None:
        payload = self._load()
        record = next((row for row in payload["items"] if row["media_id"] == media_id), None)
        if not record:
            raise MediaLibraryError("media_not_found", "This local video is no longer available.")
        if record.get("source_type") == "DEMO" or record.get("research_membership") is not False:
            raise MediaLibraryError("protected_research_media",
                                    "Research and demonstration media cannot be removed here.")
        item_dir = Path(record["local_path"]).resolve().parent
        if not item_dir.is_relative_to(self.items_root.resolve()) or item_dir == self.items_root.resolve():
            raise MediaLibraryError("unsafe_media_path", "The local video could not be removed safely.")
        shutil.rmtree(item_dir)
        from speaking_evidence.chatgpt_feedback import purge_feedback_for_input
        purge_feedback_for_input(record["sha256"])
        payload["items"] = [row for row in payload["items"] if row["media_id"] != media_id]
        self._save(payload)

    def import_tiktok(self, url: str, permission_confirmed: bool,
                      title: str | None = None,
                      runner: object = subprocess.run) -> tuple[dict, bool]:
        if not permission_confirmed:
            raise MediaLibraryError(
                "permission_required",
                "Confirm that you own this video or have permission to use it before importing.",
            )
        resolved = resolve_tiktok_url(url)
        temporary = self.root / "incoming" / f"tiktok_{uuid.uuid4().hex}"
        temporary.mkdir(parents=True, exist_ok=False)
        output_template = temporary / "imported.%(ext)s"
        command = [
            sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-part",
            "--no-write-info-json", "--restrict-filenames", "--socket-timeout", "20",
            "--retries", "1", "--max-filesize", "500M", "--match-filter",
            f"duration <= {int(MAX_DURATION_SECONDS)}", "--print", "after_move:filepath",
            "-o", str(output_template), resolved,
        ]
        try:
            completed = runner(command, check=True, capture_output=True, text=True, timeout=180)
            candidates = [Path(line.strip()) for line in completed.stdout.splitlines()
                          if line.strip() and Path(line.strip()).is_file()]
            if not candidates:
                candidates = [row for row in temporary.glob("imported.*") if row.is_file()]
            if len(candidates) != 1:
                raise MediaLibraryError("tiktok_import_failed",
                                        "This TikTok video could not be imported automatically. Download your own video from TikTok or upload the original file instead.")
            source = candidates[0].resolve()
            if not source.is_relative_to(temporary.resolve()):
                raise MediaLibraryError("unsafe_import_path", "The imported video path was rejected.")
            if source.stat().st_size > MAX_MEDIA_BYTES:
                raise MediaLibraryError("file_size_not_supported", "Use a video smaller than 500 MB.")
            return self.register_upload(
                source.name, source.read_bytes(), source_type="TIKTOK_LINK",
                source_url=resolved, title=title,
            )
        except MediaLibraryError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise MediaLibraryError(
                "tiktok_import_failed",
                "This TikTok video could not be imported automatically. Download your own video from TikTok or upload the original file instead.",
            ) from exc
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
