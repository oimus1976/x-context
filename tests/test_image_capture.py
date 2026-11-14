"""Issue #64 AC-3: one synthetic image, offline-only, immutable original stores."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from x_context import bookmark_enrichment, bookmark_store, cli, image_capture, page_capture

STAMP = "2026-11-14T12:00:00Z"
URL = "https://images.example.org/preview.png"


def _png() -> bytes:
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (signature + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))


PNG = _png()


class ImageCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "x-context" / "data"
        self.data.mkdir(parents=True)
        self.original = self.data / "bookmarks-v1.json"
        self.enrichment = self.data / "bookmark-enrichment-v1.json"
        self.manifest = self.data / "bookmark-images-v1.json"
        self.env = {"LOCALAPPDATA": str(self.root),
                    "X_CONTEXT_USER_ACCESS_TOKEN": "SYNTHETIC-SECRET-UNUSED"}
        self.original.write_text(json.dumps({
            "store_schema_version": "1", "source": "x", "collection": "bookmarks",
            "subject": {"id": "42"}, "created_at": STAMP, "updated_at": STAMP,
            "items": [{"id": "123", "text": "Synthetic source",
                       "first_seen_at": STAMP, "last_seen_at": STAMP}]
        }), encoding="utf-8")
        self._write_enrichment(URL)
        self.calls = []

    def _write_enrichment(self, url):
        media = {"media_key": "3_1", "type": "photo"}
        if url is not None:
            media["preview_image_url"] = url
        record = bookmark_enrichment.capture(
            {"id": "123", "text": "Synthetic source", "attachments": {"media_keys": ["3_1"]}},
            {"media": [media]})
        record["observed_at"] = STAMP
        self.enrichment.write_text(json.dumps({
            "schema_version": "1", "subject_id": "42", "items": {"123": record}
        }), encoding="utf-8")

    def _snapshots(self):
        primary = bookmark_store.preflight(self.env)
        extra = bookmark_enrichment.preflight(primary)
        return primary, extra, image_capture.preflight(primary, extra)

    def resolver(self, host, port):
        self.assertEqual((host, port), ("images.example.org", 443))
        return ("93.184.216.34",)

    def transport(self, url, ips, deadline):
        self.calls.append(url)
        self.assertEqual(ips, ("93.184.216.34",))
        return page_capture.PageResponse(200, {"Content-Type": "image/png"}, PNG)

    def run_cli(self, args=None):
        output, errors = io.StringIO(), io.StringIO()
        args = args if args is not None else [
            "image", "capture", "--post-id", "123", "--media-index", "0",
            "--confirm-network-request",
        ]
        with (patch.object(page_capture, "_resolver", side_effect=self.resolver),
              patch.object(image_capture, "_image_transport", side_effect=self.transport),
              patch.object(page_capture, "utcnow", return_value=STAMP),
              patch.object(cli, "resolve_user_access_token",
                           side_effect=AssertionError("must not request X credentials"))):
            code = cli.main(args, environ=self.env, stdout=output, stderr=errors)
        return code, output.getvalue(), errors.getvalue()

    def test_AC3_01_cli_image_record_relative_markdown_and_immutable_originals(self):
        original = self.original.read_bytes(), self.enrichment.read_bytes()
        code, out, err = self.run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.calls, [URL])
        self.assertEqual(json.loads(out), {
            "operation": "image", "post_id": "123", "media_index": 0,
            "state": "saved", "http_status": 200, "persistence_succeeded": True,
        })
        self.assertEqual((self.original.read_bytes(), self.enrichment.read_bytes()), original)
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual((doc["schema_version"], doc["subject_id"]), ("1", "42"))
        row = doc["items"]["123:0"]
        expected_hash = hashlib.sha256(PNG).hexdigest()
        self.assertEqual(row, {
            "post_id": "123", "media_index": 0, "source_field": "included_media.preview_image_url",
            "requested_url": URL, "final_url": URL, "http_status": 200,
            "retrieved_at": STAMP, "state": "saved", "mime_type": "image/png",
            "byte_size": len(PNG), "sha256": expected_hash,
            "relative_path": f"bookmark-images-v1/123-0-{expected_hash}.png",
        })
        path = self.data / row["relative_path"]
        self.assertEqual(path.read_bytes(), PNG)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        _, _, snap = self._snapshots()
        md = image_capture.render_markdown(snap, post_id="123", media_index=0)
        self.assertEqual(md, f"![保存画像]({row['relative_path']})")
        self.assertTrue((self.data / md.split("](", 1)[1][:-1]).is_file())
        self.assertNotIn("SYNTHETIC-SECRET-UNUSED", self.manifest.read_text()+out)

    def test_AC3_02_missing_url_is_not_available_and_not_fake_markdown(self):
        self._write_enrichment(None)
        code, out, err = self.run_cli()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["state"], "not_available")
        self.assertFalse(self.calls)
        self.assertFalse((self.data / image_capture.ASSET_DIR).exists())
        row = json.loads(self.manifest.read_text())["items"]["123:0"]
        self.assertEqual(row["source_field"], None)
        self.assertEqual(row["relative_path"], None)
        _, _, snap = self._snapshots()
        self.assertEqual(image_capture.render_markdown(snap, post_id="123", media_index=0),
                         "画像状態: not_available")

    def test_AC3_03_no_confirmation_or_unknown_post_does_not_fetch_or_write(self):
        for args in (
            ["image", "capture", "--post-id", "123", "--media-index", "0"],
            ["image", "capture", "--post-id", "999", "--confirm-network-request"],
            ["image", "capture", "--post-id", "../123", "--confirm-network-request"],
            ["image", "capture", "--post-id", "123", "--media-index", "4",
             "--confirm-network-request"],
        ):
            with self.subTest(args=args):
                code, out, err = self.run_cli(args)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertEqual(json.loads(err)["error_category"], "invalid_input")
        self.assertFalse(self.calls)
        self.assertFalse(self.manifest.exists())

    def test_AC3_04_nonpublic_address_is_rejected_before_transport(self):
        for url in ("http://127.0.0.1/a", "http://10.0.0.1/img",
                    "https://user@example.org/a.png", "file:///tmp/a.png",
                    "http://169.254.169.254/latest"):
            with self.subTest(url=url):
                result, body = image_capture.capture_one(
                    url, at=STAMP, resolver=lambda *args: self.fail("no DNS"),
                    transport=lambda *args: self.fail("no transport"))
                self.assertEqual((result["state"], body), ("blocked_target", None))

    def test_AC3_05_private_dns_and_redirect_do_not_issue_second_request(self):
        res, _ = image_capture.capture_one(
            URL, at=STAMP, resolver=lambda *args: ("127.0.0.1",),
            transport=lambda *args: self.fail("no transport"))
        self.assertEqual(res["state"], "blocked_target")
        visits = []
        def redirect(url, ips, deadline):
            visits.append(url)
            return page_capture.PageResponse(
                302, {"Location": "http://127.0.0.1/admin"}, b"")
        result, payload = image_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver, transport=redirect)
        self.assertEqual(result["state"], "blocked_target")
        self.assertIsNone(payload)
        self.assertEqual(visits, [URL])

    def test_AC3_06_content_type_magic_and_size_gate(self):
        responses = [
            (200, "image/svg+xml", b"<svg><script>x</script></svg>", "unsupported_media"),
            (200, "image/jpeg", PNG, "unsupported_media"),
            (200, "text/html", PNG, "unsupported_media"),
            (200, "image/png", PNG + b"x" * image_capture.MAX_IMAGE_BYTES, "too_large"),
            (404, "image/png", PNG, "http_error"),
            (403, "image/png", PNG, "authentication_required"),
            (200, "image/png", b"invalid", "unsupported_media"),
        ]
        for status, mime, raw, expected in responses:
            with self.subTest(expected=expected, mime=mime, status=status):
                result, body = image_capture.capture_one(
                    URL, at=STAMP, resolver=self.resolver,
                    transport=lambda *a, payload=raw, ct=mime, code=status:
                        page_capture.PageResponse(code, {"Content-Type": ct}, payload))
                self.assertEqual(result["state"], expected)
                self.assertIsNone(body)
                self.assertIsNone(result["relative_path"])

    def test_AC3_07_transport_accepts_images_without_changing_ac2_default(self):
        with patch.object(page_capture, "_resolver", side_effect=self.resolver), \
             patch.object(page_capture, "_transport",
                          return_value=page_capture.PageResponse(
                              200, {"Content-Type": "image/png"}, PNG)) as call:
            result, body = image_capture.capture_one(URL, at=STAMP)
        self.assertEqual(result["state"], "saved")
        self.assertEqual(body, PNG)
        self.assertEqual(call.call_args.kwargs["accept"], "image/png,image/jpeg,image/webp")

    def test_AC3_08_repeated_save_same_bytes_and_local_recheck(self):
        self.run_cli()
        old = self.manifest.read_bytes()
        self.run_cli()
        self.assertEqual(self.manifest.read_bytes(), old)
        _, _, snap = self._snapshots()
        row = snap.value["items"]["123:0"]
        (self.data / row["relative_path"]).write_bytes(b"tampered")
        self.assertEqual(image_capture.render_markdown(snap, post_id="123", media_index=0),
                         "画像状態: file_invalid")

    def test_AC3_09_missing_asset_does_not_claim_downloaded(self):
        self.run_cli()
        _, _, snap = self._snapshots()
        asset = self.data / snap.value["items"]["123:0"]["relative_path"]
        asset.unlink()
        self.assertEqual(image_capture.render_markdown(snap, post_id="123", media_index=0),
                         "画像状態: file_missing")

    def test_AC3_10_corrupted_manifest_fails_before_fetch(self):
        self.manifest.write_text('{"schema_version":"999","subject_id":"42","items":{}}')
        before = self.manifest.read_bytes()
        code, out, err = self.run_cli()
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(json.loads(err)["error_category"], "storage_error")
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual(self.calls, [])

    def test_AC3_11_manifest_write_failure_rolls_back_new_asset(self):
        primary, extra, snapshot = self._snapshots()
        result, content = image_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver, transport=self.transport)
        actual = image_capture.os.replace
        count = []
        def fail_manifest(source, dest):
            count.append(dest)
            if len(count) == 2:
                raise OSError("synthetic manifest write failure")
            return actual(source, dest)
        before = self.original.read_bytes(), self.enrichment.read_bytes()
        with patch.object(image_capture.os, "replace", side_effect=fail_manifest):
            with self.assertRaises(image_capture.ImageCaptureError):
                image_capture.save(snapshot, subject_id="42", post_id="123",
                                   media_index=0, source_field="included_media.preview_image_url",
                                   result=result, image=content)
        self.assertFalse(self.manifest.exists())
        self.assertEqual((self.original.read_bytes(), self.enrichment.read_bytes()), before)
        folder = self.data / image_capture.ASSET_DIR
        self.assertEqual(list(folder.iterdir()), [])

    def test_AC3_12_stale_snapshot_rejected_and_previous_bytes_retained(self):
        self.run_cli()
        primary, extra, snapshot = self._snapshots()
        before = self.manifest.read_bytes()
        result, content = image_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver, transport=self.transport)
        self.manifest.write_bytes(before + b" ")
        with self.assertRaises(image_capture.ImageCaptureError):
            image_capture.save(snapshot, subject_id="42", post_id="123",
                               media_index=0, source_field="included_media.preview_image_url",
                               result=result, image=content)
        self.assertEqual(self.manifest.read_bytes(), before + b" ")

    def test_AC3_13_symlink_asset_directory_never_written(self):
        external = self.root / "outside"
        external.mkdir()
        try:
            (self.data / image_capture.ASSET_DIR).symlink_to(
                external, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        code, out, err = self.run_cli()
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(json.loads(err)["error_category"], "storage_error")
        self.assertEqual(list(external.iterdir()), [])
        self.assertFalse(self.manifest.exists())

    def test_AC3_14_no_status_image_link_when_html_disguised_as_png(self):
        primary, extra, snapshot = self._snapshots()
        result, content = image_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver,
            transport=lambda *args: page_capture.PageResponse(
                200, {"Content-Type": "image/png"}, b"<html>not a PNG</html>"))
        image_capture.save(snapshot, subject_id="42", post_id="123",
                           media_index=0, source_field="included_media.preview_image_url",
                           result=result, image=content)
        _, _, fresh = self._snapshots()
        self.assertEqual(image_capture.render_markdown(fresh, post_id="123", media_index=0),
                         "画像状態: unsupported_media")
        self.assertFalse((self.data / image_capture.ASSET_DIR).exists())


if __name__ == "__main__":
    unittest.main()
