import json
import unittest
from dataclasses import dataclass, field

from x_context.x_api import HttpRequest, HttpResponse, XApiError, lookup_post


@dataclass
class FakeTransport:
    response: HttpResponse | None = None
    error: Exception | None = None
    requests: list[HttpRequest] = field(default_factory=list)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("fake transport has no response")
        return self.response


def response(status: int, payload: object, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={} if headers is None else headers,
        body=json.dumps(payload).encode("utf-8"),
    )


class FR002OfficialPostLookupTests(unittest.TestCase):
    def test_FR_002_uses_official_single_post_endpoint(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "123", "text": "hello"}}))

        lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url, "https://api.x.com/2/tweets/123")
        self.assertEqual(request.headers["Authorization"], "Bearer fake-bearer-token")

    def test_FR_002_rejects_provider_incompatible_post_id_without_network(self):
        invalid = ("", "abc", "１２３", "12345678901234567890")
        transport = FakeTransport(response=response(500, {}))

        for post_id in invalid:
            with self.subTest(post_id=post_id):
                with self.assertRaises(XApiError) as raised:
                    lookup_post(post_id, bearer_token="fake-bearer-token", transport=transport)
                self.assertEqual(raised.exception.category, "invalid_input")

        self.assertEqual(transport.requests, [])

    def test_FR_002_requests_no_optional_fields_or_expansions(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "123", "text": "hello"}}))

        lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        request = transport.requests[0]
        self.assertNotIn("?", request.url)
        self.assertNotIn("post.fields", request.url)
        self.assertNotIn("expansions", request.url)

    def test_FR_002_success_normalizes_id_and_text(self):
        transport = FakeTransport(
            response=response(
                200,
                {
                    "data": {
                        "id": "2095768443006177767",
                        "text": "hello from X",
                        "author_id": "999",
                    },
                    "includes": {"users": [{"id": "999", "username": "ignored"}]},
                },
            )
        )

        envelope = lookup_post(
            "2095768443006177767",
            bearer_token="fake-bearer-token",
            transport=transport,
        )

        data = envelope.to_dict()
        self.assertEqual(data["operation"], "read")
        self.assertIsNone(data["subject"])
        self.assertEqual(data["items"], [{"id": "2095768443006177767", "text": "hello from X"}])
        self.assertEqual(data["page"], {"next_token": None, "complete": True})
        self.assertNotIn("author", data["items"][0])
        self.assertNotIn("includes", data)

    def test_FR_002_rejects_provider_id_mismatch(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "124", "text": "wrong"}}))

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(raised.exception.category, "provider_error")
        self.assertEqual(len(transport.requests), 1)

    def test_FR_002_rejects_malformed_success_payload(self):
        malformed = (
            {},
            {"data": None},
            {"data": {}},
            {"data": {"id": "123"}},
            {"data": {"id": 123, "text": "hello"}},
            {"data": {"id": "123", "text": None}},
        )

        for payload in malformed:
            with self.subTest(payload=payload):
                transport = FakeTransport(response=response(200, payload))
                with self.assertRaises(XApiError) as raised:
                    lookup_post("123", bearer_token="fake-bearer-token", transport=transport)
                self.assertEqual(raised.exception.category, "provider_error")
                self.assertEqual(len(transport.requests), 1)

    def test_FR_002_authentication_failure(self):
        transport = FakeTransport(
            response=response(
                401,
                {"type": "https://api.x.com/2/problems/unauthorized", "title": "Unauthorized"},
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(raised.exception.category, "authentication_failed")
        self.assertEqual(raised.exception.status_code, 401)

    def test_FR_002_authorization_failure(self):
        transport = FakeTransport(
            response=response(
                403,
                {
                    "type": "https://api.x.com/2/problems/not-authorized-for-resource",
                    "title": "Forbidden",
                },
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(raised.exception.category, "authorization_failed")
        self.assertEqual(raised.exception.status_code, 403)

    def test_FR_002_resource_unavailable(self):
        transport = FakeTransport(
            response=response(
                404,
                {
                    "type": "https://api.x.com/2/problems/resource-not-found",
                    "title": "Not Found",
                },
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(raised.exception.category, "resource_unavailable")
        self.assertEqual(raised.exception.status_code, 404)

    def test_FR_002_rate_limited_safe_metadata(self):
        transport = FakeTransport(
            response=response(
                429,
                {
                    "type": "https://api.x.com/2/problems/rate-limit-exceeded",
                    "title": "Too Many Requests",
                },
                {
                    "X-Rate-Limit-Limit": "450",
                    "x-rate-limit-remaining": "0",
                    "X-Rate-Limit-Reset": "1789099200",
                    "x-provider-secret": "must-not-pass-through",
                },
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        error = raised.exception
        self.assertEqual(error.category, "rate_limited")
        self.assertEqual(error.rate_limit.limit, 450)
        self.assertEqual(error.rate_limit.remaining, 0)
        self.assertEqual(error.rate_limit.reset, 1789099200)
        self.assertFalse(hasattr(error.rate_limit, "x_provider_secret"))

    def test_FR_002_usage_blocked(self):
        transport = FakeTransport(
            response=response(
                429,
                {
                    "type": "https://api.x.com/2/problems/usage-capped",
                    "title": "Usage cap exceeded",
                },
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)

        self.assertEqual(raised.exception.category, "usage_blocked")

    def test_FR_002_provider_error(self):
        cases = (
            response(429, {"title": "ambiguous 429"}),
            response(500, {"title": "provider failed"}),
            HttpResponse(status=200, headers={}, body=b"not-json"),
        )
        for provider_response in cases:
            with self.subTest(status=provider_response.status):
                transport = FakeTransport(response=provider_response)
                with self.assertRaises(XApiError) as raised:
                    lookup_post("123", bearer_token="fake-bearer-token", transport=transport)
                self.assertEqual(raised.exception.category, "provider_error")

        transport = FakeTransport(error=OSError("synthetic network failure"))
        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token="fake-bearer-token", transport=transport)
        self.assertEqual(raised.exception.category, "provider_error")

    def test_FR_002_missing_bearer_token_is_configuration_error_without_network(self):
        transport = FakeTransport(response=response(500, {}))

        for token in ("", None):
            with self.subTest(token=token):
                with self.assertRaises(XApiError) as raised:
                    lookup_post("123", bearer_token=token, transport=transport)
                self.assertEqual(raised.exception.category, "configuration_error")

        self.assertEqual(transport.requests, [])

    def test_FR_002_no_fallback_or_secret_passthrough(self):
        token = "fake-bearer-token-DO-NOT-LEAK"
        private_body_value = "raw-provider-secret-DO-NOT-LEAK"
        transport = FakeTransport(
            response=response(
                403,
                {
                    "type": "https://api.x.com/2/problems/client-forbidden",
                    "detail": private_body_value,
                },
            )
        )

        with self.assertRaises(XApiError) as raised:
            lookup_post("123", bearer_token=token, transport=transport)

        error = raised.exception
        self.assertEqual(len(transport.requests), 1)
        self.assertNotIn(token, str(error))
        self.assertNotIn(private_body_value, str(error))
        self.assertFalse(hasattr(error, "raw_response"))
        self.assertFalse(hasattr(error, "authorization"))


if __name__ == "__main__":
    unittest.main()
