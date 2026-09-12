import io
import json
import unittest
from dataclasses import dataclass, field

from x_context.cli import main
from x_context.x_api import HttpRequest, HttpResponse


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


def run_cli(
    argv: list[str],
    *,
    provider_response: HttpResponse | None = None,
    environ: dict[str, str] | None = None,
):
    stdout = io.StringIO()
    stderr = io.StringIO()
    transport = FakeTransport(
        response=provider_response
        if provider_response is not None
        else response(200, {"data": {"id": "123", "text": "hello"}})
    )
    exit_code = main(
        argv,
        environ={} if environ is None else environ,
        transport=transport,
        stdout=stdout,
        stderr=stderr,
    )
    return exit_code, stdout.getvalue(), stderr.getvalue(), transport


class FR006ReadCliTests(unittest.TestCase):
    def test_FR_006_read_success_writes_canonical_json_only_to_stdout(self):
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "https://x.com/example/status/123"],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(transport.requests), 1)
        payload = json.loads(stdout)
        self.assertEqual(payload["operation"], "read")
        self.assertEqual(payload["items"], [{"id": "123", "text": "hello"}])
        self.assertNotIn("diagnostic", payload)
        self.assertNotIn("rate_limit", payload)
        self.assertTrue(stdout.endswith("\n"))
        self.assertIn('"diagnostic":"usage"', stderr)

    def test_FR_006_read_success_writes_usage_diagnostics_to_stderr(self):
        exit_code, stdout, stderr, _ = run_cli(
            ["read", "https://twitter.com/example/status/123"],
            provider_response=response(
                200,
                {"data": {"id": "123", "text": "hello"}},
                {
                    "x-rate-limit-limit": "450",
                    "x-rate-limit-remaining": "449",
                    "x-rate-limit-reset": "1789099200",
                },
            ),
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 0)
        self.assertNotEqual(stdout, "")
        diagnostic = json.loads(stderr)
        self.assertEqual(diagnostic["diagnostic"], "usage")
        self.assertEqual(diagnostic["operation"], "read")
        self.assertEqual(diagnostic["provider_requests_attempted"], 1)
        self.assertEqual(diagnostic["returned_item_count"], 1)
        self.assertIs(diagnostic["continuation_returned"], False)
        self.assertEqual(
            diagnostic["rate_limit"],
            {"limit": 450, "remaining": 449, "reset": 1789099200},
        )
        self.assertNotIn("requested_page_size", diagnostic)

    def test_FR_006_read_rejects_direct_post_id(self):
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "123"],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        diagnostic = json.loads(stderr)
        self.assertEqual(diagnostic["error_category"], "invalid_input")
        self.assertEqual(diagnostic["provider_requests_attempted"], 0)
        self.assertEqual(transport.requests, [])

    def test_FR_006_read_invalid_url_is_local_exit_2_without_network(self):
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "https://example.com/user/status/123"],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "invalid_input")
        self.assertEqual(transport.requests, [])

    def test_FR_006_read_provider_incompatible_id_is_local_exit_2_without_transport(self):
        post_id = "12345678901234567890"
        exit_code, stdout, stderr, transport = run_cli(
            ["read", f"https://x.com/example/status/{post_id}"],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        diagnostic = json.loads(stderr)
        self.assertEqual(diagnostic["error_category"], "invalid_input")
        self.assertEqual(diagnostic["provider_requests_attempted"], 0)
        self.assertEqual(transport.requests, [])

    def test_FR_006_read_missing_credential_is_configuration_exit_2_without_transport(self):
        for environ in ({}, {"X_CONTEXT_BEARER_TOKEN": ""}):
            with self.subTest(environ=environ):
                exit_code, stdout, stderr, transport = run_cli(
                    ["read", "https://x.com/example/status/123"],
                    environ=environ,
                )
                self.assertEqual(exit_code, 2)
                self.assertEqual(stdout, "")
                diagnostic = json.loads(stderr)
                self.assertEqual(diagnostic["error_category"], "configuration_error")
                self.assertEqual(diagnostic["provider_requests_attempted"], 0)
                self.assertEqual(transport.requests, [])

    def test_FR_006_read_unsafe_credential_is_configuration_exit_2_without_transport(self):
        token = "fake-token\r\nInjected: value"
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "https://x.com/example/status/123"],
            environ={"X_CONTEXT_BEARER_TOKEN": token},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "configuration_error")
        self.assertNotIn(token, stderr)
        self.assertEqual(transport.requests, [])

    def test_FR_006_read_provider_categories_exit_3(self):
        cases = (
            (401, {"type": "https://api.x.com/2/problems/unauthorized"}, "authentication_failed"),
            (403, {"type": "https://api.x.com/2/problems/not-authorized-for-resource"}, "authorization_failed"),
            (404, {"type": "https://api.x.com/2/problems/resource-not-found"}, "resource_unavailable"),
            (429, {"type": "https://api.x.com/2/problems/rate-limit-exceeded"}, "rate_limited"),
            (429, {"type": "https://api.x.com/2/problems/usage-capped"}, "usage_blocked"),
            (500, {"title": "provider failed"}, "provider_error"),
        )

        for status, payload, category in cases:
            with self.subTest(category=category):
                exit_code, stdout, stderr, transport = run_cli(
                    ["read", "https://x.com/example/status/123"],
                    provider_response=response(status, payload),
                    environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
                )
                self.assertEqual(exit_code, 3)
                self.assertEqual(stdout, "")
                diagnostic = json.loads(stderr)
                self.assertEqual(diagnostic["error_category"], category)
                self.assertEqual(diagnostic["provider_requests_attempted"], 1)
                self.assertEqual(len(transport.requests), 1)

    def test_FR_006_read_success_exposes_only_safe_rate_metadata(self):
        sentinel = "arbitrary-provider-header-secret"
        exit_code, _, stderr, _ = run_cli(
            ["read", "https://x.com/example/status/123"],
            provider_response=response(
                200,
                {"data": {"id": "123", "text": "hello"}},
                {
                    "x-rate-limit-limit": "450",
                    "x-provider-secret": sentinel,
                },
            ),
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 0)
        diagnostic = json.loads(stderr)
        self.assertEqual(diagnostic["rate_limit"]["limit"], 450)
        self.assertNotIn(sentinel, stderr)
        self.assertNotIn("x-provider-secret", stderr)

    def test_FR_006_read_missing_rate_metadata_is_not_fabricated(self):
        exit_code, _, stderr, _ = run_cli(
            ["read", "https://x.com/example/status/123"],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            json.loads(stderr)["rate_limit"],
            {"limit": None, "remaining": None, "reset": None},
        )

    def test_FR_006_read_has_no_token_cli_argument(self):
        secret = "SHOULD-NOT-APPEAR"
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "https://x.com/example/status/123", "--token", secret],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "invalid_input")
        self.assertNotIn(secret, stderr)
        self.assertEqual(transport.requests, [])

    def test_FR_006_read_does_not_leak_token_raw_body_or_arbitrary_headers(self):
        token = "fake-token-DO-NOT-LEAK"
        raw_sentinel = "raw-provider-body-DO-NOT-LEAK"
        header_sentinel = "provider-header-DO-NOT-LEAK"
        exit_code, stdout, stderr, _ = run_cli(
            ["read", "https://x.com/example/status/123"],
            provider_response=response(
                403,
                {
                    "type": "https://api.x.com/2/problems/client-forbidden",
                    "detail": raw_sentinel,
                },
                {"x-provider-secret": header_sentinel},
            ),
            environ={"X_CONTEXT_BEARER_TOKEN": token},
        )

        self.assertEqual(exit_code, 3)
        combined = stdout + stderr
        self.assertNotIn(token, combined)
        self.assertNotIn(raw_sentinel, combined)
        self.assertNotIn(header_sentinel, combined)
        self.assertNotIn("Authorization", combined)

    def test_FR_006_read_parser_error_is_stable_and_does_not_echo_secret_argument(self):
        secret = "super-secret-extra-argument"
        exit_code, stdout, stderr, transport = run_cli(
            ["read", "https://x.com/example/status/123", secret],
            environ={"X_CONTEXT_BEARER_TOKEN": "fake-token"},
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout, "")
        diagnostic = json.loads(stderr)
        self.assertEqual(diagnostic["error_category"], "invalid_input")
        self.assertNotIn(secret, stderr)
        self.assertEqual(transport.requests, [])


if __name__ == "__main__":
    unittest.main()
