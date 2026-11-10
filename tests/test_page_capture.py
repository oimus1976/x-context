"""Issue #64 AC-2: synthetic-only page capture, no network or actual X data."""
import io
import json
import socket
import threading
import time
from urllib.parse import urlsplit
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_context import bookmark_enrichment, bookmark_store, cli, page_capture


STAMP = "2026-11-10T08:00:00Z"
URL = "https://example.org/article"
SAMPLE = b'''<!DOCTYPE html><html><head><title> Synthetic &amp; Title </title>
<meta name="description" content="A synthetic description"></head>
<body><nav>Ignore nav</nav><main><h1>Heading</h1><p>first  paragraph.</p>
<p>Second &amp; final.</p></main><script>ignore script</script></body></html>'''


class PageCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "x-context" / "data"
        self.data.mkdir(parents=True)
        self.main = self.data / "bookmarks-v1.json"
        self.extras = self.data / "bookmark-enrichment-v1.json"
        self.page_path = self.data / "bookmark-pages-v1.json"
        self.env = {"LOCALAPPDATA": str(self.root), "X_CONTEXT_USER_ACCESS_TOKEN": "FAKE-NOT-USED"}
        self.main.write_text(json.dumps({
            "store_schema_version": "1", "source": "x", "collection": "bookmarks",
            "subject": {"id": "42"}, "created_at": STAMP, "updated_at": STAMP,
            "items": [{"id": "123", "text": "Source Post", "first_seen_at": STAMP,
                       "last_seen_at": STAMP}]
        }), encoding="utf-8")
        record = bookmark_enrichment.capture({
            "id": "123", "text": "Source Post",
            "entities": {"urls": [{"url": "https://t.co/example", "expanded_url": URL}]}
        }, {})
        record["observed_at"] = STAMP
        self.extras.write_text(json.dumps({
            "schema_version": "1", "subject_id": "42", "items": {"123": record}
        }), encoding="utf-8")
        self.requests = []

    def resolver(self, host, port):
        self.assertEqual(host, "example.org")
        self.assertEqual(port, 443)
        return ("93.184.216.34",)

    def transport(self, url, ips, deadline):
        self.requests.append((url, ips))
        return page_capture.PageResponse(200, {"Content-Type": "text/html"}, SAMPLE)

    def run_cmd(self, args=None):
        out, err = io.StringIO(), io.StringIO()
        args = args if args is not None else [
            "page", "capture", "--post-id", "123", "--url-index", "0",
            "--confirm-network-request",
        ]
        with (patch.object(page_capture, "_resolver", side_effect=self.resolver),
              patch.object(page_capture, "_transport", side_effect=self.transport),
              patch.object(page_capture, "utcnow", return_value=STAMP),
              patch.object(cli, "resolve_user_access_token",
                           side_effect=AssertionError("X credentials must never be read"))):
            rc = cli.main(args, environ=self.env, stdout=out, stderr=err)
        return rc, out.getvalue(), err.getvalue()

    def test_AC2_01_exact_capture_and_separate_sidecar_original_unchanged(self):
        before = self.main.read_bytes(), self.extras.read_bytes()
        rc, stdout, stderr = self.run_cmd()
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(self.requests, [(URL, ("93.184.216.34",))])
        self.assertEqual(json.loads(stdout), {
            "operation": "page", "post_id": "123", "url_index": 0,
            "state": "captured", "http_status": 200, "persistence_succeeded": True,
        })
        self.assertEqual((self.main.read_bytes(), self.extras.read_bytes()), before)
        stored = json.loads(self.page_path.read_text(encoding="utf-8"))
        self.assertEqual((stored["schema_version"], stored["subject_id"]), ("1", "42"))
        self.assertEqual(stored["items"], {
            "123:0": {
                "post_id": "123", "url_index": 0,
                "requested_url": URL, "final_url": URL, "http_status": 200,
                "retrieved_at": STAMP, "state": "captured",
                "title": "Synthetic & Title",
                "description": "A synthetic description",
                "excerpt": "Heading first paragraph. Second & final.",
            }
        })
        self.assertNotIn("FAKE-NOT-USED", self.page_path.read_text()+stdout)

    def test_AC2_02_redirect_single_target_and_public_revalidation(self):
        replies = [
            page_capture.PageResponse(302, {"Location": "/final"}, b""),
            page_capture.PageResponse(200, {"Content-Type": "text/html"}, SAMPLE)
        ]
        visits = []
        def transport(url, ips, deadline):
            visits.append(url)
            return replies.pop(0)
        result = page_capture.capture_one(URL, at=STAMP, resolver=self.resolver, transport=transport)
        self.assertEqual((result["requested_url"], result["final_url"], result["state"]),
                         (URL, "https://example.org/final", "captured"))
        self.assertEqual(visits, [URL, "https://example.org/final"])

    def test_AC2_03_forbidden_redirect_no_second_transport(self):
        attempts = []
        def transport(url, ips, deadline):
            attempts.append(url)
            return page_capture.PageResponse(302, {"Location": "http://127.0.0.1/admin"}, b"")
        result = page_capture.capture_one(URL, at=STAMP, resolver=self.resolver, transport=transport)
        self.assertEqual(result["state"], "blocked_target")
        self.assertEqual(attempts, [URL])

    def test_AC2_04_block_url_without_transport_or_dns(self):
        banned = ["http://127.0.0.1/", "http://10.0.0.9/", "http://169.254.169.254/",
                  "http://localhost/", "http://localhost.local/", "file:///tmp/nope",
                  "https://user@example.org/", "http://example.org:8080/",
                  "http://[::1]/", "http://example.org/white space",
                  "http://public.internal/"]
        for url in banned:
            with self.subTest(url=url):
                result = page_capture.capture_one(url, at=STAMP,
                    resolver=lambda *x: self.fail("DNS must not be called"),
                    transport=lambda *x: self.fail("transport must not be called"))
                self.assertEqual(result["state"], "blocked_target")

    def test_AC2_05_dns_private_result_never_connects(self):
        for result_ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1"):
            with self.subTest(ip=result_ip):
                result = page_capture.capture_one(URL, at=STAMP,
                    resolver=lambda *x: (result_ip,),
                    transport=lambda *x: self.fail("transport must not be called"))
                self.assertEqual(result["state"], "blocked_target")

    def test_AC2_06_http_status_and_failure_state_matrix(self):
        cases = [
            (401, "text/html", b"x", "authentication_required"),
            (403, "text/html", b"x", "authentication_required"),
            (404, "text/html", b"x", "http_error"),
            (500, "text/html", b"x", "http_error"),
            (200, "text/plain", b"x", "not_html"),
            (200, "text/html", b"<html></html>", "no_extractable_text"),
            (200, "text/html", b"x" * (page_capture.MAX_HTML_BYTES+1), "too_large"),
        ]
        for status, content_type, body, state in cases:
            with self.subTest(state=state):
                result = page_capture.capture_one(
                    URL, at=STAMP, resolver=self.resolver,
                    transport=lambda *x: page_capture.PageResponse(
                        status, {"Content-Type": content_type}, body))
                self.assertEqual((result["state"], result["http_status"]), (state, status))
                self.assertIsNone(result["excerpt"])

    def test_AC2_06a_dns_error_does_not_claim_policy_block(self):
        for resolver in (
            lambda *x: (),
            lambda *x: (_ for _ in ()).throw(OSError("synthetic DNS down")),
        ):
            with self.subTest(resolver=resolver):
                result = page_capture.capture_one(
                    URL, at=STAMP, resolver=resolver,
                    transport=lambda *x: self.fail("request after DNS failure"))
                self.assertEqual(result["state"], "connection_error")

    def test_AC2_06b_unexpected_compression_has_no_false_text(self):
        result = page_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver,
            transport=lambda *x: page_capture.PageResponse(
                200, {"Content-Type": "text/html", "Content-Encoding": "gzip"},
                b"synthetic gzip placeholder"))
        self.assertEqual(result["state"], "invalid_response")
        self.assertIsNone(result["excerpt"])

    def test_AC2_07_redirect_limit(self):
        requests = []
        def transport(url, ips, deadline):
            requests.append(url)
            return page_capture.PageResponse(302, {"Location": "/loop"}, b"")
        result = page_capture.capture_one(URL, at=STAMP, resolver=self.resolver, transport=transport)
        self.assertEqual(result["state"], "redirect_limit")
        self.assertEqual(len(requests), page_capture.MAX_REDIRECTS + 1)

    def test_AC2_08_network_failure_captured_as_state(self):
        result = page_capture.capture_one(URL, at=STAMP, resolver=self.resolver,
            transport=lambda *x: (_ for _ in ()).throw(OSError("SENSITIVE-ERROR")))
        self.assertEqual(result["state"], "connection_error")
        self.assertNotIn("SENSITIVE", json.dumps(result))

    def test_AC2_09_explicit_flag_and_invalid_input_before_any_access(self):
        for args in (
            ["page", "capture", "--post-id", "123"],
            ["page", "capture", "--post-id", "wrong", "--confirm-network-request"],
            ["page", "capture", "--post-id", "123", "--url-index", "-1", "--confirm-network-request"],
        ):
            with self.subTest(args=args), patch.object(cli, "bookmark_preflight",
                side_effect=AssertionError("preflight forbidden")) as pre:
                rc, out, err = self.run_cmd(args)
                self.assertEqual(rc, 2)
                self.assertEqual(json.loads(err)["error_category"], "invalid_input")
                self.assertEqual(self.requests, [])
                pre.assert_not_called()

    def test_AC2_10_bad_store_preflight_does_not_fetch(self):
        before = self.main.read_bytes()
        self.extras.write_text("SENSITIVE INVALID", encoding="utf-8")
        rc, out, err = self.run_cmd()
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(err)["error_category"], "storage_error")
        self.assertEqual(self.requests, [])
        self.assertEqual(self.main.read_bytes(), before)
        self.assertNotIn("SENSITIVE", err)

    def test_AC2_11_repeat_capture_is_idempotent_for_fixed_clock(self):
        rc, out, err = self.run_cmd()
        self.assertEqual(rc, 0)
        initial = self.page_path.read_bytes()
        self.assertEqual(self.run_cmd()[0], 0)
        self.assertEqual(initial, self.page_path.read_bytes())

    def test_AC2_12_existing_page_corruption_stops_before_fetch(self):
        self.page_path.write_text('{"schema_version":"1","subject_id":"42","items":{"123:0":{}}}')
        original = self.page_path.read_bytes()
        rc, _, err = self.run_cmd()
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(err)["error_category"], "storage_error")
        self.assertEqual(self.page_path.read_bytes(), original)
        self.assertEqual(self.requests, [])

    def test_AC2_13_storage_replacement_failure_preserves_existing_bytes(self):
        self.assertEqual(self.run_cmd()[0], 0)
        original = self.page_path.read_bytes()
        with patch.object(page_capture.os, "replace", side_effect=OSError("PRIVATE-ERROR")):
            rc, stdout, stderr = self.run_cmd()
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(stderr)["error_category"], "storage_error")
        self.assertEqual(self.page_path.read_bytes(), original)
        self.assertNotIn("PRIVATE-ERROR", stderr)
        self.assertEqual(list(self.data.glob("*.tmp")), [])

    def test_AC2_13a_loopback_slow_trickle_hits_entire_capture_budget(self):
        # Execute the actual TCP/HTTP transport against loopback only.
        # No public DNS, URL, X API or real user data is consulted.
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        def server():
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(2)
                    conn.recv(4096)
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                                 b"Content-Length: 40\r\nConnection: close\r\n\r\n")
                    for _ in range(20):
                        conn.sendall(b"x")
                        time.sleep(0.06)
            except OSError:
                pass
            finally:
                listener.close()
        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        # Validate the actual socket loopback path while keeping all external
        # target guards active in production (patched in this test only).
        def safe_loopback_url(url):
            # Use plaintext HTTP only for this synthetic loopback server.
            return urlsplit(url)._replace(scheme="http"), "example.org", port
        started = time.monotonic()
        with patch.object(page_capture, "TIMEOUT_SECONDS", 0.25), \
             patch.object(page_capture, "_url_parts", side_effect=safe_loopback_url), \
             patch.object(page_capture, "_valid_public_ip", return_value=True):
            outcome = page_capture.capture_one(
                URL, at=STAMP, resolver=lambda *args: ("127.0.0.1",))
        elapsed = time.monotonic() - started
        self.assertEqual(outcome["state"], "timeout")
        self.assertLess(elapsed, 0.80)
        thread.join(timeout=1.5)

    def test_AC2_13aa_loopback_slow_header_hits_absolute_deadline(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def server():
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(2)
                    conn.recv(4096)
                    conn.sendall(b"HTTP/1.1 200 OK\r\nX-Drip: ")
                    for _ in range(12):
                        conn.sendall(b"x")
                        time.sleep(0.06)
            except OSError:
                pass
            finally:
                listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        started = time.monotonic()
        with (
            patch.object(page_capture, "TIMEOUT_SECONDS", 0.25),
            patch.object(page_capture, "_url_parts",
                         side_effect=lambda url: (urlsplit(url)._replace(scheme="http"),
                                                  "example.org", port)),
            patch.object(page_capture, "_valid_public_ip", return_value=True),
        ):
            outcome = page_capture.capture_one(
                URL, at=STAMP, resolver=lambda *args: ("127.0.0.1",))
        elapsed = time.monotonic() - started
        self.assertEqual(outcome["state"], "timeout")
        self.assertLess(elapsed, 0.8)
        thread.join(timeout=1.5)

    def test_AC2_13ab_loopback_http_happy_path_uses_real_transport(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def server():
            try:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(2)
                    conn.recv(4096)
                    conn.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        + b"Content-Length: " + str(len(SAMPLE)).encode("ascii")
                        + b"\r\nConnection: close\r\n\r\n" + SAMPLE
                    )
            except OSError:
                pass
            finally:
                listener.close()

        thread = threading.Thread(target=server, daemon=True)
        thread.start()
        with (
            patch.object(page_capture, "_url_parts",
                         side_effect=lambda url: (urlsplit(url)._replace(scheme="http"),
                                                  "example.org", port)),
            patch.object(page_capture, "_valid_public_ip", return_value=True),
        ):
            outcome = page_capture.capture_one(
                URL, at=STAMP, resolver=lambda *args: ("127.0.0.1",))
        self.assertEqual(outcome["state"], "captured")
        self.assertEqual(outcome["title"], "Synthetic & Title")
        self.assertEqual(outcome["excerpt"], "Heading first paragraph. Second & final.")
        thread.join(timeout=1.5)

    def test_AC2_13b_deadline_interrupts_incremental_html_parser(self):
        body = b"<html><body>" + b"word " * 5000 + b"</body></html>"
        actual_feed = page_capture._PageHTML.feed
        calls = []
        def slow_once(parser, part):
            calls.append(len(part))
            if len(calls) == 1:
                time.sleep(0.05)
            return actual_feed(parser, part)
        with patch.object(page_capture, "TIMEOUT_SECONDS", 0.03), \
             patch.object(page_capture._PageHTML, "feed", slow_once):
            outcome = page_capture.capture_one(
                URL, at=STAMP, resolver=self.resolver,
                transport=lambda *args: page_capture.PageResponse(
                    200, {"Content-Type": "text/html"}, body))
        self.assertEqual(outcome["state"], "timeout")
        self.assertLess(len(calls), 4)

    def test_AC2_13bb_valid_long_html_elements_preserved_and_saved(self):
        """Large, well-formed inline content is not incomplete markup.

        Protects the exact independent L2 MAJOR regression: the old arbitrary
        16-KiB rawdata guard rejected large valid script/style/comment/attrs.
        No real website or external network is accessed.
        """
        head = (b'<html><head><title>Synthetic title</title>'
                b'<meta name="description" content="Synthetic description">')
        tail = b'</head><body><article><p>Article text</p></article></body></html>'
        elements = {
            "script_20000": b"<script>" + b"x" * 20000 + b"</script>",
            "style_20000": b"<style>" + b"x" * 20000 + b"</style>",
            "inline_json_100k": (b'<script type="application/json">'
                                + b'{"padding":"' + b"x" * 100000 + b'"}'
                                + b"</script>"),
            "comment_30000": b"<!--" + b"x" * 30000 + b"-->",
            "long_attribute_30000": (b'<meta name="synthetic" content="data:image/png;base64,'
                                     + b"A" * 30000 + b'">'),
        }
        primary = bookmark_store.preflight(self.env)
        enrich = bookmark_enrichment.preflight(primary)
        original = (self.main.read_bytes(), self.extras.read_bytes())
        for name, element in elements.items():
            with self.subTest(name=name):
                body = head + element + tail
                self.assertLess(len(body), page_capture.MAX_HTML_BYTES)
                result = page_capture.capture_one(
                    URL, at=STAMP, resolver=self.resolver,
                    transport=lambda *args, payload=body: page_capture.PageResponse(
                        200, {"Content-Type": "text/html"}, payload))
                self.assertEqual(result["state"], "captured")
                self.assertEqual(result["title"], "Synthetic title")
                self.assertEqual(result["description"], "Synthetic description")
                self.assertEqual(result["excerpt"], "Article text")
                snapshot = page_capture.preflight(primary, enrich)
                page_capture.save(snapshot, subject_id="42", post_id="123",
                                  url_index=0, result=result)
                saved = json.loads(self.page_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["items"]["123:0"]["state"], "captured")
                self.assertEqual(saved["items"]["123:0"]["excerpt"], "Article text")
                self.assertEqual((self.main.read_bytes(), self.extras.read_bytes()), original)

    def test_AC2_13c_malformed_html_returns_stable_failure(self):
        body = b"<html><body>" + b"</" * 20000
        outcome = page_capture.capture_one(
            URL, at=STAMP, resolver=self.resolver,
            transport=lambda *args: page_capture.PageResponse(
                200, {"Content-Type": "text/html"}, body))
        self.assertEqual(outcome["state"], "invalid_response")
        self.assertIsNone(outcome["excerpt"])

    def test_AC2_13d_redirect_fragment_is_not_a_network_target(self):
        observed = []
        def transport(url, ips, deadline):
            observed.append(url)
            if len(observed) == 1:
                return page_capture.PageResponse(302, {"Location": "/final#section"}, b"")
            return page_capture.PageResponse(200, {"Content-Type": "text/html"}, SAMPLE)
        output = page_capture.capture_one(
            URL + "#anchor", at=STAMP, resolver=self.resolver, transport=transport)
        self.assertEqual(output["state"], "captured")
        self.assertEqual(observed, [URL, "https://example.org/final"])
        self.assertEqual(output["requested_url"], URL + "#anchor")

    def test_AC2_13e_nat64_address_not_eligible_for_connection(self):
        for address in ("64:ff9b::7f00:1", "64:ff9b::a00:1"):
            with self.subTest(ip=address):
                output = page_capture.capture_one(
                    URL, at=STAMP, resolver=lambda *args: (address,),
                    transport=lambda *args: self.fail("No NAT64 transport"))
                self.assertEqual(output["state"], "blocked_target")

    def test_AC2_14_body_text_has_fixed_char_limit(self):
        large = b"<html><body>" + b"x" * (page_capture.MAX_PAGE_TEXT+123) + b"</body></html>"
        result = page_capture.capture_one(URL, at=STAMP, resolver=self.resolver,
            transport=lambda *x: page_capture.PageResponse(
                200, {"Content-Type": "text/html"}, large))
        self.assertEqual(len(result["excerpt"]), page_capture.MAX_PAGE_TEXT)


if __name__ == "__main__":
    unittest.main()
