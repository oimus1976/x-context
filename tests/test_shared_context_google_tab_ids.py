"""Review 5528374222: fictional Google-shaped responses, never live APIs."""
import copy
import unittest
from unittest.mock import Mock, patch

from test_shared_context_google import FakeAPI, MemoryState
from x_context.shared_context import core, drive, connector as c
from x_context.shared_context import google_api as api, google_publish as pub


def native(body="", tab_id="t.0"):
    # A literal Google-shaped empty/newline-delimited native response. IDs fictional.
    content = [{"endIndex": 1, "sectionBreak": {"sectionStyle": {}}}]
    start = 1
    for line in (body + "\n").splitlines(keepends=True):
        end = start + len(line.encode("utf-16-le")) // 2
        content.append({"startIndex": start, "endIndex": end, "paragraph": {
            "elements": [{"startIndex": start, "endIndex": end, "textRun": {"content": line}}],
            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}}})
        start = end
    return {"documentId": "FAKE-DOC", "title": "FAKE title", "revisionId": "FAKE-REV",
            "tabs": [{"tabProperties": {"tabId": tab_id, "title": "Tab 1", "index": 0},
                      "documentTab": {"body": {"content": content}}}]}


class TabIdTests(unittest.TestCase):
    def test_google_shaped_empty_t0_and_unicode_lines(self):
        for body in ("", "hello\n", "\u65e5\u672c\u8a9e\U0001f600\nsecond\n\n"):
            with self.subTest(body=body):
                self.assertEqual(api.parse_document(native(body), "FAKE-DOC"),
                                 (body, "FAKE-REV", "t.0", 1 + len(body.encode("utf-16-le")) // 2))

    def test_supported_tab_subset_boundaries(self):
        for identity in ('TAB', 't.0', 't.a_B-9', 'a' * 200):
            self.assertEqual(api.parse_document(native(tab_id=identity), 'FAKE-DOC')[2], identity)

    def test_stale_revision_never_posts(self):
        class HTTP:
            def request(self, service, method, path, **kw):
                if method != 'GET': raise AssertionError('must not write')
                return native()
        with self.assertRaisesRegex(core.ContextError, '^CONCURRENT_DRIVE_CHANGE$'):
            api.Transport(HTTP()).replace_text('FAKE-DOC', 'new', 'STALE')

    def test_replace_uses_exact_t0_and_revision_for_insert_and_delete(self):
        class HTTP:
            def __init__(self, body): self.body, self.calls = body, []
            def request(self, service, method, path, **kw):
                self.calls.append((service, method, path, kw))
                return native(self.body) if method == "GET" else {}
        for old in ("", "\u65e5\u672c\u8a9e\U0001f600\n"):
            http = HTTP(old)
            api.Transport(http).replace_text("FAKE-DOC", "replacement\U0001f600\n", "FAKE-REV")
            body = http.calls[-1][3]["body"]
            self.assertEqual(body["writeControl"], {"requiredRevisionId": "FAKE-REV"})
            self.assertEqual(body["requests"][-1]["insertText"],
                             {"location": {"index": 1, "tabId": "t.0"}, "text": "replacement\U0001f600\n"})
            self.assertEqual(len(body["requests"]), 2 if old else 1)
            if old:
                self.assertEqual(body["requests"][0]["deleteContentRange"]["range"],
                                 {"startIndex": 1, "endIndex": 1 + len(old.encode("utf-16-le")) // 2, "tabId": "t.0"})

    def test_hostile_missing_and_malformed_tabs_never_write(self):
        for tab_id in (None, False, 0, [], {}, "", ".", "..", ".t", "t.", "t..0", "t/0", "t\\0",
                       "t?0", "t#0", "t%2e0", "t:0", "t 0", "t\n0", "t\r0", "t\x000", "\uff54.0", "t" * 201):
            value = native(tab_id=tab_id)
            class HTTP:
                def __init__(self): self.writes = []
                def request(self, service, method, path, **kw):
                    if method != "GET": self.writes.append(kw)
                    return value
            http = HTTP()
            with self.subTest(tab_id=tab_id), self.assertRaisesRegex(core.ContextError, "^UNSUPPORTED_NATIVE_TEXT$"):
                api.Transport(http).replace_text("FAKE-DOC", "new", "FAKE-REV")
            self.assertEqual(http.writes, [])
        for key in ("tabId", "tabProperties"):
            value = native()
            del (value["tabs"][0]["tabProperties"] if key == "tabId" else value["tabs"][0])[key]
            with self.assertRaises(core.ContextError): api.parse_document(value, "FAKE-DOC")

    def test_file_and_http_path_ids_stay_strict_before_auth(self):
        with self.assertRaises(core.ContextError): c._identity("t.0")
        token = Mock(side_effect=AssertionError("must not access credentials"))
        for service, method, path in (("drive", "GET", "files/t.0"), ("docs", "GET", "documents/t.0"), ("docs", "POST", "documents/t.0:batchUpdate")):
            with self.assertRaises(core.ContextError): api.HTTP(token).request(service, method, path)
        token.assert_not_called()

    def test_interrupted_first_create_retains_registered_id_and_pending(self):
        http, state = FakeAPI(), MemoryState()
        backend = pub.AppBackend(api.Transport(http), state)
        folder = backend.initialize()
        records = core.load_fixture("baseline")
        plan = drive.preview(backend, folder, records)
        # Reproduce the observed old parser failure after Drive files.create.
        with patch.object(api, "parse_document", side_effect=core.ContextError("UNSUPPORTED_NATIVE_TEXT")):
            result = pub.publish(backend, records, plan)
        self.assertEqual(result, drive.Result("PARTIAL_UNPUBLISHED", 1))
        role = drive.PREFIX + "SYN-XCTX-C001"
        identity = state.value["documents"][role]
        self.assertEqual(state.value["pending"], [("", "CREATE_ATTEMPT"), (identity, "CREATED_EMPTY_UNVERIFIED")])
        self.assertEqual(http.text[identity], "\n")
        self.assertNotIn(drive.CURRENT, state.value["documents"])
        saved, effects = copy.deepcopy(state.value), list(http.effects)
        with self.assertRaisesRegex(core.ContextError, "GOOGLE_EFFECT_REQUIRES_INSPECTION"):
            pub.AppBackend(api.Transport(http), state)
        self.assertEqual(state.value, saved)
        self.assertEqual(http.effects, effects)
