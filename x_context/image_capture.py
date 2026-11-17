"""Issue #64 AC-3: one explicit X-bookmark image, stored separately.

No HTML crawling, X API calls or ambient credential use. The only optional
network operation is an explicitly confirmed public HTTP(S) GET, reusing the
AC-2 vetted-IP, redirect and monotonic deadline transport.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import time
from typing import Callable

from . import page_capture as page
from .bookmark_enrichment import Snapshot as EnrichmentSnapshot, _unique
from .bookmark_store import StoreSnapshot, _timestamp

MAX_IMAGE_BYTES = page.MAX_HTML_BYTES  # 512 KiB for the first one-image MVP
MAX_STORE_BYTES = 4 * 1024 * 1024
MAX_MEDIA_INDEX = 3
ASSET_DIR = "bookmark-images-v1"
_STATES = frozenset((
    "saved", "not_available", "blocked_target", "connection_error",
    "authentication_required", "http_error", "too_large", "unsupported_media",
    "redirect_limit", "timeout", "invalid_response",
))
_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
_SOURCE_FIELDS = frozenset(("included_media.preview_image_url", "included_media.url"))


class ImageCaptureError(ValueError):
    def __init__(self, category="storage_error", *, may_have_occurred=False):
        super().__init__(category)
        self.category = category
        self.may_have_occurred = may_have_occurred


@dataclass(frozen=True)
class ImageSnapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


def _id(value: object) -> bool:
    return isinstance(value, str) and value.isascii() and value.isdigit() and 1 <= len(value) <= 19


def _guard_asset_dir(path: Path) -> None:
    # Never follow a pre-existing symlink/junction out of the trusted data dir.
    for node in (path,):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise ImageCaptureError()


def _file_name(post_id: str, media_index: int, digest: str, mime: str) -> str:
    return f"{post_id}-{media_index}-{digest}{_TYPES[mime]}"


def _sniff_image(body: bytes) -> str | None:
    if (len(body) >= 33 and body.startswith(b"\x89PNG\r\n\x1a\n")
            and body[12:16] == b"IHDR"):
        return "image/png"
    if len(body) >= 4 and body.startswith(b"\xff\xd8\xff") and body.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if (len(body) >= 16 and body[:4] == b"RIFF" and body[8:12] == b"WEBP"
            and body[12:16] in (b"VP8 ", b"VP8L", b"VP8X")):
        return "image/webp"
    return None


def _valid_record(row: object) -> bool:
    keys = {"post_id", "media_index", "source_field", "requested_url", "final_url",
            "http_status", "retrieved_at", "state", "mime_type", "byte_size",
            "sha256", "relative_path"}
    if not isinstance(row, dict) or set(row) != keys:
        return False
    if not _id(row["post_id"]) or type(row["media_index"]) is not int or not 0 <= row["media_index"] <= MAX_MEDIA_INDEX:
        return False
    if row["source_field"] is not None and row["source_field"] not in _SOURCE_FIELDS:
        return False
    for key in ("requested_url", "final_url"):
        if row[key] is not None and (not isinstance(row[key], str) or len(row[key]) > page.MAX_URL_CHARS):
            return False
    if row["source_field"] is None and row["requested_url"] is not None:
        return False
    if type(row["http_status"]) is not int and row["http_status"] is not None:
        return False
    if row["http_status"] is not None and not 100 <= row["http_status"] <= 599:
        return False
    if not _timestamp(row["retrieved_at"]) or row["state"] not in _STATES:
        return False
    if row["state"] != "saved":
        return all(row[k] is None for k in ("mime_type", "byte_size", "sha256", "relative_path"))
    if (row["mime_type"] not in _TYPES or type(row["byte_size"]) is not int
            or not 1 <= row["byte_size"] <= MAX_IMAGE_BYTES
            or not isinstance(row["sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None):
        return False
    expected = ASSET_DIR + "/" + _file_name(row["post_id"], row["media_index"],
                                            row["sha256"], row["mime_type"])
    return (row["relative_path"] == expected and row["requested_url"] is not None
            and row["final_url"] is not None and row["http_status"] == 200)


def select_image(bookmarks: StoreSnapshot, enrichment: EnrichmentSnapshot,
                 post_id: str, media_index: int) -> tuple[str, str | None, str | None]:
    """Return subject, X-provided image URL and exact provenance field."""
    if (not isinstance(bookmarks, StoreSnapshot)
            or not isinstance(enrichment, EnrichmentSnapshot) or not _id(post_id)
            or type(media_index) is not int or not 0 <= media_index <= MAX_MEDIA_INDEX):
        raise ImageCaptureError("invalid_input")
    try:
        if bookmarks.value is None or enrichment.value is None:
            raise ValueError()
        subject = bookmarks.value["subject"]["id"]
        if enrichment.value["subject_id"] != subject:
            raise ValueError()
        if post_id not in {item["id"] for item in bookmarks.value["items"]}:
            raise ValueError()
        media = enrichment.value["items"][post_id]["included_media"][media_index]
        for key in ("preview_image_url", "url"):
            url = media.get(key)
            if isinstance(url, str) and url:
                return subject, url, "included_media." + key
        return subject, None, None
    except Exception:
        raise ImageCaptureError("invalid_input") from None


def preflight(bookmarks: StoreSnapshot, enrichment: EnrichmentSnapshot) -> ImageSnapshot:
    try:
        if bookmarks.value is None or enrichment.value is None:
            raise ValueError()
        subject = bookmarks.value["subject"]["id"]
        if enrichment.value["subject_id"] != subject:
            raise ValueError()
        path = bookmarks.path.with_name("bookmark-images-v1.json")
        with path.open("rb") as stream:
            raw = stream.read(MAX_STORE_BYTES + 1)
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "subject_id", "items"}
                or value["schema_version"] != "1" or value["subject_id"] != subject
                or not isinstance(value["items"], dict)):
            raise ValueError()
        for key, record in value["items"].items():
            if not _valid_record(record) or key != f'{record["post_id"]}:{record["media_index"]}':
                raise ValueError()
        return ImageSnapshot(path, raw, value)
    except FileNotFoundError:
        return ImageSnapshot(bookmarks.path.with_name("bookmark-images-v1.json"), None, None)
    except Exception:
        raise ImageCaptureError() from None


def _image_transport(url: str, ips: tuple[str, ...], deadline: float) -> page.PageResponse:
    return page._transport(url, ips, deadline, accept="image/png,image/jpeg,image/webp")


def capture_one(url: str | None, *, at: str,
                resolver: page.Resolver | None = None,
                transport: page.Transport | None = None) -> tuple[dict, bytes | None]:
    """One bounded image request; returns a stable record and optional bytes."""
    if not _timestamp(at):
        raise ImageCaptureError("invalid_input")
    result = {
        "requested_url": url, "final_url": None, "http_status": None,
        "retrieved_at": at, "state": "not_available", "mime_type": None,
        "byte_size": None, "sha256": None, "relative_path": None,
    }
    if url is None:
        return result, None
    current = url
    deadline = time.monotonic() + page.TIMEOUT_SECONDS
    resolve = page._resolver if resolver is None else resolver
    get = _image_transport if transport is None else transport
    for redirect in range(page.MAX_REDIRECTS + 1):
        try:
            page._remaining(deadline)
            p, host, port = page._url_parts(current)
            current = p._replace(fragment="").geturl()
            ips = resolve(host, port)
            page._remaining(deadline)
            if not isinstance(ips, tuple) or not ips:
                result["state"] = "connection_error"
                break
            if not all(page._valid_public_ip(ip) for ip in ips):
                result["state"] = "blocked_target"
                break
        except page.PageTimeout:
            result["state"] = "timeout"
            break
        except ValueError:
            result["state"] = "blocked_target"
            break
        except Exception:
            result["state"] = "connection_error"
            break
        try:
            reply = get(current, ips, deadline)
            page._remaining(deadline)
        except (page.PageTimeout, TimeoutError, socket.timeout):
            result["state"] = "timeout"
            break
        except Exception:
            result["state"] = "connection_error"
            break
        if (not isinstance(reply, page.PageResponse) or type(reply.status) is not int
                or not 100 <= reply.status <= 599
                or not isinstance(reply.headers, dict) or not isinstance(reply.body, bytes)):
            result["state"] = "invalid_response"
            break
        result["final_url"], result["http_status"] = current, reply.status
        if reply.status in (301, 302, 303, 307, 308):
            location = page._get_header(reply.headers, "location")
            if not location:
                result["state"] = "invalid_response"
                break
            if redirect == page.MAX_REDIRECTS:
                result["state"] = "redirect_limit"
                break
            current = page.urljoin(current, location)
            continue
        if reply.status in (401, 403):
            result["state"] = "authentication_required"
        elif reply.status != 200:
            result["state"] = "http_error"
        elif len(reply.body) > MAX_IMAGE_BYTES:
            result["state"] = "too_large"
        elif (page._get_header(reply.headers, "content-encoding") or "identity").lower() != "identity":
            result["state"] = "invalid_response"
        else:
            content_type = (page._get_header(reply.headers, "content-type") or "").split(";", 1)[0].strip().lower()
            actual_type = _sniff_image(reply.body)
            if content_type not in _TYPES or actual_type != content_type:
                result["state"] = "unsupported_media"
            else:
                result["state"] = "saved"
                result["mime_type"] = actual_type
                result["byte_size"] = len(reply.body)
                result["sha256"] = hashlib.sha256(reply.body).hexdigest()
                return result, reply.body
        break
    return result, None


def save(snapshot: ImageSnapshot, *, subject_id: str, post_id: str,
         media_index: int, source_field: str | None,
         result: dict, image: bytes | None) -> None:
    """Persist content-addressed image and separate manifest, fail closed."""
    tmp = None
    manifest_tmp = None
    new_asset = None
    manifest_written = False
    try:
        if not isinstance(snapshot, ImageSnapshot) or not _id(post_id):
            raise ValueError()
        record = {"post_id": post_id, "media_index": media_index,
                  "source_field": source_field, **result}
        if not _valid_record({**record, "relative_path":
                (ASSET_DIR + "/" + _file_name(post_id, media_index, record["sha256"], record["mime_type"]))
                if record["state"] == "saved" else None}):
            raise ValueError("bad record")
        if record["state"] == "saved":
            if (not isinstance(image, bytes) or len(image) != result["byte_size"]
                    or hashlib.sha256(image).hexdigest() != result["sha256"]
                    or _sniff_image(image) != result["mime_type"]):
                raise ValueError("bad image")
            record["relative_path"] = ASSET_DIR + "/" + _file_name(
                post_id, media_index, result["sha256"], result["mime_type"])
        elif image is not None:
            raise ValueError("unexpected image")
        if not _valid_record(record):
            raise ValueError("bad record")
        manifest = (json.loads(json.dumps(snapshot.value)) if snapshot.value is not None
                    else {"schema_version": "1", "subject_id": subject_id, "items": {}})
        if manifest["subject_id"] != subject_id:
            raise ValueError("subject mismatch")
        manifest["items"][f"{post_id}:{media_index}"] = record
        raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
               + "\n").encode("utf-8")
        if len(raw) > MAX_STORE_BYTES:
            raise ValueError("manifest exceeds bound")
        if (snapshot.path.read_bytes() if snapshot.path.exists() else None) != snapshot.raw:
            raise ValueError("stale manifest")
        if image is not None:
            folder = snapshot.path.parent / ASSET_DIR
            _guard_asset_dir(folder)
            folder.mkdir(mode=0o700, exist_ok=True)
            _guard_asset_dir(folder)
            asset = folder / Path(record["relative_path"]).name
            if asset.is_symlink() or (hasattr(asset, "is_junction") and asset.is_junction()):
                raise ValueError("unsafe existing asset")
            if asset.exists():
                with asset.open("rb") as stream:
                    existing = stream.read(MAX_IMAGE_BYTES + 1)
                if existing != image:
                    raise ValueError("asset collision")
            else:
                fd, name = tempfile.mkstemp(prefix=".image-", suffix=".tmp", dir=folder)
                tmp = Path(name)
                with os.fdopen(fd, "wb") as stream:
                    if stream.write(image) != len(image):
                        raise OSError("short image write")
                    stream.flush()
                    os.fsync(stream.fileno())
                if tmp.read_bytes() != image:
                    raise OSError("temp image mismatch")
                # File identity derives from the full digest; no user input in path.
                if asset.exists() or asset.is_symlink():
                    raise OSError("asset race")
                os.replace(tmp, asset)
                tmp = None
                new_asset = asset
        fd, name = tempfile.mkstemp(prefix=".bookmark-images-", suffix=".tmp",
                                    dir=snapshot.path.parent)
        manifest_tmp = Path(name)
        with os.fdopen(fd, "wb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("short manifest write")
            stream.flush()
            os.fsync(stream.fileno())
        if manifest_tmp.read_bytes() != raw:
            raise OSError("temp manifest mismatch")
        if (snapshot.path.read_bytes() if snapshot.path.exists() else None) != snapshot.raw:
            raise ValueError("stale manifest")
        os.replace(manifest_tmp, snapshot.path)
        manifest_tmp = None
        manifest_written = True
        if snapshot.path.read_bytes() != raw:
            raise OSError("manifest readback mismatch")
    except Exception:
        if not manifest_written and new_asset is not None:
            try:
                new_asset.unlink(missing_ok=True)
            except OSError:
                pass
        raise ImageCaptureError(may_have_occurred=manifest_written) from None
    finally:
        for candidate in (tmp, manifest_tmp):
            if candidate is not None:
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass


def render_markdown(snapshot: ImageSnapshot, *, post_id: str, media_index: int) -> str:
    """Local-only AC-3 image snippet, not the AC-5 combined Markdown renderer."""
    if not isinstance(snapshot, ImageSnapshot) or not _id(post_id) or type(media_index) is not int:
        raise ImageCaptureError("invalid_input")
    row = (snapshot.value or {}).get("items", {}).get(f"{post_id}:{media_index}")
    if row is None:
        return "画像状態: not_available"
    if not _valid_record(row):
        raise ImageCaptureError()
    if row["state"] != "saved":
        return "画像状態: " + row["state"]
    folder = snapshot.path.parent / ASSET_DIR
    _guard_asset_dir(folder)
    asset = folder / Path(row["relative_path"]).name
    if asset.is_symlink() or (hasattr(asset, "is_junction") and asset.is_junction()):
        return "画像状態: file_invalid"
    try:
        with asset.open("rb") as stream:
            raw = stream.read(MAX_IMAGE_BYTES + 1)
        if (len(raw) != row["byte_size"] or hashlib.sha256(raw).hexdigest() != row["sha256"]
                or _sniff_image(raw) != row["mime_type"]):
            return "画像状態: file_invalid"
    except OSError:
        return "画像状態: file_missing"
    return "![保存画像](" + row["relative_path"] + ")"
