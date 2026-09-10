import socket
import unittest
from unittest import mock

from x_context import InvalidStatusUrl, extract_post_id


class FR001UrlParserTests(unittest.TestCase):
    def test_FR_001_extract_post_id(self):
        cases = {
            "https://x.com/alice/status/1234567890": "1234567890",
            "https://www.x.com/alice/status/1234567890": "1234567890",
            "https://twitter.com/alice/status/1234567890": "1234567890",
            "https://www.twitter.com/alice/status/1234567890": "1234567890",
            "https://X.COM/alice/status/1234567890": "1234567890",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(extract_post_id(url), expected)

    def test_FR_001_query_fragment_ignored(self):
        self.assertEqual(
            extract_post_id(
                "https://x.com/alice/status/2095768443006177767?s=46&t=example#fragment"
            ),
            "2095768443006177767",
        )

    def test_FR_001_reject_foreign_host(self):
        invalid = [
            "https://example.com/alice/status/123",
            "https://x.com.example.org/alice/status/123",
            "https://example-x.com/alice/status/123",
            "https://twitter.com.example.org/alice/status/123",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(InvalidStatusUrl):
                    extract_post_id(url)

    def test_FR_001_reject_missing_numeric_status(self):
        invalid = [
            "https://x.com/alice/status/not-a-number",
            "https://x.com/alice/status/１２３",
            "https://x.com/alice/status/",
            "https://x.com/alice/123",
            "https://x.com/alice/status/123/extra",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(InvalidStatusUrl):
                    extract_post_id(url)

    def test_FR_001_invalid_input_no_network(self):
        invalid = [
            "",
            "not a url",
            "http://x.com/alice/status/123",
            "https://user@x.com/alice/status/123",
            "https://x.com:443/alice/status/123",
            "https://x.com/alice/status/not-a-number",
        ]
        with mock.patch.object(
            socket.socket,
            "connect",
            side_effect=AssertionError("network access attempted"),
        ) as connect:
            for url in invalid:
                with self.subTest(url=url):
                    with self.assertRaises(InvalidStatusUrl):
                        extract_post_id(url)
            connect.assert_not_called()

    def test_FR_001_reject_lookalike_and_malformed_paths(self):
        invalid = [
            "https://evil.example/?next=https://x.com/alice/status/123",
            "https://x.com/alice/foo/status/123",
            "https://x.com/status/123",
            "https://x.com/alice/status/123/",
            "https://x.com//status/123",
        ]
        for url in invalid:
            with self.subTest(url=url):
                with self.assertRaises(InvalidStatusUrl):
                    extract_post_id(url)


if __name__ == "__main__":
    unittest.main()
