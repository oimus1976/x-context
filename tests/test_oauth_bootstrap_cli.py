import io
import json
import unittest
from dataclasses import dataclass, field
from unittest.mock import patch

from x_context import x_api
from x_context.cli import main
from x_context.credential_lifecycle import CredentialError, CredentialRecord
from x_context.oauth import OAuthError, OAuthTokenResult


P0_REFRESH_SCOPES = (
    "tweet.read",
    "users.read",
    "bookmark.read",
    "like.read",
    "offline.access",
)

VALID_ENV = {
    "X_CONTEXT_OAUTH_CLIENT_ID": "fake-client-id",
    "X_CONTEXT_OAUTH_REDIRECT_URI": "http://127.0.0.1:8765/callback",
}


@dataclass
class FakeStore:
    record: CredentialRecord | None = None
    replacements: list[CredentialRecord] = field(default_factory=list)

    def load(self):
        return self.record

    def replace(self, record):
        self.record = record
        self.replacements.append(record)

    def delete(self):
        self.record = None


class FailingStore(FakeStore):
    def replace(self, record):
        raise CredentialError("credential_storage_error")


@dataclass
class RecordingAcquirer:
    result: OAuthTokenResult | None = None
    error: Exception | None = None
    calls: list[tuple[object, dict[str, object]]] = field(default_factory=list)

    def __call__(self, config, **kwargs):
        self.calls.append((config, dict(kwargs)))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class FailIfCalledAcquirer:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("OAuth acquisition must not be called")


class ScriptedTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return self.replies.pop(0)


def response(payload, status=200):
    return x_api.HttpResponse(status, {}, json.dumps(payload).encode("utf-8"))


def successful_result(
    *,
    access_token="fake-managed-access",
    refresh_token="fake-managed-refresh",
    expires_in=7200,
):
    return OAuthTokenResult(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
        scopes=P0_REFRESH_SCOPES,
    )


