import hashlib
import json
import subprocess
from pathlib import Path

import httpx
import numpy as np
import pytest

import speaking_evidence.media_library as media_module
from speaking_evidence.media_library import (
    MEDIA_SCHEMA_VERSION,
    MediaLibrary,
    MediaLibraryError,
    fetch_tiktok_oembed,
    resolve_tiktok_url,
    validate_tiktok_url,
)


ROOT = Path(__file__).resolve().parents[1]


def test_media_registry_json_boundary_normalizes_nested_numpy(tmp_path):
    destination = tmp_path / "registry.json"
    media_module._atomic_json(destination, {
        "schema_version": MEDIA_SCHEMA_VERSION,
        "items": [{
            "duration_seconds": np.float32(42.5),
            "frame_count": np.int64(120),
            "ready": np.bool_(True),
            "shape": np.array([1080, 1920], dtype=np.int64),
        }],
    })
    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "schema_version": MEDIA_SCHEMA_VERSION,
        "items": [{
            "duration_seconds": 42.5,
            "frame_count": 120,
            "ready": True,
            "shape": [1080, 1920],
        }],
    }


def _mock_media(monkeypatch):
    monkeypatch.setattr(media_module, "probe_media", lambda _path: {
        "duration_seconds": 42.25, "width": 1080, "height": 1920,
    })
    monkeypatch.setattr(media_module, "create_thumbnail", lambda _source, destination: (
        destination.parent.mkdir(parents=True, exist_ok=True), destination.write_bytes(b"jpg"), True
    )[-1])


@pytest.mark.parametrize("url", [
    "https://www.tiktok.com/@learner/video/123456789",
    "https://m.tiktok.com/v/123.html",
    "https://vm.tiktok.com/ABC123/",
    "https://vt.tiktok.com/ABC123/",
])
def test_valid_tiktok_url_forms(url):
    assert validate_tiktok_url(url) == url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "http://127.0.0.1/video",
    "https://example.com/video",
    "javascript:alert(1)",
    "https://tiktok.com.evil.example/video",
    "https://user:pass@www.tiktok.com/video",
])
def test_invalid_or_local_urls_are_rejected(url):
    with pytest.raises(MediaLibraryError):
        validate_tiktok_url(url)


def test_short_link_redirects_are_followed_only_within_tiktok():
    responses = {
        "https://vm.tiktok.com/ABC/": httpx.Response(
            302, headers={"location": "https://www.tiktok.com/@a/video/123"}),
        "https://www.tiktok.com/@a/video/123": httpx.Response(200),
    }
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: responses[str(request.url)]))
    assert resolve_tiktok_url("https://vm.tiktok.com/ABC/", client) == (
        "https://www.tiktok.com/@a/video/123")
    evil = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
        302, headers={"location": "http://127.0.0.1/private"})))
    with pytest.raises(MediaLibraryError):
        resolve_tiktok_url("https://vm.tiktok.com/ABC/", evil)


