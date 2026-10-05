"""SPEC-0006 contract tests: synthetic boundaries only; Issue #45 RED slice.

Missing posts APIs are referenced inside test bodies, so discovery stays valid.
Do not retain raw unittest tracebacks as evidence: assertions may hold synthetic
private data. The handoff runner reports only test IDs and failure categories.
"""
import io
import json
import traceback
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler
from urllib.parse import parse_qs, urlsplit

from x_context import x_api
from x_context.canonical import CanonicalEnvelope, CanonicalPost, Page
from x_context.cli import main
from x_context.credential_lifecycle import CredentialRecord, REFRESH_ENDPOINT
from x_context.oauth import OAuthHttpResponse


ACCESS = 'synthetic-access-sentinel'
REFRESH = 'synthetic-refresh-sentinel'
NEW_ACCESS = 'synthetic-replacement-access'
NEW_REFRESH = 'synthetic-replacement-refresh'
TEXT = 'synthetic-private-post-sentinel'
INPUT_PAGE = ' opaque+%2F&cursor=sentinel '
OUTPUT_PAGE = 'synthetic-next-page-sentinel'
PROSE = 'synthetic-provider-transport-prose'
SCOPES = ('tweet.read', 'users.read', 'bookmark.read', 'like.read', 'offline.access')


def response(payload, status=200, headers=None):
    return x_api.HttpResponse(status, headers or {}, json.dumps(payload).encode())


class ScriptedTransport:
    def __init__(self, replies=()):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if not self.replies:
            raise AssertionError('unexpected extra provider attempt')
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeStore:
    def __init__(self, record=None):
        self.record = record
        self.loads = 0
        self.replacements = []
        self.deletes = 0

    def load(self):
        self.loads += 1
        return self.record

    def replace(self, record):
        self.record = record
        self.replacements.append(record)

    def delete(self):
        self.deletes += 1
        self.record = None


def managed_record(due=False):
    return CredentialRecord(access_token=ACCESS, refresh_token=REFRESH,
                            token_type='bearer', expires_at=1200 if due else 10000,
                            scopes=SCOPES)


def refresh_response():
    return OAuthHttpResponse(200, {}, json.dumps({
        'access_token': NEW_ACCESS, 'refresh_token': NEW_REFRESH,
        'token_type': 'bearer', 'expires_in': 3600,
        'scope': ' '.join(SCOPES),
    }).encode())


