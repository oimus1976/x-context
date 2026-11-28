"""Issue #77 stage 3 (SPEC-0009): one saved thread reference page.

Selects one URL already saved in ``bookmark-threads-v1.json`` and stores the
bounded ``page_capture.capture_one`` result in a separate subject-bound sidecar
``bookmark-thread-pages-v1.json``. No X request, no arbitrary URL input, no
crawler. Fetching is reused from page_capture; this module only selects,
validates and persists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from . import page_capture
from .bookmark_enrichment import _unique as unique_json
from .bookmark_store import StoreSnapshot, _timestamp
from .bookmark_threads import ThreadSnapshot

STORE_NAME = "bookmark-thread-pages-v1.json"
MAX_URL_INDEX = 49  # bookmark_threads._valid_urls allows at most 50 URLs per Post
_RECORD_KEYS = frozenset({
    "bookmark_post_id", "source_post_id", "url_index", "requested_url", "final_url",
    "http_status", "retrieved_at", "state", "title", "description", "excerpt",
    "excerpt_truncated",
})


@dataclass(frozen=True, slots=True)
class ThreadPageSnapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


def _is_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 19 and value.isascii() and value.isdigit()


def url_source(link: dict) -> str | None:
    # Same preference order as page_capture.select_url / combined_context.
    for key in ("unwound_url", "expanded_url", "url"):
        if isinstance(link.get(key), str) and link[key]:
            return link[key]
    return None


def _page_url(value: object) -> bool:
    """A URL that the page fetcher could target: public-shaped HTTP(S), not X."""
    try:
        page_capture._url_parts(value)
    except Exception:
        return False
    return not page_capture.is_x_url(value)


def record_key(bookmark_post_id: str, source_post_id: str, url_index: int) -> str:
    return f"{bookmark_post_id}:{source_post_id}:{url_index}"


def _valid_record(record: object) -> bool:
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        return False
    if not _is_id(record["bookmark_post_id"]) or not _is_id(record["source_post_id"]):
        return False
    if type(record["url_index"]) is not int or not 0 <= record["url_index"] <= MAX_URL_INDEX:
        return False
    if not _page_url(record["requested_url"]):
        return False
    if record["final_url"] is not None and not _page_url(record["final_url"]):
        return False
    if record["http_status"] is not None and (
            type(record["http_status"]) is not int or not 100 <= record["http_status"] <= 599):
        return False
    if not _timestamp(record["retrieved_at"]) or record["state"] not in page_capture._STATES:
        return False
    # Technical-mode excerpt limit; records saved under the former 4096-
    # character limit stay valid (schema "1" unchanged). An older x-context
    # build rejects a store holding a longer excerpt (fails closed).
    for key, maximum in (("title", 512), ("description", 1024),
                         ("excerpt", page_capture.TECHNICAL_MAX_PAGE_TEXT)):
        if record[key] is not None and (not isinstance(record[key], str) or len(record[key]) > maximum):
            return False
    if type(record["excerpt_truncated"]) is not bool:
        return False
    if record["state"] == "captured" and not record["excerpt"]:
        return False
    if record["excerpt_truncated"] and (record["state"] != "captured" or not record["excerpt"]):
        return False
    return True


def current_url(thread: dict | None, source_post_id: str,
                url_index: int) -> tuple[str | None, str | None]:
    """(relation, URL) from the *current* thread record; (None, None) if absent/ambiguous.

    A Post may occur both as a thread Post and as a referenced Post; it is one
    source only when the URL at ``url_index`` is identical in every occurrence.
    """
    if thread is None:
        return None, None
    occurrences = [("thread_post", post["urls"]) for post in thread["thread_posts"]
                   if post["id"] == source_post_id]
    occurrences += [("referenced_post", ref["urls"]) for ref in thread["referenced_posts"]
                    if ref["id"] == source_post_id]
    if not occurrences:
        return None, None
    urls = set()
    for _, links in occurrences:
        if url_index >= len(links):
            return None, None
        urls.add(url_source(links[url_index]))
    if len(urls) != 1 or None in urls:
        return None, None
    relation = "+".join(sorted({name for name, _ in occurrences}))
    return relation, urls.pop()


def select_url(bookmarks: StoreSnapshot, threads: ThreadSnapshot, bookmark_post_id: str,
               source_post_id: str, url_index: int) -> tuple[str, str]:
    """Resolve (subject, URL) for the explicit selection or raise invalid_input."""
    if not isinstance(bookmarks, StoreSnapshot) or not isinstance(threads, ThreadSnapshot):
        raise page_capture.PageCaptureError()
    if (not _is_id(bookmark_post_id) or not _is_id(source_post_id)
            or type(url_index) is not int or not 0 <= url_index <= MAX_URL_INDEX):
        raise page_capture.PageCaptureError("invalid_input")
    if bookmarks.value is None:
        raise page_capture.PageCaptureError()
    subject = bookmarks.value["subject"]["id"]
    if bookmark_post_id not in {row["id"] for row in bookmarks.value["items"]}:
        raise page_capture.PageCaptureError("invalid_input")
    thread = (threads.value or {}).get("items", {}).get(bookmark_post_id)
    _, url = current_url(thread, source_post_id, url_index)
    if url is None or not _page_url(url):
        # Unknown Post/index, ambiguous duplicate, unexpanded t.co or X URL.
        raise page_capture.PageCaptureError("invalid_input")
    return subject, url


def preflight(bookmarks: StoreSnapshot) -> ThreadPageSnapshot:
    """Validate the optional sidecar; independent of enrichment/page sidecars."""
    try:
        if not isinstance(bookmarks, StoreSnapshot) or bookmarks.value is None:
            raise ValueError("missing bookmarks")
        subject = bookmarks.value["subject"]["id"]
        path = bookmarks.path.with_name(STORE_NAME)
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("unsafe store")
        try:
            with path.open("rb") as stream:
                raw = stream.read(page_capture.MAX_STORE_BYTES + 1)
        except FileNotFoundError:
            return ThreadPageSnapshot(path, None, None)
        if len(raw) > page_capture.MAX_STORE_BYTES:
            raise ValueError("store too large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json)
        if not isinstance(value, dict) or set(value) != {"schema_version", "subject_id", "items"}:
            raise ValueError("bad store")
        if (value["schema_version"] != "1" or value["subject_id"] != subject
                or not isinstance(value["items"], dict)):
            raise ValueError("bad store")
        for key, record in value["items"].items():
            if not _valid_record(record) or key != record_key(
                    record["bookmark_post_id"], record["source_post_id"], record["url_index"]):
                raise ValueError("bad record")
        return ThreadPageSnapshot(path, raw, value)
    except Exception:
        raise page_capture.PageCaptureError() from None


def save(snapshot: ThreadPageSnapshot, *, subject_id: str, bookmark_post_id: str,
         source_post_id: str, url_index: int, result: dict) -> None:
    """Add/replace one record atomically; other records and sidecars are untouched."""
    try:
        record = {"bookmark_post_id": bookmark_post_id, "source_post_id": source_post_id,
                  "url_index": url_index, **result}
        if not isinstance(snapshot, ThreadPageSnapshot) or not _valid_record(record):
            raise ValueError("invalid record")
        data = json.loads(json.dumps(snapshot.value)) if snapshot.value is not None else {
            "schema_version": "1", "subject_id": subject_id, "items": {},
        }
        if data["subject_id"] != subject_id:
            raise ValueError("subject mismatch")
        data["items"][record_key(bookmark_post_id, source_post_id, url_index)] = record
    except Exception:
        raise page_capture.PageCaptureError() from None
    page_capture.atomic_replace(snapshot.path, snapshot.raw, data, prefix=".bookmark-thread-pages-")
