import json
import os
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from x_context.x_api import (
    AuthenticatedSubject,
    HttpRequest,
    HttpResponse,
    XApiError,
    bind_collection_subject,
    resolve_authenticated_subject,
)


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


class AuthenticatedSubjectTests(unittest.TestCase):
    def test_AUTH_SUBJ_uses_official_authenticated_user_endpoint(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "123", "username": "alice"}}))

        resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)

        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url, "https://api.x.com/2/users/me")
        self.assertEqual(request.headers["Authorization"], "Bearer fake-user-token")
        self.assertEqual(request.headers["Accept"], "application/json")

    def test_AUTH_SUBJ_requests_no_optional_user_fields_or_expansions(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "123", "username": "alice"}}))

        resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)

        request = transport.requests[0]
        self.assertNotIn("?", request.url)
        self.assertNotIn("user.fields", request.url)
        self.assertNotIn("expansions", request.url)

    def test_AUTH_SUBJ_rejects_missing_or_unsafe_user_token_without_transport(self):
        transport = FakeTransport(response=response(500, {}))

        for token in (None, "", "bad\rvalue", "bad\nvalue"):
            with self.subTest(token=token):
                with self.assertRaises(XApiError) as raised:
                    resolve_authenticated_subject(user_access_token=token, transport=transport)
                self.assertEqual(raised.exception.category, "configuration_error")
                self.assertEqual(raised.exception.requests_attempted, 0)

        self.assertEqual(transport.requests, [])

    def test_AUTH_SUBJ_app_only_token_is_not_a_user_token_fallback(self):
        transport = FakeTransport(response=response(500, {}))
        with patch.dict(os.environ, {"X_CONTEXT_BEARER_TOKEN": "fake-app-only-token"}, clear=False):
            with self.assertRaises(XApiError) as raised:
                resolve_authenticated_subject(user_access_token=None, transport=transport)

        self.assertEqual(raised.exception.category, "configuration_error")
        self.assertEqual(transport.requests, [])

    def test_AUTH_SUBJ_normalizes_minimum_subject(self):
        transport = FakeTransport(
            response=response(
                200,
                {
                    "data": {
                        "id": "2244994945",
                        "username": "XDevelopers",
                        "name": "must not enter subject contract",
                        "description": "ignored",
                    }
                },
            )
        )

        result = resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)

        self.assertEqual(result.subject, AuthenticatedSubject(id="2244994945", username="XDevelopers"))
        self.assertFalse(hasattr(result.subject, "name"))
        self.assertFalse(hasattr(result.subject, "description"))

    def test_AUTH_SUBJ_username_is_optional(self):
        transport = FakeTransport(response=response(200, {"data": {"id": "123"}}))

        result = resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)

        self.assertEqual(result.subject, AuthenticatedSubject(id="123", username=None))

    def test_AUTH_SUBJ_rejects_malformed_subject_payload(self):
        malformed = (
            {},
            {"data": None},
            {"data": {}},
            {"data": {"id": 123}},
            {"data": {"id": ""}},
            {"data": {"id": "abc"}},
            {"data": {"id": "１２３"}},
            {"data": {"id": "123", "username": ""}},
            {"data": {"id": "123", "username": 99}},
        )

        for payload in malformed:
            with self.subTest(payload=payload):
                transport = FakeTransport(response=response(200, payload))
                with self.assertRaises(XApiError) as raised:
                    resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)
                self.assertEqual(raised.exception.category, "provider_error")
                self.assertEqual(raised.exception.requests_attempted, 1)

    def test_AUTH_SUBJ_maps_authentication_and_authorization_failures(self):
        cases = ((401, "authentication_failed"), (403, "authorization_failed"))

        for status, category in cases:
            with self.subTest(status=status):
                transport = FakeTransport(response=response(status, {"detail": "do not expose"}))
                with self.assertRaises(XApiError) as raised:
                    resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)
                self.assertEqual(raised.exception.category, category)
                self.assertEqual(raised.exception.requests_attempted, 1)

    def test_AUTH_SUBJ_provider_failure_is_conservative(self):
        cases = (
            response(404, {"title": "not found"}),
            response(429, {"title": "ambiguous 429"}),
            response(500, {"title": "failed"}),
            HttpResponse(status=200, headers={}, body=b"not-json"),
        )

        for provider_response in cases:
            with self.subTest(status=provider_response.status):
                transport = FakeTransport(response=provider_response)
                with self.assertRaises(XApiError) as raised:
                    resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)
                self.assertEqual(raised.exception.category, "provider_error")

    def test_AUTH_SUBJ_does_not_leak_token_raw_body_headers_or_transport_exception(self):
        token = "fake-user-token-DO-NOT-LEAK"
        raw_secret = "raw-provider-secret-DO-NOT-LEAK"
        header_secret = "header-secret-DO-NOT-LEAK"
        transport = FakeTransport(
            response=response(
                403,
                {"detail": raw_secret},
                {"x-provider-secret": header_secret},
            )
        )

        with self.assertRaises(XApiError) as raised:
            resolve_authenticated_subject(user_access_token=token, transport=transport)

        error_text = str(raised.exception)
        self.assertNotIn(token, error_text)
        self.assertNotIn(raw_secret, error_text)
        self.assertNotIn(header_secret, error_text)
        self.assertNotIn(token, repr(transport.requests[0]))

        transport_exception_secret = "transport-secret-DO-NOT-LEAK"
        transport = FakeTransport(error=RuntimeError(transport_exception_secret))
        try:
            resolve_authenticated_subject(user_access_token=token, transport=transport)
        except XApiError as exc:
            self.assertEqual(exc.category, "provider_error")
            self.assertEqual(exc.requests_attempted, 1)
            self.assertIsNone(exc.__cause__)
            self.assertNotIn(transport_exception_secret, str(exc))
            self.assertNotIn(token, str(exc))
        else:
            self.fail("expected XApiError")

    def test_AUTH_SUBJ_same_subject_binding_succeeds_locally(self):
        subject = AuthenticatedSubject(id="123", username="alice")

        bound = bind_collection_subject(subject, "123")

        self.assertEqual(bound, "123")

    def test_AUTH_SUBJ_mismatch_fails_closed_locally(self):
        subject = AuthenticatedSubject(id="123", username="alice")

        with self.assertRaises(XApiError) as raised:
            bind_collection_subject(subject, "456")

        self.assertEqual(raised.exception.category, "subject_mismatch")
        self.assertEqual(raised.exception.requests_attempted, 0)

    def test_AUTH_SUBJ_invalid_target_is_invalid_input(self):
        subject = AuthenticatedSubject(id="123", username="alice")

        for target in ("", "abc", "１２３"):
            with self.subTest(target=target):
                with self.assertRaises(XApiError) as raised:
                    bind_collection_subject(subject, target)
                self.assertEqual(raised.exception.category, "invalid_input")
                self.assertEqual(raised.exception.requests_attempted, 0)

    def test_AUTH_SUBJ_reports_request_attempt_and_safe_rate_metadata(self):
        transport = FakeTransport(
            response=response(
                200,
                {"data": {"id": "123", "username": "alice"}},
                {
                    "X-Rate-Limit-Limit": "75",
                    "x-rate-limit-remaining": "74",
                    "X-Rate-Limit-Reset": "1789099200",
                    "x-provider-secret": "must-not-pass-through",
                },
            )
        )

        result = resolve_authenticated_subject(user_access_token="fake-user-token", transport=transport)

        self.assertEqual(result.requests_attempted, 1)
        self.assertEqual(result.rate_limit.limit, 75)
        self.assertEqual(result.rate_limit.remaining, 74)
        self.assertEqual(result.rate_limit.reset, 1789099200)
        self.assertFalse(hasattr(result.rate_limit, "x_provider_secret"))


if __name__ == "__main__":
    unittest.main()
