"""Issue #77 stage 2: bounded, bookmark-anchored same-author X thread capture.

Uses official Post Lookup and at most one page of Full-Archive Search via x_api.
Original bookmarks-v1.json and bookmark-enrichment-v1.json are never modified.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from .bookmark_enrichment import Snapshot as EnrichmentSnapshot, _unique as unique_json
from .bookmark_store import StoreSnapshot, _timestamp
from . import x_api
from .x_api import RateLimitMetadata, Transport, XApiError

MIN_SEARCH_RESULTS = 10
DEFAULT_SEARCH_RESULTS = 20
MAX_SEARCH_RESULTS = 100
MAX_STORE_BYTES = 16 * 1024 * 1024
_ARCHIVE_EPOCH = "2006-03-21T00:00:00Z"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,50}$")
_SEED_ROLES = frozenset(("bookmarked_post", "quoted_post"))
_BOOKMARK_RELATIONS = frozenset(("self", "quoted"))
_SEARCH_STATES = frozenset((
    "searched",
    "no_results",
    "truncated",
    "skipped_missing_author_or_conversation",
))
_COMPLETENESS_STATES = frozenset((
    "unverified_single_page",
    "partial_truncated",
    "partial_missing_parent",
    "partial_truncated_and_missing_parent",
    "lookup_only_missing_search_key",
))
_ROOT_STATES = frozenset(("in_thread", "external_referenced", "not_returned", "unknown"))
_POST_SOURCES = frozenset(("post_lookup", "full_archive_search"))
_URL_KEYS = frozenset(("url", "expanded_url", "unwound_url", "display_url", "title", "description"))


class ThreadStoreError(RuntimeError):
    """Allow-listed category and effect state only; never private/OS prose."""

    def __init__(self, category: str = "storage_error", *, may_have_occurred: bool = False) -> None:
        super().__init__(category)
        self.category = category
        self.may_have_occurred = may_have_occurred


@dataclass(frozen=True)
class ThreadSnapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


@dataclass(frozen=True, slots=True)
class ThreadCollectionResult:
    record: dict = field(repr=False)
    requests_attempted: int
    search_returned_count: int
    post_lookup_rate_limit: RateLimitMetadata
    search_rate_limit: RateLimitMetadata


def _is_id(value: object) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= 19 and value.isascii() and value.isdigit()


def _is_digits(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value.isascii() and value.isdigit()


def _valid_username(value: object) -> bool:
    return isinstance(value, str) and _USERNAME_RE.fullmatch(value) is not None


def _has_control_chars(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _valid_urls(urls: object) -> bool:
    if not isinstance(urls, list) or len(urls) > 50:
        return False
    for entry in urls:
        if not isinstance(entry, dict) or not set(entry).issubset(_URL_KEYS):
            return False
        for val in entry.values():
            if not isinstance(val, str) or len(val.encode("utf-8")) > 4096:
                return False
    return True


def _valid_thread_post(item: object) -> bool:
    keys = {
        "id", "text", "author_id", "author_username", "conversation_id",
        "created_at", "replied_to_id", "quoted_post_id", "source", "urls",
    }
    if not isinstance(item, dict) or set(item) != keys:
        return False
    if not _is_id(item["id"]):
        return False
    if not isinstance(item["text"], str) or len(item["text"].encode("utf-8")) > x_api._MAX_POST_TEXT_BYTES:
        return False
    if item["author_id"] is not None and not _is_digits(item["author_id"]):
        return False
    if item["author_username"] is not None and not _valid_username(item["author_username"]):
        return False
    for id_key in ("conversation_id", "replied_to_id", "quoted_post_id"):
        if item[id_key] is not None and not _is_id(item[id_key]):
            return False
    if item["created_at"] is not None and not _timestamp(item["created_at"]):
        return False
    if item["source"] not in _POST_SOURCES:
        return False
    return _valid_urls(item["urls"])


def _valid_referenced_post(item: object) -> bool:
    keys = {
        "id", "relation", "from_post_id", "text", "text_state",
        "author_id", "author_username", "conversation_id", "created_at", "urls",
    }
    if not isinstance(item, dict) or set(item) != keys:
        return False
    if not _is_id(item["id"]) or not _is_id(item["from_post_id"]):
        return False
    if item["relation"] not in ("quoted", "replied_to"):
        return False
    if item["text_state"] not in ("recorded", "not_returned"):
        return False
    if item["text_state"] == "recorded":
        if not isinstance(item["text"], str) or len(item["text"].encode("utf-8")) > x_api._MAX_POST_TEXT_BYTES:
            return False
    elif item["text"] is not None:
        return False
    if item["author_id"] is not None and not _is_digits(item["author_id"]):
        return False
    if item["author_username"] is not None and not _valid_username(item["author_username"]):
        return False
    if item["conversation_id"] is not None and not _is_id(item["conversation_id"]):
        return False
    if item["created_at"] is not None and not _timestamp(item["created_at"]):
        return False
    return _valid_urls(item["urls"])


def _valid_record(record: object) -> bool:
    keys = {
        "bookmark_post_id", "seed_role", "bookmark_relation_to_target", "target_post_id",
        "retrieved_at", "conversation_id", "author_id", "author_username",
        "search_query", "search_max_results", "search_state", "search_truncated",
        "excluded_unlinked_count", "completeness", "root_state", "missing_parent_id",
        "thread_posts", "referenced_posts",
    }
    if not isinstance(record, dict) or set(record) != keys:
        return False
    if not _is_id(record["bookmark_post_id"]) or not _is_id(record["target_post_id"]):
        return False
    if record["seed_role"] not in _SEED_ROLES:
        return False
    if record["bookmark_relation_to_target"] not in _BOOKMARK_RELATIONS:
        return False
    if not _timestamp(record["retrieved_at"]):
        return False
    if record["conversation_id"] is not None and not _is_id(record["conversation_id"]):
        return False
    if record["author_id"] is not None and not _is_digits(record["author_id"]):
        return False
    if record["author_username"] is not None and not _valid_username(record["author_username"]):
        return False
    if record["search_state"] not in _SEARCH_STATES:
        return False
    if type(record["search_truncated"]) is not bool:
        return False
    if record["search_state"] == "skipped_missing_author_or_conversation":
        if record["search_query"] is not None or record["search_max_results"] is not None or record["search_truncated"]:
            return False
    else:
        if (not isinstance(record["search_query"], str) or not record["search_query"]
                or len(record["search_query"]) > 1024 or _has_control_chars(record["search_query"])):
            return False
        if (type(record["search_max_results"]) is not int
                or not MIN_SEARCH_RESULTS <= record["search_max_results"] <= MAX_SEARCH_RESULTS):
            return False
    if type(record["excluded_unlinked_count"]) is not int or record["excluded_unlinked_count"] < 0:
        return False
    if record["completeness"] not in _COMPLETENESS_STATES or record["root_state"] not in _ROOT_STATES:
        return False
    if record["missing_parent_id"] is not None and not _is_id(record["missing_parent_id"]):
        return False
    thread_posts = record["thread_posts"]
    referenced_posts = record["referenced_posts"]
    if not isinstance(thread_posts, list) or not 1 <= len(thread_posts) <= 200:
        return False
    if not isinstance(referenced_posts, list) or len(referenced_posts) > 200:
        return False
    seen_thread_ids: set[str] = set()
    for post in thread_posts:
        if not _valid_thread_post(post) or post["id"] in seen_thread_ids:
            return False
        seen_thread_ids.add(post["id"])
    if record["target_post_id"] not in seen_thread_ids:
        return False
    return all(_valid_referenced_post(ref) for ref in referenced_posts)


def select_target(
    bookmarks: StoreSnapshot,
    enrichment: EnrichmentSnapshot,
    post_id: str,
) -> tuple[str, str, str, str]:
    """Resolve the explicit bookmark anchor and target Post ID for thread capture."""
    if not isinstance(bookmarks, StoreSnapshot) or not isinstance(enrichment, EnrichmentSnapshot):
        raise ThreadStoreError("storage_error")
    if not _is_id(post_id):
        raise ThreadStoreError("invalid_input")
    if bookmarks.value is None:
        raise ThreadStoreError("storage_error")
    subject = bookmarks.value["subject"]["id"]
    if enrichment.value is not None and enrichment.value["subject_id"] != subject:
        raise ThreadStoreError("subject_mismatch")
    if post_id not in {item["id"] for item in bookmarks.value["items"]}:
        raise ThreadStoreError("invalid_input")
    item = (enrichment.value or {}).get("items", {}).get(post_id)
    if item is not None:
        refs = item["fields"]["referenced_posts"]
        if refs["state"] == "present":
            for ref in refs["value"]:
                if ref.get("type") == "quoted":
                    return subject, ref["id"], "quoted_post", "quoted"
    return subject, post_id, "bookmarked_post", "self"


def build_thread_query(conversation_id: str, author_username: str) -> str:
    """Build a bounded single-author conversation query for Full-Archive Search."""
    if not _is_id(conversation_id) or not _valid_username(author_username):
        raise ValueError("invalid query parameters")
    return f"conversation_id:{conversation_id} from:{author_username} -is:retweet"


def _first_ref(post: dict, ref_type: str) -> str | None:
    for ref in post.get("referenced_posts", ()):
        if ref.get("type") == ref_type:
            return ref["id"]
    return None


def _is_retweet(post: dict) -> bool:
    return any(ref.get("type") == "retweeted" for ref in post.get("referenced_posts", ()))


def _sort_key(post: dict) -> tuple[str, int]:
    return (post.get("created_at") or "", int(post["id"]))


def _safe_username(users_by_id: dict[str, str], author_id: str | None) -> str | None:
    if author_id is None:
        return None
    uname = users_by_id.get(author_id)
    return uname if _valid_username(uname) else None


def reconstruct_same_author_thread(
    *,
    bookmark_post_id: str,
    seed_role: str,
    bookmark_relation_to_target: str,
    retrieved_at: str,
    target_post: dict,
    lookup_included_posts: tuple[dict, ...],
    users_by_id: dict[str, str],
    search_posts: tuple[dict, ...],
    search_included_posts: tuple[dict, ...],
    search_query: str | None,
    search_max_results: int | None,
    search_state: str,
    search_truncated: bool,
) -> dict:
    """Reconstruct same-author ancestor/descendant thread strictly via replied_to links."""
    target_id = target_post["id"]
    target_author_id = target_post.get("author_id")
    target_conversation_id = target_post.get("conversation_id")
    target_author_username = _safe_username(users_by_id, target_author_id)

    included_by_id: dict[str, dict] = {}
    for inc in (*lookup_included_posts, *search_included_posts):
        if inc["id"] not in included_by_id:
            included_by_id[inc["id"]] = inc

    same_author_pool: dict[str, tuple[dict, str]] = {target_id: (target_post, "post_lookup")}
    if target_author_id is not None and target_conversation_id is not None:
        for post in lookup_included_posts:
            if (post["id"] not in same_author_pool
                    and post.get("author_id") == target_author_id
                    and post.get("conversation_id") == target_conversation_id
                    and not _is_retweet(post)):
                same_author_pool[post["id"]] = (post, "post_lookup")
        for post in search_posts:
            if (post["id"] not in same_author_pool
                    and post.get("author_id") == target_author_id
                    and post.get("conversation_id") == target_conversation_id
                    and not _is_retweet(post)):
                same_author_pool[post["id"]] = (post, "full_archive_search")

    ancestors: list[str] = []
    visited_up = {target_id}
    current_id = target_id
    missing_parent_id: str | None = None
    while True:
        current_post = same_author_pool[current_id][0]
        parent_id = _first_ref(current_post, "replied_to")
        if parent_id is None or parent_id in visited_up:
            break
        if parent_id not in same_author_pool:
            external = included_by_id.get(parent_id)
            if (external is None
                    or external.get("author_id") is None
                    or external.get("author_id") == target_author_id):
                missing_parent_id = parent_id
            break
        visited_up.add(parent_id)
        ancestors.append(parent_id)
        current_id = parent_id
    ancestors.reverse()

    children: dict[str, list[str]] = {}
    for pid, (post, _) in same_author_pool.items():
        parent_id = _first_ref(post, "replied_to")
        if parent_id is not None and parent_id in same_author_pool:
            children.setdefault(parent_id, []).append(pid)
    for child_ids in children.values():
        child_ids.sort(key=lambda cid: _sort_key(same_author_pool[cid][0]))

    descendants: list[str] = []
    visited_down = set(ancestors) | {target_id}

    def _walk_down(node_id: str) -> None:
        for child_id in children.get(node_id, ()):
            if child_id in visited_down:
                continue
            visited_down.add(child_id)
            descendants.append(child_id)
            _walk_down(child_id)

    _walk_down(target_id)
    ordered_ids = ancestors + [target_id] + descendants
    connected_set = set(ordered_ids)
    excluded_unlinked_count = sum(1 for post in search_posts if post["id"] not in connected_set)

    thread_posts: list[dict] = []
    referenced_posts: list[dict] = []
    seen_refs: set[tuple[str, str, str]] = set()

    for pid in ordered_ids:
        post, source = same_author_pool[pid]
        author_id = post.get("author_id")
        author_username = _safe_username(users_by_id, author_id)
        replied_to_id = _first_ref(post, "replied_to")
        quoted_post_id = _first_ref(post, "quoted")
        thread_posts.append({
            "id": post["id"],
            "text": post["text"],
            "author_id": author_id,
            "author_username": author_username,
            "conversation_id": post.get("conversation_id"),
            "created_at": post.get("created_at"),
            "replied_to_id": replied_to_id,
            "quoted_post_id": quoted_post_id,
            "source": source,
            "urls": copy.deepcopy(post.get("urls", [])),
        })
        for ref in post.get("referenced_posts", ()):
            rel = ref.get("type")
            if rel not in ("quoted", "replied_to"):
                continue
            ref_id = ref["id"]
            if rel == "replied_to" and ref_id in connected_set:
                continue
            key = (post["id"], rel, ref_id)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            inc = included_by_id.get(ref_id)
            if inc is not None:
                inc_author_id = inc.get("author_id")
                inc_username = _safe_username(users_by_id, inc_author_id)
                referenced_posts.append({
                    "id": ref_id,
                    "relation": rel,
                    "from_post_id": post["id"],
                    "text": inc["text"],
                    "text_state": "recorded",
                    "author_id": inc_author_id,
                    "author_username": inc_username,
                    "conversation_id": inc.get("conversation_id"),
                    "created_at": inc.get("created_at"),
                    "urls": copy.deepcopy(inc.get("urls", [])),
                })
            else:
                referenced_posts.append({
                    "id": ref_id,
                    "relation": rel,
                    "from_post_id": post["id"],
                    "text": None,
                    "text_state": "not_returned",
                    "author_id": None,
                    "author_username": None,
                    "conversation_id": None,
                    "created_at": None,
                    "urls": [],
                })

    if target_conversation_id is None:
        root_state = "unknown"
    elif target_conversation_id in connected_set:
        root_state = "in_thread"
    elif any(
        ref["id"] == target_conversation_id and ref["text_state"] == "recorded"
        for ref in referenced_posts
    ):
        root_state = "external_referenced"
    else:
        root_state = "not_returned"

    if search_state == "skipped_missing_author_or_conversation":
        completeness = "lookup_only_missing_search_key"
    elif search_truncated and missing_parent_id is not None:
        completeness = "partial_truncated_and_missing_parent"
    elif search_truncated:
        completeness = "partial_truncated"
    elif missing_parent_id is not None:
        completeness = "partial_missing_parent"
    else:
        completeness = "unverified_single_page"

    return {
        "bookmark_post_id": bookmark_post_id,
        "seed_role": seed_role,
        "bookmark_relation_to_target": bookmark_relation_to_target,
        "target_post_id": target_id,
        "retrieved_at": retrieved_at,
        "conversation_id": target_conversation_id,
        "author_id": target_author_id,
        "author_username": target_author_username,
        "search_query": search_query,
        "search_max_results": search_max_results,
        "search_state": search_state,
        "search_truncated": search_truncated,
        "excluded_unlinked_count": excluded_unlinked_count,
        "completeness": completeness,
        "root_state": root_state,
        "missing_parent_id": missing_parent_id,
        "thread_posts": thread_posts,
        "referenced_posts": referenced_posts,
    }


def collect_thread(
    *,
    bookmark_post_id: str,
    target_post_id: str,
    seed_role: str,
    bookmark_relation_to_target: str,
    bearer_token: str | None,
    max_results: int = DEFAULT_SEARCH_RESULTS,
    transport: Transport | None = None,
    retrieved_at: str | None = None,
) -> ThreadCollectionResult:
    """Fetch target Post metadata and at most one Full-Archive Search page."""
    if (not _is_id(bookmark_post_id) or not _is_id(target_post_id)
            or seed_role not in _SEED_ROLES or bookmark_relation_to_target not in _BOOKMARK_RELATIONS):
        raise XApiError("invalid_input")
    if type(max_results) is not int or not MIN_SEARCH_RESULTS <= max_results <= MAX_SEARCH_RESULTS:
        raise XApiError("invalid_input")
    if retrieved_at is not None and not _timestamp(retrieved_at):
        raise XApiError("invalid_input")

    lookup = x_api.lookup_post_detail(
        target_post_id,
        bearer_token=bearer_token,
        transport=transport,
    )
    target = lookup.post
    conversation_id = target.get("conversation_id")
    author_id = target.get("author_id")
    author_username = lookup.included_users.get(author_id) if author_id is not None else None
    users_by_id = dict(lookup.included_users)

    if conversation_id and author_id and _valid_username(author_username):
        assert author_username is not None
        query = build_thread_query(conversation_id, author_username)
        start_time = _ARCHIVE_EPOCH
        if target["id"] == conversation_id and target.get("created_at"):
            start_time = target["created_at"]
        else:
            for inc in lookup.included_posts:
                if inc["id"] == conversation_id and inc.get("created_at"):
                    start_time = inc["created_at"]
                    break
        try:
            search = x_api.search_all_posts(
                query,
                bearer_token=bearer_token,
                max_results=max_results,
                start_time=start_time,
                transport=transport,
            )
        except XApiError as exc:
            failure = XApiError(
                exc.category,
                status_code=exc.status_code,
                rate_limit=exc.rate_limit,
                requests_attempted=lookup.requests_attempted + exc.requests_attempted,
            )
            failure.post_lookup_rate_limit = lookup.rate_limit
            raise failure from None
        users_by_id.update(search.included_users)
        search_posts = search.posts
        search_included_posts = search.included_posts
        search_truncated = search.truncated
        search_rate = search.rate_limit
        search_attempts = search.requests_attempted
        search_max_recorded: int | None = max_results
        search_query: str | None = query
        if search.truncated:
            search_state = "truncated"
        elif not search.posts:
            search_state = "no_results"
        else:
            search_state = "searched"
    else:
        search_posts = ()
        search_included_posts = ()
        search_truncated = False
        search_rate = RateLimitMetadata()
        search_attempts = 0
        search_max_recorded = None
        search_query = None
        search_state = "skipped_missing_author_or_conversation"

    stamp = utcnow() if retrieved_at is None else retrieved_at
    record = reconstruct_same_author_thread(
        bookmark_post_id=bookmark_post_id,
        seed_role=seed_role,
        bookmark_relation_to_target=bookmark_relation_to_target,
        retrieved_at=stamp,
        target_post=target,
        lookup_included_posts=lookup.included_posts,
        users_by_id=users_by_id,
        search_posts=search_posts,
        search_included_posts=search_included_posts,
        search_query=search_query,
        search_max_results=search_max_recorded,
        search_state=search_state,
        search_truncated=search_truncated,
    )
    if not _valid_record(record):
        raise XApiError(
            "provider_error",
            rate_limit=search_rate,
            requests_attempted=lookup.requests_attempted + search_attempts,
        )
    return ThreadCollectionResult(
        record=record,
        requests_attempted=lookup.requests_attempted + search_attempts,
        search_returned_count=len(search_posts),
        post_lookup_rate_limit=lookup.rate_limit,
        search_rate_limit=search_rate,
    )


def preflight(bookmarks: StoreSnapshot) -> ThreadSnapshot:
    """Validate optional bookmark-threads-v1.json against bookmarks subject."""
    try:
        if not isinstance(bookmarks, StoreSnapshot) or bookmarks.value is None:
            raise ValueError("missing bookmarks")
        subject = bookmarks.value["subject"]["id"]
        path = bookmarks.path.with_name("bookmark-threads-v1.json")
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError("unsafe thread store")
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_STORE_BYTES + 1)
        except FileNotFoundError:
            return ThreadSnapshot(path, None, None)
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError("store too large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_json)
        if not isinstance(value, dict) or set(value) != {"schema_version", "subject_id", "items"}:
            raise ValueError("bad store")
        if value["schema_version"] != "1" or not _is_digits(value["subject_id"]) or not isinstance(value["items"], dict):
            raise ValueError("bad store")
        if value["subject_id"] != subject:
            raise ValueError("subject mismatch")
        for key, record in value["items"].items():
            if not _valid_record(record) or key != record["bookmark_post_id"]:
                raise ValueError("bad record")
        return ThreadSnapshot(path, raw, value)
    except ThreadStoreError:
        raise
    except Exception:
        raise ThreadStoreError() from None


def save(snapshot: ThreadSnapshot, *, subject_id: str, record: dict) -> None:
    """Atomically save one thread record without modifying primary bookmarks."""
    tmp = None
    fd = None
    replaced = False
    try:
        if not isinstance(snapshot, ThreadSnapshot) or not _is_digits(subject_id) or not _valid_record(record):
            raise ValueError("invalid save arguments")
        if snapshot.value is not None and snapshot.value["subject_id"] != subject_id:
            raise ThreadStoreError("subject_mismatch")
        data = copy.deepcopy(snapshot.value) if snapshot.value is not None else {
            "schema_version": "1",
            "subject_id": subject_id,
            "items": {},
        }
        data["items"][record["bookmark_post_id"]] = copy.deepcopy(record)
        raw = (json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError("store too large")
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".bookmark-threads-", suffix=".tmp", dir=snapshot.path.parent)
        tmp = Path(name)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            if stream.write(raw) != len(raw):
                raise OSError("short write")
            stream.flush()
            os.fsync(stream.fileno())
        if tmp.read_bytes() != raw:
            raise ValueError("temp mismatch")
        if (snapshot.path.read_bytes() if snapshot.path.exists() else None) != snapshot.raw:
            raise ValueError("changed store")
        os.replace(tmp, snapshot.path)
        replaced = True
        if snapshot.path.read_bytes() != raw:
            raise OSError("post-write mismatch")
    except ThreadStoreError:
        raise
    except Exception:
        raise ThreadStoreError(may_have_occurred=replaced) from None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
