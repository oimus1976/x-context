import io
import json
import unittest
from dataclasses import dataclass, field

from x_context.cli import main
from x_context.credential_lifecycle import CredentialRecord
from x_context.oauth import OAuthHttpResponse


READ_SCOPES = ("tweet.read", "users.read", "bookmark.read", "like.read", "offline.access")


@dataclass
class FakeStore:
    record: CredentialRecord
    replacements: list[CredentialRecord] = field(default_factory=list)

    def load(self):
        return self.record

    def replace(self, record):
        self.record = record
        self.replacements.append(record)

    def delete(self):
        self.record = None


@dataclass
class FailIfCalledTransport:
    requests: list[object] = field(default_factory=list)

    def __call__(self, request):
        self.requests.append(request)
        raise AssertionError("network transport must not be called for local invalid input")


def due_record():
    return CredentialRecord(
        access_token="fake-access",
        refresh_token="fake-refresh",
        token_type="bearer",
        expires_at=1200,
        scopes=READ_SCOPES,
    )


class CredentialLifecycleCliOrderingTests(unittest.TestCase):
    def _assert_local_rejection_without_network(self, argv):
        store = FakeStore(due_record())
        oauth_transport = FailIfCalledTransport()
        x_transport = FailIfCalledTransport()
        out, err = io.StringIO(), io.StringIO()

        code = main(
            argv,
            environ={"X_CONTEXT_OAUTH_CLIENT_ID": "fake-client"},
            credential_store=store,
            oauth_transport=oauth_transport,
            transport=x_transport,
            clock=lambda: 1000,
            stdout=out,
            stderr=err,
        )

        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(oauth_transport.requests, [])
        self.assertEqual(x_transport.requests, [])
        self.assertEqual(store.replacements, [])
        diagnostic = json.loads(err.getvalue())
        self.assertEqual(diagnostic["error_category"], "invalid_input")
        self.assertEqual(diagnostic["provider_requests_attempted"], 0)
        self.assertEqual(diagnostic["credential_provider_requests_attempted"], 0)
        self.assertFalse(diagnostic["credential_refresh_attempted"])

    def test_CRED_failed_refresh_counted_once_for_bookmarks_and_likes(self):
        for operation in ('bookmarks', 'likes'):
            for transport_error in (False, True):
                original = due_record()
                store = FakeStore(original)
                oauth_requests = []
                x_transport = FailIfCalledTransport()
                out, err = io.StringIO(), io.StringIO()

                def oauth_transport(request):
                    oauth_requests.append(request)
                    if transport_error:
                        raise RuntimeError('synthetic-refresh-prose')
                    return OAuthHttpResponse(503, {}, b'{"detail":"synthetic-refresh-prose"}')

                code = main(
                    [operation], environ={'X_CONTEXT_OAUTH_CLIENT_ID': 'fake-client'},
                    credential_store=store, oauth_transport=oauth_transport,
                    transport=x_transport, clock=lambda: 1000, stdout=out, stderr=err,
                )
                diagnostic = json.loads(err.getvalue())
                self.assertEqual(code, 3)
                self.assertEqual(len(out.getvalue()), 0, 'unexpected success output')
                self.assertEqual(diagnostic['error_category'], 'provider_error')
                self.assertEqual(diagnostic['provider_requests_attempted'], 1)
                self.assertEqual(diagnostic['credential_provider_requests_attempted'], 1)
                self.assertTrue(diagnostic['credential_refresh_attempted'])
                self.assertEqual(diagnostic['operation'], operation)
                self.assertEqual(len(oauth_requests), 1)
                self.assertEqual(x_transport.requests, [])
                self.assertIs(store.record, original)
                self.assertEqual(store.replacements, [])
                self.assertTrue(all(value not in err.getvalue() for value in
                                    (original.access_token, original.refresh_token, 'synthetic-refresh-prose')),
                                'refresh diagnostics redaction violated')

    def test_CRED_invalid_max_results_precedes_due_refresh(self):
        self._assert_local_rejection_without_network(["bookmarks", "--max-results", "0"])

    def test_CRED_invalid_page_token_precedes_due_refresh(self):
        self._assert_local_rejection_without_network(["likes", "--page-token", "bad\npage"])


if __name__ == "__main__":
    unittest.main()
