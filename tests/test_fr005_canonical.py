import json
import unittest
from datetime import datetime, timedelta, timezone

from x_context import CanonicalEnvelope, CanonicalPost, Page, make_read_envelope


class FR005CanonicalReadTests(unittest.TestCase):
    def test_FR_005_read_envelope_shape_and_schema_version(self):
        envelope = make_read_envelope(
            [CanonicalPost(id="2095768443006177767", text="hello")],
            retrieved_at=datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            envelope.to_dict(),
            {
                "schema_version": "1",
                "source": "x",
                "operation": "read",
                "retrieved_at": "2026-09-10T03:00:00Z",
                "subject": None,
                "items": [{"id": "2095768443006177767", "text": "hello"}],
                "page": {"next_token": None, "complete": True},
            },
        )
        self.assertEqual(json.loads(envelope.to_json()), envelope.to_dict())

    def test_FR_005_retrieved_at_is_normalized_to_utc(self):
        jst = timezone(timedelta(hours=9))
        envelope = make_read_envelope(
            [], retrieved_at=datetime(2026, 9, 10, 12, 34, 56, tzinfo=jst)
        )
        self.assertEqual(envelope.to_dict()["retrieved_at"], "2026-09-10T03:34:56Z")
        self.assertEqual(envelope.retrieved_at.utcoffset(), timedelta(0))

    def test_FR_005_rejects_naive_retrieved_at(self):
        with self.assertRaises(ValueError):
            make_read_envelope([], retrieved_at=datetime(2026, 9, 10, 3, 0))

    def test_FR_005_read_subject_and_page_contract(self):
        envelope = make_read_envelope([])
        self.assertIsNone(envelope.subject)
        self.assertEqual(envelope.page, Page(next_token=None, complete=True))
        with self.assertRaises(ValueError):
            CanonicalEnvelope(
                operation="read",
                retrieved_at=datetime.now(timezone.utc),
                subject=None,
                items=(),
                page=Page(next_token="token", complete=False),
            )

    def test_FR_005_page_rejects_complete_with_next_token(self):
        with self.assertRaises(ValueError):
            Page(next_token="token", complete=True)
        self.assertEqual(
            Page(next_token="token", complete=False).to_dict(),
            {"next_token": "token", "complete": False},
        )

    def test_FR_005_unrequested_optional_fields_are_not_fabricated(self):
        item = CanonicalPost(id="123", text="hello").to_dict()
        self.assertEqual(item, {"id": "123", "text": "hello"})
        for key in ("author", "created_at", "url", "referenced_posts", "media", "links"):
            self.assertNotIn(key, item)

    def test_FR_005_provider_or_secret_passthrough_is_not_part_of_model(self):
        with self.assertRaises(TypeError):
            CanonicalPost(id="123", text="hello", raw={"provider_field": "value"})
        with self.assertRaises(TypeError):
            CanonicalPost(id="123", text="hello", access_token="fake-token")

    def test_FR_005_rejects_non_ascii_or_non_numeric_post_id(self):
        for value in ("", "abc", "１２３"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    CanonicalPost(id=value, text="hello")


if __name__ == "__main__":
    unittest.main()
