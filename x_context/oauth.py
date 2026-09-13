"""Official X OAuth 2.0 Authorization Code + PKCE acquisition boundary."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser

AUTHORIZE_ENDPOINT = "https://x.com/i/oauth2/authorize"
TOKEN_ENDPOINT = "https://api.x.com/2/oauth2/token"
_READ_SCOPES = ("tweet.read", "users.read", "bookmark.read", "like.read")


class OAuthError(RuntimeError):
    """Stable OAuth failure with no raw secret/provider text."""

    def __init__(
        self,
        category: str,
        *,
        status_code: int | None = None,
        browser_launch_attempted: bool = False,
        callback_received: bool = False,
        token_exchange_attempted: bool = False,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.status_code = status_code
        self.browser_launch_attempted = browser_launch_attempted
        self.callback_received = callback_received
        self.token_exchange_attempted = token_exchange_attempted


@dataclass(frozen=True, slots=True)
class OAuthConfig:
    """Non-secret configuration for a fixed registered native-app callback."""

    client_id: str
    redirect_uri: str

    def __post_init__(self) -> None:
        if not _safe_text(self.client_id) or self.client_id != self.client_id.strip():
            raise OAuthError("configuration_error")
        _validate_redirect_uri(self.redirect_uri)


@dataclass(slots=True)
class OAuthAuthorizationAttempt:
    """One bounded authorization ceremony; verifier/state are secret."""

    authorization_url: str = field(repr=False)
    scopes: tuple[str, ...]
    refresh_capable: bool
    state: str = field(repr=False)
    code_verifier: str = field(repr=False)
    code_challenge: str = field(repr=False)
    _complete: bool = field(default=False, init=False, repr=False)


@dataclass(frozen=True, slots=True)
class OAuthTokenResult:
    """Secret-bearing in-memory token result with credential-safe repr."""

    access_token: str = field(repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    token_type: str | None = None
    expires_in: int | None = None
    scopes: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class OAuthHttpRequest:
    """Transport-neutral OAuth request; URL/headers/body are hidden from repr."""

    method: str
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class OAuthHttpResponse:
    """Transport-neutral OAuth response; provider content is hidden from repr."""

    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


OAuthTransport = Callable[[OAuthHttpRequest], OAuthHttpResponse]
BrowserLauncher = Callable[[str], bool]


class CallbackListener(Protocol):
    def __enter__(self) -> "CallbackListener": ...

    def wait_for_callback(self, timeout: float) -> str: ...

    def __exit__(self, exc_type, exc, tb) -> bool | None: ...


ListenerFactory = Callable[[OAuthAuthorizationAttempt], CallbackListener]


def _safe_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and "\r" not in value
        and "\n" not in value
    )


def _validate_redirect_uri(redirect_uri: object) -> None:
    if not _safe_text(redirect_uri):
        raise OAuthError("configuration_error")
    try:
        parsed = urlparse(redirect_uri)
        port = parsed.port
    except ValueError:
        raise OAuthError("configuration_error") from None
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not (1 <= port <= 65535)
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path
        or parsed.path == "/"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise OAuthError("configuration_error")


def _make_code_verifier() -> str:
    # token_urlsafe(64) produces an RFC 7636-compatible URL-safe verifier
    # comfortably inside the 43..128 character range.
    verifier = secrets.token_urlsafe(64)
    if not (43 <= len(verifier) <= 128) or not verifier.isascii():
        raise OAuthError("configuration_error")
    return verifier


def _make_state() -> str:
    state = secrets.token_urlsafe(32)
    if not state or not state.isascii():
        raise OAuthError("configuration_error")
    return state


def _s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def build_authorization_attempt(
    config: OAuthConfig,
    *,
    refresh_capable: bool = False,
) -> OAuthAuthorizationAttempt:
    """Construct one fresh official-X authorization request."""

    verifier = _make_code_verifier()
    state = _make_state()
    challenge = _s256(verifier)
    scopes = _READ_SCOPES + (("offline.access",) if refresh_capable else ())
    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return OAuthAuthorizationAttempt(
        authorization_url=f"{AUTHORIZE_ENDPOINT}?{query}",
        scopes=scopes,
        refresh_capable=refresh_capable,
        state=state,
        code_verifier=verifier,
        code_challenge=challenge,
    )


def _json_object(body: bytes) -> dict[str, object] | None:
    try:
        value = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _provider_failure(response: OAuthHttpResponse) -> OAuthError:
    if response.status == 401:
        category = "authentication_failed"
    elif response.status == 403:
        category = "authorization_failed"
    else:
        category = "provider_error"
    return OAuthError(
        category,
        status_code=response.status,
        callback_received=True,
        token_exchange_attempted=True,
    )


def _parse_granted_scopes(value: object, expected: tuple[str, ...]) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)
    scopes = tuple(value.split())
    if not scopes or len(set(scopes)) != len(scopes) or set(scopes) != set(expected):
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)
    return scopes


def _normalize_token_result(
    response: OAuthHttpResponse,
    attempt: OAuthAuthorizationAttempt,
) -> OAuthTokenResult:
    payload = _json_object(response.body)
    if payload is None:
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)

    access_token = payload.get("access_token")
    if not _safe_text(access_token):
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)

    refresh_token = payload.get("refresh_token")
    if refresh_token is not None and not _safe_text(refresh_token):
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)
    if refresh_token is not None and not attempt.refresh_capable:
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)

    token_type = payload.get("token_type")
    if token_type is not None and not _safe_text(token_type):
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)

    expires_in = payload.get("expires_in")
    if expires_in is not None and (
        isinstance(expires_in, bool)
        or not isinstance(expires_in, int)
        or expires_in <= 0
    ):
        raise OAuthError("provider_error", callback_received=True, token_exchange_attempted=True)

    scopes = _parse_granted_scopes(payload.get("scope"), attempt.scopes)

    return OAuthTokenResult(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        expires_in=expires_in,
        scopes=scopes,
    )


def _validate_callback(
    config: OAuthConfig,
    attempt: OAuthAuthorizationAttempt,
    callback_url: object,
) -> str:
    if not _safe_text(callback_url):
        raise OAuthError("oauth_callback_invalid", callback_received=True)

    expected = urlparse(config.redirect_uri)
    try:
        actual = urlparse(callback_url)
        actual_port = actual.port
    except ValueError:
        raise OAuthError("oauth_callback_invalid", callback_received=True) from None

    if (
        actual.scheme != expected.scheme
        or actual.hostname != expected.hostname
        or actual_port != expected.port
        or actual.path != expected.path
        or actual.params
        or actual.fragment
    ):
        raise OAuthError("oauth_callback_invalid", callback_received=True)

    query = parse_qs(actual.query, keep_blank_values=True)
    states = query.get("state", [])
    if len(states) != 1 or states[0] != attempt.state:
        raise OAuthError("oauth_state_mismatch", callback_received=True)

    errors = query.get("error", [])
    if errors:
        if len(errors) == 1 and errors[0] == "access_denied":
            raise OAuthError("authorization_failed", callback_received=True)
        raise OAuthError("provider_error", callback_received=True)

    codes = query.get("code", [])
    if len(codes) != 1 or not _safe_text(codes[0]):
        raise OAuthError("oauth_callback_invalid", callback_received=True)
    return codes[0]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _urllib_oauth_transport(request: OAuthHttpRequest) -> OAuthHttpResponse:
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
        raise OSError("X OAuth transport failed") from None


def exchange_callback(
    config: OAuthConfig,
    attempt: OAuthAuthorizationAttempt,
    callback_url: str,
    *,
    transport: OAuthTransport | None = None,
) -> OAuthTokenResult:
    """Validate one callback and perform at most one official token exchange."""

    if attempt._complete:
        raise OAuthError("oauth_attempt_complete", callback_received=True)

    code = _validate_callback(config, attempt, callback_url)
    # A validated authorization callback is terminal for this attempt even if
    # the one permitted exchange later fails.
    attempt._complete = True

    body = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
            "code_verifier": attempt.code_verifier,
        }
    ).encode("ascii")
    request = OAuthHttpRequest(
        method="POST",
        url=TOKEN_ENDPOINT,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body=body,
    )

    active_transport = _urllib_oauth_transport if transport is None else transport
    try:
        response = active_transport(request)
    except Exception:
        raise OAuthError(
            "provider_error",
            callback_received=True,
            token_exchange_attempted=True,
        ) from None

    if response.status != 200:
        raise _provider_failure(response)
    return _normalize_token_result(response, attempt)


class _CallbackHTTPServer(HTTPServer):
    callback_target: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    server: _CallbackHTTPServer

    def do_GET(self) -> None:
        if self.server.callback_target is None:
            self.server.callback_target = self.path
        body = b"Authorization response received. You may close this window."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        # BaseHTTPRequestHandler otherwise logs the full request target/query.
        return


class LoopbackCallbackListener:
    """One-shot fixed-port IPv4 loopback callback listener."""

    def __init__(self, redirect_uri: str) -> None:
        _validate_redirect_uri(redirect_uri)
        parsed = urlparse(redirect_uri)
        self._redirect_uri = redirect_uri
        self._origin = f"http://127.0.0.1:{parsed.port}"
        self._server: _CallbackHTTPServer | None = None
        self._port = parsed.port

    def __enter__(self) -> "LoopbackCallbackListener":
        assert self._port is not None
        self._server = _CallbackHTTPServer(("127.0.0.1", self._port), _CallbackHandler)
        return self

    def wait_for_callback(self, timeout: float) -> str:
        if self._server is None:
            raise RuntimeError("listener is not active")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise OAuthError("configuration_error")
        self._server.timeout = float(timeout)
        self._server.handle_request()
        target = self._server.callback_target
        if target is None:
            raise TimeoutError("OAuth callback timed out")
        return f"{self._origin}{target}"

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._server is not None:
            self._server.server_close()
            self._server = None
        return False


def _system_browser_launcher(url: str) -> bool:
    return bool(webbrowser.open(url, new=1, autoraise=True))


def acquire_user_token(
    config: OAuthConfig,
    *,
    refresh_capable: bool = False,
    browser_launcher: BrowserLauncher | None = None,
    listener_factory: ListenerFactory | None = None,
    transport: OAuthTransport | None = None,
    timeout: float = 120.0,
) -> OAuthTokenResult:
    """Run one bounded native authorization ceremony without persistence."""

    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise OAuthError("configuration_error")

    attempt = build_authorization_attempt(config, refresh_capable=refresh_capable)
    browser = _system_browser_launcher if browser_launcher is None else browser_launcher
    factory = (
        (lambda current: LoopbackCallbackListener(config.redirect_uri))
        if listener_factory is None
        else listener_factory
    )

    try:
        listener = factory(attempt)
        with listener:
            try:
                launched = browser(attempt.authorization_url)
            except Exception:
                raise OAuthError(
                    "browser_launch_failed",
                    browser_launch_attempted=True,
                ) from None
            if not launched:
                raise OAuthError(
                    "browser_launch_failed",
                    browser_launch_attempted=True,
                )
            try:
                callback_url = listener.wait_for_callback(timeout)
            except TimeoutError:
                raise OAuthError(
                    "oauth_callback_timeout",
                    browser_launch_attempted=True,
                ) from None
            except OAuthError:
                raise
            except Exception:
                raise OAuthError(
                    "callback_listener_failed",
                    browser_launch_attempted=True,
                ) from None
    except OAuthError:
        raise
    except Exception:
        raise OAuthError("callback_listener_failed") from None

    return exchange_callback(
        config,
        attempt,
        callback_url,
        transport=transport,
    )
