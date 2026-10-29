"""Issue #64 AC-1: bounded, explicit X bookmark metadata extraction and local sidecar.

Provider data is untrusted. No link traversal, media download or remote calls here.
The original SPEC-0007 bookmarks-v1.json is not changed by this module.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile

from .bookmark_store import StoreSnapshot, _timestamp

_FIELDS = ("entities.urls", "attachments.media_keys", "referenced_posts", "card_uri")
_URL_KEYS = ("url", "expanded_url", "unwound_url", "display_url", "title", "description", "media_key")
_MEDIA_KEYS = ("media_key", "type", "url", "preview_image_url", "alt_text")
_LIMIT_BYTES = 32 * 1024 * 1024
# Up to 100 Posts/page, 4 media each, up to 20 references per Post.
_PAGE_MEDIA_LIMIT = 400
_PAGE_POST_LIMIT = 2000
_REFERENCE_TYPES = frozenset(("retweeted", "quoted", "replied_to"))


class EnrichmentError(ValueError):
    def __init__(self, category: str = "storage_error", *, may_have_occurred: bool = False):
        super().__init__(category)
        self.category = category
        self.may_have_occurred = may_have_occurred


def _id(value):
    return isinstance(value, str) and 1 <= len(value) <= 19 and value.isascii() and value.isdigit()


def _string(value, limit=8192):
    if not isinstance(value, str) or len(value.encode("utf-8")) > limit:
        raise ValueError("invalid provider field")
    return value


def _list(value, maximum=20):
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("invalid provider list")
    return value


def _status(value, key):
    return {"state": "present", "value": value} if key else {"state": "not_returned"}


def capture(post: dict, includes: dict) -> dict:
    """Take only known attributes linked to one primary Post from one API reply.

    The source value is never replaced by a guess or by content of an unrelated
    included object. Not-returned differs from an explicitly empty list.
    """
    if not isinstance(post, dict) or not _id(post.get("id")) or not isinstance(includes, dict):
        raise ValueError("invalid provider post")
    _string(post.get("text"))
    entities = post.get("entities", {})
    if not isinstance(entities, dict):
        raise ValueError("invalid entities")
    urls = []
    if "urls" in entities:
        for entry in _list(entities["urls"]):
            if not isinstance(entry, dict):
                raise ValueError("invalid URL")
            values = {k: _string(entry[k], 4096) for k in _URL_KEYS if k in entry}
            if "status" in entry:
                if type(entry["status"]) is not int or not 100 <= entry["status"] <= 599:
                    raise ValueError("invalid URL status")
                values["status"] = entry["status"]
            # X URL entities may omit the url key; retain returned metadata only.
            urls.append(values)
    attachments = post.get("attachments", {})
    if not isinstance(attachments, dict):
        raise ValueError("invalid attachments")
    media_keys = []
    if "media_keys" in attachments and attachments["media_keys"] is not None:
        media_keys = [_string(k, 128) for k in _list(attachments["media_keys"])]
        if len(media_keys) != len(set(media_keys)):
            raise ValueError("duplicate media key")
    # X currently describes the expansion as referenced_posts; accept
    # either response spelling, retaining its actual field name.
    ref_field = "referenced_posts" if "referenced_posts" in post else "referenced_tweets"
    references = []
    if ref_field in post:
        seen_refs = set()
        for item in _list(post[ref_field]):
            if not isinstance(item, dict) or not _id(item.get("id")):
                raise ValueError("invalid reference")
            if "type" in item and item["type"] not in _REFERENCE_TYPES:
                raise ValueError("invalid reference type")
            if item["id"] in seen_refs:
                raise ValueError("duplicate reference")
            seen_refs.add(item["id"])
            references.append({"id": item["id"], **({"type": item["type"]} if "type" in item else {})})
    refs = {r["id"] for r in references}
    media = []
    posts = []
    seen_media = set()
    seen_posts = set()
    for obj in _list(includes.get("media", []), _PAGE_MEDIA_LIMIT):
        if not isinstance(obj, dict):
            raise ValueError("invalid included media")
        if obj.get("media_key") in media_keys:
            if obj["media_key"] in seen_media:
                raise ValueError("duplicate included media")
            seen_media.add(obj["media_key"])
            media.append({k: _string(obj[k], 8192) for k in _MEDIA_KEYS if k in obj})
    for obj in _list(includes.get("posts", includes.get("tweets", [])), _PAGE_POST_LIMIT):
        if not isinstance(obj, dict):
            raise ValueError("invalid included post")
        if obj.get("id") in refs:
            if obj["id"] in seen_posts:
                raise ValueError("duplicate included post")
            seen_posts.add(obj["id"])
            if not _id(obj["id"]):
                raise ValueError("invalid included id")
            posts.append({"id": obj["id"], "text": _string(obj.get("text"))})
    fields = {
        "entities.urls": _status(urls, "urls" in entities),
        "attachments.media_keys": _status(None if attachments.get("media_keys", False) is None else media_keys,
                                          "media_keys" in attachments),
        "referenced_posts": _status(references, ref_field in post),
        "card_uri": _status(_string(post["card_uri"], 4096) if "card_uri" in post else None,
                            "card_uri" in post),
    }
    return {"id": post["id"], "fields": fields,
            "reference_field_name": ref_field if ref_field in post else None,
            "included_media": media, "included_posts": posts}


def _validate_record(record: dict) -> None:
    if not isinstance(record, dict) or set(record) != {
        "id", "observed_at", "fields", "reference_field_name", "included_media", "included_posts"
    } or not _id(record["id"]):
        raise ValueError("invalid record")
    if not _timestamp(record["observed_at"]):
        raise ValueError("invalid timestamp")
    if not isinstance(record["fields"], dict) or set(record["fields"]) != set(_FIELDS):
        raise ValueError("invalid fields")
    for field_value in record["fields"].values():
        if not isinstance(field_value, dict) or field_value.get("state") not in ("present", "not_returned"):
            raise ValueError("invalid state")
        if set(field_value) != ({"state", "value"} if field_value["state"] == "present" else {"state"}):
            raise ValueError("invalid state shape")
    if record["reference_field_name"] not in (None, "referenced_posts", "referenced_tweets"):
        raise ValueError("invalid reference field")
    if not isinstance(record["included_media"], list) or not isinstance(record["included_posts"], list):
        raise ValueError("invalid includes")
    # Reconstruct the provider subset and compare to catch invalid/oversized
    # values before either persisting or trusting existing stored data.
    fields = record["fields"]
    entities = {"urls": fields["entities.urls"]["value"]} if fields["entities.urls"]["state"] == "present" else {}
    attachments = {"media_keys": fields["attachments.media_keys"]["value"]} if fields["attachments.media_keys"]["state"] == "present" else {}
    post = {"id": record["id"], "text": ""}
    if entities: post["entities"] = entities
    if attachments: post["attachments"] = attachments
    if fields["referenced_posts"]["state"] == "present":
        if record["reference_field_name"] not in ("referenced_posts", "referenced_tweets"):
            raise ValueError("invalid reference label")
        post[record["reference_field_name"]] = fields["referenced_posts"]["value"]
    elif record["reference_field_name"] is not None:
        raise ValueError("invalid absent reference label")
    if fields["card_uri"]["state"] == "present":
        post["card_uri"] = fields["card_uri"]["value"]
    regenerated = capture(post, {"media": record["included_media"], "posts": record["included_posts"]})
    for key in ("fields", "included_media", "included_posts", "reference_field_name"):
        if record[key] != regenerated[key]:
            raise ValueError("invalid record content")


@dataclass(frozen=True)
class Snapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


def preflight(bookmarks: StoreSnapshot) -> Snapshot:
    """Use the already-validated fixed bookmark storage directory, no writes."""
    try:
        if not isinstance(bookmarks, StoreSnapshot):
            raise ValueError("invalid original store")
        path = bookmarks.path.with_name("bookmark-enrichment-v1.json")
        # Bound the read *before* UTF-8 decoding and JSON parsing.
        if path.exists():
            with path.open("rb") as stream:
                raw = stream.read(_LIMIT_BYTES + 1)
            if len(raw) > _LIMIT_BYTES:
                raise ValueError("oversized enrichment store")
        else:
            raw = None
        value = None if raw is None else json.loads(raw.decode("utf-8"),
                                                    object_pairs_hook=_unique)
        if value is not None:
            if not isinstance(value, dict) or set(value) != {"schema_version", "subject_id", "items"} or value["schema_version"] != "1":
                raise ValueError("invalid snapshot")
            if not _id(value["subject_id"]) or not isinstance(value["items"], dict):
                raise ValueError("invalid snapshot")
            for key, record in value["items"].items():
                _validate_record(record)
                if key != record["id"]:
                    raise ValueError("mismatched id")
            if bookmarks.value is None:
                # An orphan sidecar cannot be safely joined to a new principal.
                raise EnrichmentError("storage_error")
            if value["subject_id"] != bookmarks.value["subject"]["id"]:
                raise EnrichmentError("subject_mismatch")
        return Snapshot(path, raw, value)
    except EnrichmentError:
        raise
    except Exception:
        raise EnrichmentError() from None


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate key")
        obj[key] = value
    return obj


def save(snapshot: Snapshot, records: tuple[dict, ...], *, subject_id: str, observed_at: str) -> None:
    """Atomic sidecar update with snapshot compare; no original bookmark writes."""
    tmp = None
    replaced = False
    fd = None
    try:
        if not isinstance(snapshot, Snapshot) or not _id(subject_id) or not _timestamp(observed_at):
            raise ValueError("invalid save arguments")
        if snapshot.value is not None and snapshot.value["subject_id"] != subject_id:
            raise EnrichmentError("subject_mismatch")
        if not isinstance(records, tuple) or len(records) > 100:
            raise ValueError("invalid records")
        state = copy.deepcopy(snapshot.value) if snapshot.value is not None else {
            "schema_version": "1", "subject_id": subject_id, "items": {}
        }
        for record in records:
            item = {**record, "observed_at": observed_at}
            _validate_record(item)
            state["items"][item["id"]] = item
        raw = (json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        if len(raw) > _LIMIT_BYTES:
            raise ValueError("store too large")
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix=".bookmark-enrichment-", suffix=".tmp", dir=snapshot.path.parent)
        tmp = Path(filename)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if tmp.read_bytes() != raw or (snapshot.path.read_bytes() if snapshot.path.exists() else None) != snapshot.raw:
            raise ValueError("changed store")
        os.replace(tmp, snapshot.path)
        replaced = True
        if snapshot.path.read_bytes() != raw:
            raise ValueError("write mismatch")
    except EnrichmentError:
        raise
    except Exception:
        raise EnrichmentError(may_have_occurred=replaced) from None
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
