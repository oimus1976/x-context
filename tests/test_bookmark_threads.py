"""Issue #77 stage 2: synthetic-only tests for bookmark-anchored thread collection."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from x_context import (
    bookmark_enrichment,
    bookmark_store,
    bookmark_threads,
    cli,
    image_capture,
    local_context,
    page_capture,
    x_api,
)

STAMP = "2026-10-01T10:00:00Z"
BEARER = "FICTIONAL-BEARER-NEVER-USE"


def json_reply(status: int, payload: object, *, headers: dict[str, str] | None = None) -> x_api.HttpResponse:
    return x_api.HttpResponse(
        status=status,
        headers={} if headers is None else headers,
        body=json.dumps(payload).encode("utf-8"),
    )


class FakeThreadTransport:
    def __init__(self, responses: list[x_api.HttpResponse]) -> None:
        self.responses = list(responses)
        self.requests: list[x_api.HttpRequest] = []

    def __call__(self, request: x_api.HttpRequest) -> x_api.HttpResponse:
        idx = len(self.requests)
        self.requests.append(request)
        if idx >= len(self.responses):
            raise AssertionError(f"unexpected X request #{idx + 1}: {request.url}")
        return self.responses[idx]


class BookmarkThreadTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / "x-context" / "data"
        self.data.mkdir(parents=True)
        self.env = {
            "LOCALAPPDATA": str(self.root),
            "X_CONTEXT_BEARER_TOKEN": BEARER,
        }
        self.main_store = self.data / "bookmarks-v1.json"
        self.enrichment_store = self.data / "bookmark-enrichment-v1.json"
        self.thread_store = self.data / "bookmark-threads-v1.json"
        self.main_store.write_text(json.dumps({
            "store_schema_version": "1",
            "source": "x",
            "collection": "bookmarks",
            "subject": {"id": "42", "username": "owner_user"},
            "created_at": STAMP,
            "updated_at": STAMP,
            "items": [
                {"id": "123", "text": "Bookmark quoting thread root", "first_seen_at": STAMP, "last_seen_at": STAMP},
                {"id": "202", "text": "Mid-thread bookmark post", "first_seen_at": STAMP, "last_seen_at": STAMP},
                {"id": "301", "text": "Reply to another author", "first_seen_at": STAMP, "last_seen_at": STAMP},
            ],
        }), encoding="utf-8")

    def add_quoted_enrichment(self, bookmark_id: str = "123", quoted_id: str = "789") -> None:
        record = bookmark_enrichment.capture({
            "id": bookmark_id,
            "text": "Bookmark quoting thread root",
            "referenced_posts": [{"id": quoted_id, "type": "quoted"}],
        }, {
            "posts": [{"id": quoted_id, "text": "Quoted root text"}],
        })
        record["observed_at"] = STAMP
        self.enrichment_store.write_text(json.dumps({
            "schema_version": "1",
            "subject_id": "42",
            "items": {bookmark_id: record},
        }), encoding="utf-8")

    def run_cli(self, args: list[str], *, transport=None, env: dict[str, str] | None = None):
        out, err = io.StringIO(), io.StringIO()
        rc = cli.main(
            args,
            environ=self.env if env is None else env,
            transport=transport,
            stdout=out,
            stderr=err,
        )
        return rc, out.getvalue(), err.getvalue()

    def test_quoted_bookmark_collects_same_author_thread_and_renders_markdown(self) -> None:
        self.add_quoted_enrichment("123", "789")
        before_main = self.main_store.read_bytes()
        before_enrichment = self.enrichment_store.read_bytes()

        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "789",
                    "text": "Thread part 1/3",
                    "author_id": "1001",
                    "conversation_id": "789",
                    "created_at": STAMP,
                    "entities": {"urls": [{"url": "https://t.co/doc", "expanded_url": "https://example.org/doc"}]},
                },
                "includes": {
                    "users": [
                        {"id": "1001", "username": "alice"},
                        {"id": "2002", "username": "bob"},
                    ],
                    "posts": [{
                        "id": "888",
                        "text": "Someone else's post in conversation",
                        "author_id": "2002",
                        "conversation_id": "789",
                        "created_at": "2026-10-01T10:02:30Z",
                    }],
                },
            }, headers={"x-rate-limit-limit": "300", "x-rate-limit-remaining": "299", "x-rate-limit-reset": "1700000000"}),
            json_reply(200, {
                "data": [
                    {
                        "id": "791",
                        "text": "Thread part 3/3\n<script>untrusted</script>",
                        "author_id": "1001",
                        "conversation_id": "789",
                        "created_at": "2026-10-01T10:02:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "790"}],
                    },
                    {
                        "id": "790",
                        "text": "Thread part 2/3",
                        "author_id": "1001",
                        "conversation_id": "789",
                        "created_at": "2026-10-01T10:01:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "789"}],
                    },
                    {
                        "id": "795",
                        "text": "Reply to someone else in same conversation",
                        "author_id": "1001",
                        "conversation_id": "789",
                        "created_at": "2026-10-01T10:03:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "888"}],
                    },
                ],
                "includes": {
                    "users": [
                        {"id": "1001", "username": "alice"},
                        {"id": "2002", "username": "bob"},
                    ],
                    "posts": [{
                        "id": "888",
                        "text": "Someone else's post in conversation",
                        "author_id": "2002",
                        "conversation_id": "789",
                        "created_at": "2026-10-01T10:02:30Z",
                    }],
                },
                "meta": {"result_count": 3},
            }, headers={"x-rate-limit-limit": "300", "x-rate-limit-remaining": "298", "x-rate-limit-reset": "1700000100"}),
        ])

        rc, out, err = self.run_cli(
            ["thread", "capture", "--post-id", "123", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(transport.requests), 2)

        req1 = urlsplit(transport.requests[0].url)
        self.assertEqual(req1.path, "/2/tweets/789")
        self.assertEqual(parse_qs(req1.query), {
            "post.fields": ["conversation_id,created_at,entities"],
            "expansions": ["author_id,referenced_posts"],
            "user.fields": ["username"],
        })
        self.assertEqual(transport.requests[0].headers["Authorization"], f"Bearer {BEARER}")

        req2 = urlsplit(transport.requests[1].url)
        self.assertEqual(req2.path, "/2/tweets/search/all")
        self.assertEqual(parse_qs(req2.query), {
            "query": ["conversation_id:789 from:alice -is:retweet"],
            "max_results": ["20"],
            "post.fields": ["conversation_id,created_at,entities"],
            "expansions": ["author_id,referenced_posts"],
            "start_time": [STAMP],
        })

        stdout_obj = json.loads(out)
        diag_obj = json.loads(err)
        self.assertEqual(stdout_obj["operation"], "thread")
        self.assertEqual(stdout_obj["target_post_id"], "789")
        self.assertEqual(stdout_obj["seed_role"], "quoted_post")
        self.assertEqual(stdout_obj["thread_post_count"], 3)
        self.assertEqual(diag_obj["provider_requests_attempted"], 2)
        self.assertEqual(diag_obj["rate_limits"]["post_lookup"]["remaining"], 299)
        self.assertEqual(diag_obj["rate_limits"]["search_all"]["remaining"], 298)
        self.assertNotIn(BEARER, out + err)

        saved = json.loads(self.thread_store.read_text(encoding="utf-8"))
        self.assertEqual(saved["subject_id"], "42")
        record = saved["items"]["123"]
        self.assertEqual([p["id"] for p in record["thread_posts"]], ["789", "790", "791"])
        self.assertEqual(record["excluded_unlinked_count"], 1)
        self.assertEqual(record["unverified_unlinked_count"], 0)
        self.assertEqual(record["unverified_missing_parent_ids"], [])
        self.assertEqual(record["root_state"], "in_thread")
        self.assertEqual(record["completeness"], "unverified_single_page")
        self.assertEqual(self.main_store.read_bytes(), before_main)
        self.assertEqual(self.enrichment_store.read_bytes(), before_enrichment)
        self.assertNotIn(BEARER, self.thread_store.read_text(encoding="utf-8"))

        # Offline Markdown display must join thread without touching network or credentials.
        with (patch.object(cli, "resolve_user_access_token", side_effect=AssertionError("credential accessed")),
              patch.object(x_api, "_urllib_transport", side_effect=AssertionError("X API accessed")),
              patch.object(x_api, "_bookmarks_transport", side_effect=AssertionError("X transport accessed")),
              patch.object(page_capture, "_transport", side_effect=AssertionError("HTTP accessed")),
              patch.object(image_capture, "_image_transport", side_effect=AssertionError("image accessed"))):
            rc2, md, err2 = self.run_cli(["context", "--include-saved-details", "--post-id", "123"])
        self.assertEqual((rc2, err2), (0, ""))
        self.assertIn("### Collected same-author X thread", md)
        self.assertIn("Thread seed: quoted_post (bookmark relation: quoted)", md)
        self.assertIn("Thread author (X-provided): @alice (id: 1001)", md)
        self.assertIn("#### Thread post 1 (789)", md)
        self.assertIn("#### Thread post 2 (790)", md)
        self.assertIn("Relation in thread: replied_to 789 (in_thread)", md)
        self.assertIn("#### Thread post 3 (791)", md)
        self.assertIn("> &lt;script&gt;untrusted&lt;/script&gt;", md)
        self.assertIn("> https://example.org/doc", md)
        self.assertNotIn("<script>", md)
        self.assertNotIn("Mid-thread bookmark post", md)

    def test_mid_thread_bookmark_restores_ancestor_and_continuation(self) -> None:
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "202",
                    "text": "Middle post 2/3",
                    "author_id": "1002",
                    "conversation_id": "201",
                    "created_at": "2026-10-02T10:01:00Z",
                    "referenced_posts": [{"type": "replied_to", "id": "201"}],
                },
                "includes": {
                    "users": [{"id": "1002", "username": "bob"}],
                    "posts": [{
                        "id": "201",
                        "text": "Root post 1/3",
                        "author_id": "1002",
                        "conversation_id": "201",
                        "created_at": "2026-10-02T10:00:00Z",
                    }],
                },
            }),
            json_reply(200, {
                "data": [
                    {
                        "id": "203",
                        "text": "End post 3/3",
                        "author_id": "1002",
                        "conversation_id": "201",
                        "created_at": "2026-10-02T10:02:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "202"}],
                    },
                ],
                "includes": {
                    "users": [{"id": "1002", "username": "bob"}],
                },
                "meta": {"result_count": 1},
            }),
        ])

        rc, out, _ = self.run_cli(
            ["thread", "capture", "--post-id", "202", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["seed_role"], "bookmarked_post")
        req2_q = parse_qs(urlsplit(transport.requests[1].url).query)
        self.assertEqual(req2_q["start_time"], ["2026-10-02T10:00:00Z"])
        record = json.loads(self.thread_store.read_text(encoding="utf-8"))["items"]["202"]
        self.assertEqual([p["id"] for p in record["thread_posts"]], ["201", "202", "203"])
        self.assertEqual([p["source"] for p in record["thread_posts"]],
                         ["post_lookup", "post_lookup", "full_archive_search"])
        self.assertEqual(record["root_state"], "in_thread")

    def test_search_zero_results_records_honest_no_results_state(self) -> None:
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "202",
                    "text": "Standalone post",
                    "author_id": "1002",
                    "conversation_id": "202",
                    "created_at": STAMP,
                },
                "includes": {"users": [{"id": "1002", "username": "bob"}]},
            }),
            json_reply(200, {"meta": {"result_count": 0}}),
        ])

        rc, out, _ = self.run_cli(
            ["thread", "capture", "--post-id", "202", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["search_state"], "no_results")
        record = json.loads(self.thread_store.read_text(encoding="utf-8"))["items"]["202"]
        self.assertEqual(record["completeness"], "unverified_single_page")

        rc2, md, err2 = self.run_cli(["context", "--include-saved-details", "--post-id", "202"])
        self.assertEqual((rc2, err2), (0, ""))
        self.assertIn("Search state: no_results (does not prove no continuations exist)", md)

    def test_truncated_search_and_missing_parent_stops_at_one_page_without_token_leak(self) -> None:
        secret_token = "OPAQUE-SECRET-NEXT-TOKEN"
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "202",
                    "text": "Mid-thread post 2",
                    "author_id": "1002",
                    "conversation_id": "100",
                    "created_at": "2026-10-02T10:02:00Z",
                    "referenced_posts": [{"type": "replied_to", "id": "100"}],
                },
                "includes": {"users": [{"id": "1002", "username": "bob"}]},
            }),
            json_reply(200, {
                "data": [{
                    "id": "203",
                    "text": "Mid-thread post 3",
                    "author_id": "1002",
                    "conversation_id": "100",
                    "created_at": "2026-10-02T10:03:00Z",
                    "referenced_posts": [{"type": "replied_to", "id": "202"}],
                }],
                "meta": {"result_count": 1, "next_token": secret_token},
            }),
        ])

        rc, out, err = self.run_cli(
            ["thread", "capture", "--post-id", "202", "--max-results", "15", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(len(transport.requests), 2)
        req2_q = parse_qs(urlsplit(transport.requests[1].url).query)
        self.assertEqual(req2_q["start_time"], ["2006-03-21T00:00:00Z"])
        self.assertEqual(req2_q["max_results"], ["15"])

        saved_raw = self.thread_store.read_text(encoding="utf-8")
        record = json.loads(saved_raw)["items"]["202"]
        self.assertTrue(record["search_truncated"])
        self.assertEqual(record["missing_parent_id"], "100")
        self.assertEqual(record["completeness"], "partial_truncated_and_missing_parent")
        self.assertEqual(record["root_state"], "not_returned")
        self.assertNotIn(secret_token, saved_raw + out + err)

    def test_external_replied_to_and_missing_quoted_post_stay_separate_from_thread(self) -> None:
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "301",
                    "text": "Alice replies to Bob and quotes deleted post",
                    "author_id": "1001",
                    "conversation_id": "300",
                    "created_at": STAMP,
                    "referenced_posts": [
                        {"type": "replied_to", "id": "300"},
                        {"type": "quoted", "id": "400"},
                    ],
                },
                "includes": {
                    "users": [
                        {"id": "1001", "username": "alice"},
                        {"id": "1002", "username": "bob"},
                    ],
                    "posts": [{
                        "id": "300",
                        "text": "Bob's original post",
                        "author_id": "1002",
                        "conversation_id": "300",
                        "created_at": "2026-10-01T09:50:00Z",
                    }],
                },
            }),
            json_reply(200, {"meta": {"result_count": 0}}),
        ])

        rc, _, _ = self.run_cli(
            ["thread", "capture", "--post-id", "301", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0)
        record = json.loads(self.thread_store.read_text(encoding="utf-8"))["items"]["301"]
        self.assertEqual([p["id"] for p in record["thread_posts"]], ["301"])
        self.assertEqual(record["root_state"], "external_referenced")
        self.assertIsNone(record["missing_parent_id"])
        refs = {(r["id"], r["relation"]): r for r in record["referenced_posts"]}
        self.assertEqual(refs[("300", "replied_to")]["text_state"], "recorded")
        self.assertEqual(refs[("300", "replied_to")]["author_username"], "bob")
        self.assertEqual(refs[("400", "quoted")]["text_state"], "not_returned")

        rc2, md, _ = self.run_cli(["context", "--include-saved-details", "--post-id", "301"])
        self.assertEqual(rc2, 0)
        self.assertIn("Thread-related referenced posts (2)", md)
        self.assertIn("Thread reference 300 (replied_to from 301)", md)
        self.assertIn("> Bob's original post", md)
        self.assertIn("Thread reference 400 (quoted from 301)", md)
        self.assertIn("Referenced Post text state: not_returned", md)

    def test_local_guards_fail_closed_with_zero_requests(self) -> None:
        transport = FakeThreadTransport([])
        for args, env in (
            (["thread", "capture", "--post-id", "123"], self.env),
            (["thread", "capture", "--post-id", "999", "--confirm-network-request"], self.env),
            (["thread", "capture", "--post-id", "123", "--max-results", "9", "--confirm-network-request"], self.env),
            (["thread", "capture", "--post-id", "123", "--max-results", "101", "--confirm-network-request"], self.env),
            (["thread", "capture", "--post-id", "123", "--confirm-network-request"], {"LOCALAPPDATA": str(self.root)}),
        ):
            with self.subTest(args=args, has_bearer="X_CONTEXT_BEARER_TOKEN" in env):
                rc, out, err = self.run_cli(args, transport=transport, env=env)
                diag = json.loads(err)
                self.assertEqual((rc, out), (2, ""))
                self.assertEqual(diag["provider_requests_attempted"], 0)
                self.assertIn(diag["error_category"], ("invalid_input", "configuration_error"))
                self.assertEqual(transport.requests, [])
                self.assertFalse(self.thread_store.exists())

    def test_search_api_error_exits_3_without_modifying_local_files(self) -> None:
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "202",
                    "text": "Post",
                    "author_id": "1002",
                    "conversation_id": "202",
                    "created_at": STAMP,
                },
                "includes": {"users": [{"id": "1002", "username": "bob"}]},
            }),
            json_reply(403, {"type": "https://api.x.com/2/problems/not-authorized-for-resource", "title": "Forbidden"}),
        ])
        rc, out, err = self.run_cli(
            ["thread", "capture", "--post-id", "202", "--confirm-network-request"],
            transport=transport,
        )
        diag = json.loads(err)
        self.assertEqual((rc, out), (3, ""))
        self.assertEqual(diag["error_category"], "authorization_failed")
        self.assertEqual(diag["provider_requests_attempted"], 2)
        self.assertFalse(diag["persistence_attempted"])
        self.assertFalse(self.thread_store.exists())

    def test_plain_context_unchanged_and_corrupt_thread_sidecar_fails_closed(self) -> None:
        baseline = local_context.render(json.loads(self.main_store.read_text(encoding="utf-8")))
        self.thread_store.write_text(json.dumps({
            "schema_version": "1",
            "subject_id": "42",
            "items": {
                "202": {
                    "bookmark_post_id": "202",
                    "seed_role": "bookmarked_post",
                    "bookmark_relation_to_target": "self",
                    "target_post_id": "202",
                    "retrieved_at": STAMP,
                    "conversation_id": "202",
                    "author_id": "1002",
                    "author_username": "bob",
                    "search_query": "conversation_id:202 from:bob -is:retweet",
                    "search_max_results": 20,
                    "search_state": "no_results",
                    "search_truncated": False,
                    "excluded_unlinked_count": 0,
                    "unverified_unlinked_count": 0,
                    "unverified_missing_parent_ids": [],
                    "completeness": "unverified_single_page",
                    "root_state": "in_thread",
                    "missing_parent_id": None,
                    "thread_posts": [{
                        "id": "202",
                        "text": "Mid-thread bookmark post",
                        "author_id": "1002",
                        "author_username": "bob",
                        "conversation_id": "202",
                        "created_at": STAMP,
                        "replied_to_id": None,
                        "quoted_post_id": None,
                        "source": "post_lookup",
                        "urls": [],
                    }],
                    "referenced_posts": [],
                },
            },
        }), encoding="utf-8")

        rc, out, err = self.run_cli(["context"])
        self.assertEqual((rc, out, err), (0, baseline, ""))

        rc_flag, out_flag, err_flag = self.run_cli(["context", "--post-id", "202"])
        self.assertEqual((rc_flag, out_flag), (2, ""))
        self.assertEqual(json.loads(err_flag)["error_category"], "invalid_input")

        contradictory_record = {
            "schema_version": "1",
            "subject_id": "42",
            "items": {
                "202": {
                    "bookmark_post_id": "202",
                    "seed_role": "bookmarked_post",
                    "bookmark_relation_to_target": "self",
                    "target_post_id": "202",
                    "retrieved_at": STAMP,
                    "conversation_id": "202",
                    "author_id": "1002",
                    "author_username": "bob",
                    "search_query": "conversation_id:202 from:bob -is:retweet",
                    "search_max_results": 20,
                    "search_state": "searched",
                    "search_truncated": False,
                    "excluded_unlinked_count": 0,
                    "unverified_unlinked_count": 1,
                    "unverified_missing_parent_ids": ["102"],
                    "completeness": "unverified_single_page",
                    "root_state": "in_thread",
                    "missing_parent_id": None,
                    "thread_posts": [{
                        "id": "202",
                        "text": "Mid-thread bookmark post",
                        "author_id": "1002",
                        "author_username": "bob",
                        "conversation_id": "202",
                        "created_at": STAMP,
                        "replied_to_id": None,
                        "quoted_post_id": None,
                        "source": "post_lookup",
                        "urls": [],
                    }],
                    "referenced_posts": [],
                },
            },
        }
        for bad in (
            b"{broken",
            json.dumps({"schema_version": "1", "subject_id": "999", "items": {}}).encode("utf-8"),
            json.dumps(contradictory_record).encode("utf-8"),
        ):
            self.thread_store.write_bytes(bad)
            rc_bad, out_bad, err_bad = self.run_cli(["context", "--include-saved-details"])
            self.assertEqual((rc_bad, out_bad), (2, ""))
            self.assertEqual(json.loads(err_bad)["error_category"], "storage_error")

    def test_missing_descendant_parent_marks_partial_and_preserves_state_across_save_reload_markdown(self) -> None:
        self.add_quoted_enrichment("123", "100")
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "100",
                    "text": "Thread post 100",
                    "author_id": "1001",
                    "conversation_id": "100",
                    "created_at": STAMP,
                },
                "includes": {"users": [{"id": "1001", "username": "alice"}]},
            }),
            json_reply(200, {
                "data": [
                    {
                        "id": "101",
                        "text": "Thread post 101",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:01:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "100"}],
                    },
                    {
                        "id": "103",
                        "text": "Thread post 103",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "102"}],
                    },
                    {
                        "id": "104",
                        "text": "Thread post 104",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "103"}],
                    },
                ],
                "includes": {"users": [{"id": "1001", "username": "alice"}], "posts": []},
                "meta": {"result_count": 3},
            }),
        ])

        rc, out, err = self.run_cli(
            ["thread", "capture", "--post-id", "123", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0, msg=err)
        self.assertEqual(len(transport.requests), 2)
        stdout_obj = json.loads(out)
        self.assertEqual(stdout_obj["completeness"], "partial_missing_parent")
        self.assertEqual(stdout_obj["thread_post_count"], 2)

        record = json.loads(self.thread_store.read_text(encoding="utf-8"))["items"]["123"]
        self.assertEqual([p["id"] for p in record["thread_posts"]], ["100", "101"])
        self.assertIsNone(record["missing_parent_id"])
        self.assertEqual(record["unverified_missing_parent_ids"], ["102"])
        self.assertEqual(record["unverified_unlinked_count"], 2)
        self.assertEqual(record["excluded_unlinked_count"], 0)
        self.assertEqual(record["completeness"], "partial_missing_parent")
        self.assertEqual(record["root_state"], "in_thread")

        reloaded = bookmark_threads.preflight(bookmark_store.preflight(self.env))
        self.assertIsNotNone(reloaded.value)
        self.assertEqual(reloaded.value["items"]["123"], record)

        with (patch.object(cli, "resolve_user_access_token", side_effect=AssertionError("credential accessed")),
              patch.object(x_api, "_urllib_transport", side_effect=AssertionError("X API accessed")),
              patch.object(x_api, "_bookmarks_transport", side_effect=AssertionError("X transport accessed")),
              patch.object(page_capture, "_transport", side_effect=AssertionError("HTTP accessed")),
              patch.object(image_capture, "_image_transport", side_effect=AssertionError("image accessed"))):
            rc2, md, err2 = self.run_cli(["context", "--include-saved-details", "--post-id", "123"])
        self.assertEqual((rc2, err2), (0, ""))
        self.assertIn("Thread completeness: partial_missing_parent", md)
        self.assertIn("Excluded unlinked same-author posts in conversation: 0", md)
        self.assertIn("Unverified unlinked same-author posts (missing parent; connection not confirmed): 2", md)
        self.assertIn(
            "Unverified missing parent Post IDs (unlinked posts; continuation not confirmed): 102 (https://x.com/i/web/status/102)",
            md,
        )
        self.assertIn("#### Thread post 1 (100)", md)
        self.assertIn("#### Thread post 2 (101)", md)
        self.assertNotIn("#### Thread post 3", md)

        truncated_record = bookmark_threads.reconstruct_same_author_thread(
            bookmark_post_id="123",
            seed_role="quoted_post",
            bookmark_relation_to_target="quoted",
            retrieved_at=STAMP,
            target_post={
                "id": "100", "text": "p0", "author_id": "1001", "conversation_id": "100",
                "created_at": STAMP, "referenced_posts": [], "urls": [],
            },
            lookup_included_posts=(),
            users_by_id={"1001": "alice"},
            search_posts=(
                {
                    "id": "101", "text": "p1", "author_id": "1001", "conversation_id": "100",
                    "created_at": "2026-10-01T10:01:00Z", "referenced_posts": [{"type": "replied_to", "id": "100"}], "urls": [],
                },
                {
                    "id": "103", "text": "p3", "author_id": "1001", "conversation_id": "100",
                    "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "102"}], "urls": [],
                },
                {
                    "id": "104", "text": "p4", "author_id": "1001", "conversation_id": "100",
                    "created_at": "2026-10-01T10:04:00Z", "referenced_posts": [{"type": "replied_to", "id": "103"}], "urls": [],
                },
            ),
            search_included_posts=(),
            search_query="conversation_id:100 from:alice -is:retweet",
            search_max_results=20,
            search_state="truncated",
            search_truncated=True,
        )
        self.assertEqual(truncated_record["completeness"], "partial_truncated_and_missing_parent")
        self.assertEqual(truncated_record["unverified_missing_parent_ids"], ["102"])
        self.assertEqual(truncated_record["unverified_unlinked_count"], 2)

    def test_proven_third_party_reply_branch_excluded_separately_from_missing_parent(self) -> None:
        base_target = {
            "id": "100", "text": "p0", "author_id": "1001", "conversation_id": "100",
            "created_at": STAMP, "referenced_posts": [], "urls": [],
        }
        p101 = {
            "id": "101", "text": "p1", "author_id": "1001", "conversation_id": "100",
            "created_at": "2026-10-01T10:01:00Z", "referenced_posts": [{"type": "replied_to", "id": "100"}], "urls": [],
        }
        third_party_888 = {
            "id": "888", "text": "Bob reply", "author_id": "2002", "conversation_id": "100",
            "created_at": "2026-10-01T10:02:00Z", "referenced_posts": [{"type": "replied_to", "id": "100"}], "urls": [],
        }

        with self.subTest("proven_third_party_chain"):
            rec_a = bookmark_threads.reconstruct_same_author_thread(
                bookmark_post_id="100",
                seed_role="bookmarked_post",
                bookmark_relation_to_target="self",
                retrieved_at=STAMP,
                target_post=base_target,
                lookup_included_posts=(),
                users_by_id={"1001": "alice", "2002": "bob"},
                search_posts=(
                    p101,
                    {
                        "id": "103", "text": "Alice replies to Bob", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "888"}], "urls": [],
                    },
                    {
                        "id": "104", "text": "Alice continues reply to Bob", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z", "referenced_posts": [{"type": "replied_to", "id": "103"}], "urls": [],
                    },
                ),
                search_included_posts=(third_party_888,),
                search_query="conversation_id:100 from:alice -is:retweet",
                search_max_results=20,
                search_state="searched",
                search_truncated=False,
            )
            self.assertEqual([p["id"] for p in rec_a["thread_posts"]], ["100", "101"])
            self.assertEqual(rec_a["excluded_unlinked_count"], 2)
            self.assertEqual(rec_a["unverified_unlinked_count"], 0)
            self.assertEqual(rec_a["unverified_missing_parent_ids"], [])
            self.assertEqual(rec_a["completeness"], "unverified_single_page")

        with self.subTest("mixed_third_party_and_missing_parent"):
            rec_b = bookmark_threads.reconstruct_same_author_thread(
                bookmark_post_id="100",
                seed_role="bookmarked_post",
                bookmark_relation_to_target="self",
                retrieved_at=STAMP,
                target_post=base_target,
                lookup_included_posts=(),
                users_by_id={"1001": "alice", "2002": "bob"},
                search_posts=(
                    p101,
                    {
                        "id": "795", "text": "Alice replies to Bob", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:02:30Z", "referenced_posts": [{"type": "replied_to", "id": "888"}], "urls": [],
                    },
                    {
                        "id": "103", "text": "p3", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "102"}], "urls": [],
                    },
                    {
                        "id": "104", "text": "p4", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z", "referenced_posts": [{"type": "replied_to", "id": "103"}], "urls": [],
                    },
                ),
                search_included_posts=(third_party_888,),
                search_query="conversation_id:100 from:alice -is:retweet",
                search_max_results=20,
                search_state="searched",
                search_truncated=False,
            )
            self.assertEqual([p["id"] for p in rec_b["thread_posts"]], ["100", "101"])
            self.assertEqual(rec_b["excluded_unlinked_count"], 1)
            self.assertEqual(rec_b["unverified_unlinked_count"], 2)
            self.assertEqual(rec_b["unverified_missing_parent_ids"], ["102"])
            self.assertEqual(rec_b["completeness"], "partial_missing_parent")

        with self.subTest("included_parent_missing_author_id_fails_closed"):
            rec_c = bookmark_threads.reconstruct_same_author_thread(
                bookmark_post_id="100",
                seed_role="bookmarked_post",
                bookmark_relation_to_target="self",
                retrieved_at=STAMP,
                target_post=base_target,
                lookup_included_posts=(),
                users_by_id={"1001": "alice"},
                search_posts=(
                    p101,
                    {
                        "id": "103", "text": "p3", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "102"}], "urls": [],
                    },
                    {
                        "id": "104", "text": "p4", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z", "referenced_posts": [{"type": "replied_to", "id": "103"}], "urls": [],
                    },
                ),
                search_included_posts=({
                    "id": "102", "text": "unknown author", "author_id": None, "conversation_id": "100",
                    "created_at": "2026-10-01T10:02:00Z", "referenced_posts": [], "urls": [],
                },),
                search_query="conversation_id:100 from:alice -is:retweet",
                search_max_results=20,
                search_state="searched",
                search_truncated=False,
            )
            self.assertEqual(rec_c["unverified_unlinked_count"], 2)
            self.assertEqual(rec_c["unverified_missing_parent_ids"], ["102"])
            self.assertEqual(rec_c["completeness"], "partial_missing_parent")

    def test_fetched_search_includes_parent_resolves_without_extra_requests_and_coexists_with_ancestor_gap(self) -> None:
        self.add_quoted_enrichment("123", "100")
        transport = FakeThreadTransport([
            json_reply(200, {
                "data": {
                    "id": "100",
                    "text": "Thread post 100",
                    "author_id": "1001",
                    "conversation_id": "100",
                    "created_at": STAMP,
                },
                "includes": {"users": [{"id": "1001", "username": "alice"}]},
            }),
            json_reply(200, {
                "data": [
                    {
                        "id": "101",
                        "text": "Thread post 101",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:01:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "100"}],
                    },
                    {
                        "id": "103",
                        "text": "Thread post 103",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "102"}],
                    },
                    {
                        "id": "104",
                        "text": "Thread post 104",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "103"}],
                    },
                ],
                "includes": {
                    "users": [{"id": "1001", "username": "alice"}],
                    "posts": [{
                        "id": "102",
                        "text": "Thread post 102 from includes",
                        "author_id": "1001",
                        "conversation_id": "100",
                        "created_at": "2026-10-01T10:02:00Z",
                        "referenced_posts": [{"type": "replied_to", "id": "101"}],
                    }],
                },
                "meta": {"result_count": 3},
            }),
        ])

        rc, _, err = self.run_cli(
            ["thread", "capture", "--post-id", "123", "--confirm-network-request"],
            transport=transport,
        )
        self.assertEqual(rc, 0, msg=err)
        self.assertEqual(len(transport.requests), 2)
        record = json.loads(self.thread_store.read_text(encoding="utf-8"))["items"]["123"]
        self.assertEqual([p["id"] for p in record["thread_posts"]], ["100", "101", "102", "103", "104"])
        self.assertEqual(record["excluded_unlinked_count"], 0)
        self.assertEqual(record["unverified_unlinked_count"], 0)
        self.assertEqual(record["unverified_missing_parent_ids"], [])
        self.assertEqual(record["completeness"], "unverified_single_page")

        reloaded = bookmark_threads.preflight(bookmark_store.preflight(self.env))
        self.assertIsNotNone(reloaded.value)
        self.assertEqual(reloaded.value["items"]["123"], record)
        rc2, md, err2 = self.run_cli(["context", "--include-saved-details", "--post-id", "123"])
        self.assertEqual((rc2, err2), (0, ""))
        self.assertIn("Thread completeness: unverified_single_page", md)
        for idx, pid in enumerate(("100", "101", "102", "103", "104"), 1):
            self.assertIn(f"#### Thread post {idx} ({pid})", md)

        with self.subTest("included_parent_stops_at_further_missing_parent_999"):
            rec_b = bookmark_threads.reconstruct_same_author_thread(
                bookmark_post_id="100",
                seed_role="bookmarked_post",
                bookmark_relation_to_target="self",
                retrieved_at=STAMP,
                target_post={
                    "id": "100", "text": "p0", "author_id": "1001", "conversation_id": "100",
                    "created_at": STAMP, "referenced_posts": [], "urls": [],
                },
                lookup_included_posts=(),
                users_by_id={"1001": "alice"},
                search_posts=(
                    {
                        "id": "101", "text": "p1", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:01:00Z", "referenced_posts": [{"type": "replied_to", "id": "100"}], "urls": [],
                    },
                    {
                        "id": "103", "text": "p3", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "102"}], "urls": [],
                    },
                    {
                        "id": "104", "text": "p4", "author_id": "1001", "conversation_id": "100",
                        "created_at": "2026-10-01T10:04:00Z", "referenced_posts": [{"type": "replied_to", "id": "103"}], "urls": [],
                    },
                ),
                search_included_posts=({
                    "id": "102", "text": "p2", "author_id": "1001", "conversation_id": "100",
                    "created_at": "2026-10-01T10:02:00Z", "referenced_posts": [{"type": "replied_to", "id": "999"}], "urls": [],
                },),
                search_query="conversation_id:100 from:alice -is:retweet",
                search_max_results=20,
                search_state="searched",
                search_truncated=False,
            )
            self.assertEqual([p["id"] for p in rec_b["thread_posts"]], ["100", "101"])
            self.assertEqual(rec_b["unverified_missing_parent_ids"], ["999"])
            self.assertEqual(rec_b["unverified_unlinked_count"], 2)
            self.assertEqual(rec_b["excluded_unlinked_count"], 0)
            self.assertEqual(rec_b["completeness"], "partial_missing_parent")

        with self.subTest("ancestor_and_descendant_missing_parents_coexist"):
            rec_c = bookmark_threads.reconstruct_same_author_thread(
                bookmark_post_id="202",
                seed_role="bookmarked_post",
                bookmark_relation_to_target="self",
                retrieved_at=STAMP,
                target_post={
                    "id": "202", "text": "p202", "author_id": "1002", "conversation_id": "200",
                    "created_at": "2026-10-01T10:02:00Z", "referenced_posts": [{"type": "replied_to", "id": "201"}], "urls": [],
                },
                lookup_included_posts=(),
                users_by_id={"1002": "bob"},
                search_posts=(
                    {
                        "id": "203", "text": "p203", "author_id": "1002", "conversation_id": "200",
                        "created_at": "2026-10-01T10:03:00Z", "referenced_posts": [{"type": "replied_to", "id": "202"}], "urls": [],
                    },
                    {
                        "id": "205", "text": "p205", "author_id": "1002", "conversation_id": "200",
                        "created_at": "2026-10-01T10:05:00Z", "referenced_posts": [{"type": "replied_to", "id": "204"}], "urls": [],
                    },
                ),
                search_included_posts=(),
                search_query="conversation_id:200 from:bob -is:retweet",
                search_max_results=20,
                search_state="searched",
                search_truncated=False,
            )
            self.assertEqual([p["id"] for p in rec_c["thread_posts"]], ["202", "203"])
            self.assertEqual(rec_c["missing_parent_id"], "201")
            self.assertEqual(rec_c["unverified_missing_parent_ids"], ["204"])
            self.assertEqual(rec_c["unverified_unlinked_count"], 1)
            self.assertEqual(rec_c["completeness"], "partial_missing_parent")
            self.assertEqual(rec_c["root_state"], "not_returned")


if __name__ == "__main__":
    unittest.main()
