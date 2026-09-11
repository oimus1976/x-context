"""Official X API single-Post lookup provider for FR-002."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .canonical import CanonicalEnvelope, CanonicalPost, make_read_envelope

OFFICIAL_X_API_ORIGIN = "https://api.x.com"
_SINGLE_POST_PATH = "/2/tweets/{post_id}"


@dataclass(frozen=True, slots=True)
class HttpRequest:
    """Small transport-neutral request contract used by the provider."""

    method: str
    url: str
    headers: Mapping[str, str]


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


class XApiError(RuntimeError):
    """Stable FR-002 provider failure without raw response or credential data."""

    def __init__(
        self,
        category: str,
        *,
        status_code: int | None = None,
        rate_limit: RateLimitMetadata | None = None,
    ) -> None:
        super().__init__(category)
        self.category = category
        self.status_code = status_code
        self.rate_limit = RateLimitMetadata() if rate_limit is None else rate_limit


Transport = Callable[[HttpRequest], HttpResponse]


def _is_provider_compatible_post_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 19
        and value.isascii()
        and value.isdigit()
    )


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
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _problem_slug(payload: dict[str, object] | None) -> str | None:
    if payload is None:
        return None
    problem_type = payload.get("type")
    if not isinstance(problem_type, str) or not problem_type:
        return None
    return problem_type.rstrip("/").rsplit("/", 1)[-1].lower()


def _raise_for_provider_failure(response: HttpResponse) -> None:
    payload = _json_object(response.body)
    slug = _problem_slug(payload)
    rate_limit = _rate_limit_metadata(response.headers)

    if response.status == 401:
        category = "authentication_failed"
    elif response.status == 403:
        category = "authorization_failed"
    elif response.status == 404:
        category = "resource_unavailable"
    elif response.status == 429 and slug == "rate-limit-exceeded":
        category = "rate_limited"
    elif slug == "usage-capped":
        category = "usage_blocked"
    else:
        category = "provider_error"

    raise XApiError(
        category,
        status_code=response.status,
        rate_limit=rate_limit,
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
    except URLError as exc:
        raise OSError("X API transport failed") from exc


def lookup_post(
    post_id: str,
    *,
    bearer_token: str | None,
    transport: Transport | None = None,
) -> CanonicalEnvelope:
    """Fetch one Post through the official X API and normalize id/text only."""

    if not _is_provider_compatible_post_id(post_id):
        raise XApiError("invalid_input")
    if not isinstance(bearer_token, str) or not bearer_token:
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
    except OSError as exc:
        raise XApiError("provider_error") from exc

    if not isinstance(provider_response, HttpResponse):
        raise XApiError("provider_error")
    if provider_response.status != 200:
        _raise_for_provider_failure(provider_response)

    payload = _json_object(provider_response.body)
    if payload is None:
        raise XApiError("provider_error", status_code=provider_response.status)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise XApiError("provider_error", status_code=provider_response.status)

    provider_id = data.get("id")
    text = data.get("text")
    if not isinstance(provider_id, str) or not _is_provider_compatible_post_id(provider_id):
        raise XApiError("provider_error", status_code=provider_response.status)
    if provider_id != post_id:
        raise XApiError("provider_error", status_code=provider_response.status)
    if not isinstance(text, str):
        raise XApiError("provider_error", status_code=provider_response.status)

    return make_read_envelope([CanonicalPost(id=provider_id, text=text)])
