import io
import json
import os
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs

from x_context.cli import main
from x_context.credential_lifecycle import (
    REFRESH_ENDPOINT,
    REVOKE_ENDPOINT,
    CredentialError,
    CredentialRecord,
    DPAPIFileCredentialStore,
    delete_local_credential,
    persist_oauth_result,
    resolve_user_access_token,
    revoke_persisted_credential,
)
from x_context.oauth import OAuthHttpRequest, OAuthHttpResponse, OAuthTokenResult, acquire_user_token, OAuthConfig
from x_context.x_api import HttpRequest, HttpResponse


READ_SCOPES = ("tweet.read", "users.read", "bookmark.read", "like.read", "offline.access")


@dataclass
class FakeStore:
    record: CredentialRecord | None = None
    replace_error: Exception | None = None
    deletes: int = 0
    replacements: list[CredentialRecord] = field(default_factory=list)

    def load(self):
        return self.record

    def replace(self, record):
        if self.replace_error is not None:
            raise self.replace_error
        self.record = record
        self.replacements.append(record)

    def delete(self):
        self.record = None
        self.deletes += 1


@dataclass
class FakeTransport:
    responses: list[OAuthHttpResponse] = field(default_factory=list)
    error: Exception | None = None
    requests: list[OAuthHttpRequest] = field(default_factory=list)

    def __call__(self, request: OAuthHttpRequest) -> OAuthHttpResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if not self.responses:
            raise AssertionError("no fake response")
        return self.responses.pop(0)


@dataclass
class FakeXTransport:
    responses: list[HttpResponse]
    requests: list[HttpRequest] = field(default_factory=list)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("no fake X response")
        return self.responses.pop(0)


def response(status: int, payload: object) -> OAuthHttpResponse:
    return OAuthHttpResponse(status=status, headers={"content-type": "application/json"}, body=json.dumps(payload).encode())


def x_response(payload: object, status: int = 200) -> HttpResponse:
    return HttpResponse(status=status, headers={}, body=json.dumps(payload).encode())


def record(*, access="fake-access", refresh="fake-refresh", expires_at=10_000, scopes=READ_SCOPES):
    return CredentialRecord(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_at=expires_at,
        scopes=scopes,
    )