class OwnPostsTests(unittest.TestCase):
    def setUp(self):
        # Every provider boundary is synthetic, including the default-transport
        # test. Guard against accidentally opening a real socket.
        for target in ('socket.create_connection', 'socket.socket.connect'):
            guard = patch(target, side_effect=AssertionError('real network forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def transport(self, payload=None, status=200):
        return ScriptedTransport([
            response({'data': {'id': '42', 'username': 'example'}}),
            response({'data': [{'id': '123', 'text': TEXT}], 'meta': {'result_count': 1}}
                     if payload is None else payload, status),
        ])

    def cli(self, transport, args=(), environ=None, store=None, oauth=None):
        out, err = io.StringIO(), io.StringIO()
        code = main(['posts', *args],
                    environ={'X_CONTEXT_USER_ACCESS_TOKEN': ACCESS} if environ is None else environ,
                    transport=transport, credential_store=FakeStore() if store is None else store,
                    oauth_transport=ScriptedTransport() if oauth is None else oauth,
                    oauth_acquirer=lambda *a, **k: self.fail('unexpected acquisition'),
                    clock=lambda: 1000, stdout=out, stderr=err)
        return code, out.getvalue(), json.loads(err.getvalue())

    def assert_redacted(self, value, include_payload=True):
        forbidden = [ACCESS, REFRESH, NEW_ACCESS, NEW_REFRESH, 'Authorization', PROSE]
        if include_payload:
            forbidden += [TEXT, INPUT_PAGE, OUTPUT_PAGE]
        self.assertTrue(all(secret not in value for secret in forbidden), 'redaction contract violated')

    def assert_local(self, transport, args, store, oauth):
        code, out, diag = self.cli(transport, args, {'X_CONTEXT_OAUTH_CLIENT_ID': 'synthetic-client'}, store, oauth)
        self.assertEqual(code, 2)
        self.assertEqual(len(out), 0, 'unexpected success output')
        self.assertEqual(diag['error_category'], 'invalid_input')
        self.assertEqual((store.loads, store.replacements, store.deletes), (0, [], 0))
        self.assertEqual((transport.requests, oauth.requests), ([], []))
        self.assertEqual(diag['operation'], 'posts')
        self.assertEqual(diag['provider_requests_attempted'], 0)
        self.assertEqual(diag['credential_provider_requests_attempted'], 0)
        self.assertFalse(diag['credential_refresh_attempted'])
        self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_001_missing_credential_no_fallback_or_acquisition(self):
        for env in ({}, {'X_CONTEXT_BEARER_TOKEN': 'synthetic-app-only'}):
            store, oauth, transport = FakeStore(), ScriptedTransport(), ScriptedTransport()
            code, out, diag = self.cli(transport, environ=env, store=store, oauth=oauth)
            self.assertEqual(code, 2)
            self.assertEqual(len(out), 0, 'unexpected success output')
            self.assertEqual(diag['error_category'], 'configuration_error')
            self.assertEqual(diag['operation'], 'posts')
            self.assertEqual(diag['provider_requests_attempted'], 0)
            self.assertEqual(diag['credential_provider_requests_attempted'], 0)
            self.assertFalse(diag['credential_refresh_attempted'])
            self.assertEqual((transport.requests, oauth.requests, store.replacements, store.deletes), ([], [], [], 0))

    def test_OWNPOST_001_invalid_override_fails_closed(self):
        for token in ('', 'bad\rvalue', 'bad\nvalue'):
            store, oauth, transport = FakeStore(managed_record(True)), ScriptedTransport(), ScriptedTransport()
            code, out, diag = self.cli(transport, environ={'X_CONTEXT_USER_ACCESS_TOKEN': token}, store=store, oauth=oauth)
            self.assertEqual(code, 2)
            self.assertEqual(len(out), 0, 'unexpected success output')
            self.assertEqual(diag['error_category'], 'configuration_error')
            self.assertEqual(diag['provider_requests_attempted'], 0)
            self.assertEqual((store.loads, store.replacements, transport.requests, oauth.requests), (0, [], [], []))

    def test_OWNPOST_001_override_wins_without_import(self):
        store, oauth, transport = FakeStore(managed_record(True)), ScriptedTransport(), self.transport()
        code, out, diag = self.cli(transport, store=store, oauth=oauth)
        self.assertEqual(code, 0)
        self.assertEqual((store.loads, store.replacements, store.deletes, oauth.requests), (0, [], 0, []))
        self.assertEqual(diag['credential_source'], 'environment')
        self.assertTrue(all(r.headers['Authorization'] == 'Bearer ' + ACCESS for r in transport.requests))
        self.assert_redacted(out, include_payload=False)

    def test_OWNPOST_002_resolved_subject_binding_and_endpoint(self):
        transport = self.transport()
        transport.replies[0] = response({'data': {'id': '987', 'username': 'example'}})
        with patch.object(x_api, 'resolve_authenticated_subject', wraps=x_api.resolve_authenticated_subject) as resolve, \
             patch.object(x_api, 'bind_collection_subject', wraps=x_api.bind_collection_subject) as bind:
            code, out, diag = self.cli(transport, environ={'X_CONTEXT_USER_ACCESS_TOKEN': ACCESS, 'X_CONTEXT_USER_ID': '999'})
        self.assertEqual(code, 0)
        resolve.assert_called_once()
        bind.assert_called_once_with(x_api.AuthenticatedSubject('987', 'example'), '987')
        self.assertEqual([r.method for r in transport.requests], ['GET', 'GET'])
        self.assertEqual(transport.requests[0].url, 'https://api.x.com/2/users/me')
        target = urlsplit(transport.requests[1].url)
        self.assertEqual((target.scheme, target.netloc, target.path), ('https', 'api.x.com', '/2/users/987/tweets'))
        self.assertEqual(json.loads(out)['subject'], {'id': '987', 'username': 'example'})
        self.assertEqual(diag['provider_requests_attempted'], 2)

    def test_OWNPOST_002_malformed_subject_stops_before_tweets(self):
        for payload in ({}, {'data': None}, {'data': []}, {'data': {'id': 'bad'}},
                        {'data': {'id': 42}}, {'data': {'id': '42', 'username': ''}},
                        {'data': {'id': '42'}, 'errors': [{'detail': PROSE}]}):
            transport = ScriptedTransport([response(payload)])
            code, out, diag = self.cli(transport)
            self.assertEqual(code, 3)
            self.assertEqual(len(out), 0, 'unexpected success output')
            self.assertEqual(diag['error_category'], 'provider_error')
            self.assertEqual((diag['provider_requests_attempted'], len(transport.requests)), (1, 1))
            self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_002_binding_failure_stops_before_tweets(self):
        transport = self.transport()
        original = x_api.bind_collection_subject
        with patch.object(x_api, 'bind_collection_subject', side_effect=lambda subject, target: original(subject, '43')):
            code, out, diag = self.cli(transport)
        self.assertEqual(code, 3)
        self.assertEqual(len(out), 0, 'unexpected success output')
        self.assertEqual(diag['error_category'], 'subject_mismatch')
        self.assertEqual((diag['provider_requests_attempted'], len(transport.requests)), (1, 1))

    def test_OWNPOST_003_007_prohibited_cli_scope(self):
        for args in (['999'], ['--user-id', '999'], ['--all'], ['--start-time', PROSE],
                     ['--end-time', PROSE], ['--since-id', '1'], ['--until-id', '2'],
                     ['--scope', PROSE], ['--token', ACCESS], ['--max-r', '5']):
            self.assert_local(ScriptedTransport(), args, FakeStore(managed_record(True)), ScriptedTransport())

    def test_OWNPOST_004_canonical_success_shape(self):
        code, out, diag = self.cli(self.transport())
        self.assertEqual(code, 0)
        value = json.loads(out)
        self.assertEqual(set(value), {'schema_version', 'source', 'operation', 'retrieved_at', 'subject', 'items', 'page'})
        self.assertEqual((value['schema_version'], value['source'], value['operation']), ('1', 'x', 'posts'))
        self.assertEqual(value['subject'], {'id': '42', 'username': 'example'})
        self.assertTrue(value['items'] == [{'id': '123', 'text': TEXT}], 'canonical item projection differs')
        self.assertTrue(value['page'] == {'next_token': None, 'complete': True}, 'canonical page projection differs')
        self.assertTrue(value['retrieved_at'].endswith('Z'))
        self.assertEqual(datetime.fromisoformat(value['retrieved_at'].replace('Z', '+00:00')).utcoffset().total_seconds(), 0)
        self.assertEqual((diag['returned_item_count'], diag['provider_requests_attempted']), (1, 2))
        self.assert_redacted(out, include_payload=False)
        self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_004_canonical_posts_requires_valid_subject_and_closed_operation(self):
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Establish supported posts first: rejection must not pass merely because
        # all posts envelopes are currently unsupported.
        envelope = CanonicalEnvelope('posts', stamp, x_api.AuthenticatedSubject('42'), (), Page())
        self.assertEqual(envelope.to_dict()['subject'], {'id': '42'})
        for subject in (None, {}, {'id': '42'}, '42'):
            with self.assertRaises(ValueError):
                CanonicalEnvelope('posts', stamp, subject, (), Page())
        for operation in ('unknown', 'timeline', ''):
            with self.assertRaises(ValueError):
                CanonicalEnvelope(operation, stamp, x_api.AuthenticatedSubject('42'), (), Page())
        for ident in ('', 'bad', 42):
            with self.assertRaises(ValueError):
                x_api.AuthenticatedSubject(ident)

    def test_OWNPOST_004_malformed_provider_payload_fails_closed(self):
        payloads = [{}, {'data': None}, {'data': {}}, {'data': [None]},
                    {'data': [{'id': 'bad', 'text': TEXT}]}, {'data': [{'id': '1', 'text': 2}]},
                    {'data': [], 'errors': [{'detail': PROSE}]}, {'data': [], 'meta': None},
                    {'data': [], 'meta': {'next_token': ''}}, {'data': [], 'meta': {'next_token': 3}},
                    {'data': [], 'meta': {'next_token': 'bad\nvalue'}},
                    {'data': [], 'meta': {'result_count': 1}}, {'data': [], 'meta': {'result_count': False}},
                    {'data': [], 'meta': {'result_count': -1}}, {'data': [], 'meta': {'result_count': '0'}},
                    {'data': [{'id': str(i + 1), 'text': TEXT} for i in range(6)], 'meta': {'result_count': 6}}]
        for payload in payloads:
            transport = self.transport(payload)
            code, out, diag = self.cli(transport, ['--max-results', '5'])
            self.assertEqual(code, 3)
            self.assertEqual(len(out), 0, 'unexpected success output')
            self.assertEqual(diag['error_category'], 'provider_error')
            self.assertEqual((diag['provider_requests_attempted'], len(transport.requests)), (2, 2))
            self.assert_redacted(json.dumps(diag))
        for reply in (x_api.HttpResponse(200, {}, b'not-json'), x_api.HttpResponse(200, {}, b'[]'), object()):
            transport = self.transport()
            transport.replies[1] = reply
            code, out, diag = self.cli(transport)
            self.assertEqual(code, 3)
            self.assertEqual(len(out), 0, 'unexpected success output')
            self.assertEqual(diag['error_category'], 'provider_error')
            self.assertEqual(diag['provider_requests_attempted'], 2)

    def test_OWNPOST_004_005_safe_errors_and_attempt_counts(self):
        cases = ((401, {}, 'authentication_failed'), (403, {}, 'authorization_failed'),
                 (404, {}, 'provider_error'), (429, {}, 'provider_error'),
                 (429, {'type': 'https://api.x.com/2/problems/rate-limit-exceeded'}, 'rate_limited'),
                 (402, {'type': 'https://api.x.com/2/problems/usage-capped'}, 'usage_blocked'),
                 (500, {'detail': PROSE}, 'provider_error'), (302, {}, 'provider_error'))
        for status, body, category in cases:
            for stage in (0, 1):
                transport = self.transport()
                transport.replies[stage] = response(body, status)
                code, out, diag = self.cli(transport)
                self.assertEqual(code, 3)
                self.assertEqual(len(out), 0, 'unexpected success output')
                self.assertEqual(diag['error_category'], category)
                self.assertEqual((diag['provider_requests_attempted'], len(transport.requests)), (stage + 1, stage + 1))
                self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_005_default_and_posts_bounds(self):
        for args, expected in (([], 25), (['--max-results', '5'], 5), (['--max-results', '100'], 100)):
            transport = self.transport()
            code, _, diag = self.cli(transport, args)
            self.assertEqual(code, 0)
            self.assertEqual(diag['requested_page_size'], expected)
            self.assertTrue(parse_qs(urlsplit(transport.requests[1].url).query) == {'max_results': [str(expected)], 'exclude': ['retweets']}, 'posts query differs')

    def test_OWNPOST_005_invalid_cli_input_precedes_store_load_and_due_refresh(self):
        for size in ('4', '101', '0', '-1', 'True', '1.5', PROSE):
            self.assert_local(ScriptedTransport(), ['--max-results', size], FakeStore(managed_record(True)), ScriptedTransport())
        for token in ('', 'bad\x00value', 'bad\nvalue', 'bad\x1fvalue', 'bad\x7fvalue'):
            self.assert_local(ScriptedTransport(), ['--page-token', token], FakeStore(managed_record(True)), ScriptedTransport())

    def test_OWNPOST_005_invalid_library_size_and_token_before_transport(self):
        for size in (True, False, 4, 101, -1, 25.0, '25', None):
            transport = ScriptedTransport()
            with self.assertRaises(x_api.XApiError) as caught:
                x_api.lookup_posts(user_access_token=ACCESS, max_results=size, transport=transport)
            self.assertEqual((caught.exception.category, caught.exception.requests_attempted), ('invalid_input', 0))
            self.assertEqual(transport.requests, [])
        for token in ('', 3, True, [], 'bad\x00value', 'bad\x1fvalue', 'bad\x7fvalue'):
            transport = ScriptedTransport()
            with self.assertRaises(x_api.XApiError) as caught:
                x_api.lookup_posts(user_access_token=ACCESS, page_token=token, transport=transport)
            self.assertEqual((caught.exception.category, caught.exception.requests_attempted), ('invalid_input', 0))
            self.assertEqual(transport.requests, [])

    def test_OWNPOST_005_opaque_continuation_one_page_and_count_independent_completeness(self):
        for count in (0, 1, 25):
            for continued in (False, True):
                meta = {'result_count': count}
                if continued:
                    meta['next_token'] = OUTPUT_PAGE
                payload = {'data': [{'id': str(i + 1), 'text': TEXT} for i in range(count)], 'meta': meta}
                transport = self.transport(payload)
                code, out, diag = self.cli(transport, ['--page-token', INPUT_PAGE])
                self.assertEqual(code, 0)
                self.assertEqual(len(transport.requests), 2)
                self.assertTrue(parse_qs(urlsplit(transport.requests[1].url).query)['pagination_token'] == [INPUT_PAGE], 'opaque token changed')
                self.assertTrue(json.loads(out)['page'] == {'next_token': OUTPUT_PAGE if continued else None, 'complete': not continued}, 'continuation mapping differs')
                self.assertEqual(diag['continuation_returned'], continued)
                self.assert_redacted(json.dumps(diag))
        code, out, _ = self.cli(self.transport({'meta': {'result_count': 0}}))
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['items'] == [], 'unexpected post items')

    def test_OWNPOST_005_refresh_success_and_failure_accounting(self):
        for stage in ('success', 'refresh', 'subject', 'tweets'):
            store, oauth, transport = FakeStore(managed_record(True)), ScriptedTransport([refresh_response()]), self.transport()
            if stage == 'refresh':
                oauth.replies[0] = OAuthHttpResponse(500, {}, json.dumps({'detail': PROSE}).encode())
            elif stage == 'subject':
                transport.replies[0] = response({}, 401)
            elif stage == 'tweets':
                transport.replies[1] = response({}, 403)
            code, out, diag = self.cli(transport, environ={'X_CONTEXT_OAUTH_CLIENT_ID': 'synthetic-client'}, store=store, oauth=oauth)
            expected_code = 0 if stage == 'success' else 3
            self.assertEqual(code, expected_code)
            self.assertEqual(diag['provider_requests_attempted'], {'success': 3, 'refresh': 1, 'subject': 2, 'tweets': 3}[stage])
            self.assertEqual(diag['credential_provider_requests_attempted'], 1)
            self.assertTrue(diag['credential_refresh_attempted'])
            self.assertEqual(len(oauth.requests), 1)
            self.assertEqual(oauth.requests[0].url, REFRESH_ENDPOINT)
            self.assertEqual(len(transport.requests), {'success': 2, 'refresh': 0, 'subject': 1, 'tweets': 2}[stage])
            self.assertEqual(len(store.replacements), 0 if stage == 'refresh' else 1)
            self.assertEqual(store.deletes, 0)
            if stage == 'refresh':
                self.assertTrue(store.record.access_token == ACCESS, 'failed refresh changed credential')
            else:
                self.assertTrue(store.record.access_token == NEW_ACCESS and store.record.refresh_token == NEW_REFRESH, 'replacement not committed')
                self.assertTrue(all(r.headers['Authorization'] == 'Bearer ' + NEW_ACCESS for r in transport.requests))
            if stage != 'success':
                self.assertEqual(len(out), 0, 'unexpected success output')
                self.assertEqual(diag['error_category'], {'refresh': 'provider_error', 'subject': 'authentication_failed', 'tweets': 'authorization_failed'}[stage])
            self.assert_redacted(out, include_payload=False)
            self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_005_per_endpoint_rates_on_success_and_failure(self):
        for stage in ('success', 'subject', 'tweets'):
            transport = self.transport()
            transport.replies[0] = response({'data': {'id': '42'}} if stage != 'subject' else {}, headers={'x-rate-limit-remaining': '7', 'arbitrary': PROSE})
            transport.replies[1] = response({'data': []} if stage != 'tweets' else {}, 200 if stage != 'tweets' else 403,
                                            {'x-rate-limit-remaining': '3', 'x-rate-limit-reset': PROSE})
            code, _, diag = self.cli(transport)
            self.assertEqual(code, 0 if stage == 'success' else 3)
            self.assertEqual(diag['rate_limits']['subject']['remaining'], 7)
            self.assertEqual(diag['rate_limits']['posts']['remaining'], None if stage == 'subject' else 3)
            self.assertIsNone(diag['rate_limits']['posts']['reset'])
            self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_005_bookmarks_likes_retain_1_to_100(self):
        for operation in ('bookmarks', 'likes'):
            for size in (1, 100):
                transport = self.transport()
                result = getattr(x_api, 'lookup_' + operation)(user_access_token=ACCESS, max_results=size, transport=transport)
                self.assertEqual(result.requested_page_size, size)
                self.assertTrue(parse_qs(urlsplit(transport.requests[1].url).query) == {'max_results': [str(size)]}, 'collection query differs')

    def test_OWNPOST_006_retweets_only_exclusion_reply_quote_projection(self):
        items = [{'id': '1', 'text': TEXT},
                 {'id': '2', 'text': 'synthetic-own-reply', 'referenced_tweets': [{'type': 'replied_to', 'id': '9'}]},
                 {'id': '3', 'text': 'synthetic-own-quote', 'referenced_tweets': [{'type': 'quoted', 'id': '8'}]}]
        transport = self.transport({'data': items, 'meta': {'result_count': 3}})
        code, out, _ = self.cli(transport)
        self.assertEqual(code, 0)
        self.assertTrue(parse_qs(urlsplit(transport.requests[1].url).query) == {'max_results': ['25'], 'exclude': ['retweets']}, 'posts exclusion query differs')
        self.assertTrue(json.loads(out)['items'] == [{'id': item['id'], 'text': item['text']} for item in items], 'reply/quote eligibility or projection differs')
        self.assertEqual(len(transport.requests), 2)

    def test_OWNPOST_006_default_transport_disables_redirects_and_retries(self):
        for redirect in (False, True):
            opener = MagicMock()
            subject = MagicMock()
            subject.__enter__.return_value = subject
            subject.getcode.return_value = 200
            subject.headers = {}
            subject.read.return_value = response({'data': {'id': '42'}}).body
            tweets = MagicMock()
            tweets.__enter__.return_value = tweets
            tweets.getcode.return_value = 200
            tweets.headers = {}
            tweets.read.return_value = response({'data': []}).body
            if redirect:
                tweets = HTTPError('https://api.x.com/2/users/42/tweets', 302, 'redirect',
                                   {'Location': 'https://example.invalid/'}, io.BytesIO(PROSE.encode()))
            opener.open.side_effect = [subject, tweets]
            with patch.object(x_api, 'build_opener', return_value=opener) as build:
                if redirect:
                    with self.assertRaises(x_api.XApiError) as caught:
                        x_api.lookup_posts(user_access_token=ACCESS)
                    self.assertEqual((caught.exception.category, caught.exception.requests_attempted), ('provider_error', 2))
                    self.assert_redacted(repr(caught.exception))
                else:
                    result = x_api.lookup_posts(user_access_token=ACCESS)
                    self.assertEqual(result.requests_attempted, 2)
                self.assertEqual(opener.open.call_count, 2)
                self.assertTrue(build.called)
                for call in build.call_args_list:
                    handlers = [arg for arg in call.args if isinstance(arg, HTTPRedirectHandler)]
                    self.assertTrue(handlers, 'redirect policy handler missing')
                    for handler in handlers:
                        self.assertIsNone(handler.redirect_request(Request('https://api.x.com/2/users/me'), None,
                                                                   302, 'redirect', {}, 'https://example.invalid/'))
                requests = [call.args[0] for call in opener.open.call_args_list]
                self.assertEqual(requests[0].full_url, 'https://api.x.com/2/users/me')
                self.assertEqual(urlsplit(requests[1].full_url).path, '/2/users/42/tweets')

    def test_OWNPOST_007_result_request_response_repr_and_diagnostics_redacted(self):
        transport = self.transport({'data': [{'id': '123', 'text': TEXT}], 'meta': {'next_token': OUTPUT_PAGE}})
        result = x_api.lookup_posts(user_access_token=ACCESS, page_token=INPUT_PAGE, transport=transport)
        self.assertEqual(result.envelope.operation, 'posts')
        self.assert_redacted(repr(result) + repr(result.envelope) + repr(result.envelope.items) + repr(result.envelope.page) + repr(transport.requests))
        transport = self.transport({'data': [{'id': '123', 'text': TEXT}], 'meta': {'next_token': OUTPUT_PAGE}})
        code, out, diag = self.cli(transport, ['--page-token', INPUT_PAGE])
        self.assertEqual(code, 0)
        self.assert_redacted(out, include_payload=False)
        self.assert_redacted(json.dumps(diag))
        self.assert_redacted(repr(response({'detail': PROSE}, headers={'Authorization': ACCESS})))

    def test_OWNPOST_007_transport_errors_controlled_exception_and_cli_redacted(self):
        for exception_type in (RuntimeError, x_api.XApiError):
            for stage in (0, 1):
                transport = self.transport()
                transport.replies[stage] = exception_type(PROSE)
                with self.assertRaises(x_api.XApiError) as caught:
                    x_api.lookup_posts(user_access_token=ACCESS, page_token=INPUT_PAGE, transport=transport)
                self.assertEqual((caught.exception.category, caught.exception.requests_attempted), ('provider_error', stage + 1))
                self.assertEqual(len(transport.requests), stage + 1)
                self.assert_redacted(repr(caught.exception) + ''.join(traceback.format_exception(caught.exception)))
                transport = self.transport()
                transport.replies[stage] = exception_type(PROSE)
                code, out, diag = self.cli(transport)
                self.assertEqual(code, 3)
                self.assertEqual(len(out), 0, 'unexpected success output')
                self.assertEqual(diag['error_category'], 'provider_error')
                self.assertEqual(diag['provider_requests_attempted'], stage + 1)
                self.assert_redacted(json.dumps(diag))

    def test_OWNPOST_007_managed_read_has_no_payload_persistence(self):
        store, transport = FakeStore(managed_record()), self.transport()
        with patch('builtins.open', side_effect=AssertionError('unexpected payload persistence')), \
             patch('io.open', side_effect=AssertionError('unexpected payload persistence')):
            code, out, diag = self.cli(transport, environ={}, store=store)
        self.assertEqual(code, 0)
        self.assertEqual((store.loads, store.replacements, store.deletes), (1, [], 0))
        self.assertEqual(len(transport.requests), 2)
        self.assertFalse(diag['credential_refresh_attempted'])
        self.assert_redacted(json.dumps(diag))
        self.assert_redacted(out, include_payload=False)


if __name__ == '__main__':
    unittest.main()
