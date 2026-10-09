"""SPEC-0007 contracts. All identities, credentials and payloads are synthetic."""
import copy
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from x_context import cli, x_api
from x_context.canonical import CanonicalEnvelope, CanonicalPost, Page
from datetime import datetime


T1 = '2026-10-08T00:00:00Z'
T2 = '2026-10-09T01:02:03Z'


class BookmarkStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-bmstore-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'x-context' / 'data' / 'bookmarks-v1.json'
        self.env = {'LOCALAPPDATA': str(self.root), 'X_CONTEXT_USER_ACCESS_TOKEN': 'synthetic-access-secret'}

    def envelope(self, items=(('111', 'synthetic 日本語'),), at=T1, subject='90001', username='synthetic_user'):
        return CanonicalEnvelope('bookmarks', datetime.fromisoformat(at.replace('Z', '+00:00')),
                                 x_api.AuthenticatedSubject(subject, username),
                                 tuple(CanonicalPost(*item) for item in items), Page('synthetic-output-cursor', False))

    def run_cli(self, envelope=None, args=None, env=None, lookup_effect=None):
        out, err = io.StringIO(), io.StringIO()
        result = x_api.BookmarksLookupResult(envelope=envelope or self.envelope(), rate_limit=x_api.RateLimitMetadata(100, 98, 123), requests_attempted=2,
                                           subject_rate_limit=x_api.RateLimitMetadata(100, 99, 123), requested_page_size=25)
        with patch.object(cli, 'lookup_bookmarks', return_value=result, side_effect=lookup_effect) as lookup:
            code = cli.main(['bookmarks', *(args if args is not None else ['save'])],
                            environ=self.env if env is None else env, stdout=out, stderr=err,
                            credential_store=Mock(load=Mock(side_effect=AssertionError('real credential read'))),
                            transport=Mock(side_effect=AssertionError('real provider call')))
        return code, out.getvalue(), [json.loads(line) for line in err.getvalue().splitlines()], lookup

    def read(self):
        return json.loads(self.path.read_bytes())

    def seed(self):
        value = {'store_schema_version': '1', 'source': 'x', 'collection': 'bookmarks',
                 'subject': {'id': '90001', 'username': 'synthetic_user'}, 'created_at': T1, 'updated_at': T1,
                 'items': [{'id': '111', 'text': 'synthetic old', 'first_seen_at': T1, 'last_seen_at': T1}]}
        self.write(value)
        return value

    def write(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def assert_failure(self, result, category, requests=0, post=False):
        code, out, diagnostics, _ = result
        self.assertEqual(code, 2 if category in ('invalid_input', 'configuration_error') else 3)
        self.assertEqual(out, '')
        self.assertEqual(diagnostics[-1]['error_category'], category)
        self.assertEqual(diagnostics[-1]['provider_requests_attempted'], requests)
        if category == 'storage_error':
            self.assertEqual(diagnostics[-1]['persistence_may_have_occurred'], post)
        for sentinel in ('synthetic-access-secret', 'synthetic-output-cursor', 'synthetic-input-cursor',
                         'synthetic 日本語', 'synthetic old', '90001', 'synthetic_user', 'RAW-OS-SECRET'):
            self.assertNotIn(sentinel, json.dumps(diagnostics, ensure_ascii=False))

    def test_AC001_plain_bookmarks_never_persists(self):
        self.seed()
        before = self.path.read_bytes()
        with patch('builtins.open', side_effect=AssertionError('unexpected write')), patch('io.open', side_effect=AssertionError('unexpected write')):
            self.assertEqual(self.run_cli(args=[])[0], 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_AC002_save_real_acquisition_composition_one_page(self):
        requests = []
        def transport(request):
            requests.append(request)
            value = {'data': {'id': '90001', 'username': 'synthetic_user'}} if len(requests) == 1 else {
                'data': [{'id': '111', 'text': 'synthetic 日本語', 'ignored': 'synthetic-raw-secret'}],
                'meta': {'result_count': 1, 'next_token': 'synthetic-output-cursor'}}
            return x_api.HttpResponse(200, {}, json.dumps(value).encode())
        out, err = io.StringIO(), io.StringIO()
        code = cli.main(['bookmarks', 'save', '--max-results', '1', '--page-token', 'synthetic-input-cursor'],
                        environ=self.env, transport=transport, stdout=out, stderr=err)
        self.assertEqual(code, 0)
        self.assertEqual([r.method for r in requests], ['GET', 'GET'])
        self.assertEqual([urlsplit(r.url).path for r in requests], ['/2/users/me', '/2/users/90001/bookmarks'])
        self.assertEqual(parse_qs(urlsplit(requests[1].url).query), {'max_results': ['1'], 'pagination_token': ['synthetic-input-cursor']})
        self.assertEqual(json.loads(err.getvalue())['provider_requests_attempted'], 2)
        self.assertEqual(json.loads(out.getvalue())['page']['next_token'], 'synthetic-output-cursor')
        for secret in ('synthetic-access-secret', 'synthetic-input-cursor', 'synthetic-output-cursor', 'synthetic-raw-secret', 'ignored'):
            self.assertNotIn(secret, self.path.read_text(encoding='utf-8'))
            self.assertNotIn(secret, err.getvalue())

    def test_AC002_invalid_local_input_precedes_credentials_and_store(self):
        for args in (['save', '--max-results', '0'], ['save', '--max-results', '101'],
                     ['save', '--page-token', ''], ['save', '--page-token', 'synthetic\nsecret']):
            with self.subTest(args=args), patch.object(cli, 'resolve_user_access_token') as resolve:
                result = self.run_cli(args=args, env={})
                self.assert_failure(result, 'invalid_input')
                resolve.assert_not_called()
                result[3].assert_not_called()

    def test_AC003_missing_localappdata_precedes_credentials(self):
        for env in ({}, {'LOCALAPPDATA': ''}):
            with self.subTest(env=env), patch.object(cli, 'resolve_user_access_token') as resolve:
                result = self.run_cli(env=env)
                self.assert_failure(result, 'configuration_error')
                resolve.assert_not_called()
                result[3].assert_not_called()
        self.assertFalse(self.path.exists())

    def test_AC003_reject_repository_local_root(self):
        result = self.run_cli(env={**self.env, 'LOCALAPPDATA': str(Path(__file__).resolve().parents[1])})
        self.assert_failure(result, 'configuration_error')
        result[3].assert_not_called()

    def test_AC003_AC004_fixed_utf8_schema_and_no_extra_files(self):
        code, out, diag, _ = self.run_cli()
        self.assertEqual(code, 0)
        value = self.read()
        self.assertEqual(set(value), {'store_schema_version', 'source', 'collection', 'subject', 'created_at', 'updated_at', 'items'})
        self.assertEqual((value['store_schema_version'], value['source'], value['collection']), ('1', 'x', 'bookmarks'))
        self.assertEqual(value['subject'], {'id': '90001', 'username': 'synthetic_user'})
        self.assertEqual((value['created_at'], value['updated_at']), (T1, T1))
        self.assertEqual(value['items'], [{'id': '111', 'text': 'synthetic 日本語', 'first_seen_at': T1, 'last_seen_at': T1}])
        self.assertIn('日本語'.encode(), self.path.read_bytes())
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [self.path])
        self.assertEqual(json.loads(out), self.envelope().to_dict())

    def test_AC004_corrupt_schema_preflight_unchanged_zero_credentials(self):
        value = self.seed()
        variants = [b'not json', b'\xff', b'[]', b'null', b'{"source":"x","source":"x"}']
        for key, bad in [('store_schema_version', '2'), ('source', 'other'), ('collection', 'likes'),
                         ('created_at', '2026-02-30T00:00:00Z'), ('updated_at', '2026-10-08T00:00:00'),
                         ('updated_at', '2026-10-08T00:00:00+01:00'), ('items', {}), ('subject', {'id': '９０００１'}),
                         ('subject', {'id': '90001', 'username': None}), ('extra_secret', 'synthetic-access-secret')]:
            bad_value = copy.deepcopy(value)
            bad_value[key] = bad
            variants.append(json.dumps(bad_value).encode())
        for bad in variants:
            with self.subTest(bad=bad), patch.object(cli, 'resolve_user_access_token') as resolve:
                self.path.write_bytes(bad)
                result = self.run_cli()
                self.assert_failure(result, 'storage_error')
                resolve.assert_not_called()
                result[3].assert_not_called()
                self.assertEqual(self.path.read_bytes(), bad)

    def test_AC004_duplicate_invalid_items_preflight(self):
        value = self.seed()
        for items in ([value['items'][0]] * 2, [{'id': 'x', 'text': 'synthetic', 'first_seen_at': T1, 'last_seen_at': T1}],
                      [{'id': '111', 'text': 1, 'first_seen_at': T1, 'last_seen_at': T1}],
                      [{'id': '111', 'text': 'synthetic', 'first_seen_at': 'invalid', 'last_seen_at': T1}],
                      [{'id': '111', 'text': 'synthetic', 'first_seen_at': T1, 'last_seen_at': T1, 'page_token': 'secret'}]):
            with self.subTest(items=items):
                self.write({**value, 'items': items})
                before = self.path.read_bytes()
                result = self.run_cli()
                self.assert_failure(result, 'storage_error')
                result[3].assert_not_called()
                self.assertEqual(self.path.read_bytes(), before)

    def test_AC005_subject_mismatch_preserves_bytes(self):
        self.seed()
        before = self.path.read_bytes()
        self.assert_failure(self.run_cli(self.envelope(subject='90002')), 'subject_mismatch', 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_AC005_same_id_username_change_and_optional_omission(self):
        self.seed()
        for name in ('synthetic_new', None):
            self.assertEqual(self.run_cli(self.envelope(username=name))[0], 0)
            self.assertEqual(self.read()['subject'], {'id': '90001', **({'username': name} if name else {})})

    def test_AC006_merge_observation_times_order_and_latest_text(self):
        self.seed()
        incoming = self.envelope((('222', 'synthetic second'), ('111', 'synthetic changed'), ('333', 'synthetic third')), T2)
        self.assertEqual(self.run_cli(incoming)[0], 0)
        value = self.read()
        self.assertEqual([i['id'] for i in value['items']], ['111', '222', '333'])
        self.assertEqual((value['created_at'], value['updated_at']), (T1, T2))
        self.assertEqual(value['items'][0], {'id': '111', 'text': 'synthetic changed', 'first_seen_at': T1, 'last_seen_at': T2})
        self.assertTrue(all(i['first_seen_at'] == i['last_seen_at'] == T2 for i in value['items'][1:]))
        self.assertEqual(self.run_cli(incoming)[0], 0)
        self.assertEqual(self.read(), value)

    def test_AC006_repeated_ids_in_incoming_page_never_duplicate(self):
        self.assertEqual(self.run_cli(self.envelope((('111', 'synthetic a'), ('111', 'synthetic b'))))[0], 0)
        self.assertEqual(len(self.read()['items']), 1)
        self.assertEqual(self.read()['items'][0]['text'], 'synthetic b')

    def test_AC007_empty_partial_page_keeps_all_items_updates_store_time(self):
        value = self.seed()
        self.assertEqual(self.run_cli(self.envelope((), T2))[0], 0)
        saved = self.read()
        self.assertEqual(saved['items'], value['items'])
        self.assertEqual((saved['created_at'], saved['updated_at']), (T1, T2))

    def test_AC008_changed_appeared_disappeared_store_blocks_replace(self):
        for state in ('changed', 'appeared', 'disappeared'):
            with self.subTest(state=state):
                self.seed()
                if state == 'appeared':
                    self.path.unlink()
                expected = b'synthetic-external-change' if state != 'disappeared' else None
                def mutate(*args, **kwargs):
                    if expected is None:
                        self.path.unlink()
                    else:
                        self.path.write_bytes(expected)
                    return x_api.BookmarksLookupResult(envelope=self.envelope(), rate_limit=x_api.RateLimitMetadata(), requests_attempted=2, subject_rate_limit=x_api.RateLimitMetadata(), requested_page_size=25)
                result = self.run_cli(lookup_effect=mutate)
                self.assert_failure(result, 'storage_error', 2)
                self.assertEqual(self.path.read_bytes() if self.path.exists() else None, expected)
                self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def store_module(self):
        return importlib.import_module('x_context.bookmark_store')

    def test_AC008_serialization_failure_preserves_prior_bytes(self):
        self.seed()
        before = self.path.read_bytes()
        store = self.store_module()
        with patch.object(store, '_serialize', side_effect=ValueError('RAW-OS-SECRET')):
            self.assert_failure(self.run_cli(), 'storage_error', 2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_AC008_temp_creation_write_flush_replace_failures(self):
        store = self.store_module()
        for boundary in ('mkstemp', '_write_temp', 'replace'):
            with self.subTest(boundary=boundary):
                self.seed()
                before = self.path.read_bytes()
                target = store.tempfile if boundary == 'mkstemp' else store.os if boundary == 'replace' else store
                with patch.object(target, boundary, side_effect=OSError('RAW-OS-SECRET')):
                    self.assert_failure(self.run_cli(), 'storage_error', 2)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_AC004_unpaired_unicode_surrogate_rejected_before_provider(self):
        value = self.seed()
        value['items'][0]['text'] = '\ud800'
        self.write(value)
        before = self.path.read_bytes()
        result = self.run_cli()
        self.assert_failure(result, 'storage_error')
        result[3].assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_AC008_partial_write_flush_and_close_failure(self):
        store = self.store_module()
        original_fdopen = store.os.fdopen
        for boundary in ('write', 'flush', 'close'):
            with self.subTest(boundary=boundary):
                self.seed()
                before = self.path.read_bytes()
                class FailingStream:
                    def __init__(self, stream):
                        self.stream = stream
                    def __enter__(self):
                        return self
                    def write(self, raw):
                        if boundary == 'write':
                            self.stream.write(raw[:3])
                            raise OSError('RAW-OS-SECRET')
                        return self.stream.write(raw)
                    def flush(self):
                        if boundary == 'flush':
                            raise OSError('RAW-OS-SECRET')
                        self.stream.flush()
                    def fileno(self):
                        return self.stream.fileno()
                    def __exit__(self, *args):
                        self.stream.close()
                        if boundary == 'close':
                            raise OSError('RAW-OS-SECRET')
                with patch.object(store.os, 'fdopen', side_effect=lambda *a, **k: FailingStream(original_fdopen(*a, **k))):
                    self.assert_failure(self.run_cli(), 'storage_error', 2)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_AC008_temporary_image_corruption_blocks_replace(self):
        store = self.store_module()
        original = store._write_temp
        self.seed()
        before = self.path.read_bytes()
        def corrupt(fd, raw):
            original(fd, raw)
            next(self.path.parent.glob('*.tmp')).write_bytes(b'synthetic-corrupt-temp')
        with patch.object(store, '_write_temp', side_effect=corrupt), patch.object(store.os, 'replace') as replace:
            self.assert_failure(self.run_cli(), 'storage_error', 2)
            replace.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_AC004_unreadable_store_stops_credentials(self):
        store = self.store_module()
        with patch.object(store, '_read_snapshot', side_effect=PermissionError('RAW-OS-SECRET')), patch.object(cli, 'resolve_user_access_token') as resolve:
            result = self.run_cli()
            self.assert_failure(result, 'storage_error')
            resolve.assert_not_called()
            result[3].assert_not_called()

    def test_AC008_post_replace_mismatch_is_post_effect_no_rollback(self):
        self.seed()
        store = self.store_module()
        original = store.os.replace
        def replace_then_change(src, dst):
            self.assertEqual(Path(src).parent, self.path.parent)
            original(src, dst)
            self.path.write_bytes(b'synthetic-readback-mismatch')
        with patch.object(store.os, 'replace', side_effect=replace_then_change):
            self.assert_failure(self.run_cli(), 'storage_error', 2, post=True)
        self.assertEqual(self.path.read_bytes(), b'synthetic-readback-mismatch')

    def test_AC008_post_replace_read_failure_is_post_effect(self):
        self.seed()
        store = self.store_module()
        original_read = store._read_snapshot
        calls = 0
        def read(path):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('RAW-OS-SECRET')
            return original_read(path)
        with patch.object(store, '_read_snapshot', side_effect=read):
            self.assert_failure(self.run_cli(), 'storage_error', 2, post=True)
        self.assertEqual(self.read()['items'][0]['text'], 'synthetic 日本語')

    def test_AC009_stdout_waits_for_verified_commit_safe_diagnostics(self):
        store = self.store_module()
        original = store._read_snapshot
        out, err = io.StringIO(), io.StringIO()
        calls = 0
        def read(path):
            nonlocal calls
            calls += 1
            self.assertEqual(out.getvalue(), '')
            return original(path)
        result = x_api.BookmarksLookupResult(envelope=self.envelope(), rate_limit=x_api.RateLimitMetadata(), requests_attempted=2, subject_rate_limit=x_api.RateLimitMetadata(), requested_page_size=25)
        with patch.object(store, '_read_snapshot', side_effect=read), patch.object(cli, 'lookup_bookmarks', return_value=result):
            self.assertEqual(cli.main(['bookmarks', 'save'], environ=self.env, stdout=out, stderr=err), 0)
        self.assertEqual(calls, 3)
        diag = json.loads(err.getvalue())
        self.assertTrue(diag['persistence_succeeded'])
        self.assertEqual((diag['new_item_count'], diag['updated_item_count'], diag['stored_item_count']), (1, 0, 1))
        for private in ('111', '90001', 'synthetic', '日本語'):
            self.assertNotIn(private, err.getvalue())

    def test_AC010_no_extra_cli_capabilities(self):
        for args in (['save', '--all'], ['save', '--path', 'synthetic'], ['save', '--user-id', '90002'],
                     ['delete'], ['export'], ['save', '--max-r', '1'], ['save', 'save']):
            with self.subTest(args=args):
                self.assert_failure(self.run_cli(args=args), 'invalid_input')
        self.assertFalse(self.path.exists())

    def test_AC002_provider_failure_never_creates_directories(self):
        self.assert_failure(self.run_cli(lookup_effect=x_api.XApiError('rate_limited', requests_attempted=1)), 'rate_limited', 1)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
