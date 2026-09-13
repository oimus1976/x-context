import io
import json
import traceback
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from x_context import x_api
from x_context.cli import main


def response(payload, status=200, headers=None):
    return x_api.HttpResponse(status, headers or {}, json.dumps(payload).encode())


class ScriptedTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FR003BookmarksTests(unittest.TestCase):
    def transport(self, payload=None, status=200):
        return ScriptedTransport([
            response({'data': {'id': '42', 'username': 'example'}}),
            response(payload if payload is not None else {'data': [{'id': '123', 'text': 'fake-private-post'}], 'meta': {'result_count': 1}}, status),
        ])

    def cli(self, transport, args=(), environ=None):
        out, err = io.StringIO(), io.StringIO()
        code = main(['bookmarks', *args], environ={'X_CONTEXT_USER_ACCESS_TOKEN': 'fake-user-token'} if environ is None else environ,
                    transport=transport, stdout=out, stderr=err)
        return code, out.getvalue(), json.loads(err.getvalue())

    def test_FR_003_official_endpoint_subject_binding_and_canonical(self):
        transport = self.transport()
        with patch.object(x_api, 'resolve_authenticated_subject', wraps=x_api.resolve_authenticated_subject) as resolve, patch.object(x_api, 'bind_collection_subject', wraps=x_api.bind_collection_subject) as bind:
            code, out, diagnostic = self.cli(transport)
        self.assertEqual(code, 0)
        resolve.assert_called_once()
        bind.assert_called_once_with(x_api.AuthenticatedSubject('42', 'example'), '42')
        self.assertEqual([r.method for r in transport.requests], ['GET', 'GET'])
        self.assertEqual(transport.requests[0].url, 'https://api.x.com/2/users/me')
        parsed = urlsplit(transport.requests[1].url)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path), ('https', 'api.x.com', '/2/users/42/bookmarks'))
        self.assertEqual(parse_qs(parsed.query), {'max_results': ['25']})
        for request in transport.requests:
            self.assertEqual(request.headers['Authorization'], 'Bearer fake-user-token')
        value = json.loads(out)
        self.assertEqual(value['operation'], 'bookmarks')
        self.assertEqual(value['schema_version'], '1')
        self.assertEqual(value['source'], 'x')
        self.assertEqual(value['subject'], {'id': '42', 'username': 'example'})
        self.assertEqual(value['items'], [{'id': '123', 'text': 'fake-private-post'}])
        self.assertEqual(diagnostic['provider_requests_attempted'], 2)
        self.assertEqual(diagnostic['returned_item_count'], 1)

    def test_FR_003_user_credential_only(self):
        for token in (None, '', 'fake\runsafe', 'fake\nunsafe'):
            transport = self.transport()
            env = {'X_CONTEXT_BEARER_TOKEN': 'fake-app-token'}
            if token is not None:
                env['X_CONTEXT_USER_ACCESS_TOKEN'] = token
            code, out, diag = self.cli(transport, environ=env)
            self.assertEqual((code, out, diag['error_category']), (2, '', 'configuration_error'))
            self.assertEqual(transport.requests, [])
        transport = self.transport()
        code, _, _ = self.cli(transport, environ={'X_CONTEXT_USER_ACCESS_TOKEN': 'fake-user-token', 'X_CONTEXT_BEARER_TOKEN': 'fake-app-token'})
        self.assertEqual(code, 0)
        self.assertTrue(all(r.headers['Authorization'] == 'Bearer fake-user-token' for r in transport.requests))

    def test_FR_003_default_and_bounds(self):
        for args, expected in (([], 25), (['--max-results', '1'], 1), (['--max-results', '100'], 100)):
            transport = self.transport()
            code, _, diag = self.cli(transport, args)
            self.assertEqual(code, 0)
            self.assertEqual(diag['requested_page_size'], expected)
            self.assertEqual(parse_qs(urlsplit(transport.requests[1].url).query)['max_results'], [str(expected)])

    def test_FR_003_invalid_input_before_transport(self):
        for value in ('0', '-1', '101', '1.5', 'fake-sensitive-invalid', '1e2'):
            transport = self.transport()
            code, out, diag = self.cli(transport, ['--max-results', value, '--page-token', 'fake-page-secret'])
            self.assertEqual((code, out, diag['error_category']), (2, '', 'invalid_input'))
            self.assertEqual(transport.requests, [])
            self.assertNotIn('fake-page-secret', str(diag))

        for token in ('', 'fake\nunsafe', 3):
            transport = self.transport()
            with self.assertRaises(x_api.XApiError) as caught:
                x_api.lookup_bookmarks(user_access_token='fake-user', page_token=token, transport=transport)
            self.assertEqual(caught.exception.category, 'invalid_input')
            self.assertEqual(transport.requests, [])
        for value in (True, 0, 101, 2.5, '25', None):
            transport = self.transport()
            with self.assertRaises(x_api.XApiError) as caught:
                x_api.lookup_bookmarks(user_access_token='fake-user', max_results=value, transport=transport)
            self.assertEqual(caught.exception.category, 'invalid_input')
            self.assertEqual(transport.requests, [])

    def test_FR_003_binding_failure_stops_collection(self):
        transport = self.transport()
        original = x_api.bind_collection_subject
        with patch.object(x_api, 'bind_collection_subject', side_effect=lambda subject, target: original(subject, '43')):
            code, _, diag = self.cli(transport)
        self.assertEqual((code, diag['error_category'], diag['provider_requests_attempted']), (3, 'subject_mismatch', 1))
        self.assertEqual(len(transport.requests), 1)

    def test_FR_003_one_page_continuation_and_completeness(self):
        for count in (0, 1, 25):
            for continued in (False, True):
                meta = {'result_count': count}
                if continued:
                    meta['next_token'] = 'fake-next-secret'
                transport = self.transport({'data': [{'id': str(i + 1), 'text': 'fake'} for i in range(count)], 'meta': meta})
                code, out, diag = self.cli(transport, ['--page-token', 'fake-input&token=opaque'])
                self.assertEqual(code, 0)
                self.assertEqual(len(transport.requests), 2)
                self.assertEqual(parse_qs(urlsplit(transport.requests[1].url).query)['pagination_token'], ['fake-input&token=opaque'])
                self.assertEqual(json.loads(out)['page'], {'next_token': 'fake-next-secret' if continued else None, 'complete': not continued})
                self.assertEqual(diag['continuation_returned'], continued)
                self.assertNotIn('fake-input', str(diag))
                self.assertNotIn('fake-next', str(diag))
        code, out, _ = self.cli(self.transport({'meta': {'result_count': 0}}))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)['items'], [])

    def test_FR_003_malformed_success_fails_closed(self):
        payloads = [{}, {'data': None}, {'data': {}}, {'data': [None]}, {'data': [{'id': 'x', 'text': 'fake'}]},
                    {'data': [{'id': '1', 'text': 2}]}, {'data': [], 'errors': [{'detail': 'fake-private'}]},
                    {'data': [], 'meta': None}, {'data': [], 'meta': {'next_token': ''}},
                    {'data': [], 'meta': {'next_token': 3}}, {'data': [], 'meta': {'result_count': 1}},
                    {'data': [], 'meta': {'result_count': False}}]
        for payload in payloads:
            code, out, diag = self.cli(self.transport(payload))
            self.assertEqual((code, out, diag['error_category'], diag['provider_requests_attempted']), (3, '', 'provider_error', 2))

    def test_FR_003_conservative_errors_and_accounting(self):
        for status, body, category in ((401, {}, 'authentication_failed'), (403, {}, 'authorization_failed'),
                                      (404, {}, 'provider_error'), (429, {}, 'provider_error'),
                                      (429, {'type': 'https://api.x.com/2/problems/rate-limit-exceeded'}, 'rate_limited'),
                                      (402, {'type': 'https://api.x.com/2/problems/usage-capped'}, 'usage_blocked'), (500, {}, 'provider_error')):
            for stage in (0, 1):
                transport = self.transport(body, status)
                if stage == 0:
                    transport.replies[0] = response(body, status)
                code, out, diag = self.cli(transport)
                self.assertEqual((code, out, diag['error_category']), (3, '', category))
                self.assertEqual(diag['provider_requests_attempted'], stage + 1)
                self.assertEqual(len(transport.requests), stage + 1)

    def test_FR_003_private_values_excluded_from_diagnostics_and_repr(self):
        transport = self.transport({'data': [{'id': '1', 'text': 'fake-private-post'}], 'meta': {'next_token': 'fake-next-secret'}})
        transport.replies[1] = response({'data': [{'id': '1', 'text': 'fake-private-post'}], 'meta': {'next_token': 'fake-next-secret'}}, headers={'arbitrary': 'fake-header-secret'})
        result = x_api.lookup_bookmarks(user_access_token='fake-user-token', page_token='fake-input-secret', transport=transport)
        exposed = repr(result) + repr(result.envelope) + repr(result.envelope.items) + repr(result.envelope.page) + repr(transport.requests) + repr(transport.replies)
        for secret in ('fake-private-post', 'fake-next-secret', 'fake-input-secret', 'fake-user-token', 'fake-header-secret'):
            self.assertNotIn(secret, exposed)
        self.assertNotIn("id='1'", repr(result.envelope.items))
        transport = self.transport()
        code, _, diag = self.cli(transport)
        self.assertEqual(code, 0)
        self.assertNotIn('fake-private-post', str(diag))
        self.assertNotIn('fake-user-token', str(diag))

    def test_FR_003_transport_failure_redacted(self):
        for exception_type in (RuntimeError, x_api.XApiError):
            for stage in (0, 1):
                transport = self.transport()
                transport.replies[stage] = exception_type('fake-transport-secret')
                try:
                    x_api.lookup_bookmarks(user_access_token='fake-user-token', transport=transport)
                except x_api.XApiError as exc:
                    self.assertEqual(exc.category, 'provider_error')
                    self.assertEqual(exc.requests_attempted, stage + 1)
                    self.assertNotIn('fake-transport-secret', ''.join(traceback.format_exception(exc)))
                else:
                    self.fail('expected provider_error')
                transport = self.transport()
                transport.replies[stage] = exception_type('fake-transport-secret')
                code, out, diag = self.cli(transport)
                self.assertEqual((code, out, diag['error_category']), (3, '', 'provider_error'))
                self.assertNotIn('fake-transport-secret', str(diag))

    def test_FR_003_no_default_persistence(self):
        with patch('builtins.open', side_effect=AssertionError('unexpected persistence')), patch('io.open', side_effect=AssertionError('unexpected persistence')):
            self.assertEqual(self.cli(self.transport())[0], 0)

    def test_FR_003_no_target_or_all_cli(self):
        for args in (['42'], ['--user-id', '42'], ['--all'], ['--token', 'fake-secret'], ['--max-r', '1']):
            transport = self.transport()
            code, out, diag = self.cli(transport, args)
            self.assertEqual((code, out), (2, ''))
            self.assertEqual(transport.requests, [])
            self.assertEqual(diag['operation'], 'bookmarks')

    def test_FR_003_rate_metadata_for_both_attempts(self):
        transport = self.transport()
        transport.replies[0] = response({'data': {'id': '42'}}, headers={'x-rate-limit-remaining': '7', 'arbitrary': 'fake-secret'})
        transport.replies[1] = response({'data': []}, headers={'x-rate-limit-remaining': '3', 'x-rate-limit-reset': 'unsafe'})
        code, _, diag = self.cli(transport)
        self.assertEqual(code, 0)
        self.assertEqual(diag['rate_limits']['subject']['remaining'], 7)
        self.assertEqual(diag['rate_limits']['bookmarks']['remaining'], 3)
        self.assertIsNone(diag['rate_limits']['bookmarks']['reset'])
        self.assertNotIn('fake-secret', str(diag))
        transport = ScriptedTransport([response({}, headers={'x-rate-limit-remaining': '7'})])
        code, _, diag = self.cli(transport)
        self.assertEqual(code, 3)
        self.assertEqual(diag['rate_limits']['subject']['remaining'], 7)

    def test_FR_003_redirects_not_followed(self):
        # The production bookmark transport must reject redirect responses.
        from urllib.request import Request
        handler = x_api._NoRedirect()
        self.assertIsNone(handler.redirect_request(Request('https://api.x.com/2/users/me'), None, 302, 'redirect', {}, 'https://example.org/'))


if __name__ == '__main__':
    unittest.main()
