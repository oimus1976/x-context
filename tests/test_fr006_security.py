import io
import json
import unittest

from x_context.cli import main
from x_context.x_api import HttpRequest


class ExplodingTransport:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.requests: list[HttpRequest] = []

    def __call__(self, request: HttpRequest):
        self.requests.append(request)
        raise RuntimeError(self.secret)


class FR006SecurityTests(unittest.TestCase):
    def test_FR_006_read_transport_exception_is_redacted_and_counted(self):
        token = "fake-token-DO-NOT-LEAK"
        provider_secret = "provider-exception-secret-DO-NOT-LEAK"
        transport = ExplodingTransport(provider_secret)
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["read", "https://x.com/example/status/123"],
            environ={"X_CONTEXT_BEARER_TOKEN": token},
            transport=transport,
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 3)
        self.assertEqual(stdout.getvalue(), "")
        diagnostic = json.loads(stderr.getvalue())
        self.assertEqual(diagnostic["error_category"], "provider_error")
        self.assertEqual(diagnostic["provider_requests_attempted"], 1)
        self.assertEqual(len(transport.requests), 1)
        combined = stdout.getvalue() + stderr.getvalue()
        self.assertNotIn(token, combined)
        self.assertNotIn(provider_secret, combined)
        self.assertNotIn("Authorization", combined)


if __name__ == "__main__":
    unittest.main()
