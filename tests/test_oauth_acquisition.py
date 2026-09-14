import base64
import hashlib
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

from x_context.oauth import (
    AUTHORIZE_ENDPOINT,
    TOKEN_ENDPOINT,
    OAuthConfig,
    OAuthError,
    OAuthHttpRequest,
    OAuthHttpResponse,
    OAuthTokenResult,
    acquire_user_token,
    build_authorization_attempt,
    exchange_callback,
)


@dataclass
class FakeBrowser:
    result: bool = True
    error: Exception | None = None
    urls: list[str] = field(default_factory=list)

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass
class FakeListener:
    callback_url: str | None = None
    bind_error: Exception | None = None
    wait_error: Exception | None = None
    entered: int = 0
    waits: int = 0
    closed: int = 0

    def __enter__(self):
        self.entered += 1
        if self.bind_error is not None:
            raise self.bind_error
        return self

    def wait_for_callback(self, timeout: float) -> str:
        self.waits += 1
        if self.wait_error is not None:
            raise self.wait_error
        if self.callback_url is None:
            raise AssertionError("fake listener has no callback")
        return self.callback_url

    def __exit__(self, exc_type, exc, tb):
        self.closed += 1
        return False


@dataclass
class FakeTransport:
    response: OAuthHttpResponse | None = None
    error: Exception | None = None
    requests: list[OAuthHttpRequest] = field(default_factory=list)

    def __call__(self, request: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("fake transport has no response")
        return self.response


def token_response(status: int, payload: object) -> OAuthHttpResponse:
    return OAuthHttpResponse(
        status=status,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def config() -> OAuthConfig:
    return OAuthConfig(
        client_id="fake-public-client-id",
        redirect_uri="http://127.0.0.1:8765/oauth/callback",
    )


class OAuthAcquisitionTests(unittest.TestCase):
    def test_OAUTH_uses_official_authorize_endpoint_and_read_scopes(self):
        attempt = build_authorization_attempt(config())
        parsed = urlparse(attempt.authorization_url)
        query = parse_qs(parsed.query)

        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", AUTHORIZE_ENDPOINT)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["client_id"], ["fake-public-client-id"])
        self.assertEqual(query["redirect_uri"], ["http://127.0.0.1:8765/oauth/callback"])
        self.assertEqual(
            set(query["scope"][0].split()),
            {"tweet.read", "users.read", "bookmark.read", "like.read"},
        )
        self.assertNotIn("offline.access", query["scope"][0].split())

    def test_OAUTH_offline_access_is_explicit_only(self):
        normal = parse_qs(urlparse(build_authorization_attempt(config()).authorization_url).query)
        refresh = parse_qs(
            urlparse(build_authorization_attempt(config(), refresh_capable=True).authorization_url).query
        )

        self.assertNotIn("offline.access", normal["scope"][0].split())
        self.assertIn("offline.access", refresh["scope"][0].split())

    def test_OAUTH_generates_fresh_state_and_verifier_per_attempt(self):
        first = build_authorization_attempt(config())
        second = build_authorization_attempt(config())

        self.assertNotEqual(first.state, second.state)
        self.assertNotEqual(first.code_verifier, second.code_verifier)

        rendered = repr(first)
        self.assertNotIn(first.state, rendered)
        self.assertNotIn(first.code_verifier, rendered)
        self.assertNotIn(first.authorization_url, rendered)

    def test_OAUTH_derives_s256_challenge_without_plain_fallback(self):
        attempt = build_authorization_attempt(config())
        query = parse_qs(urlparse(attempt.authorization_url).query)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(attempt.code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")

        self.assertEqual(attempt.code_challenge, expected)
        self.assertEqual(query["code_challenge"], [expected])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotEqual(expected, attempt.code_verifier)

    def test_OAUTH_public_client_uses_client_id_without_secret(self):
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))

        exchange_callback(
            config(),
            attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        request = transport.requests[0]
        body = parse_qs(request.body.decode("ascii"))
        self.assertEqual(body["client_id"], ["fake-public-client-id"])
        self.assertNotIn("client_secret", body)
        self.assertNotIn("Authorization", request.headers)

    def test_OAUTH_exact_token_endpoint_form_contract(self):
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))

        exchange_callback(
            config(),
            attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        request = transport.requests[0]
        body = parse_qs(request.body.decode("ascii"))
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, TOKEN_ENDPOINT)
        self.assertEqual(request.headers["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(body["grant_type"], ["authorization_code"])
        self.assertEqual(body["code"], ["fake-code"])
        self.assertEqual(body["redirect_uri"], [config().redirect_uri])
        self.assertEqual(body["client_id"], [config().client_id])
        self.assertEqual(body["code_verifier"], [attempt.code_verifier])

    def test_OAUTH_loopback_configuration_requires_127_0_0_1_fixed_registered_redirect(self):
        invalid = (
            "http://localhost:8765/oauth/callback",
            "http://0.0.0.0:8765/oauth/callback",
            "http://192.168.1.10:8765/oauth/callback",
            "https://127.0.0.1:8765/oauth/callback",
            "http://127.0.0.1/oauth/callback",
            "http://127.0.0.1:8765/",
            "http://127.0.0.1:8765/oauth/callback?x=1",
            "http://127.0.0.1:8765/oauth/callback#fragment",
        )
        for redirect_uri in invalid:
            with self.subTest(redirect_uri=redirect_uri):
                with self.assertRaises(OAuthError) as raised:
                    OAuthConfig(client_id="fake-public-client-id", redirect_uri=redirect_uri)
                self.assertEqual(raised.exception.category, "configuration_error")

    def test_OAUTH_bind_failure_prevents_browser_launch(self):
        browser = FakeBrowser()
        listener = FakeListener(bind_error=OSError("bind failed with secret-shaped noise"))

        with self.assertRaises(OAuthError) as raised:
            acquire_user_token(
                config(),
                browser_launcher=browser,
                listener_factory=lambda _: listener,
                transport=FakeTransport(),
            )

        self.assertEqual(raised.exception.category, "callback_listener_failed")
        self.assertEqual(browser.urls, [])

    def test_OAUTH_browser_launch_failure_closes_listener_without_wait_or_exchange(self):
        listener = FakeListener(
            callback_url="http://127.0.0.1:8765/oauth/callback?unused=1"
        )
        transport = FakeTransport()

        for browser in (
            FakeBrowser(result=False),
            FakeBrowser(error=RuntimeError("browser failure with secret-shaped noise")),
        ):
            with self.subTest(browser=browser):
                with self.assertRaises(OAuthError) as raised:
                    acquire_user_token(
                        config(),
                        browser_launcher=browser,
                        listener_factory=lambda _: listener,
                        transport=transport,
                    )

                self.assertEqual(raised.exception.category, "browser_launch_failed")
                self.assertEqual(listener.waits, 0)
                self.assertEqual(transport.requests, [])

    def test_OAUTH_external_browser_boundary_is_single_launch(self):
        attempt_holder = {}

        def listener_factory(attempt):
            attempt_holder["attempt"] = attempt
            return FakeListener(
                callback_url=f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}"
            )

        browser = FakeBrowser()
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))

        acquire_user_token(
            config(),
            browser_launcher=browser,
            listener_factory=listener_factory,
            transport=transport,
        )

        self.assertEqual(len(browser.urls), 1)
        self.assertEqual(browser.urls[0], attempt_holder["attempt"].authorization_url)

    def test_OAUTH_correct_state_callback_exchanges_once(self):
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))

        result = exchange_callback(
            config(),
            attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        self.assertIsInstance(result, OAuthTokenResult)
        self.assertEqual(len(transport.requests), 1)

    def test_OAUTH_missing_wrong_or_duplicate_state_blocks_exchange(self):
        attempt = build_authorization_attempt(config())
        callbacks = (
            "http://127.0.0.1:8765/oauth/callback?code=fake-code",
            "http://127.0.0.1:8765/oauth/callback?code=fake-code&state=wrong",
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}&state={attempt.state}",
        )
        for callback in callbacks:
            with self.subTest(callback=callback):
                transport = FakeTransport(response=token_response(200, {"access_token": "unused"}))
                with self.assertRaises(OAuthError) as raised:
                    exchange_callback(config(), attempt, callback, transport=transport)
                self.assertEqual(raised.exception.category, "oauth_state_mismatch")
                self.assertEqual(transport.requests, [])

    def test_OAUTH_wrong_path_malformed_or_provider_error_callback_blocks_exchange(self):
        attempt = build_authorization_attempt(config())
        callbacks = (
            f"http://127.0.0.1:8765/wrong?code=fake-code&state={attempt.state}",
            f"http://127.0.0.1:8765/oauth/callback?state={attempt.state}",
            f"http://127.0.0.1:8765/oauth/callback?code=a&code=b&state={attempt.state}",
            f"http://127.0.0.1:8765/oauth/callback?error=access_denied&state={attempt.state}",
        )
        for callback in callbacks:
            with self.subTest(callback=callback):
                transport = FakeTransport(response=token_response(200, {"access_token": "unused"}))
                with self.assertRaises(OAuthError):
                    exchange_callback(config(), attempt, callback, transport=transport)
                self.assertEqual(transport.requests, [])

    def test_OAUTH_duplicate_late_callback_cannot_reexchange(self):
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))
        callback = f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}"

        exchange_callback(config(), attempt, callback, transport=transport)
        with self.assertRaises(OAuthError) as raised:
            exchange_callback(config(), attempt, callback, transport=transport)

        self.assertEqual(raised.exception.category, "oauth_attempt_complete")
        self.assertEqual(len(transport.requests), 1)

    def test_OAUTH_unrelated_request_does_not_terminate_loopback_wait(self):
        from x_context.oauth import LoopbackCallbackListener

        class FakeServer:
            def __init__(self):
                self.callback_target = None
                self.timeout = None
                self.calls = 0

            def handle_request(self):
                self.calls += 1
                if self.calls == 2:
                    self.callback_target = "/oauth/callback?code=fake-code&state=fake-state"

        listener = LoopbackCallbackListener(config().redirect_uri)
        fake_server = FakeServer()
        listener._server = fake_server

        callback = listener.wait_for_callback(1.0)

        self.assertEqual(fake_server.calls, 2)
        self.assertEqual(
            callback,
            "http://127.0.0.1:8765/oauth/callback?code=fake-code&state=fake-state",
        )

    def test_OAUTH_timeout_closes_listener_without_exchange(self):
        browser = FakeBrowser()
        listener = FakeListener(wait_error=TimeoutError("timeout with no secret echo"))
        transport = FakeTransport()

        with self.assertRaises(OAuthError) as raised:
            acquire_user_token(
                config(),
                browser_launcher=browser,
                listener_factory=lambda _: listener,
                transport=transport,
                timeout=0.01,
            )

        self.assertEqual(raised.exception.category, "oauth_callback_timeout")
        self.assertEqual(listener.closed, 1)
        self.assertEqual(transport.requests, [])

    def test_OAUTH_access_token_only_result_is_in_memory_and_redacted(self):
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(
            response=token_response(
                200,
                {"access_token": "fake-access-secret", "token_type": "bearer", "expires_in": 7200, "scope": "tweet.read users.read bookmark.read like.read"},
            )
        )

        result = exchange_callback(
            config(), attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        self.assertEqual(result.access_token, "fake-access-secret")
        self.assertIsNone(result.refresh_token)
        self.assertNotIn("fake-access-secret", repr(result))

    def test_OAUTH_refresh_token_result_requires_provider_value(self):
        attempt = build_authorization_attempt(config(), refresh_capable=True)
        transport = FakeTransport(
            response=token_response(
                200,
                {"access_token": "fake-access", "refresh_token": "fake-refresh-secret", "token_type": "bearer"},
            )
        )

        result = exchange_callback(
            config(), attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        self.assertEqual(result.refresh_token, "fake-refresh-secret")
        self.assertNotIn("fake-refresh-secret", repr(result))

    def test_OAUTH_malformed_success_fails_closed(self):
        attempt = build_authorization_attempt(config())
        malformed = (
            {},
            {"access_token": ""},
            {"access_token": 123},
            {"access_token": "bad\nvalue"},
            {"access_token": "fake-access", "refresh_token": ""},
            {"access_token": "fake-access", "expires_in": "7200"},
            {"access_token": "fake-access", "scope": ["tweet.read"]},
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                transport = FakeTransport(response=token_response(200, payload))
                fresh_attempt = build_authorization_attempt(config())
                with self.assertRaises(OAuthError) as raised:
                    exchange_callback(
                        config(), fresh_attempt,
                        f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={fresh_attempt.state}",
                        transport=transport,
                    )
                self.assertEqual(raised.exception.category, "provider_error")

    def test_OAUTH_transport_and_provider_failures_are_conservative_and_redacted(self):
        attempt = build_authorization_attempt(config())
        secret = "SENTINEL-OAUTH-CODE"
        cases = (
            FakeTransport(response=token_response(500, {"detail": secret})),
            FakeTransport(error=OSError(f"transport exploded {secret}")),
        )
        for transport in cases:
            with self.subTest(transport=transport):
                fresh_attempt = build_authorization_attempt(config())
                try:
                    exchange_callback(
                        config(), fresh_attempt,
                        f"http://127.0.0.1:8765/oauth/callback?code={secret}&state={fresh_attempt.state}",
                        transport=transport,
                    )
                except OAuthError as exc:
                    rendered = f"{exc!r} {exc}"
                    self.assertEqual(exc.category, "provider_error")
                    self.assertNotIn(secret, rendered)
                    self.assertIsNone(exc.__cause__)
                else:
                    self.fail("expected OAuthError")

    def test_OAUTH_secret_sentinels_absent_from_stdout_stderr_repr_traceback(self):
        attempt = build_authorization_attempt(config(), refresh_capable=True)
        sentinels = {
            "code": "SENTINEL-CODE",
            "access": "SENTINEL-ACCESS",
            "refresh": "SENTINEL-REFRESH",
        }
        transport = FakeTransport(
            response=token_response(
                200,
                {"access_token": sentinels["access"], "refresh_token": sentinels["refresh"], "token_type": "bearer"},
            )
        )
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = exchange_callback(
                config(), attempt,
                f"http://127.0.0.1:8765/oauth/callback?code={sentinels['code']}&state={attempt.state}",
                transport=transport,
            )

        rendered = stdout.getvalue() + stderr.getvalue() + repr(result)
        for sentinel in sentinels.values():
            self.assertNotIn(sentinel, rendered)
        self.assertNotIn(attempt.state, rendered)
        self.assertNotIn(attempt.code_verifier, rendered)

    def test_OAUTH_no_persistence_or_environment_side_effect(self):
        before_env = dict(os.environ)
        before_cwd = os.getcwd()
        attempt = build_authorization_attempt(config())
        transport = FakeTransport(response=token_response(200, {"access_token": "fake-access", "token_type": "bearer"}))

        exchange_callback(
            config(), attempt,
            f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={attempt.state}",
            transport=transport,
        )

        self.assertEqual(dict(os.environ), before_env)
        self.assertEqual(os.getcwd(), before_cwd)


if __name__ == "__main__":
    unittest.main()
