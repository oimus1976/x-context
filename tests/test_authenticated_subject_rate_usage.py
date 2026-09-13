import json
import unittest
from dataclasses import dataclass, field

from x_context.x_api import HttpRequest, HttpResponse, XApiError, resolve_authenticated_subject


@dataclass
class FakeTransport:
    response: HttpResponse
    requests: list[HttpRequest] = field(default_factory=list)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return self.response


def response(status: int, payload: object, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(
        status=status,
        headers={} if headers is None else headers,
        body=json.dumps(payload).encode("utf-8"),
    )


class AuthenticatedSubjectRateUsageTests(unittest.TestCase):
    def test_AUTH_SUBJ_maps_identified_rate_and_usage_failures(self):
        cases = (
            (
                response(
                    429,
                    {"type": "https://api.x.com/2/problems/rate-limit-exceeded"},
                    {
                        "x-rate-limit-limit": "75",
                        "x-rate-limit-remaining": "0",
                        "x-rate-limit-reset": "1789099200",
                    },
                ),
                "rate_limited",
            ),
            (
                response(
                    429,
                    {"type": "https://api.x.com/2/problems/usage-capped"},
                ),
                "usage_blocked",
            ),
        )

        for provider_response, category in cases:
            with self.subTest(category=category):
                transport = FakeTransport(provider_response)
                with self.assertRaises(XApiError) as raised:
                    resolve_authenticated_subject(
                        user_access_token="fake-user-token",
                        transport=transport,
                    )

                error = raised.exception
                self.assertEqual(error.category, category)
                self.assertEqual(error.requests_attempted, 1)
                self.assertEqual(len(transport.requests), 1)

                if category == "rate_limited":
                    self.assertEqual(error.rate_limit.limit, 75)
                    self.assertEqual(error.rate_limit.remaining, 0)
                    self.assertEqual(error.rate_limit.reset, 1789099200)


if __name__ == "__main__":
    unittest.main()
