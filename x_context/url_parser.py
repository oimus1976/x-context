"""Strict parsing for supported X/Twitter status URLs (FR-001)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

_SUPPORTED_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com"})
_STATUS_PATH_RE = re.compile(r"^/[^/]+/status/([0-9]+)$")


class InvalidStatusUrl(ValueError):
    """Raised when a URL does not match the accepted FR-001 status URL families."""


def extract_post_id(url: str) -> str:
    """Return the numeric post ID from a supported X/Twitter status URL.

    Parsing is local-only and performs no network access. Query strings and
    fragments are intentionally ignored for ID extraction.
    """

    if not isinstance(url, str) or not url:
        raise InvalidStatusUrl("status URL must be a non-empty string")

    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise InvalidStatusUrl("invalid status URL") from exc

    if parsed.scheme.lower() != "https":
        raise InvalidStatusUrl("unsupported URL scheme")

    if parsed.username is not None or parsed.password is not None:
        raise InvalidStatusUrl("userinfo is not allowed in status URLs")

    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidStatusUrl("invalid URL port") from exc

    if port is not None:
        raise InvalidStatusUrl("explicit ports are not supported")

    hostname = parsed.hostname.lower() if parsed.hostname else None
    if hostname not in _SUPPORTED_HOSTS:
        raise InvalidStatusUrl("unsupported X/Twitter host")

    match = _STATUS_PATH_RE.fullmatch(parsed.path)
    if match is None:
        raise InvalidStatusUrl("URL path must match /{user}/status/{numeric_id}")

    return match.group(1)