def run_login(*, environ=None, store=None, acquirer=None, clock=None):
    out, err = io.StringIO(), io.StringIO()
    selected_store = FakeStore() if store is None else store
    selected_acquirer = RecordingAcquirer(result=successful_result()) if acquirer is None else acquirer
    code = main(
        ["auth", "login"],
        environ=dict(VALID_ENV if environ is None else environ),
        credential_store=selected_store,
        oauth_acquirer=selected_acquirer,
        clock=(lambda: 1000) if clock is None else clock,
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue(), selected_store, selected_acquirer


class OAuthBootstrapCliTests(unittest.TestCase):
    def test_AUTH_login_success_composes_refresh_capable_acquisition_and_persistence(self):
        acquirer = RecordingAcquirer(result=successful_result())
        code, stdout, stderr, store, _ = run_login(acquirer=acquirer)

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(acquirer.calls), 1)
        config, kwargs = acquirer.calls[0]
        self.assertEqual(config.client_id, VALID_ENV["X_CONTEXT_OAUTH_CLIENT_ID"])
        self.assertEqual(config.redirect_uri, VALID_ENV["X_CONTEXT_OAUTH_REDIRECT_URI"])
        self.assertIs(kwargs["refresh_capable"], True)
        self.assertEqual(len(store.replacements), 1)
        self.assertEqual(store.record.access_token, "fake-managed-access")
        self.assertEqual(store.record.refresh_token, "fake-managed-refresh")
        self.assertEqual(store.record.expires_at, 8200)
        self.assertEqual(store.record.scopes, P0_REFRESH_SCOPES)
        self.assertEqual(
            json.loads(stdout),
            {
                "operation": "auth_login",
                "status": "success",
                "credential_persisted": True,
                "refresh_capable": True,
            },
        )

    def test_AUTH_login_missing_or_invalid_configuration_has_zero_oauth_and_store_effects(self):
        cases = (
            {},
            {"X_CONTEXT_OAUTH_CLIENT_ID": "fake-client-id"},
            {"X_CONTEXT_OAUTH_REDIRECT_URI": VALID_ENV["X_CONTEXT_OAUTH_REDIRECT_URI"]},
            {
                "X_CONTEXT_OAUTH_CLIENT_ID": " fake-client-id ",
                "X_CONTEXT_OAUTH_REDIRECT_URI": VALID_ENV["X_CONTEXT_OAUTH_REDIRECT_URI"],
            },
            {
                "X_CONTEXT_OAUTH_CLIENT_ID": "fake-client-id",
                "X_CONTEXT_OAUTH_REDIRECT_URI": "http://localhost:8765/callback",
            },
        )
        for environ in cases:
            with self.subTest(environ=environ):
                old = CredentialRecord(access_token="old-access", expires_at=9000)
                store = FakeStore(old)
                acquirer = FailIfCalledAcquirer()
                code, stdout, stderr, _, _ = run_login(
                    environ=environ,
                    store=store,
                    acquirer=acquirer,
                )
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(json.loads(stderr)["error_category"], "configuration_error")
                self.assertEqual(acquirer.calls, [])
                self.assertIs(store.record, old)
                self.assertEqual(store.replacements, [])

    def test_AUTH_login_requires_refresh_token_before_persistence(self):
        old = CredentialRecord(access_token="old-access", expires_at=9000)
        store = FakeStore(old)
        acquirer = RecordingAcquirer(result=successful_result(refresh_token=None))

        code, stdout, stderr, _, _ = run_login(store=store, acquirer=acquirer)

        self.assertEqual(code, 3)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "provider_error")
        self.assertIs(store.record, old)
        self.assertEqual(store.replacements, [])

    def test_AUTH_login_requires_expiry_before_persistence(self):
        old = CredentialRecord(access_token="old-access", expires_at=9000)
        store = FakeStore(old)
        acquirer = RecordingAcquirer(result=successful_result(expires_in=None))

        code, stdout, stderr, _, _ = run_login(store=store, acquirer=acquirer)

        self.assertEqual(code, 3)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "provider_error")
        self.assertIs(store.record, old)
        self.assertEqual(store.replacements, [])

    def test_AUTH_login_acquisition_failure_preserves_existing_credential(self):
        old = CredentialRecord(access_token="old-access", expires_at=9000)
        store = FakeStore(old)
        acquirer = RecordingAcquirer(
            error=OAuthError(
                "oauth_callback_timeout",
                browser_launch_attempted=True,
            )
        )

        code, stdout, stderr, _, _ = run_login(store=store, acquirer=acquirer)

        self.assertEqual(code, 3)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "oauth_callback_timeout")
        self.assertIs(store.record, old)
        self.assertEqual(store.replacements, [])

    def test_AUTH_login_persistence_failure_is_local_and_does_not_leak_secrets(self):
        old = CredentialRecord(access_token="old-access", expires_at=9000)
        store = FailingStore(old)
        access = "SENTINEL-ACCESS-DO-NOT-LEAK"
        refresh = "SENTINEL-REFRESH-DO-NOT-LEAK"
        acquirer = RecordingAcquirer(result=successful_result(access_token=access, refresh_token=refresh))

        code, stdout, stderr, _, _ = run_login(store=store, acquirer=acquirer)

        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error_category"], "credential_storage_error")
        self.assertIs(store.record, old)
        combined = stdout + stderr
        self.assertNotIn(access, combined)
        self.assertNotIn(refresh, combined)

    def test_AUTH_login_never_imports_environment_access_token(self):
        unmanaged = "SENTINEL-UNMANAGED-TOKEN"
        environ = dict(VALID_ENV)
        environ["X_CONTEXT_USER_ACCESS_TOKEN"] = unmanaged
        store = FakeStore()
        acquirer = RecordingAcquirer(result=successful_result())

        code, stdout, stderr, _, _ = run_login(
            environ=environ,
            store=store,
            acquirer=acquirer,
        )

        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(store.record.access_token, "fake-managed-access")
        self.assertNotEqual(store.record.access_token, unmanaged)
        self.assertNotIn(unmanaged, stdout + stderr)

    def test_AUTH_login_secret_values_are_absent_from_success_output(self):
        access = "SENTINEL-ACCESS-DO-NOT-LEAK"
        refresh = "SENTINEL-REFRESH-DO-NOT-LEAK"
        acquirer = RecordingAcquirer(result=successful_result(access_token=access, refresh_token=refresh))

        code, stdout, stderr, _, _ = run_login(acquirer=acquirer)

        self.assertEqual(code, 0)
        combined = stdout + stderr
        self.assertNotIn(access, combined)
        self.assertNotIn(refresh, combined)
        self.assertNotIn("Authorization", combined)

    def test_AUTH_login_unsupported_default_store_fails_before_oauth(self):
        out, err = io.StringIO(), io.StringIO()
        acquirer = FailIfCalledAcquirer()
        with patch("x_context.cli.default_credential_store", return_value=None):
            code = main(
                ["auth", "login"],
                environ=dict(VALID_ENV),
                credential_store=None,
                oauth_acquirer=acquirer,
                stdout=out,
                stderr=err,
            )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(err.getvalue())["error_category"], "configuration_error")
        self.assertEqual(acquirer.calls, [])

    def test_AUTH_login_persisted_result_is_consumed_by_existing_bookmarks_path(self):
        store = FakeStore()
        acquirer = RecordingAcquirer(result=successful_result())
        code, _, _, _, _ = run_login(store=store, acquirer=acquirer)
        self.assertEqual(code, 0)

        transport = ScriptedTransport(
            [
                response({"data": {"id": "42", "username": "example"}}),
                response({"data": [{"id": "123", "text": "private"}], "meta": {"result_count": 1}}),
            ]
        )
        out, err = io.StringIO(), io.StringIO()
        code = main(
            ["bookmarks"],
            environ={"X_CONTEXT_OAUTH_CLIENT_ID": "fake-client-id"},
            credential_store=store,
            transport=transport,
            clock=lambda: 1001,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 0)
        self.assertEqual(len(transport.requests), 2)
        self.assertTrue(
            all(
                request.headers["Authorization"] == "Bearer fake-managed-access"
                for request in transport.requests
            )
        )
        self.assertEqual(json.loads(out.getvalue())["operation"], "bookmarks")


if __name__ == "__main__":
    unittest.main()
