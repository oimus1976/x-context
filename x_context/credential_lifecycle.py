"""Secure lifecycle for OAuth 2.0 user-context credentials."""

from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .oauth import OAuthHttpRequest, OAuthHttpResponse, OAuthTokenResult, TOKEN_ENDPOINT

REFRESH_ENDPOINT = TOKEN_ENDPOINT
REVOKE_ENDPOINT = "https://api.x.com/2/oauth2/revoke"
REFRESH_WINDOW_SECONDS = 300
_SCHEMA_VERSION = 1
_PROVIDER = "x"
_ALLOWED_SCOPES = frozenset(
    {"tweet.read", "users.read", "bookmark.read", "like.read", "offline.access"}
)


class CredentialError(RuntimeError):
    """Stable lifecycle failure without raw secret, OS, or provider prose."""

    def __init__(self, category: str, *, refresh_attempted: bool = False, revoke_attempted: bool = False) -> None:
        super().__init__(category)
        self.category = category
        self.refresh_attempted = refresh_attempted
        self.revoke_attempted = revoke_attempted


@dataclass(frozen=True, slots=True)
class CredentialRecord:
    """Version-1 normalized credential state. Secret fields are repr-hidden."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    token_type: str | None = None
    expires_at: int | None = None
    scopes: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not _safe_secret(self.access_token):
            raise CredentialError("credential_storage_error")
        if self.refresh_token is not None and not _safe_secret(self.refresh_token):
            raise CredentialError("credential_storage_error")
        if self.token_type is not None and not _safe_text(self.token_type):
            raise CredentialError("credential_storage_error")
        if self.expires_at is not None and (
            isinstance(self.expires_at, bool)
            or not isinstance(self.expires_at, int)
            or self.expires_at <= 0
        ):
            raise CredentialError("credential_storage_error")
        _validate_scope_tuple(self.scopes)


@dataclass(frozen=True, slots=True)
class CredentialResolution:
    """Resolved user credential plus safe lifecycle facts."""

    access_token: str = field(repr=False)
    source: str
    refresh_attempted: bool


class CredentialStore(Protocol):
    def load(self) -> CredentialRecord | None: ...
    def replace(self, record: CredentialRecord) -> None: ...
    def delete(self) -> None: ...


OAuthTransport = Callable[[OAuthHttpRequest], OAuthHttpResponse]
Clock = Callable[[], int | float]
Protector = Callable[[bytes], bytes]


def _safe_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\r" not in value and "\n" not in value


def _safe_secret(value: object) -> bool:
    return _safe_text(value)


def _safe_client_id(value: object) -> bool:
    return _safe_text(value) and value == value.strip()


def _validate_scope_tuple(scopes: tuple[str, ...] | None) -> None:
    if scopes is None:
        return
    if not isinstance(scopes, tuple) or not scopes or len(set(scopes)) != len(scopes):
        raise CredentialError("credential_storage_error")
    for scope in scopes:
        if not _safe_text(scope) or scope not in _ALLOWED_SCOPES:
            raise CredentialError("credential_storage_error")


def _clock_value(clock: Clock | None) -> int:
    active = time.time if clock is None else clock
    try:
        value = active()
    except Exception:
        raise CredentialError("configuration_error") from None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise CredentialError("configuration_error")
    return int(value)


def _load(store: CredentialStore) -> CredentialRecord | None:
    try:
        value = store.load()
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("credential_storage_error") from None
    if value is not None and not isinstance(value, CredentialRecord):
        raise CredentialError("credential_storage_error")
    return value


def _replace(store: CredentialStore, record: CredentialRecord) -> None:
    try:
        store.replace(record)
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("credential_storage_error") from None


def persist_oauth_result(
    result: OAuthTokenResult,
    *,
    store: CredentialStore,
    now: Clock | None = None,
) -> CredentialRecord:
    """Explicitly persist one normalized acquisition result."""

    if not isinstance(result, OAuthTokenResult):
        raise CredentialError("configuration_error")
    current = _clock_value(now)
    expires_at = None
    if result.expires_in is not None:
        if isinstance(result.expires_in, bool) or not isinstance(result.expires_in, int) or result.expires_in <= 0:
            raise CredentialError("credential_storage_error")
        expires_at = current + result.expires_in
    scopes = None if result.scopes is None else tuple(result.scopes)
    record = CredentialRecord(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_at=expires_at,
        scopes=scopes,
    )
    _replace(store, record)
    return record


def resolve_user_access_token(
    *,
    environ: Mapping[str, str],
    store: CredentialStore,
    client_id: str | None,
    transport: OAuthTransport | None = None,
    now: Clock | None = None,
) -> CredentialResolution:
    """Resolve an env override or lifecycle-managed credential for one operation."""

    if "X_CONTEXT_USER_ACCESS_TOKEN" in environ:
        token = environ.get("X_CONTEXT_USER_ACCESS_TOKEN")
        if not _safe_secret(token):
            raise CredentialError("configuration_error")
        return CredentialResolution(token, "environment", False)

    current = _load(store)
    if current is None:
        raise CredentialError("credential_missing")

    timestamp = _clock_value(now)
    if current.expires_at is None:
        return CredentialResolution(current.access_token, "persisted", False)

    due_for_refresh = current.expires_at <= timestamp + REFRESH_WINDOW_SECONDS
    if not due_for_refresh:
        return CredentialResolution(current.access_token, "persisted", False)

    if current.refresh_token is None:
        if current.expires_at > timestamp:
            return CredentialResolution(current.access_token, "persisted", False)
        raise CredentialError("credential_expired")

    refreshed = _refresh(current, client_id=client_id, transport=transport, now=timestamp)
    try:
        _replace(store, refreshed)
    except CredentialError:
        raise CredentialError("credential_storage_error", refresh_attempted=True) from None
    return CredentialResolution(refreshed.access_token, "persisted", True)


def _refresh(
    current: CredentialRecord,
    *,
    client_id: str | None,
    transport: OAuthTransport | None,
    now: int,
) -> CredentialRecord:
    if not _safe_client_id(client_id):
        raise CredentialError("configuration_error", refresh_attempted=False)
    assert current.refresh_token is not None
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token,
            "client_id": client_id,
        }
    ).encode("ascii")
    request = OAuthHttpRequest(
        method="POST",
        url=REFRESH_ENDPOINT,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
    )
    response = _perform(request, transport=transport, operation="refresh")
    if response.status != 200:
        raise CredentialError(_provider_category(response.status), refresh_attempted=True)
    payload = _json_object(response.body)
    if payload is None:
        raise CredentialError("provider_error", refresh_attempted=True)

    access_token = payload.get("access_token")
    if not _safe_secret(access_token):
        raise CredentialError("provider_error", refresh_attempted=True)

    returned_refresh = payload.get("refresh_token")
    if not _safe_secret(returned_refresh):
        raise CredentialError("provider_error", refresh_attempted=True)

    token_type = payload.get("token_type")
    if token_type is not None and not _safe_text(token_type):
        raise CredentialError("provider_error", refresh_attempted=True)

    expires_in = payload.get("expires_in")
    if expires_in is not None and (
        isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or expires_in <= 0
    ):
        raise CredentialError("provider_error", refresh_attempted=True)

    returned_scopes = _parse_scope_string(payload.get("scope"))
    if returned_scopes is not None:
        if current.scopes is None or set(returned_scopes) != set(current.scopes):
            raise CredentialError("provider_error", refresh_attempted=True)
        scopes = current.scopes
    else:
        scopes = current.scopes

    return CredentialRecord(
        access_token=access_token,
        refresh_token=returned_refresh,
        token_type=current.token_type if token_type is None else token_type,
        expires_at=None if expires_in is None else now + expires_in,
        scopes=scopes,
    )


def delete_local_credential(store: CredentialStore) -> None:
    """Idempotently delete lifecycle-managed local state only."""

    try:
        store.delete()
    except CredentialError:
        raise
    except Exception:
        raise CredentialError("credential_storage_error") from None


def revoke_persisted_credential(
    *,
    store: CredentialStore,
    client_id: str,
    transport: OAuthTransport | None = None,
) -> None:
    """Revoke one persisted provider token, then delete local state."""

    current = _load(store)
    if current is None:
        raise CredentialError("credential_missing")
    if not _safe_client_id(client_id):
        raise CredentialError("configuration_error")
    token = current.refresh_token if current.refresh_token is not None else current.access_token
    body = urlencode({"token": token, "client_id": client_id}).encode("ascii")
    request = OAuthHttpRequest(
        method="POST",
        url=REVOKE_ENDPOINT,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
    )
    response = _perform(request, transport=transport, operation="revoke")
    if response.status != 200:
        raise CredentialError(_provider_category(response.status), revoke_attempted=True)
    try:
        delete_local_credential(store)
    except CredentialError:
        raise CredentialError("credential_storage_error", revoke_attempted=True) from None


def _provider_category(status: int) -> str:
    if status == 401:
        return "authentication_failed"
    if status == 403:
        return "authorization_failed"
    return "provider_error"


def _json_object(body: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _parse_scope_string(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not _safe_text(value):
        raise CredentialError("provider_error", refresh_attempted=True)
    scopes = tuple(value.split())
    if not scopes or len(set(scopes)) != len(scopes) or any(scope not in _ALLOWED_SCOPES for scope in scopes):
        raise CredentialError("provider_error", refresh_attempted=True)
    return scopes


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_transport(request: OAuthHttpRequest) -> OAuthHttpResponse:
    urllib_request = Request(
        request.url,
        data=request.body,
        method=request.method,
        headers=dict(request.headers),
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(urllib_request, timeout=30) as response:
            return OAuthHttpResponse(
                status=response.getcode(),
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    except HTTPError as exc:
        return OAuthHttpResponse(
            status=exc.code,
            headers={} if exc.headers is None else dict(exc.headers.items()),
            body=exc.read(),
        )
    except (URLError, OSError):
        raise OSError("X OAuth lifecycle transport failed") from None


def _perform(
    request: OAuthHttpRequest,
    *,
    transport: OAuthTransport | None,
    operation: str,
) -> OAuthHttpResponse:
    active = _urllib_transport if transport is None else transport
    try:
        response = active(request)
    except Exception:
        if operation == "refresh":
            raise CredentialError("provider_error", refresh_attempted=True) from None
        raise CredentialError("provider_error", revoke_attempted=True) from None
    if not isinstance(response, OAuthHttpResponse):
        if operation == "refresh":
            raise CredentialError("provider_error", refresh_attempted=True)
        raise CredentialError("provider_error", revoke_attempted=True)
    return response


def _record_to_plaintext(record: CredentialRecord) -> bytes:
    value: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "provider": _PROVIDER,
        "access_token": record.access_token,
        "refresh_token": record.refresh_token,
        "token_type": record.token_type,
        "expires_at": record.expires_at,
        "scopes": None if record.scopes is None else list(record.scopes),
    }
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _record_from_plaintext(value: bytes) -> CredentialRecord:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialError("credential_storage_error") from None
    if not isinstance(payload, dict):
        raise CredentialError("credential_storage_error")
    expected_keys = {
        "schema_version", "provider", "access_token", "refresh_token", "token_type", "expires_at", "scopes"
    }
    if set(payload) != expected_keys:
        raise CredentialError("credential_storage_error")
    if payload.get("schema_version") != _SCHEMA_VERSION or payload.get("provider") != _PROVIDER:
        raise CredentialError("credential_storage_error")
    raw_scopes = payload.get("scopes")
    if raw_scopes is None:
        scopes = None
    elif isinstance(raw_scopes, list) and all(isinstance(item, str) for item in raw_scopes):
        scopes = tuple(raw_scopes)
    else:
        raise CredentialError("credential_storage_error")
    return CredentialRecord(
        access_token=payload.get("access_token"),
        refresh_token=payload.get("refresh_token"),
        token_type=payload.get("token_type"),
        expires_at=payload.get("expires_at"),
        scopes=scopes,
    )


class DPAPIFileCredentialStore:
    """One DPAPI-protected versioned envelope with atomic file replacement."""

    concurrency_contract = "single-process-single-writer"

    def __init__(
        self,
        *,
        path: str | os.PathLike[str] | Path,
        protect: Protector | None = None,
        unprotect: Protector | None = None,
    ) -> None:
        self.path = Path(path)
        self._protect = _dpapi_protect if protect is None else protect
        self._unprotect = _dpapi_unprotect if unprotect is None else unprotect

    def load(self) -> CredentialRecord | None:
        if not self.path.exists():
            return None
        try:
            protected = self.path.read_bytes()
            if not protected:
                raise CredentialError("credential_storage_error")
            plaintext = self._unprotect(protected)
            if not isinstance(plaintext, bytes) or not plaintext:
                raise CredentialError("credential_storage_error")
            return _record_from_plaintext(plaintext)
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("credential_storage_error") from None

    def replace(self, record: CredentialRecord) -> None:
        if not isinstance(record, CredentialRecord):
            raise CredentialError("credential_storage_error")
        temp_path: Path | None = None
        try:
            plaintext = _record_to_plaintext(record)
            protected = self._protect(plaintext)
            if not isinstance(protected, bytes) or not protected:
                raise CredentialError("credential_storage_error")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(protected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
            temp_path = None
        except CredentialError:
            raise
        except Exception:
            raise CredentialError("credential_storage_error") from None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def delete(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError:
            raise CredentialError("credential_storage_error") from None


def default_credential_store(environ: Mapping[str, str] | None = None) -> CredentialStore | None:
    """Return the concrete Windows store, or None when unsupported/unconfigured."""

    if os.name != "nt":
        return None
    selected = os.environ if environ is None else environ
    root = selected.get("LOCALAPPDATA")
    if not isinstance(root, str) or not root:
        raise CredentialError("configuration_error")
    return DPAPIFileCredentialStore(path=Path(root) / "x-context" / "credential-v1.dpapi")


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    blob = _DATA_BLOB(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _dpapi_protect(value: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("credential_storage_error")
    in_blob, keepalive = _blob_from_bytes(value)
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    _ = keepalive
    if not ok:
        raise CredentialError("credential_storage_error")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(value: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialError("credential_storage_error")
    in_blob, keepalive = _blob_from_bytes(value)
    out_blob = _DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(out_blob),
    )
    _ = keepalive
    if not ok:
        raise CredentialError("credential_storage_error")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)