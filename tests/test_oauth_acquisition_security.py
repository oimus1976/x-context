import unittest

from x_context.oauth import (
    OAuthConfig,
    OAuthError,
    OAuthHttpResponse,
    build_authorization_attempt,
    exchange_callback,
)


class _Transport:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.response


class OAuthAcquisitionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.config = OAuthConfig(
            client_id="fake-public-client-id",
            redirect_uri="http://127.0.0.1:8765/oauth/callback",
        )

    def test_OAUTH_unrequested_refresh_token_fails_closed(self):
        attempt = build_authorization_attempt(self.config, refresh_capable=False)
        transport = _Transport(
            OAuthHttpResponse(
                status=200,
                headers={},
                body=b'{"access_token":"fake-access","refresh_token":"unexpected-refresh"}',
            )
        )

        with self.assertRaises(OAuthError) as raised:
            exchange_callback(
                self.config,
                attempt,
                f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
                transport=transport,
            )

        self.assertEqual(raised.exception.category, "provider_error")
        self.assertEqual(len(transport.requests), 1)

    def test_OAUTH_unsafe_client_id_is_configuration_error(self):
        for client_id in ("", " leading", "trailing ", "bad\rvalue", "bad\nvalue"):
            with self.subTest(client_id=client_id):
                with self.assertRaises(OAuthError) as raised:
                    OAuthConfig(
                        client_id=client_id,
                        redirect_uri="http://127.0.0.1:8765/oauth/callback",
                    )
                self.assertEqual(raised.exception.category, "configuration_error")


if __name__ == "__main__":
    unittest.main()