class CredentialLifecycleTests(unittest.TestCase):
    def test_CRED_explicit_persistence_round_trip_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.bin"
            protector = lambda value: b"protected:" + value[::-1]
            unprotector = lambda value: value[len(b"protected:") :][::-1]
            store = DPAPIFileCredentialStore(path=path, protect=protector, unprotect=unprotector)
            token = OAuthTokenResult(
                access_token="persist-access-secret",
                refresh_token="persist-refresh-secret",
                token_type="bearer",
                expires_in=7200,
                scopes=READ_SCOPES,
            )

            persist_oauth_result(token, store=store, now=lambda: 1000)
            loaded = store.load()

            self.assertEqual(loaded.access_token, "persist-access-secret")
            self.assertEqual(loaded.refresh_token, "persist-refresh-secret")
            self.assertEqual(loaded.expires_at, 8200)
            durable = path.read_bytes()
            self.assertNotIn(b"persist-access-secret", durable)
            self.assertNotIn(b"persist-refresh-secret", durable)
            self.assertNotIn("persist-access-secret", repr(loaded))
            self.assertNotIn("persist-refresh-secret", repr(loaded))

    def test_CRED_oauth_acquisition_remains_nonpersistent(self):
        store = FakeStore()
        config = OAuthConfig(client_id="fake-client", redirect_uri="http://127.0.0.1:8765/oauth/callback")

        class Listener:
            def __init__(self):
                self.attempt = None
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def wait_for_callback(self, timeout):
                return f"http://127.0.0.1:8765/oauth/callback?code=fake-code&state={self.attempt.state}"

        def listener_factory(attempt):
            listener = Listener()
            listener.attempt = attempt
            return listener

        acquire_user_token(
            config,
            refresh_capable=True,
            browser_launcher=lambda _: True,
            listener_factory=listener_factory,
            transport=FakeTransport([response(200, {
                "access_token": "fake-access",
                "refresh_token": "fake-refresh",
                "token_type": "bearer",
                "expires_in": 7200,
                "scope": " ".join(READ_SCOPES),
            })]),
        )
        self.assertIsNone(store.record)
        self.assertEqual(store.replacements, [])

    def test_CRED_env_override_wins_and_invalid_override_fails_closed(self):
        store = FakeStore(record(access="persisted-access"))
        result = resolve_user_access_token(
            environ={"X_CONTEXT_USER_ACCESS_TOKEN": "env-access"},
            store=store,
            client_id=None,
            now=lambda: 1000,
        )
        self.assertEqual(result.access_token, "env-access")
        self.assertEqual(result.source, "environment")
        self.assertFalse(result.refresh_attempted)

        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={"X_CONTEXT_USER_ACCESS_TOKEN": "bad\nvalue"},
                store=store,
                client_id="fake-client",
                now=lambda: 1000,
            )
        self.assertEqual(raised.exception.category, "configuration_error")

    def test_CRED_no_app_bearer_fallback_or_env_auto_import(self):
        store = FakeStore()
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={"X_CONTEXT_BEARER_TOKEN": "app-only-secret"},
                store=store,
                client_id="fake-client",
                now=lambda: 1000,
            )
        self.assertEqual(raised.exception.category, "credential_missing")
        self.assertEqual(store.replacements, [])

    def test_CRED_expiry_and_refresh_window(self):
        far = FakeStore(record=record(expires_at=1401))
        result = resolve_user_access_token(environ={}, store=far, client_id=None, now=lambda: 1000)
        self.assertEqual(result.access_token, "fake-access")
        self.assertFalse(result.refresh_attempted)

        no_refresh = FakeStore(record=record(refresh=None, expires_at=1200))
        result = resolve_user_access_token(environ={}, store=no_refresh, client_id=None, now=lambda: 1000)
        self.assertEqual(result.access_token, "fake-access")
        self.assertFalse(result.refresh_attempted)

        expired = FakeStore(record=record(refresh=None, expires_at=999))
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(environ={}, store=expired, client_id=None, now=lambda: 1000)
        self.assertEqual(raised.exception.category, "credential_expired")

    def test_CRED_refresh_request_public_client_contract_and_single_attempt(self):
        store = FakeStore(record=record(expires_at=1200))
        transport = FakeTransport([response(200, {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "bearer",
            "expires_in": 7200,
            "scope": " ".join(READ_SCOPES),
        })])
        result = resolve_user_access_token(
            environ={}, store=store, client_id="fake-client", transport=transport, now=lambda: 1000
        )
        self.assertEqual(result.access_token, "new-access")
        self.assertTrue(result.refresh_attempted)
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, REFRESH_ENDPOINT)
        body = parse_qs(request.body.decode("ascii"))
        self.assertEqual(body, {
            "grant_type": ["refresh_token"],
            "refresh_token": ["fake-refresh"],
            "client_id": ["fake-client"],
        })
        self.assertNotIn("Authorization", request.headers)
        self.assertNotIn("client_secret", request.body.decode("ascii"))

    def test_CRED_malformed_or_scope_expanding_refresh_preserves_state(self):
        original = record(expires_at=1200)
        for payload in (
            {"refresh_token": "replacement"},
            {"access_token": "new", "expires_in": -1},
            {"access_token": "new", "scope": "tweet.read users.read bookmark.read like.read offline.access tweet.write"},
        ):
            with self.subTest(payload=payload):
                store = FakeStore(record=original)
                with self.assertRaises(CredentialError):
                    resolve_user_access_token(
                        environ={}, store=store, client_id="fake-client",
                        transport=FakeTransport([response(200, payload)]), now=lambda: 1000,
                    )
                self.assertIs(store.record, original)
                self.assertEqual(store.replacements, [])

    def test_CRED_successful_refresh_commits_before_use(self):
        store = FakeStore(record=record(expires_at=1200), replace_error=OSError("write failure secret-shaped-noise"))
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={}, store=store, client_id="fake-client",
                transport=FakeTransport([response(200, {
                    "access_token": "new-access-not-returned",
                    "refresh_token": "new-refresh",
                    "expires_in": 7200,
                    "scope": " ".join(READ_SCOPES),
                })]), now=lambda: 1000,
            )
        self.assertEqual(raised.exception.category, "credential_storage_error")
        self.assertNotIn("new-access-not-returned", str(raised.exception))

    def test_CRED_refresh_token_replacement_and_omission_rule(self):
        replacing = FakeStore(record=record(expires_at=1200))
        resolve_user_access_token(
            environ={}, store=replacing, client_id="fake-client",
            transport=FakeTransport([response(200, {
                "access_token": "new-access", "refresh_token": "rotated-refresh",
                "expires_in": 7200, "scope": " ".join(READ_SCOPES),
            })]), now=lambda: 1000,
        )
        self.assertEqual(replacing.record.refresh_token, "rotated-refresh")

        original = record(expires_at=1200)
        omitted = FakeStore(record=original)
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={}, store=omitted, client_id="fake-client",
                transport=FakeTransport([response(200, {
                    "access_token": "new-access-not-usable", "expires_in": 7200,
                    "scope": " ".join(READ_SCOPES),
                })]), now=lambda: 1000,
            )
        self.assertEqual(raised.exception.category, "provider_error")
        self.assertTrue(raised.exception.refresh_attempted)
        self.assertIs(omitted.record, original)
        self.assertEqual(omitted.replacements, [])

    def test_CRED_failed_refresh_preserves_state_and_blocks_collection(self):
        original = record(expires_at=1200)
        store = FakeStore(record=original)
        transport = FakeTransport([response(503, {"error": "secret-provider-noise"})])
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={}, store=store, client_id="fake-client", transport=transport, now=lambda: 1000
            )
        self.assertEqual(raised.exception.category, "provider_error")
        self.assertIs(store.record, original)
        self.assertEqual(len(transport.requests), 1)

    def test_CRED_collection_subject_binding_still_runs(self):
        store = FakeStore(record=record(access="persisted-user-token", expires_at=5000))
        transport = FakeXTransport([
            x_response({"data": {"id": "42", "username": "example"}}),
            x_response({"data": [{"id": "123", "text": "fake-private-post"}], "meta": {"result_count": 1}}),
        ])
        out, err = io.StringIO(), io.StringIO()
        code = main(
            ["bookmarks"],
            environ={},
            credential_store=store,
            clock=lambda: 1000,
            transport=transport,
            stdout=out,
            stderr=err,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(transport.requests[0].url, "https://api.x.com/2/users/me")
        self.assertIn("/2/users/42/bookmarks?", transport.requests[1].url)
        self.assertTrue(all(r.headers["Authorization"] == "Bearer persisted-user-token" for r in transport.requests))
        diagnostic = json.loads(err.getvalue())
        self.assertEqual(diagnostic["credential_source"], "persisted")
        self.assertFalse(diagnostic["credential_refresh_attempted"])
        self.assertEqual(diagnostic["provider_requests_attempted"], 2)

    def test_CRED_local_delete_is_idempotent_and_local_only(self):
        store = FakeStore(record=record())
        env = {"X_CONTEXT_USER_ACCESS_TOKEN": "env-secret"}
        delete_local_credential(store)
        delete_local_credential(store)
        self.assertIsNone(store.record)
        self.assertEqual(store.deletes, 2)
        self.assertEqual(env["X_CONTEXT_USER_ACCESS_TOKEN"], "env-secret")

    def test_CRED_provider_revoke_contract_and_delete_order(self):
        store = FakeStore(record=record())
        transport = FakeTransport([response(200, {"revoked": True})])
        revoke_persisted_credential(store=store, client_id="fake-client", transport=transport)
        self.assertEqual(len(transport.requests), 1)
        request = transport.requests[0]
        self.assertEqual(request.url, REVOKE_ENDPOINT)
        body = parse_qs(request.body.decode("ascii"))
        self.assertEqual(body["token"], ["fake-refresh"])
        self.assertEqual(body["client_id"], ["fake-client"])
        self.assertIsNone(store.record)
        self.assertEqual(store.deletes, 1)

        retained = FakeStore(record=record())
        with self.assertRaises(CredentialError):
            revoke_persisted_credential(
                store=retained,
                client_id="fake-client",
                transport=FakeTransport([response(503, {"error": "no"})]),
            )
        self.assertIsNotNone(retained.record)
        self.assertEqual(retained.deletes, 0)

    def test_CRED_corrupt_or_unsupported_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.bin"
            cases = (
                b"not-json",
                json.dumps({
                    "schema_version": 99,
                    "provider": "x",
                    "access_token": "fake-access",
                    "refresh_token": None,
                    "token_type": "bearer",
                    "expires_at": None,
                    "scopes": None,
                }).encode(),
            )
            for plaintext in cases:
                with self.subTest(plaintext=plaintext[:20]):
                    path.write_bytes(b"protected")
                    store = DPAPIFileCredentialStore(
                        path=path,
                        protect=lambda value: value,
                        unprotect=lambda value, plain=plaintext: plain,
                    )
                    with self.assertRaises(CredentialError) as raised:
                        store.load()
                    self.assertEqual(raised.exception.category, "credential_storage_error")
                    self.assertTrue(path.exists())

    def test_CRED_secret_sentinels_absent_from_repr_errors_and_diagnostics(self):
        secret_access = "ACCESS-SENTINEL-SECRET"
        secret_refresh = "REFRESH-SENTINEL-SECRET"
        value = CredentialRecord(secret_access, secret_refresh, "bearer", 1200, READ_SCOPES)
        self.assertNotIn(secret_access, repr(value))
        self.assertNotIn(secret_refresh, repr(value))
        store = FakeStore(record=value)
        with self.assertRaises(CredentialError) as raised:
            resolve_user_access_token(
                environ={}, store=store, client_id="fake-client",
                transport=FakeTransport(error=RuntimeError(secret_refresh)), now=lambda: 1000,
            )
        rendered = str(raised.exception) + repr(raised.exception)
        self.assertNotIn(secret_access, rendered)
        self.assertNotIn(secret_refresh, rendered)

    def test_CRED_scope_authority_remains_read_only(self):
        with self.assertRaises(CredentialError):
            CredentialRecord(
                access_token="fake-access",
                refresh_token="fake-refresh",
                token_type="bearer",
                expires_at=1200,
                scopes=("tweet.read", "tweet.write"),
            )

    def test_CRED_storage_replace_failure_keeps_prior_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "credential.bin"
            protector = lambda value: b"P" + value
            unprotector = lambda value: value[1:]
            store = DPAPIFileCredentialStore(path=path, protect=protector, unprotect=unprotector)
            store.replace(record(access="old-access", expires_at=5000))
            before = path.read_bytes()

            def fail_protect(value):
                raise OSError("protect failed")

            failing = DPAPIFileCredentialStore(path=path, protect=fail_protect, unprotect=unprotector)
            with self.assertRaises(CredentialError):
                failing.replace(record(access="new-access", expires_at=6000))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.load().access_token, "old-access")

    def test_CRED_concurrency_claim_is_single_writer(self):
        self.assertEqual(DPAPIFileCredentialStore.concurrency_contract, "single-process-single-writer")


if __name__ == "__main__":
    unittest.main()