def test_oembed_uses_official_endpoint_and_returns_safe_display_fields():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "vm.tiktok.com":
            return httpx.Response(302, headers={
                "location": "https://www.tiktok.com/@a/video/123"
            })
        if request.url.path == "/@a/video/123":
            return httpx.Response(200)
        return httpx.Response(200, json={
            "title": "My Duet", "author_name": "Learner",
            "thumbnail_url": "https://p16.tiktokcdn.com/image.jpg",
            "html": "<blockquote class='tiktok-embed'></blockquote>",
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    preview = fetch_tiktok_oembed("https://vm.tiktok.com/ABC/", client)
    assert preview["provider_name"] == "TikTok"
    assert preview["title"] == "My Duet"
    assert any("www.tiktok.com/oembed" in url for url in seen)


def test_upload_registration_hash_duplicate_recent_and_restart_persistence(tmp_path, monkeypatch):
    _mock_media(monkeypatch)
    library = MediaLibrary(tmp_path / "library")
    first, created = library.register_upload("practice one.mp4", b"video-one")
    assert created is True
    assert first["data_class"] == "UNSEEN_USER_MEDIA"
    assert first["research_membership"] is False
    assert first["sha256"] == hashlib.sha256(b"video-one").hexdigest()
    assert Path(first["local_path"]).is_file()
    assert Path(first["thumbnail_path"]).is_file()
    duplicate, created = library.register_upload("renamed.mp4", b"video-one")
    assert created is False and duplicate["media_id"] == first["media_id"]
    second, _ = library.register_upload("practice two.mov", b"video-two")
    restarted = MediaLibrary(tmp_path / "library")
    assert {row["media_id"] for row in restarted.list_recent()} == {
        first["media_id"], second["media_id"]
    }
    restarted.mark_assessed(first["media_id"], "result_1")
    assert restarted.get(first["media_id"])["assessment_state"] == "ASSESSED"


def test_upload_is_offline_and_never_modifies_research_manifests(tmp_path, monkeypatch):
    _mock_media(monkeypatch)
    watched = [
        ROOT / "p24d_multipa_plan_v1.json",
        ROOT / "p25_frozen_mini_validation_plan_v1.json",
        ROOT / "competition_freeze_v1.json",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
    library = MediaLibrary(tmp_path / "library")
    record, _ = library.register_upload("offline.mp4", b"offline-video")
    assert record["research_membership"] is False
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}


def test_remove_deletes_only_local_user_media_and_survives_restart(tmp_path, monkeypatch):
    _mock_media(monkeypatch)
    monkeypatch.setenv("NCKH12_APP_DATA", str(tmp_path / "app-data"))
    library = MediaLibrary(tmp_path / "library")
    record, _ = library.register_upload("remove.mp4", b"remove-me")
    source = Path(record["local_path"])
    library.remove(record["media_id"])
    assert not source.exists() and library.list_recent() == []
    registry = {
        "schema_version": MEDIA_SCHEMA_VERSION,
        "items": [{
            **record, "media_id": "demo", "source_type": "DEMO",
            "local_path": str(tmp_path / "library" / "items" / "demo" / "source.mp4"),
        }],
    }
    library.registry_path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(MediaLibraryError, match="Research and demonstration"):
        library.remove("demo")


def test_tiktok_import_requires_permission_and_invokes_ytdlp_without_shell(tmp_path, monkeypatch):
    _mock_media(monkeypatch)
    monkeypatch.setattr(media_module, "resolve_tiktok_url", lambda url: validate_tiktok_url(url))
    library = MediaLibrary(tmp_path / "library")
    with pytest.raises(MediaLibraryError, match="permission"):
        library.import_tiktok("https://www.tiktok.com/@a/video/123", False)
    captured = {}

    def runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        template = Path(command[command.index("-o") + 1])
        output = Path(str(template).replace("%(ext)s", "mp4"))
        output.write_bytes(b"downloaded-video")
        return subprocess.CompletedProcess(command, 0, stdout=str(output) + "\n", stderr="")

    record, created = library.import_tiktok(
        "https://www.tiktok.com/@a/video/123", True, title="TikTok practice", runner=runner)
    assert created is True and record["source_type"] == "TIKTOK_LINK"
    assert record["data_class"] == "UNSEEN_USER_MEDIA"
    assert isinstance(captured["command"], list)
    assert "shell" not in captured["kwargs"]
    assert "--no-playlist" in captured["command"]
    assert not any("cookie" in value.lower() for value in captured["command"])


def test_tiktok_import_failure_has_manual_upload_fallback(tmp_path, monkeypatch):
    library = MediaLibrary(tmp_path / "library")
    monkeypatch.setattr(media_module, "resolve_tiktok_url", lambda url: validate_tiktok_url(url))

    def runner(_command, **_kwargs):
        raise subprocess.CalledProcessError(1, ["yt-dlp"])

    with pytest.raises(MediaLibraryError, match="upload the original file"):
        library.import_tiktok(
            "https://www.tiktok.com/@a/video/123", True, runner=runner)
