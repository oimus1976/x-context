"""Issue #77 reference-page capture quality (SPEC-0009 Q-1..Q-4), synthetic only.

No real network, X API, credentials or owner data: DNS and HTTP are faked and
all stores live in a temporary LOCALAPPDATA. The Gist-like markup below is a
synthetic shape based on public GitHub Gist class names (``file``,
``gist-blob-name``, ``blob-wrapper``, ``markdown-body``, ``blob-num``); it was
not compared with the real page DOM.
"""
import hashlib
import io
import json
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from x_context import cli, page_capture, thread_pages
from x_context import combined_context

import test_thread_page_capture as stage3
from test_thread_page_capture import EXCERPT_LABEL, GIST, STAMP, literal_fields

TECH_MAX = page_capture.TECHNICAL_MAX_PAGE_TEXT
DISPLAY = combined_context.THREAD_PAGE_DISPLAY_CHARS
BUDGET = combined_context.FULL_PAGE_TEXT_BUDGET_CHARS

_UI = ('<div class="gisthead"><div class="pagehead-actions">'
       '<button>Embed</button><button>Share</button><button>Clone via HTTPS</button>'
       '<a>Download ZIP</a><button>Star</button><span>12</span></div>'
       '<nav class="UnderlineNav"><a>Code</a><a>Revisions 3</a><a>Stars 12</a></nav></div>')

DIAGRAM = ("+--------+      +--------+\n"
           "| client | ---> | server |\n"
           "+--------+      +--------+\n"
           "\n"
           "\tindented\twith tabs")

QUALITY_HTML = ('''<!DOCTYPE html><html><head><title>Synthetic multi-file gist</title></head><body>
<header>Site chrome</header>
<main>''' + _UI + _UI + '''
<div class="file" id="file-a-py">
 <div class="file-header"><div class="file-actions"><a>Raw</a></div>
  <strong class="gist-blob-name">a.py</strong></div>
 <div class="Box-body blob-wrapper data type-python">
  <table class="highlight">
   <tr><td class="blob-num js-line-number" data-line-number="1">1</td><td class="blob-code blob-code-inner">def share():</td></tr>
   <tr><td class="blob-num js-line-number" data-line-number="2">2</td><td class="blob-code blob-code-inner"></td></tr>
   <tr><td class="blob-num js-line-number" data-line-number="3">3</td><td class="blob-code blob-code-inner">\treturn "Embed"</td></tr>
  </table>
 </div>
</div>
<div class="file" id="file-notes-md">
 <div class="file-header"><div class="file-actions"><a>Raw</a></div>
  <strong class="gist-blob-name">notes.md</strong></div>
 <div class="Box-body readme blob"><article class="markdown-body entry-content">
  <h1>Notes</h1><p>Use   Share and   Embed  from the menu.</p>
<pre>''' + DIAGRAM + '''</pre>
 </article></div>
</div>
<div class="timeline-comment"><div class="comment-body markdown-body"><p>Someone else's comment</p></div></div>
</main><footer>Footer chrome</footer></body></html>''').encode("utf-8")

QUALITY_EXPECTED = "\n".join([
    "a.py",
    "def share():",
    "",
    '\treturn "Embed"',
    "notes.md",
    "Notes",
    "Use Share and Embed from the menu.",
    DIAGRAM,
])


