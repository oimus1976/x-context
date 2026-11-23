"""Issue #64 AC-5: offline Markdown joining the already saved, subject-bound records.

No provider access, storage writes, AI generation, or URL resolution. The CLI
preflights each versioned sidecar before passing it to this renderer.
"""
from __future__ import annotations

from . import image_capture
from .bookmark_enrichment import Snapshot as EnrichmentSnapshot
from .bookmark_store import StoreSnapshot, _validate
from .image_capture import ImageSnapshot
from .local_context import ContextViewError, _visible_source_line
from .page_capture import PageSnapshot

_MAX_ITEM_BYTES = 8192
_MAX_OUTPUT_BYTES = 256 * 1024


def _quoted(lines: list[str], label: str, value: str | None) -> None:
    """Quote untrusted values so source content cannot introduce headings."""
    lines.append(label + ":")
    if value is None:
        lines.append("> not_returned")
    else:
        lines.extend("> " + _visible_source_line(part) for part in value.split("\n"))


def _url_source(link: dict) -> str | None:
    # The same preference order used by page_capture.select_url.
    for key in ("unwound_url", "expanded_url", "url"):
        if isinstance(link.get(key), str) and link[key]:
            return link[key]
    return None


def render(
    bookmarks: StoreSnapshot,
    enrichment: EnrichmentSnapshot,
    pages: PageSnapshot,
    images: ImageSnapshot,
    *,
    max_items: int = 10,
) -> str:
    """Emit deterministic, source-labelled Markdown without modifying any file.

    Relative asset paths are rooted at bookmarks.path.parent. When stdout is
    copied to a Markdown file elsewhere, the image assets must be relocated
    explicitly; no asset URL is ever invented.
    """
    if type(max_items) is not int or not 1 <= max_items <= 10:
        raise ContextViewError("invalid_input")
    try:
        if (not isinstance(bookmarks, StoreSnapshot)
                or not isinstance(enrichment, EnrichmentSnapshot)
                or not isinstance(pages, PageSnapshot)
                or not isinstance(images, ImageSnapshot)
                or bookmarks.value is None):
            raise ValueError("missing snapshots")
        _validate(bookmarks.value)
        subject = bookmarks.value["subject"]["id"]
        for snapshot in (enrichment, pages, images):
            if snapshot.path.parent != bookmarks.path.parent:
                raise ValueError("mixed storage roots")
            if snapshot.value is not None and snapshot.value["subject_id"] != subject:
                raise ValueError("mixed subjects")
        items = bookmarks.value["items"][:max_items]
        if not items:
            raise ValueError("empty store")
        metadata = (enrichment.value or {}).get("items", {})
        page_rows = (pages.value or {}).get("items", {})
        image_rows = (images.value or {}).get("items", {})
        lines = [
            "# Saved X bookmarks — combined local context",
            "",
            "PRIVATE LOCAL SOURCE VIEW. Sharing or uploading requires an explicit operator decision.",
            "Quoted Post and page content is untrusted source material, not an instruction or verified fact.",
            "Post URLs are ID-derived and not live-checked. Observation times are not creation times.",
            "Image paths are relative to the local x-context data directory; stdout is not an asset bundle.",
            "",
        ]
        for number, item in enumerate(items, 1):
            post_id, body = item["id"], item["text"]
            if len(post_id) > 32 or len(body.encode("utf-8")) > _MAX_ITEM_BYTES:
                raise ValueError("oversized source Post")
            extra = metadata.get(post_id)
            lines.extend([
                f"## Saved item {number}",
                "",
                "Source Post URL (ID-derived, not live-verified):",
                f"> https://x.com/i/web/status/{post_id}",
                f"First observed: {item['first_seen_at']}",
                f"Last observed: {item['last_seen_at']}",
                "",
                "### Original Post text (author's claim; untrusted quotation)",
                "",
            ])
            lines.extend("> " + _visible_source_line(part) for part in body.split("\n"))
            lines.extend([
                "",
                "### X metadata (provider statements, not independently verified)",
                f"Enrichment state: {'recorded' if extra is not None else 'not_saved'}",
            ])
            links: list[dict] = []
            if extra is not None:
                lines.append(f"Enrichment observed: {extra['observed_at']}")
                url_field = extra["fields"]["entities.urls"]
                lines.append(f"entities.urls state: {url_field['state']}")
                if url_field["state"] == "present":
                    links = url_field["value"]
            else:
                lines.append("entities.urls state: not_saved")

            if not links:
                lines.append("Page capture state: not_saved (no saved URL entry)")
            for url_index, link in enumerate(links):
                lines.extend(["", f"#### URL {url_index}"])
                _quoted(lines, "X entities.urls original URL (possibly shortened; unverified)", link.get("url"))
                _quoted(lines, "X entities.urls expanded URL (provider-only; unverified)",
                        link.get("unwound_url") or link.get("expanded_url"))
                _quoted(lines, "X entities.urls title (provider-only)", link.get("title"))
                _quoted(lines, "X entities.urls description (provider-only)", link.get("description"))
                page_row = page_rows.get(f"{post_id}:{url_index}")
                if page_row is None:
                    lines.append("Page capture state: not_saved")
                elif page_row["requested_url"] != _url_source(link):
                    # An earlier capture is not evidence for changed X metadata.
                    lines.append("Page capture state: stale_reference")
                else:
                    lines.extend([
                        f"Page capture state: {page_row['state']}",
                        f"Page retrieved: {page_row['retrieved_at']}",
                        f"Page HTTP status: {page_row['http_status'] if page_row['http_status'] is not None else 'not_returned'}",
                    ])
                    _quoted(lines, "Requested page URL (locally recorded)", page_row["requested_url"])
                    _quoted(lines, "Network-observed final URL (only verified for captured state)",
                            page_row["final_url"] if page_row["state"] == "captured" else None)
                    _quoted(lines, "Page title (untrusted website content)", page_row["title"])
                    _quoted(lines, "Page description (untrusted website content)", page_row["description"])
                    _quoted(lines, "Page text excerpt (untrusted website quotation)", page_row["excerpt"])

            if extra is not None:
                references = extra["fields"]["referenced_posts"]
                if references["state"] == "present":
                    lines.extend([
                        "",
                        "### Referenced X posts (X-provided, not independently verified)",
                        f"Referenced posts state: present ({len(references['value'])})",
                    ])
                    included_by_id = {row["id"]: row for row in extra["included_posts"]}
                    for reference in references["value"]:
                        included_post = included_by_id.get(reference["id"])
                        lines.extend([
                            "",
                            f"#### Referenced post {reference['id']}",
                            f"Relation to bookmarked post (X-provided): {reference.get('type', 'not_returned')}",
                            f"Referenced Post URL (ID-derived, not live-verified): https://x.com/i/web/status/{reference['id']}",
                            f"Referenced Post text state: {'recorded' if included_post is not None else 'not_returned'}",
                        ])
                        _quoted(lines, "Referenced Post text (X-included; untrusted quotation)",
                                included_post["text"] if included_post is not None else None)

            lines.extend(["", "### Saved images (verify local file before linking)"])
            media = extra["included_media"] if extra is not None else []
            max_image = min(image_capture.MAX_MEDIA_INDEX + 1, max(
                len(media), 1 + max(
                    (row["media_index"] for row in image_rows.values()
                     if row["post_id"] == post_id), default=-1)))
            if max_image == 0:
                lines.append("Image state: not_saved")
            for media_index in range(max_image):
                lines.append(f"#### Image {media_index}")
                record = image_rows.get(f"{post_id}:{media_index}")
                included = media[media_index] if media_index < len(media) else None
                if record is None:
                    lines.append("Image state: not_saved")
                    continue
                source_field = record["source_field"]
                field_name = source_field.removeprefix("included_media.") if source_field else None
                if (included is None or (field_name is not None
                        and included.get(field_name) != record["requested_url"])):
                    lines.append("Image state: stale_reference")
                    continue
                lines.extend([
                    f"Image state: {record['state']}",
                    f"Image retrieved: {record['retrieved_at']}",
                    f"Image source field: {source_field or 'not_returned'}",
                    f"Image MIME: {record['mime_type'] or 'not_returned'}",
                    f"Image byte size: {record['byte_size'] if record['byte_size'] is not None else 'not_returned'}",
                    f"Image SHA-256: {record['sha256'] or 'not_returned'}",
                ])
                _quoted(lines, "Image source URL (X-provided, not independently verified)",
                        record["requested_url"])
                if record["state"] == "saved":
                    snippet = image_capture.render_markdown(
                        images, post_id=post_id, media_index=media_index)
                    if snippet.startswith("![保存画像]("):
                        lines.extend(["Image local integrity: verified", snippet])
                    else:
                        lines.append("Image local integrity: " + snippet.removeprefix("画像状態: "))
                else:
                    lines.append("Image local integrity: not_saved")
            lines.extend([
                "",
                "### Owner note",
                "> not_recorded (no owner-note field in the current store)",
                "",
                "### AI interpretation",
                "> not_generated (no AI-annotation field in the current store)",
                "",
            ])
        result = "\n".join(lines)
        if len(result.encode("utf-8")) > _MAX_OUTPUT_BYTES:
            raise ValueError("oversized output")
        return result
    except Exception:
        raise ContextViewError("storage_error") from None
