"""Issue #77 stage 3 (SPEC-0009): one saved thread reference page, synthetic only.

No real network, X API, credentials or owner data: DNS and HTTP are replaced by
fakes, and all stores live in a temporary LOCALAPPDATA.
"""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_context import cli, page_capture, thread_pages


STAMP = "2026-11-28T08:00:00Z"
GIST = "https://gist.github.com/synthetic-user/0123456789abcdef"
REF_URL = "https://example.org/reference"
PUBLIC_IP = ("93.184.216.34",)

GIST_HTML = b'''<!DOCTYPE html><html><head><title>Synthetic gist</title>
<meta name="description" content="Synthetic gist description"></head><body>
<header>Site chrome to skip</header>
<div>Outside main sidebar</div>
<main><h1>plan.py</h1><p>A   short   intro.</p>
<pre>def run():
    if ready:
        return 1
</pre>
<table><tr><td class="blob-num" data-line-number="1"></td><td class="blob-code blob-code-inner">for x in y:</td></tr>
<tr><td class="blob-num" data-line-number="2"></td><td class="blob-code blob-code-inner">    print(x)</td></tr></table>
</main><footer>skip footer</footer></body></html>'''

SIMPLE_HTML = b'''<html><head><title>Ref</title></head><body><p>Reference body.</p></body></html>'''
EXCERPT_LABEL = "Page text excerpt (untrusted website quotation; layout preserved)"
FINAL_LABEL = "Network-observed final URL (last HTTP response; content only when captured)"


def _fences(view):
    """Minimal CommonMark backtick-fence scan: (label line before, content, span)."""
    lines = view.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        ticks = len(line) - len(line.lstrip("`"))
        if ticks >= 3 and "`" not in line[ticks:]:
            start = i
            j = i + 1
            while j < len(lines):
                close = lines[j]
                n = len(close) - len(close.lstrip("`"))
                if n >= ticks and not close[n:].strip():
                    break
                j += 1
            yield lines[start - 1], "\n".join(lines[start + 1:j]), (start, j)
            i = j + 1
        else:
            i += 1


def literal_fields(view):
    """Map ``Label:`` -> fenced literal content of the thread-page section."""
    section = view.split("### Saved thread reference pages", 1)[1]
    return {label.rstrip(":"): content for label, content, _ in _fences(section)}


def outside_fences(view):
    lines = view.split("\n")
    inside = set()
    for _, _, (start, end) in _fences(view):
        inside.update(range(start, end + 1))
    return "\n".join(line for n, line in enumerate(lines) if n not in inside)


def _post(post_id, *, replied_to=None, urls=(), source="full_archive_search"):
    return {
        "id": post_id, "text": f"synthetic text {post_id}", "text_source": "note_post",
        "author_id": "7", "author_username": "synthetic_author",
        "conversation_id": "100", "created_at": "2025-01-01T00:00:00.000Z",
        "replied_to_id": replied_to, "quoted_post_id": None, "source": source,
        "urls": list(urls),
    }


def _thread_record(bookmark_id="100", *, posts=None, refs=None):
    return {
        "bookmark_post_id": bookmark_id, "seed_role": "bookmarked_post",
        "bookmark_relation_to_target": "self", "target_post_id": bookmark_id,
        "retrieved_at": STAMP, "conversation_id": bookmark_id,
        "author_id": "7", "author_username": "synthetic_author",
        "search_query": f"conversation_id:{bookmark_id} from:synthetic_author to:synthetic_author -is:retweet",
        "search_max_results": 20, "search_state": "searched", "search_truncated": False,
        "excluded_unlinked_count": 0, "unverified_unlinked_count": 0,
        "unverified_missing_parent_ids": [], "completeness": "unverified_single_page",
        "root_state": "in_thread", "missing_parent_id": None,
        "thread_posts": posts if posts is not None else [
            _post(bookmark_id, source="post_lookup", urls=[
                {"url": "https://t.co/photo", "expanded_url": f"https://x.com/synthetic_author/status/{bookmark_id}/photo/1",
                 "display_url": "pic.x.com/photo"},
            ]),
            _post("101", replied_to=bookmark_id, urls=[
                {"url": "https://t.co/gist", "expanded_url": GIST, "display_url": "gist.github.com/synthetic…"},
                {"url": "https://t.co/onlyshort"},
            ]),
        ],
        "referenced_posts": refs if refs is not None else [{
            "id": "900", "relation": "quoted", "from_post_id": "101",
            "text": "referenced synthetic", "text_state": "recorded", "text_source": "post_text",
            "author_id": "8", "author_username": "other_author", "conversation_id": "900",
            "created_at": "2025-01-01T00:00:00.000Z",
            "urls": [{"url": "https://t.co/ref", "expanded_url": "https://example.org/old",
                      "unwound_url": REF_URL}],
        }],
    }


class ThreadPageCaptureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "x-context" / "data"
        self.data.mkdir(parents=True)
        self.main = self.data / "bookmarks-v1.json"
        self.threads = self.data / "bookmark-threads-v1.json"
        self.legacy_pages = self.data / "bookmark-pages-v1.json"
        self.store = self.data / "bookmark-thread-pages-v1.json"
        self.env = {"LOCALAPPDATA": str(self.root)}
        self.main.write_text(json.dumps({
            "store_schema_version": "1", "source": "x", "collection": "bookmarks",
            "subject": {"id": "42"}, "created_at": STAMP, "updated_at": STAMP,
            "items": [
                {"id": "100", "text": "Bookmarked root", "first_seen_at": STAMP, "last_seen_at": STAMP},
                {"id": "300", "text": "Bookmark without thread", "first_seen_at": STAMP, "last_seen_at": STAMP},
            ],
        }), encoding="utf-8")
        self.write_threads({"100": _thread_record()})
        self.requests = []
        self.dns = []
        self.replies = None

    def write_threads(self, items, subject="42"):
        self.threads.write_text(json.dumps({
            "schema_version": "1", "subject_id": subject, "items": items,
        }), encoding="utf-8")

    def resolver(self, host, port):
        self.dns.append(host)
        return PUBLIC_IP

    def transport(self, url, ips, deadline):
        self.requests.append(url)
        if self.replies:
            return self.replies.pop(0)
        body = GIST_HTML if url.startswith("https://gist.github.com/") else SIMPLE_HTML
        return page_capture.PageResponse(200, {"Content-Type": "text/html; charset=utf-8"}, body)

    def run_cmd(self, *extra, confirm=True):
        args = ["page", "capture", "--post-id", "100", *extra]
        if confirm:
            args.append("--confirm-network-request")
        out, err = io.StringIO(), io.StringIO()
        with (patch.object(page_capture, "_resolver", side_effect=self.resolver),
              patch.object(page_capture, "_transport", side_effect=self.transport),
              patch.object(page_capture, "utcnow", return_value=STAMP),
              patch.object(cli, "resolve_user_access_token",
                           side_effect=AssertionError("X credentials must never be read"))):
            rc = cli.main(args, environ=self.env, stdout=out, stderr=err)
        return rc, out.getvalue(), err.getvalue()

    def context(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with (patch.object(page_capture, "_resolver", side_effect=AssertionError("no DNS")),
              patch.object(page_capture, "_transport", side_effect=AssertionError("no network"))):
            rc = cli.main(["context", "--include-saved-details", *extra],
                          environ=self.env, stdout=out, stderr=err)
        return rc, out.getvalue(), err.getvalue()

    def stored(self):
        return json.loads(self.store.read_text(encoding="utf-8"))

    def snapshot_bytes(self):
        return {p.name: p.read_bytes() for p in sorted(self.data.iterdir()) if p.is_file()}

    # ---- AC-1 selection -------------------------------------------------
    def test_AC1_01_thread_post_url_selected_and_saved(self):
        before = self.snapshot_bytes()
        rc, stdout, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(self.requests, [GIST])
        self.assertEqual(json.loads(stdout), {
            "operation": "page", "post_id": "100", "source_post_id": "101", "url_index": 0,
            "state": "captured", "http_status": 200, "excerpt_truncated": False,
            "persistence_succeeded": True,
        })
        after = self.snapshot_bytes()
        self.assertEqual({k: v for k, v in after.items() if k != self.store.name}, before)
        value = self.stored()
        self.assertEqual((value["schema_version"], value["subject_id"]), ("1", "42"))
        record = value["items"]["100:101:0"]
        self.assertEqual(
            {k: record[k] for k in ("bookmark_post_id", "source_post_id", "url_index",
                                     "requested_url", "final_url", "http_status", "state",
                                     "retrieved_at", "title", "description")},
            {"bookmark_post_id": "100", "source_post_id": "101", "url_index": 0,
             "requested_url": GIST, "final_url": GIST, "http_status": 200, "state": "captured",
             "retrieved_at": STAMP, "title": "Synthetic gist",
             "description": "Synthetic gist description"})

    def test_AC1_02_referenced_post_prefers_unwound_url(self):
        rc, _, stderr = self.run_cmd("--source-post-id", "900", "--url-index", "0")
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(self.requests, [REF_URL])
        self.assertEqual(self.stored()["items"]["100:900:0"]["requested_url"], REF_URL)

    def test_AC1_03_invalid_selection_stops_before_dns_and_write(self):
        cases = [
            ("--source-post-id", "101"),                           # index must be explicit
            ("--source-post-id", "101", "--url-index", "50"),
            ("--source-post-id", "101", "--url-index", "-1"),
            ("--source-post-id", "101", "--url-index", "2"),       # beyond saved URLs
            ("--source-post-id", "555", "--url-index", "0"),       # not in thread record
            ("--source-post-id", "abc", "--url-index", "0"),
            ("--source-post-id", "100", "--url-index", "0"),       # x.com photo URL
            ("--source-post-id", "101", "--url-index", "1"),       # unexpanded t.co
        ]
        before = self.snapshot_bytes()
        for extra in cases:
            with self.subTest(extra=extra):
                rc, stdout, stderr = self.run_cmd(*extra)
                self.assertEqual((rc, stdout), (2, ""))
                diag = json.loads(stderr)
                self.assertEqual((diag["error_category"], diag["external_requests_attempted"]),
                                 ("invalid_input", 0))
        self.assertEqual((self.requests, self.dns), ([], []))
        self.assertEqual(self.snapshot_bytes(), before)

    def test_AC1_04_unconfirmed_and_bookmark_scope_rejected(self):
        before = self.snapshot_bytes()
        rc, _, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0", confirm=False)
        self.assertEqual((rc, json.loads(stderr)["error_category"]), (2, "invalid_input"))
        for bookmark in ("300", "999"):
            with self.subTest(bookmark=bookmark):
                out, err = io.StringIO(), io.StringIO()
                with (patch.object(page_capture, "_resolver", side_effect=self.resolver),
                      patch.object(page_capture, "_transport", side_effect=self.transport)):
                    rc = cli.main(["page", "capture", "--post-id", bookmark, "--source-post-id", "101",
                                   "--url-index", "0", "--confirm-network-request"],
                                  environ=self.env, stdout=out, stderr=err)
                self.assertEqual((rc, json.loads(err.getvalue())["error_category"]), (2, "invalid_input"))
        self.assertEqual((self.requests, self.dns), ([], []))
        self.assertEqual(self.snapshot_bytes(), before)

    def test_AC1_05_duplicate_source_requires_identical_url(self):
        same = _thread_record(refs=[{
            "id": "101", "relation": "replied_to", "from_post_id": "100",
            "text": None, "text_state": "not_returned",
            "author_id": None, "author_username": None, "conversation_id": None, "created_at": None,
            "urls": [{"url": "https://t.co/gist", "expanded_url": GIST}],
        }])
        self.write_threads({"100": same})
        rc, _, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(self.requests, [GIST])

        self.requests.clear()
        self.store.unlink()
        ambiguous = json.loads(json.dumps(same))
        ambiguous["referenced_posts"][0]["urls"][0]["expanded_url"] = REF_URL
        self.write_threads({"100": ambiguous})
        rc, _, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual((rc, json.loads(stderr)["error_category"]), (2, "invalid_input"))
        self.assertEqual((self.requests, self.store.exists()), ([], False))

    def test_AC1_06_legacy_path_range_and_default_unchanged(self):
        rc, _, stderr = self.run_cmd("--url-index", "20")
        self.assertEqual((rc, json.loads(stderr)["error_category"]), (2, "invalid_input"))
        self.assertEqual(self.requests, [])
        self.assertFalse(self.store.exists())

    def test_AC1_07_mixed_subject_thread_store_stops_before_network(self):
        self.write_threads({"100": _thread_record()}, subject="43")
        before = self.snapshot_bytes()
        rc, _, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(stderr)["external_requests_attempted"], 0)
        self.assertEqual((self.requests, self.dns, self.snapshot_bytes()), ([], [], before))

    # ---- AC-2 capture ---------------------------------------------------
    def test_AC2_01_redirect_to_x_is_blocked_and_recorded(self):
        self.replies = [page_capture.PageResponse(302, {"Location": "https://mobile.twitter.com/i/status/1"}, b"")]
        rc, stdout, _ = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(stdout)["state"], "blocked_target")
        self.assertEqual(self.requests, [GIST])
        record = self.stored()["items"]["100:101:0"]
        self.assertEqual((record["state"], record["excerpt"], record["title"]), ("blocked_target", None, None))

    def test_AC2_02_public_redirect_revalidated_and_failures_distinct(self):
        self.replies = [
            page_capture.PageResponse(301, {"Location": "/moved"}, b""),
            page_capture.PageResponse(404, {"Content-Type": "text/html"}, b"<p>nope</p>"),
        ]
        rc, stdout, _ = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(self.requests, [GIST, "https://gist.github.com/moved"])
        record = self.stored()["items"]["100:101:0"]
        self.assertEqual((record["state"], record["http_status"], record["excerpt"], record["excerpt_truncated"]),
                         ("http_error", 404, None, False))
        self.assertEqual(self.dns, ["gist.github.com", "gist.github.com"])

    def test_AC2_03_technical_extraction_keeps_code_layout_and_prefers_main(self):
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        excerpt = self.stored()["items"]["100:101:0"]["excerpt"]
        self.assertIn("def run():\n    if ready:\n        return 1", excerpt)
        self.assertIn("for x in y:\n    print(x)", excerpt)
        self.assertIn("A short intro.", excerpt)
        self.assertTrue(excerpt.startswith("plan.py"))
        for skipped in ("Site chrome", "Outside main sidebar", "skip footer"):
            self.assertNotIn(skipped, excerpt)

    def test_AC2_04_truncation_is_recorded_not_silent(self):
        long_body = ("<html><body><main><pre>" + "x = 1\n" * 2000 + "</pre></main></body></html>").encode()
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, long_body)]
        rc, stdout, _ = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 0)
        self.assertTrue(json.loads(stdout)["excerpt_truncated"])
        record = self.stored()["items"]["100:101:0"]
        self.assertEqual(len(record["excerpt"]), page_capture.MAX_PAGE_TEXT)
        self.assertTrue(record["excerpt_truncated"])

    def test_AC2_05_legacy_extraction_unchanged(self):
        title, description, excerpt = page_capture._extract_html(GIST_HTML)
        self.assertEqual(title, "Synthetic gist")
        self.assertNotIn("\n", excerpt)
        self.assertIn("Outside main sidebar", excerpt)

    # ---- AC-3 storage ---------------------------------------------------
    def test_AC3_01_second_record_preserves_first_and_other_files(self):
        self.legacy_pages.write_text("legacy bytes are not parsed here", encoding="utf-8")
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        first = self.stored()["items"]["100:101:0"]
        before = {k: v for k, v in self.snapshot_bytes().items() if k != self.store.name}
        self.run_cmd("--source-post-id", "900", "--url-index", "0")
        items = self.stored()["items"]
        self.assertEqual(set(items), {"100:101:0", "100:900:0"})
        self.assertEqual(items["100:101:0"], first)
        self.assertEqual({k: v for k, v in self.snapshot_bytes().items() if k != self.store.name}, before)

    def test_AC3_02_corrupt_or_inconsistent_store_stops_before_network(self):
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        good = self.stored()
        bad_key = json.loads(json.dumps(good))
        bad_key["items"]["100:101:1"] = bad_key["items"].pop("100:101:0")
        x_target = json.loads(json.dumps(good))
        x_target["items"]["100:101:0"]["requested_url"] = "https://x.com/a/status/1"
        other_subject = json.loads(json.dumps(good))
        other_subject["subject_id"] = "43"
        for raw in (b"{not json", json.dumps(bad_key).encode(), json.dumps(x_target).encode(),
                    json.dumps(other_subject).encode()):
            with self.subTest(raw=raw[:40]):
                self.store.write_bytes(raw)
                self.requests.clear()
                self.dns.clear()
                rc, _, stderr = self.run_cmd("--source-post-id", "900", "--url-index", "0")
                self.assertEqual((rc, json.loads(stderr)["error_category"]), (2, "storage_error"))
                self.assertEqual((self.requests, self.dns, self.store.read_bytes()), ([], [], raw))

    def test_AC3_03_validator_rejects_out_of_range_record(self):
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        record = self.stored()["items"]["100:101:0"]
        self.assertTrue(thread_pages._valid_record(record))
        for key, value in (("url_index", 50), ("excerpt_truncated", "no"), ("state", "fetched"),
                           ("source_post_id", "1a")):
            with self.subTest(key=key):
                self.assertFalse(thread_pages._valid_record({**record, key: value}))

    # ---- AC-4 display ---------------------------------------------------
    def test_AC4_01_markdown_shows_page_source_and_state_offline(self):
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        before = self.snapshot_bytes()
        for extra in (("--post-id", "100"), ()):
            with self.subTest(extra=extra):
                rc, view, stderr = self.context(*extra)
                self.assertEqual((rc, stderr), (0, ""))
                self.assertIn("### Saved thread reference pages (untrusted website content)", view)
                self.assertIn("#### Thread page: Post 101 URL 0", view)
                self.assertIn("Source Post relation: thread_post", view)
                self.assertIn("Page capture state: captured", view)
                self.assertIn("Excerpt truncated: false", view)
                fields = literal_fields(view)
                self.assertEqual(fields["Requested page URL (from saved thread record)"], GIST)
                self.assertIn("\n    if ready:\n", fields[EXCERPT_LABEL])
        self.assertEqual(self.snapshot_bytes(), before)

    def test_AC4_02_changed_url_or_missing_thread_is_stale_without_old_text(self):
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        changed = _thread_record()
        changed["thread_posts"][1]["urls"][0]["expanded_url"] = "https://example.org/changed"
        self.write_threads({"100": changed})
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertIn("Page capture state: stale_reference", view)
        self.assertNotIn("if ready", view)
        self.write_threads({})
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertIn("Page capture state: stale_reference", view)
        self.assertNotIn("if ready", view)

    def test_AC4_03_no_sidecar_means_no_new_section(self):
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertNotIn("Saved thread reference pages", view)

    def test_AC4_04_untrusted_excerpt_cannot_inject_headings(self):
        hostile = b"<html><body><main><pre># injected heading\n## more</pre></main></body></html>"
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, hostile)]
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        _, view, _ = self.context("--post-id", "100")
        # Only inside a fenced code block, where CommonMark does not parse headings.
        self.assertEqual(literal_fields(view)[EXCERPT_LABEL], "# injected heading\n## more")
        self.assertEqual(view.count("\n# injected heading"), 1)

    # ---- L2 review remediation (PR #81 review 6096552383) ---------------
    def test_M1_blank_lines_and_tabs_survive_save_and_markdown(self):
        body = (b"<html><body><main><pre>first\n\n\n\tsecond</pre>"
                b"<table><tr><td class=\"blob-num\" data-line-number=\"1\"></td>"
                b"<td class=\"blob-code blob-code-inner\">alpha</td></tr>"
                b"<tr><td class=\"blob-num\" data-line-number=\"2\"></td>"
                b"<td class=\"blob-code blob-code-inner\"></td></tr>"
                b"<tr><td class=\"blob-num\" data-line-number=\"3\"></td>"
                b"<td class=\"blob-code blob-code-inner\">\tomega</td></tr></table>"
                b"<p>after   text</p></main></body></html>")
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, body)]
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        expected = "first\n\n\n\tsecond\nalpha\n\n\tomega\nafter text"
        self.assertEqual(self.stored()["items"]["100:101:0"]["excerpt"], expected)
        _, view, _ = self.context("--post-id", "100")
        self.assertEqual(literal_fields(view)[EXCERPT_LABEL], expected)
        self.assertNotIn("\\u0009", view)

    def capture_and_view(self, body):
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, body)]
        rc, stdout, _ = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 0)
        record = self.stored()["items"]["100:101:0"]
        _, view, _ = self.context("--post-id", "100")
        return json.loads(stdout), record, literal_fields(view).get(EXCERPT_LABEL)

    def test_M1r_pre_leading_inner_trailing_blank_lines_and_tabs_kept(self):
        code = "\n\n\n\tfirst\n\n\n    last\n\n\n"
        _, record, shown = self.capture_and_view(
            ("<html><body><main><pre>" + code + "</pre></main></body></html>").encode())
        self.assertEqual(record["excerpt"], code)
        self.assertEqual(shown, code)
        self.assertFalse(record["excerpt_truncated"])

    def test_M1r_gist_table_leading_inner_trailing_empty_code_lines_kept(self):
        def row(n, text):
            return (f'<tr><td class="blob-num" data-line-number="{n}"></td>'
                    f'<td class="blob-code blob-code-inner">{text}</td></tr>')
        cells = ["", "", "alpha", "", "", "", "\tomega", "", ""]
        body = ("<html><body><main><table>"
                + "".join(row(n, text) for n, text in enumerate(cells, 1))
                + "</table></main></body></html>").encode()
        expected = "\n".join(cells)
        _, record, shown = self.capture_and_view(body)
        self.assertEqual(record["excerpt"], expected)
        self.assertEqual(shown, expected)

    def test_M1r_truncation_boundary_counts_code_blank_lines(self):
        for total in (4095, 4096, 4097):
            with self.subTest(total=total):
                if self.store.exists():
                    self.store.unlink()
                code = "\n\n" + "y" * (total - 2)
                out, record, shown = self.capture_and_view(
                    ("<html><body><main><pre>" + code + "</pre></main></body></html>").encode())
                expected = code[:page_capture.MAX_PAGE_TEXT]
                self.assertEqual(record["excerpt"], expected)
                self.assertEqual(shown, expected)
                self.assertEqual(record["excerpt_truncated"], total > page_capture.MAX_PAGE_TEXT)
                self.assertEqual(out["excerpt_truncated"], total > page_capture.MAX_PAGE_TEXT)

    def test_M2_untrusted_markdown_is_literal_and_cannot_close_fence(self):
        hostile = ("**literal** [link](https://evil.example/) ![img](https://evil.example/i.png)\n"
                   "<b>html</b> _em_ `code`\n````\n```text\n> quote")
        body = ("<html><head><title>**t** [x](https://evil.example/)</title></head><body><main><pre>"
                + hostile.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                + "</pre></main></body></html>").encode()
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, body)]
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        fields = literal_fields(view)
        self.assertEqual(fields[EXCERPT_LABEL], hostile)
        self.assertEqual(fields["Page title (untrusted website content)"], "**t** [x](https://evil.example/)")
        # Nothing of the hostile text leaks outside a fence.
        outside = outside_fences(view)
        for token in ("**literal**", "](https://evil.example", "<b>", "> quote"):
            self.assertNotIn(token, outside)

    def test_M2_fenced_output_bound_with_backtick_heavy_excerpt(self):
        heavy = "<html><body><main><pre>" + "`" * 4096 + "</pre></main></body></html>"
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, heavy.encode())]
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertEqual(literal_fields(view)[EXCERPT_LABEL], "`" * 4096)

    def test_M2_output_bounds_with_50_worst_case_records(self):
        urls = [{"expanded_url": f"https://example.org/p{i}"} for i in range(50)]
        record = _thread_record()
        record["thread_posts"][1]["urls"] = urls
        self.write_threads({"100": record})
        # Escape-heavy text: backtick runs, controls, bidi marks, HTML specials.
        excerpt = ("`" * 7 + "\x01‮&<>\t") * 300
        excerpt = excerpt[:page_capture.MAX_PAGE_TEXT]
        items = {}
        for i in range(50):
            items[f"100:101:{i}"] = {
                "bookmark_post_id": "100", "source_post_id": "101", "url_index": i,
                "requested_url": f"https://example.org/p{i}", "final_url": f"https://example.org/p{i}",
                "http_status": 200, "retrieved_at": STAMP, "state": "captured",
                "title": "`" * 512, "description": "\x02" * 1024, "excerpt": excerpt,
                "excerpt_truncated": True,
            }
        self.store.write_text(json.dumps({"schema_version": "1", "subject_id": "42", "items": items}),
                              encoding="utf-8")
        rc, view, stderr = self.context("--post-id", "100")
        self.assertEqual((rc, stderr), (0, ""))
        self.assertEqual(view.count("#### Thread page: Post 101 URL"), 50)
        self.assertNotIn("\x01", view)
        self.assertNotIn("‮", view)
        self.assertGreater(len(view.encode("utf-8")), 256 * 1024)
        # Without --post-id the existing 256 KiB combined cap still fails closed.
        rc, view, stderr = self.context()
        self.assertEqual((rc, view, json.loads(stderr)["error_category"]), (2, "", "storage_error"))

    def test_m1_redirect_to_x_on_last_allowed_get_is_blocked_target(self):
        self.replies = [
            page_capture.PageResponse(302, {"Location": "/one"}, b""),
            page_capture.PageResponse(302, {"Location": "/two"}, b""),
            page_capture.PageResponse(302, {"Location": "https://t.co/synthetic"}, b""),
        ]
        rc, stdout, _ = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual(rc, 0)
        self.assertEqual(self.requests, [GIST, "https://gist.github.com/one", "https://gist.github.com/two"])
        self.assertEqual(self.dns, ["gist.github.com"] * 3)
        record = self.stored()["items"]["100:101:0"]
        self.assertEqual((record["state"], record["final_url"], record["http_status"]),
                         ("blocked_target", "https://gist.github.com/two", 302))

    def test_m1_legacy_capture_keeps_redirect_limit(self):
        replies = [page_capture.PageResponse(302, {"Location": loc}, b"")
                   for loc in ("/one", "/two", "https://t.co/synthetic")]
        result = page_capture.capture_one(GIST, at=STAMP, resolver=self.resolver,
                                          transport=lambda u, i, d: replies.pop(0))
        self.assertEqual(result["state"], "redirect_limit")

    def test_m2_http_error_shows_observed_final_url(self):
        self.replies = [
            page_capture.PageResponse(301, {"Location": "/other"}, b""),
            page_capture.PageResponse(404, {"Content-Type": "text/html"}, b"<p>missing</p>"),
        ]
        self.run_cmd("--source-post-id", "101", "--url-index", "0")
        _, view, _ = self.context("--post-id", "100")
        self.assertIn("Page capture state: http_error", view)
        self.assertEqual(literal_fields(view)[FINAL_LABEL], "https://gist.github.com/other")
        self.assertNotIn(EXCERPT_LABEL, literal_fields(view))


if __name__ == "__main__":
    unittest.main()