def _long_text(total: int) -> str:
    """Deterministic ASCII/Japanese/code text of exactly ``total`` characters."""
    unit = "日本語の本文と code: x = 1  # コメント\n\tindent\n"
    text = (unit * (total // len(unit) + 1))[:total - len("END-MARKER")] + "END-MARKER"
    return text


def _pre_page(text: str) -> bytes:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return ("<html><body><main><pre>" + escaped + "</pre></main></body></html>").encode("utf-8")


def _record(index: int, excerpt: str, *, truncated: bool = False) -> dict:
    return {
        "bookmark_post_id": "100", "source_post_id": "101", "url_index": index,
        "requested_url": f"https://example.org/p{index}", "final_url": f"https://example.org/p{index}",
        "http_status": 200, "retrieved_at": STAMP, "state": "captured",
        "title": "t", "description": None, "excerpt": excerpt, "excerpt_truncated": truncated,
    }


class ReferenceCaptureQualityTests(stage3.ThreadPageCaptureTests):
    """Reuses the stage-3 fixture (stores, fake DNS/HTTP, CLI helpers)."""

    def capture(self, body: bytes):
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"}, body)]
        rc, stdout, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual((rc, stderr), (0, ""))
        return json.loads(stdout), self.stored()["items"]["100:101:0"]

    def write_records(self, records):
        record = json.loads(json.dumps(self._thread()))
        record["thread_posts"][1]["urls"] = [{"expanded_url": r["requested_url"]} for r in records]
        self.write_threads({"100": record})
        self.store.write_text(json.dumps({"schema_version": "1", "subject_id": "42", "items": {
            f"100:101:{r['url_index']}": r for r in records}}, ensure_ascii=False), encoding="utf-8")

    def _thread(self):
        return json.loads(self.threads.read_text(encoding="utf-8"))["items"]["100"]

    # ---- Q-1 body quality ------------------------------------------------
    def test_Q1_01_gist_file_bodies_exclude_ui_line_numbers_and_comments(self):
        out, record = self.capture(QUALITY_HTML)
        self.assertEqual(record["excerpt"], QUALITY_EXPECTED)
        self.assertFalse(record["excerpt_truncated"])
        for chrome in ("Download ZIP", "Clone via HTTPS", "Revisions 3", "Raw", "Site chrome",
                       "Footer chrome", "Someone else's comment"):
            self.assertNotIn(chrome, record["excerpt"])
        # UI words inside file bodies are kept (no global string removal).
        self.assertIn("Use Share and Embed", record["excerpt"])

    def test_Q1_02_markdown_body_outside_gist_file_keeps_main_fallback(self):
        page = (b"<html><body><main><p>Intro</p><article class='markdown-body'><p>Doc</p>"
                b"</article></main><div>Outside</div></body></html>")
        _, record = self.capture(page)
        self.assertEqual(record["excerpt"], "Intro\nDoc")

    def test_Q1_03_unidentifiable_or_empty_file_region_falls_back(self):
        empty_region = (b"<html><body><main><p>Main text</p><div class='file'>"
                        b"<div class='blob-wrapper'><table><tr><td class='blob-num'>1</td></tr>"
                        b"</table></div></div></main></body></html>")
        _, record = self.capture(empty_region)
        self.assertEqual(record["excerpt"], "Main text\n1")
        self.store.unlink()
        no_main = b"<html><body><div class='x'><p>Body only</p></div></body></html>"
        _, record = self.capture(no_main)
        self.assertEqual(record["excerpt"], "Body only")
        self.store.unlink()
        out, record = self.capture(b"<html><body><div class='file'></div></body></html>")
        self.assertEqual((record["state"], record["excerpt"]), ("no_extractable_text", None))

    # ---- Q-2 storage volume ----------------------------------------------
    def test_Q2_01_long_mixed_text_is_saved_to_end_marker_and_reread(self):
        text = _long_text(20000)
        out, record = self.capture(_pre_page(text))
        self.assertEqual(record["excerpt"], text)
        self.assertTrue(record["excerpt"].endswith("END-MARKER"))
        self.assertFalse(record["excerpt_truncated"])
        self.assertFalse(out["excerpt_truncated"])
        snapshot = thread_pages.preflight(cli.bookmark_preflight(self.env))
        self.assertEqual(snapshot.value["items"]["100:101:0"]["excerpt"], text)

    def test_Q2_02_technical_limit_boundaries(self):
        for total in (TECH_MAX - 1, TECH_MAX, TECH_MAX + 1):
            with self.subTest(total=total):
                if self.store.exists():
                    self.store.unlink()
                text = "y" * total
                out, record = self.capture(_pre_page(text))
                self.assertEqual(record["excerpt"], text[:TECH_MAX])
                self.assertEqual(record["excerpt_truncated"], total > TECH_MAX)
                self.assertEqual(out["excerpt_truncated"], total > TECH_MAX)

    def test_Q2_03_worst_case_json_escaping_fits_worker_and_parent_bounds(self):
        # Control characters escape to 6 JSON bytes each (\\u0001).
        title = "\x01" * 600
        body = ("<html><head><title>" + title + "</title><meta name='description' content='"
                + "\x02" * 1100 + "'></head><body><main><pre>" + "\x01" * (TECH_MAX + 10)
                + "</pre></main></body></html>").encode("utf-8")
        self.assertLessEqual(len(body), page_capture.MAX_HTML_BYTES)
        result = page_capture._extract_html(body, technical=True)
        self.assertEqual(len(result[2]), TECH_MAX)
        self.assertTrue(result[3])
        raw = json.dumps(list(result), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertGreater(len(raw), 6 * TECH_MAX)
        self.assertLessEqual(len(raw), page_capture.TECHNICAL_MAX_WORKER_BYTES)

    def test_Q2_04_worker_limits_match_parent_constants(self):
        worker = runpy.run_path(str(page_capture._HTML_WORKER_PATH))
        self.assertEqual(worker["MAX_TECHNICAL_TEXT"], page_capture.TECHNICAL_MAX_PAGE_TEXT)
        self.assertEqual(worker["MAX_TECHNICAL_OUTPUT_BYTES"], page_capture.TECHNICAL_MAX_WORKER_BYTES)
        self.assertEqual(worker["MAX_PAGE_TEXT"], page_capture.MAX_PAGE_TEXT)
        self.assertEqual(worker["MAX_OUTPUT_BYTES"], page_capture.MAX_WORKER_BYTES)

    def test_Q2_05_full_store_fails_closed_without_changing_bytes(self):
        filler = _long_text(TECH_MAX)
        records = [_record(i, filler) for i in range(50)]
        # Fill close to 16 MiB with valid records across several bookmarks.
        items = {}
        n = 0
        while True:
            r = dict(records[n % 50], bookmark_post_id="100", source_post_id=str(1000 + n // 50))
            items[f"100:{r['source_post_id']}:{r['url_index']}"] = r
            n += 1
            size = len(json.dumps({"schema_version": "1", "subject_id": "42", "items": items},
                                  ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
            if size > page_capture.MAX_STORE_BYTES - 100_000:
                break
        self.store.write_bytes((json.dumps({"schema_version": "1", "subject_id": "42", "items": items},
                                           ensure_ascii=False, separators=(",", ":"), sort_keys=True)
                                + "\n").encode("utf-8"))
        before = self.snapshot_bytes()
        self.replies = [page_capture.PageResponse(200, {"Content-Type": "text/html"},
                                                  _pre_page(_long_text(TECH_MAX)))]
        rc, stdout, stderr = self.run_cmd("--source-post-id", "101", "--url-index", "0")
        self.assertEqual((rc, stdout, json.loads(stderr)["error_category"]), (2, "", "storage_error"))
        self.assertEqual(self.snapshot_bytes(), before)

    def test_Q2_06_legacy_path_limits_unchanged(self):
        long_page = _pre_page("z" * 10000)
        title, description, excerpt = page_capture._extract_html(long_page)
        self.assertEqual(len(excerpt), page_capture.MAX_PAGE_TEXT)
        legacy = {"post_id": "1", "url_index": 0, "requested_url": GIST, "final_url": GIST,
                  "http_status": 200, "retrieved_at": STAMP, "state": "captured",
                  "title": None, "description": None, "excerpt": "z" * (page_capture.MAX_PAGE_TEXT + 1)}
        self.assertFalse(page_capture._valid_record(legacy))
        self.assertEqual(page_capture.MAX_PAGE_TEXT, 4096)

    # ---- Q-3 storage vs display ------------------------------------------
    def test_Q3_01_default_and_full_views_from_one_saved_record(self):
        text = _long_text(20000)
        self.capture(_pre_page(text))
        before = hashlib.sha256(self.store.read_bytes()).hexdigest()
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertEqual(literal_fields(view)[EXCERPT_LABEL], text[:DISPLAY])
        self.assertIn("Excerpt truncated: false", view)
        self.assertIn(f"Excerpt display: shortened (shown {DISPLAY} of 20000 saved characters;", view)
        rc, full, _ = self.context("--post-id", "100", "--full-page-text")
        self.assertEqual(rc, 0)
        self.assertEqual(literal_fields(full)[EXCERPT_LABEL], text)
        self.assertIn("Excerpt display: complete (all 20000 saved characters)", full)
        self.assertEqual(hashlib.sha256(self.store.read_bytes()).hexdigest(), before)

    def test_Q3_02_full_view_requires_explicit_single_bookmark(self):
        for extra in (("--full-page-text",), ):
            rc, view, err = self.context(*extra)
            self.assertEqual((rc, view, json.loads(err)["error_category"]), (2, "", "invalid_input"))
        out, err = io.StringIO(), io.StringIO()
        rc = cli.main(["context", "--post-id", "100", "--full-page-text"],
                      environ=self.env, stdout=out, stderr=err)
        self.assertEqual((rc, out.getvalue(), json.loads(err.getvalue())["error_category"]),
                         (2, "", "invalid_input"))

    def test_Q3_03_capture_truncation_and_display_shortening_are_distinct(self):
        saved = _long_text(TECH_MAX)
        self.write_records([_record(0, saved, truncated=True)])
        _, view, _ = self.context("--post-id", "100")
        self.assertIn("Excerpt truncated: true", view)
        self.assertIn(f"Excerpt display: shortened (shown {DISPLAY} of {TECH_MAX} saved characters;", view)
        _, full, _ = self.context("--post-id", "100", "--full-page-text")
        self.assertIn("Excerpt truncated: true", full)
        self.assertIn(f"Excerpt display: complete (all {TECH_MAX} saved characters)", full)
        self.assertEqual(literal_fields(full)[EXCERPT_LABEL], saved)

    def test_Q3_04_full_view_total_is_bounded_across_pages(self):
        saved = "w" * TECH_MAX
        count = BUDGET // TECH_MAX + 3
        self.write_records([_record(i, saved) for i in range(count)])
        rc, full, err = self.context("--post-id", "100", "--full-page-text")
        self.assertEqual((rc, err), (0, ""))
        section = full.split("### Saved thread reference pages", 1)[1]
        excerpts = [content for label, content, _ in stage3._fences(section)
                    if label == EXCERPT_LABEL + ":"]
        self.assertEqual(len(excerpts), count)
        lengths = [len(text) for text in excerpts]
        complete = BUDGET // TECH_MAX
        # Full pages until the budget is used, then the default amount per page.
        self.assertEqual(lengths, [TECH_MAX] * complete + [DISPLAY] * (count - complete))
        self.assertLessEqual(sum(lengths), BUDGET + DISPLAY * count)
        self.assertEqual(full.count("Excerpt display: complete"), complete)
        self.assertEqual(full.count(f"full-text display budget of {BUDGET} characters used"),
                         count - complete)

    def test_Q3_05_thread_section_and_short_records_unchanged(self):
        self.capture(_pre_page("short body"))
        _, view, _ = self.context("--post-id", "100")
        _, full, _ = self.context("--post-id", "100", "--full-page-text")
        self.assertNotIn("Excerpt display:", view)
        head = view.split("### Saved thread reference pages", 1)[0]
        self.assertEqual(full.split("### Saved thread reference pages", 1)[0], head)

    def test_Q3_06_view_without_post_id_stays_within_combined_cap(self):
        self.write_records([_record(i, _long_text(TECH_MAX)) for i in range(20)])
        rc, view, err = self.context()
        self.assertEqual((rc, err), (0, ""))
        self.assertLessEqual(len(view.encode("utf-8")), 256 * 1024)
        self.assertEqual(view.count("Excerpt display: shortened"), 20)

    # ---- Q-4 compatibility -------------------------------------------------
    def test_Q4_01_stage3_v1_record_still_reads(self):
        old = _record(0, "v" * page_capture.MAX_PAGE_TEXT, truncated=True)
        self.write_records([old])
        rc, view, _ = self.context("--post-id", "100")
        self.assertEqual(rc, 0)
        self.assertEqual(literal_fields(view)[EXCERPT_LABEL], "v" * page_capture.MAX_PAGE_TEXT)
        self.assertNotIn("Excerpt display:", view)

    def test_Q4_02_record_above_technical_limit_rejected(self):
        self.assertTrue(thread_pages._valid_record(_record(0, "a" * TECH_MAX)))
        self.assertFalse(thread_pages._valid_record(_record(0, "a" * (TECH_MAX + 1))))


# Only the Q tests run here; the inherited stage-3 tests run in their own module.
for _name in [n for n in dir(stage3.ThreadPageCaptureTests) if n.startswith("test_")]:
    setattr(ReferenceCaptureQualityTests, _name, None)


if __name__ == "__main__":
    unittest.main()
