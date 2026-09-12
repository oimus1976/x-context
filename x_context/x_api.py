"""Official X API provider boundaries for read and authenticated subject resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .canonical import CanonicalEnvelope, CanonicalPost, make_read_envelope

OFFICIAL_X_API_ORIGIN = "https://api.x.com"
_SINGLE_POST_PATH = "/2/tweets/{post_id}"
_AUTHENTICATED_USER_PATH = "/2/users/me"


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """Small transport-neutral request contract used by the provider."""

    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Small transport-neutral response contract used by the provider."""

    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class RateLimitMetadata:
    """Allow-listed, non-secret X rate-limit metadata."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None


@dataclass(frozen=True, slots=True)
class PostLookupResult:
    """Canonical success plus non-canonical safe diagnostics for FR-006."""

    envelope: CanonicalEnvelope
    rate_limit: RateLimitMetadata
    requests_attempted: int


@dataclass(frozen=True, slots=True)
class AuthenticatedSubject:
    """Minimum authenticated X identity needed to bind collection reads."""

    id: str
    username: str | None = None

    def __post_init__(self) -> None:
        if not _is_ascii_numeric_user_id(self.id):
            raise ValueError("subject id must be a non-empty ASCII numeric string")
        if self.username is not None and (
            not isinstance(self.username, str) or not self.username
        ):
            raise ValueError("subject username must be null or a non-empty string")


@dataclass(frozen=True, slots=True)
class SubjectResolutionResult:
    """Authenticated subject plus non-canonical safe diagnostics."""

    subject: AuthenticatedSubject
    rate_limit: RateLimitMetadata
    requests_attempted: int


class XApiError(RuntimeError):
    """Stable provider failure without raw response or credential data."""

    def __init__(
        self,
        category: str,
        *,
        status_code: int | None = None,
        rate_limit: RateLimitMetadata | None = None,
        requests_attempted: int = 0,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.status_code = status_code
        self.rate_limit = RateLimitMetadata() if rate_limit is None else rate_limit
        self.requests_attempted = requests_attempted


Transport = Callable[[HttpRequest], HttpResponse]


def _is_provider_compatible_post_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 19
        and value.isascii()
        and value.isdigit()
    )


def _is_ascii_numeric_user_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value.isascii()
        and value.isdigit()
    )


def _is_safe_bearer_token(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\r" not in value and "\n" not in value


def _header(headers: Mapping[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == target and isinstance(value, str):
            return value
    return None


def _safe_int_header(headers: Mapping[str, str], name: str) -> int | None:
    value = _header(headers, name)
    if value is None or not value.isascii() or not value.isdigit():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _rate_limit_metadata(headers: Mapping[str, str]) -> RateLimitMetadata:
    return RateLimitMetadata(
        limit=_safe_int_header(headers, "x-rate-limit-limit"),
        remaining=_safe_int_header(headers, "x-rate-limit-remaining"),
        reset=_safe_int_header(headers, "x-rate-limit-reset"),
    )


def _json_object(body: bytes) -> dict[str, object] | None:
    try:
        decoded = body.decode("utf-8")
        value = json.loads(decoded)
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _problem_slug(payload: dict[str, object] | None) -> str | None:
    if payload is None:
        return None
    problem_type = payload.get("type")
    if not isinstance(problem_type, str) or not problem_type:
        return None
    return problem_type.rstrip("/").rsplit("/", 1)[-1].lower()


def _provider_failure_category(response: HttpResponse, *, allow_resource_unavailable: bool) -> str:
    payload = _json_object(response.body)
    slug = _problem_slug(payload)

    if response.status == 401:
        return "authentication_failed"
    if response.status == 403:
        return "authorization_failed"
    if allow_resource_unavailable and response.status == 404:
        return "resource_unavailable"
    if response.status == 429 and slug == "rate-limit-exceeded":
        return "rate_limited"
    if slug == "usage-capped":
        return "usage_blocked"
    return "provider_error"


def _raise_for_provider_failure(response: HttpResponse) -> None:
    raise XApiError(
        _provider_failure_category(response, allow_resource_unavailable=True),
        status_code=response.status,
        rate_limit=_rate_limit_metadata(response.headers),
        requests_attempted=1,
    )


def _raise_for_authenticated_user_failure(response: HttpResponse) -> None:
    raise XApiError(
        _provider_failure_category(response, allow_resource_unavailable=False),
        status_code=response.status,
        rate_limit=_rate_limit_metadata(response.headers),
        requests_attempted=1,
    )


def _urllib_transport(request: HttpRequest) -> HttpResponse:
    urllib_request = Request(
        request.url,
        method=request.method,
        headers=dict(request.headers),
    )
    try:
        with urlopen(urllib_request, timeout=30) as provider_response:
            return HttpResponse(
                status=provider_response.getcode(),
                headers=dict(provider_response.headers.items()),
                body=provider_response.read(),
            )
    except HTTPError as exc:
        return HttpResponse(
            status=exc.code,
            headers={} if exc.headers is None else dict(exc.headers.items()),
            body=exc.read(),
        )
    except URLError:
        raise OSError("X API transport failed") from None


def lookup_post_with_diagnostics(
    post_id: str,
    *,
    bearer_token: str | None,
    transport: Transport | None = None,
) -> PostLookupResult:
    """Fetch one Post and retain only allow-listed success diagnostics."""

    if not _is_provider_compatible_post_id(post_id):
        raise XApiError("invalid_input")
    if not _is_safe_bearer_token(bearer_token):
        raise XApiError("configuration_error")

    request = HttpRequest(
        method="GET",
        url=f"{OFFICIAL_X_API_ORIGIN}{_SINGLE_POST_PATH.format(post_id=post_id)}",
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        },
    )

    selected_transport = _urllib_transport if transport is None else transport
    try:
        provider_response = selected_transport(request)
    except Exception:
        raise XApiError("provider_error", requests_attempted=1) from None

    if not isinstance(provider_response, HttpResponse):
        raise XApiError("provider_error", requests_attempted=1)
    if provider_response.status != 200:
        _raise_for_provider_failure(provider_response)

    payload = _json_object(provider_response.body)
    if payload is None:
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    provider_id = data.get("id")
    text = data.get("text")
    if not isinstance(provider_id, str) or not _is_provider_compatible_post_id(provider_id):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )
    if provider_id != post_id:
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )
    if not isinstance(text, str):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    envelope = make_read_envelope([CanonicalPost(id=provider_id, text=text)])
    return PostLookupResult(
        envelope=envelope,
        rate_limit=_rate_limit_metadata(provider_response.headers),
        requests_attempted=1,
    )


def lookup_post(
    post_id: str,
    *,
    bearer_token: str | None,
    transport: Transport | None = None,
) -> CanonicalEnvelope:
    """Fetch one Post through the official X API and normalize id/text only."""

    return lookup_post_with_diagnostics(
        post_id,
        bearer_token=bearer_token,
        transport=transport,
    ).envelope


def resolve_authenticated_subject(
    *,
    user_access_token: str | None,
    transport: Transport | None = None,
) -> SubjectResolutionResult:
    """Resolve the current user through the official authenticated-user endpoint."""

    if not _is_safe_bearer_token(user_access_token):
        raise XApiError("configuration_error")

    request = HttpRequest(
        method="GET",
        url=f"{OFFICIAL_X_API_ORIGIN}{_AUTHENTICATED_USER_PATH}",
        headers={
            "Authorization": f"Bearer {user_access_token}",
            "Accept": "application/json",
        },
    )

    selected_transport = _urllib_transport if transport is None else transport
    try:
        provider_response = selected_transport(request)
    except Exception:
        raise XApiError("provider_error", requests_attempted=1) from None

    if not isinstance(provider_response, HttpResponse):
        raise XApiError("provider_error", requests_attempted=1)
    if provider_response.status != 200:
        _raise_for_authenticated_user_failure(provider_response)

    payload = _json_object(provider_response.body)
    if payload is None:
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    subject_id = data.get("id")
    username = data.get("username")
    if not _is_ascii_numeric_user_id(subject_id):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )
    if username is not None and (not isinstance(username, str) or not username):
        raise XApiError(
            "provider_error",
            status_code=provider_response.status,
            requests_attempted=1,
        )

    return SubjectResolutionResult(
        subject=AuthenticatedSubject(id=subject_id, username=username),
        rate_limit=_rate_limit_metadata(provider_response.headers),
        requests_attempted=1,
    )


def bind_collection_subject(subject: AuthenticatedSubject, target_user_id: str) -> str:
    """Fail closed unless a future collection target equals the authenticated subject."""

    if not isinstance(subject, AuthenticatedSubject):
        raise XApiError("invalid_input")
    if not _is_ascii_numeric_user_id(target_user_id):
        raise XApiError("invalid_input")
    if target_user_id != subject.id:
        raise XApiError("subject_mismatch")
    return target_user_id
