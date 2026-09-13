"""Official X API provider boundaries for read and authenticated subject resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.parse import urlencode

from .canonical import CanonicalEnvelope, CanonicalPost, Page, make_read_envelope

OFFICIAL_X_API_ORIGIN = "https://api.x.com"
_SINGLE_POST_PATH = "/2/tweets/{post_id}"
_AUTHENTICATED_USER_PATH = "/2/users/me"


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """Small transport-neutral request contract used by the provider."""

    method: str
    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Small transport-neutral response contract used by the provider."""

    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


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

    errors = payload.get("errors")
    if errors not in (None, []):
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


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _bookmarks_transport(request: HttpRequest) -> HttpResponse:
    """No redirects/retries: each call is one attempt at the authorized endpoint."""
    req = Request(request.url, method=request.method, headers=dict(request.headers))
    try:
        with build_opener(_NoRedirect()).open(req, timeout=30) as reply:
            return HttpResponse(reply.getcode(), dict(reply.headers.items()), reply.read())
    except HTTPError as exc:
        return HttpResponse(exc.code, {} if exc.headers is None else dict(exc.headers.items()), exc.read())


@dataclass(frozen=True, slots=True)
class CollectionLookupResult:
    envelope: CanonicalEnvelope = field(repr=False)
    subject_rate_limit: RateLimitMetadata
    rate_limit: RateLimitMetadata
    requests_attempted: int
    requested_page_size: int


@dataclass(frozen=True, slots=True)
class BookmarksLookupResult(CollectionLookupResult):
    """Bookmark canonical output and safe per-endpoint diagnostics."""


@dataclass(frozen=True, slots=True)
class LikesLookupResult(CollectionLookupResult):
    """Liked-post canonical output and safe per-endpoint diagnostics."""


def lookup_bookmarks(
    *, user_access_token: str | None, max_results: int = 25,
    page_token: str | None = None, transport: Transport | None = None,
) -> BookmarksLookupResult:
    """Resolve the user, bind the target, and fetch exactly one bookmark page."""
    return _lookup_collection("bookmarks", user_access_token=user_access_token,
                              max_results=max_results, page_token=page_token, transport=transport)


def lookup_likes(
    *, user_access_token: str | None, max_results: int = 25,
    page_token: str | None = None, transport: Transport | None = None,
) -> LikesLookupResult:
    """Resolve the user, bind the target, and fetch exactly one liked-post page."""
    return _lookup_collection("likes", user_access_token=user_access_token,
                              max_results=max_results, page_token=page_token, transport=transport)


def _lookup_collection(
    operation: str, *, user_access_token: str | None, max_results: int,
    page_token: str | None, transport: Transport | None,
) -> BookmarksLookupResult | LikesLookupResult:
    # Closed operation mapping: callers cannot supply an endpoint or target user.
    if operation == "bookmarks":
        collection_path, result_type = "bookmarks", BookmarksLookupResult
    elif operation == "likes":
        collection_path, result_type = "liked_tweets", LikesLookupResult
    else:
        raise XApiError("invalid_input")
    if type(max_results) is not int or not 1 <= max_results <= 100:
        raise XApiError("invalid_input")
    if page_token is not None and (
        not isinstance(page_token, str) or not page_token or any(ord(c) < 32 or ord(c) == 127 for c in page_token)
    ):
        raise XApiError("invalid_input")
    selected_transport = _bookmarks_transport if transport is None else transport
    subject_rate = RateLimitMetadata()
    subject_attempts = 0

    def subject_transport(request: HttpRequest) -> HttpResponse:
        nonlocal subject_rate, subject_attempts
        subject_attempts += 1
        reply = selected_transport(request)
        if isinstance(reply, HttpResponse):
            subject_rate = _rate_limit_metadata(reply.headers)
        return reply

    try:
        resolution = resolve_authenticated_subject(user_access_token=user_access_token, transport=subject_transport)
    except XApiError as exc:
        exc.rate_limit = subject_rate
        raise
    except Exception:
        raise XApiError("provider_error", rate_limit=subject_rate, requests_attempted=subject_attempts) from None
    try:
        target = bind_collection_subject(resolution.subject, resolution.subject.id)
    except XApiError as exc:
        exc.requests_attempted += resolution.requests_attempted
        exc.subject_rate_limit = resolution.rate_limit
        raise
    query = {"max_results": max_results}
    if page_token is not None:
        query["pagination_token"] = page_token
    attempted = resolution.requests_attempted + 1
    rate = RateLimitMetadata()
    try:
        request = HttpRequest("GET", f"{OFFICIAL_X_API_ORIGIN}/2/users/{target}/{collection_path}?{urlencode(query)}",
                              {"Authorization": f"Bearer {user_access_token}", "Accept": "application/json"})
        try:
            reply = selected_transport(request)
        except Exception:
            raise XApiError("provider_error") from None
        if not isinstance(reply, HttpResponse):
            raise XApiError("provider_error")
        rate = _rate_limit_metadata(reply.headers)
        if reply.status != 200:
            raise XApiError(_provider_failure_category(reply, allow_resource_unavailable=False), status_code=reply.status)
        payload = _json_object(reply.body)
        if payload is None or payload.get("errors") not in (None, []):
            raise XApiError("provider_error")
        meta = payload.get("meta", {})
        if not isinstance(meta, dict):
            raise XApiError("provider_error")
        data = payload.get("data", [] if type(meta.get("result_count")) is int and meta["result_count"] == 0 else None)
        if not isinstance(data, list) or len(data) > max_results:
            raise XApiError("provider_error")
        if "result_count" in meta and (type(meta["result_count"]) is not int or meta["result_count"] != len(data)):
            raise XApiError("provider_error")
        next_token = meta.get("next_token")
        if next_token is not None and (not isinstance(next_token, str) or not next_token):
            raise XApiError("provider_error")
        items = []
        for post in data:
            if not isinstance(post, dict) or not _is_provider_compatible_post_id(post.get("id")) or not isinstance(post.get("text"), str):
                raise XApiError("provider_error")
            items.append(CanonicalPost(post["id"], post["text"]))
        envelope = CanonicalEnvelope(operation, datetime.now(timezone.utc), resolution.subject,
                                     tuple(items), Page(next_token, next_token is None))
    except Exception as exc:
        # Reconstruct only safe fields, suppressing arbitrary transport/decoder text.
        failure = XApiError(exc.category if isinstance(exc, XApiError) else "provider_error",
                            status_code=exc.status_code if isinstance(exc, XApiError) else None,
                            rate_limit=rate, requests_attempted=attempted)
        failure.subject_rate_limit = resolution.rate_limit
        raise failure from None
    return result_type(envelope, resolution.rate_limit, rate, attempted, max_results)
