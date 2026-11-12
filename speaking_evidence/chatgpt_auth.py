"""Official Sign in with ChatGPT flow for the local NCKH12 product.

This module follows OpenAI's open-source token-sharing contract. It never uses
an API key, never calls ChatGPT web internals, and keeps credentials outside the
repository. On Windows, the credential payload is protected with DPAPI.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.hashes import SHA256


AUTHORIZATION_ENDPOINT = "https://auth.openai.com/api/accounts/authorize"
TOKEN_ENDPOINT = "https://auth.openai.com/api/accounts/oauth/token"
DISCOVERY_ENDPOINT = "https://auth.openai.com/.well-known/openid-configuration"
RESOURCE = "https://api.openai.com/v1"
MODELS_ENDPOINT = f"{RESOURCE}/models"
RESPONSES_ENDPOINT = f"{RESOURCE}/responses"
MANAGE_USAGE_URL = "https://chatgpt.com/settings/usage"
REQUIRED_SCOPES = (
    "openid", "profile", "email", "offline_access", "resource.invoke",
    "chatgpt.tokens.use.direct",
)
PLAN_USAGE_SCOPE = "chatgpt.tokens.use.direct"
APP_NAME = "NCKH12 Speaking Coach"
OAUTH_IMPLEMENTATION_VERSION = "nckh12-sign-in-with-chatgpt-v1"


class ChatGPTConnectionError(RuntimeError):
    """Safe, token-free connection failure."""

    def __init__(self, code: str, public_message: str):
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def redact_secrets(text: str, values: list[str] | tuple[str, ...] = ()) -> str:
    """Redact explicit secrets and common bearer/JWT shapes from diagnostics."""
    clean = str(text)
    for value in values:
        if value:
            clean = clean.replace(str(value), "[REDACTED]")
    import re
    clean = re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED]", clean)
    clean = re.sub(r"(?i)((?:access|refresh|id)_token[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+",
                   r"\1[REDACTED]", clean)
    clean = re.sub(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
                   "[REDACTED_JWT]", clean)
    return clean


def app_data_root() -> Path:
    override = os.environ.get("NCKH12_APP_DATA")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]).resolve() / "NCKH12"
    return Path.home() / ".local" / "share" / "nckh12"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_ulong),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _dpapi(value: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        return value
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    destination = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    operation = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    if decrypt:
        ok = operation(ctypes.byref(source), None, None, None, None, 0,
                       ctypes.byref(destination))
    else:
        ok = operation(ctypes.byref(source), "NCKH12 ChatGPT connection", None,
                       None, None, 0, ctypes.byref(destination))
    if not ok:
        raise ChatGPTConnectionError("credential_storage_failed",
                                     "ChatGPT connection storage is unavailable.")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        kernel32.LocalFree(destination.pbData)


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)


class CredentialStore:
    """Stable host identity plus protected local account credentials."""

    def __init__(self, root: Path | None = None):
        self.root = (root or app_data_root()).resolve() / "chatgpt"
        self.host_path = self.root / "host.json"
        self.profile_path = self.root / "profile.dat"
        self.registration_path = self.root / "registration.json"

    def host_id(self) -> str:
        if self.host_path.is_file():
            value = json.loads(self.host_path.read_text(encoding="utf-8")).get("ext_agent_host_id")
            if isinstance(value, str) and value.startswith("urn:uuid:"):
                return value
        value = f"urn:uuid:{uuid.uuid4()}"
        _atomic_write(self.host_path, (json.dumps({"ext_agent_host_id": value}) + "\n").encode())
        return value

    def load(self) -> dict | None:
        if not self.profile_path.is_file():
            return None
        try:
            return json.loads(_dpapi(self.profile_path.read_bytes(), decrypt=True).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ChatGPTConnectionError("credential_storage_invalid",
                                         "The saved ChatGPT connection could not be read.") from exc

    def save(self, profile: dict) -> None:
        raw = json.dumps(profile, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_write(self.profile_path, _dpapi(raw))
        # The issued public client identifier is not a credential. Keep only
        # this mapping so reconnect can reuse the registration; do not retain
        # the account subject after the protected profile is disconnected.
        registration = {"client_id": profile.get("client_id")}
        _atomic_write(self.registration_path,
                      (json.dumps(registration, separators=(",", ":")) + "\n").encode())

    def registration(self) -> dict | None:
        if not self.registration_path.is_file():
            return None
        try:
            value = json.loads(self.registration_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value.get("client_id"), str) else None

    def clear(self) -> None:
        if self.profile_path.is_file():
            self.profile_path.unlink()


@dataclass(frozen=True)
class AuthorizationAttempt:
    state: str
    nonce: str
    verifier: str
    challenge: str
    redirect_uri: str
    client_id: str
    host_id: str


def create_authorization_attempt(host_id: str, port: int,
                                 client_id: str = "dynamic_agent_client") -> AuthorizationAttempt:
    verifier = _b64url_encode(secrets.token_bytes(64))
    return AuthorizationAttempt(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=verifier,
        challenge=_b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest()),
        redirect_uri=f"http://127.0.0.1:{port}/auth/callback",
        client_id=client_id,
        host_id=host_id,
    )


def authorization_url(attempt: AuthorizationAttempt) -> str:
    params = {
        "client_id": attempt.client_id,
        "response_type": "code",
        "redirect_uri": attempt.redirect_uri,
        "scope": " ".join(REQUIRED_SCOPES),
        "resource": RESOURCE,
        "state": attempt.state,
        "nonce": attempt.nonce,
        "code_challenge_method": "S256",
        "code_challenge": attempt.challenge,
        "ext_agent_host_id": attempt.host_id,
    }
    if attempt.client_id == "dynamic_agent_client":
        params["agent_name_hint"] = APP_NAME
    return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"


def validate_callback(attempt: AuthorizationAttempt, query: dict[str, list[str]]) -> dict:
    state = (query.get("state") or [""])[0]
    if not secrets.compare_digest(state, attempt.state):
        raise ChatGPTConnectionError("invalid_oauth_state",
                                     "The ChatGPT sign-in response did not match this request.")
    if query.get("error"):
        raise ChatGPTConnectionError("access_denied", "ChatGPT connection was not approved.")
    code = (query.get("code") or [""])[0]
    if not code:
        raise ChatGPTConnectionError("missing_authorization_code",
                                     "ChatGPT did not return an authorization code.")
    returned_client = (query.get("client_id") or [""])[0]
    if attempt.client_id == "dynamic_agent_client":
        if not returned_client or returned_client == "dynamic_agent_client":
            raise ChatGPTConnectionError("registration_incomplete",
                                         "ChatGPT client registration did not complete.")
        client_id = returned_client
    else:
        if returned_client and returned_client != attempt.client_id:
            raise ChatGPTConnectionError("client_mismatch",
                                         "The ChatGPT connection returned a different client.")
        client_id = attempt.client_id
    return {"code": code, "client_id": client_id}


def _decode_json_part(value: str) -> dict:
    try:
        return json.loads(_b64url_decode(value).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ChatGPTConnectionError("invalid_id_token",
                                     "ChatGPT identity validation failed.") from exc


def verify_id_token(token: str, client_id: str, nonce: str, client: httpx.Client) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ChatGPTConnectionError("invalid_id_token", "ChatGPT identity validation failed.")
    header = _decode_json_part(parts[0])
    claims = _decode_json_part(parts[1])
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise ChatGPTConnectionError("invalid_id_token", "ChatGPT identity validation failed.")
    try:
        discovery_response = client.get(DISCOVERY_ENDPOINT, timeout=15)
        discovery_response.raise_for_status()
        discovery = discovery_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ChatGPTConnectionError(
            "invalid_openid_configuration",
            "ChatGPT identity configuration is unavailable.",
        ) from exc
    issuer = discovery.get("issuer")
    jwks_uri = discovery.get("jwks_uri")
    if not issuer or not jwks_uri:
        raise ChatGPTConnectionError("invalid_openid_configuration",
                                     "ChatGPT identity configuration is unavailable.")
    try:
        keys_response = client.get(jwks_uri, timeout=15)
        keys_response.raise_for_status()
        keys = keys_response.json().get("keys", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise ChatGPTConnectionError(
            "signing_keys_unavailable", "ChatGPT identity validation is unavailable."
        ) from exc
    key = next((row for row in keys if row.get("kid") == header["kid"]), None)
    if not key or key.get("kty") != "RSA":
        raise ChatGPTConnectionError("unknown_signing_key", "ChatGPT identity validation failed.")
    public_key = rsa.RSAPublicNumbers(
        int.from_bytes(_b64url_decode(key["e"]), "big"),
        int.from_bytes(_b64url_decode(key["n"]), "big"),
    ).public_key()
    try:
        public_key.verify(_b64url_decode(parts[2]), f"{parts[0]}.{parts[1]}".encode("ascii"),
                          padding.PKCS1v15(), SHA256())
    except Exception as exc:
        raise ChatGPTConnectionError("invalid_id_token_signature",
                                     "ChatGPT identity validation failed.") from exc
    audience = claims.get("aud")
    audience_ok = client_id in audience if isinstance(audience, list) else audience == client_id
    now = int(time.time())
    if (claims.get("iss") != issuer or not audience_ok or claims.get("nonce") != nonce
            or not isinstance(claims.get("sub"), str)
            or not isinstance(claims.get("exp"), (int, float)) or claims["exp"] < now - 60):
        raise ChatGPTConnectionError("invalid_id_token_claims",
                                     "ChatGPT identity validation failed.")
    return claims


class _CallbackHandler(BaseHTTPRequestHandler):
    query: dict[str, list[str]] | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return
        type(self).query = parse_qs(parsed.query, keep_blank_values=True)
        body = ("<!doctype html><meta charset='utf-8'><title>NCKH12 connected</title>"
                "<style>body{font-family:system-ui;margin:4rem;color:#14213d}</style>"
                "<h1>You can return to NCKH12.</h1><p>This window can be closed.</p>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


class ChatGPTAuthManager:
    """Connect, refresh, discover models, and disconnect one local account."""

    def __init__(self, store: CredentialStore | None = None,
                 client_factory: Callable[[], httpx.Client] | None = None):
        self.store = store or CredentialStore()
        self.client_factory = client_factory or (lambda: httpx.Client())
        self._refresh_lock = threading.Lock()

    def status(self) -> dict:
        profile = self.store.load()
        if not profile:
            return {"connected": False, "plan_usage_enabled": False, "selected_model": None}
        scopes = set(profile.get("scopes", []))
        return {
            "connected": True,
            "plan_usage_enabled": PLAN_USAGE_SCOPE in scopes,
            "selected_model": profile.get("selected_model"),
            "models": profile.get("models", []),
            "account_label": profile.get("account_label", "Connected account"),
        }

    def sign_in(self, timeout: int = 240,
                browser_open: Callable[[str], object] = webbrowser.open) -> dict:
        current = self.store.load()
        registration = self.store.registration()
        existing_client = ((current or {}).get("client_id")
                           or (registration or {}).get("client_id"))
        server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
        _CallbackHandler.query = None
        server.timeout = timeout
        attempt = create_authorization_attempt(
            self.store.host_id(), server.server_port,
            existing_client or "dynamic_agent_client",
        )
        browser_open(authorization_url(attempt))
        try:
            server.handle_request()
        finally:
            server.server_close()
        if _CallbackHandler.query is None:
            raise ChatGPTConnectionError("callback_timeout", "ChatGPT sign-in timed out.")
        callback = validate_callback(attempt, _CallbackHandler.query)
        with self.client_factory() as client:
            try:
                response = client.post(TOKEN_ENDPOINT, data={
                    "grant_type": "authorization_code",
                    "client_id": callback["client_id"],
                    "code": callback["code"],
                    "code_verifier": attempt.verifier,
                    "redirect_uri": attempt.redirect_uri,
                    "resource": RESOURCE,
                }, timeout=30)
                response.raise_for_status()
                token_data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ChatGPTConnectionError("token_exchange_failed",
                                             "ChatGPT sign-in could not be completed.") from exc
            id_token = token_data.get("id_token")
            if not isinstance(id_token, str):
                raise ChatGPTConnectionError("invalid_id_token",
                                             "ChatGPT did not return a verifiable identity.")
            claims = verify_id_token(id_token, callback["client_id"], attempt.nonce, client)
        scopes = str(token_data.get("scope", "")).split()
        saved_at = datetime.now(timezone.utc).isoformat()
        profile = {
            "issuer": claims["iss"],
            "subject": claims["sub"],
            "account_label": claims.get("email") or claims.get("name") or "Connected account",
            "client_id": callback["client_id"],
            "ext_agent_host_id": attempt.host_id,
            "id_token": id_token,
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "token_type": token_data.get("token_type", "Bearer"),
            "expires_at": time.time() + float(token_data.get("expires_in", 0)),
            "scopes": scopes,
            "saved_at": saved_at,
            "selected_model": current.get("selected_model") if current else None,
            "models": [],
        }
        if PLAN_USAGE_SCOPE in scopes and not isinstance(profile["access_token"], str):
            raise ChatGPTConnectionError("missing_access_token",
                                         "ChatGPT plan access was not returned.")
        self.store.save(profile)
        if PLAN_USAGE_SCOPE in scopes:
            self.discover_models()
        return self.status()

    def _refresh(self, profile: dict) -> dict:
        if not profile.get("refresh_token"):
            raise ChatGPTConnectionError("reauthorization_required",
                                         "Please connect ChatGPT again.")
        with self.client_factory() as client:
            try:
                response = client.post(TOKEN_ENDPOINT, data={
                    "grant_type": "refresh_token",
                    "client_id": profile["client_id"],
                    "refresh_token": profile["refresh_token"],
                    "resource": RESOURCE,
                }, timeout=30)
                response.raise_for_status()
                updated = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ChatGPTConnectionError("reauthorization_required",
                                             "Please connect ChatGPT again.") from exc
        profile.update({
            "access_token": updated.get("access_token"),
            "refresh_token": updated.get("refresh_token", profile.get("refresh_token")),
            "id_token": updated.get("id_token", profile.get("id_token")),
            "expires_at": time.time() + float(updated.get("expires_in", 0)),
            "scopes": str(updated.get("scope", " ".join(profile.get("scopes", [])))).split(),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        })
        if not isinstance(profile.get("access_token"), str):
            raise ChatGPTConnectionError("reauthorization_required",
                                         "Please connect ChatGPT again.")
        self.store.save(profile)
        return profile

    def access_profile(self) -> dict:
        with self._refresh_lock:
            profile = self.store.load()
            if not profile:
                raise ChatGPTConnectionError("not_connected", "ChatGPT is not connected.")
            if PLAN_USAGE_SCOPE not in set(profile.get("scopes", [])):
                raise ChatGPTConnectionError("plan_usage_not_authorized",
                                             "ChatGPT plan usage is not enabled.")
            if float(profile.get("expires_at", 0)) <= time.time() + 60:
                profile = self._refresh(profile)
            return profile

    def discover_models(self) -> list[dict]:
        profile = self.access_profile()
        with self.client_factory() as client:
            try:
                response = client.get(MODELS_ENDPOINT, headers={
                    "Authorization": f"Bearer {profile['access_token']}"
                }, timeout=30)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ChatGPTConnectionError("model_discovery_failed",
                                             "Available ChatGPT models could not be loaded.") from exc
        rows = payload.get("models", payload.get("data", []))
        models = [{"slug": row.get("slug", row.get("id")),
                   "display_name": row.get("display_name", row.get("id"))}
                  for row in rows if row.get("visibility", "list") == "list"
                  and isinstance(row.get("slug", row.get("id")), str)]
        if not models:
            raise ChatGPTConnectionError("no_available_models",
                                         "No eligible ChatGPT model is available for this account.")
        visible = {row["slug"] for row in models}
        if profile.get("selected_model") not in visible:
            profile["selected_model"] = models[0]["slug"]
        profile["models"] = models
        self.store.save(profile)
        return models

    def select_model(self, slug: str) -> None:
        profile = self.store.load()
        if not profile or slug not in {row.get("slug") for row in profile.get("models", [])}:
            raise ChatGPTConnectionError("invalid_model_selection",
                                         "Choose a model available to the connected account.")
        profile["selected_model"] = slug
        self.store.save(profile)

    def disconnect(self) -> bool:
        profile = self.store.load()
        remotely_revoked = False
        if profile and profile.get("refresh_token"):
            try:
                with self.client_factory() as client:
                    discovery = client.get(DISCOVERY_ENDPOINT, timeout=15).json()
                    endpoint = discovery.get("revocation_endpoint")
                    if endpoint:
                        response = client.post(endpoint, data={
                            "token": profile["refresh_token"],
                            "token_type_hint": "refresh_token",
                            "client_id": profile["client_id"],
                        }, timeout=15)
                        remotely_revoked = response.status_code == 200
            except (httpx.HTTPError, ValueError):
                remotely_revoked = False
        self.store.clear()
        return remotely_revoked
