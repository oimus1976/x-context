"""Canonical JSON model for successful x-context reads (FR-005 slice)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .x_api import AuthenticatedSubject

SCHEMA_VERSION = "1"
SOURCE = "x"


def _require_ascii_numeric_post_id(value: str) -> None:
    if not isinstance(value, str) or not value or not value.isascii() or not value.isdigit():
        raise ValueError("post id must be a non-empty ASCII numeric string")


def _format_rfc3339_utc(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise TypeError("retrieved_at must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class CanonicalPost:
    """Minimum canonical post representation for the first `read` slice.

    Optional expansion-backed fields are intentionally not represented yet.
    Their absence means unrequested/unresolved/not represented, not known-empty.
    """

    id: str = field(repr=False)
    text: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_ascii_numeric_post_id(self.id)
        if not isinstance(self.text, str):
            raise TypeError("post text must be a string")

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "text": self.text}


@dataclass(frozen=True, slots=True)
class Page:
    """Canonical page metadata shared with later collection slices."""

    next_token: str | None = field(default=None, repr=False)
    complete: bool = True

    def __post_init__(self) -> None:
        if self.next_token is not None:
            if not isinstance(self.next_token, str) or not self.next_token:
                raise ValueError("next_token must be null or a non-empty string")
            if self.complete:
                raise ValueError("page.complete cannot be true when next_token is present")
        if not isinstance(self.complete, bool):
            raise TypeError("page.complete must be a bool")

    def to_dict(self) -> dict[str, object]:
        return {"next_token": self.next_token, "complete": self.complete}


@dataclass(frozen=True, slots=True)
class CanonicalEnvelope:
    """Successful read or authenticated bookmarks envelope."""

    operation: str
    retrieved_at: datetime
    subject: AuthenticatedSubject | None
    items: tuple[CanonicalPost, ...] = field(repr=False)
    page: Page
    schema_version: str = field(default=SCHEMA_VERSION, init=False)
    source: str = field(default=SOURCE, init=False)

    def __post_init__(self) -> None:
        from .x_api import AuthenticatedSubject

        if self.operation == "read":
            if self.subject is not None:
                raise ValueError("read envelopes must use subject = null")
            if self.page.next_token is not None or not self.page.complete:
                raise ValueError("read envelopes must use a complete page with no next_token")
        elif self.operation == "bookmarks":
            if not isinstance(self.subject, AuthenticatedSubject):
                raise ValueError("bookmarks require an authenticated subject")
        else:
            raise ValueError("unsupported operation")
        if not isinstance(self.items, tuple) or not all(
            isinstance(item, CanonicalPost) for item in self.items
        ):
            raise TypeError("items must be a tuple of CanonicalPost values")
        if not isinstance(self.retrieved_at, datetime):
            raise TypeError("retrieved_at must be a datetime")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "operation": self.operation,
            "retrieved_at": _format_rfc3339_utc(self.retrieved_at),
            "subject": None if self.subject is None else {
                "id": self.subject.id,
                **({"username": self.subject.username} if self.subject.username is not None else {}),
            },
            "items": [item.to_dict() for item in self.items],
            "page": self.page.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))


def make_read_envelope(
    items: Iterable[CanonicalPost], *, retrieved_at: datetime | None = None
) -> CanonicalEnvelope:
    """Build a canonical successful envelope for an arbitrary-post read."""

    acquired_at = datetime.now(timezone.utc) if retrieved_at is None else retrieved_at
    return CanonicalEnvelope(
        operation="read",
        retrieved_at=acquired_at,
        subject=None,
        items=tuple(items),
        page=Page(next_token=None, complete=True),
    )
