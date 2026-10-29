"""Issue #64 AC-1: synthetic-only, one X bookmark page, additive sidecar."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from x_context import bookmark_enrichment as meta
from x_context import cli, x_api


POST = {
    'id': '1234567890', 'text': 'Synthetic check https://t.co/fake',
    'entities': {'urls': [{
        'url': 'https://t.co/fake', 'expanded_url': 'https://example.org/article',
        'display_url': 'example.org/article', 'title': 'Synthetic title',
        'description': 'Synthetic description', 'status': 200,
        'unwound_url': 'https://example.org/article'
    }]},
    'attachments': {'media_keys': ['3_fake1']},
    'referenced_posts': [{'id': '5555', 'type': 'quoted'}],
    'card_uri': 'card://synthetic',
}
INCLUDES = {
    'media': [
        {'media_key': '3_fake1', 'type': 'photo', 'url': 'https://pbs.twimg.com/fake.jpg',
         'alt_text': 'Synthetic picture', 'preview_image_url': 'https://pbs.twimg.com/preview.jpg'},
        {'media_key': '3_unrelated', 'type': 'photo', 'url': 'https://elsewhere.invalid/'}
    ],
    'posts': [
        {'id': '5555', 'text': 'Synthetic quote', 'unknown_secret': 'do-not-copy'},
        {'id': '7777', 'text': 'Unrelated quote'}
    ],
}


def reply(value):
    return x_api.HttpResponse(200, {}, json.dumps(value).encode('utf-8'))


class FakeTransport:
    def __init__(self, posts=None, includes=None):
        self.requests = []
        self.posts = posts if posts is not None else [POST]
        self.includes = includes if includes is not None else INCLUDES

    def __call__(self, request):
        self.requests.append(request)
        if len(self.requests) == 1:
            return reply({'data': {'id': '42', 'username': 'synthetic'}})
        if len(self.requests) == 2:
            return reply({'data': self.posts, 'includes': self.includes,
                          'meta': {'result_count': len(self.posts)}})
        raise AssertionError('unexpected third X request')


class AC1Tests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.data = self.root / 'x-context' / 'data'
        self.primary = self.data / 'bookmarks-v1.json'
        self.sidecar = self.data / 'bookmark-enrichment-v1.json'
        self.env = {'LOCALAPPDATA': str(self.root), 'X_CONTEXT_USER_ACCESS_TOKEN': 'FAKE-SECRET'}

    def run_cli(self, args=None, transport=None, env=None):
        t = transport or FakeTransport()
        stdout, stderr = io.StringIO(), io.StringIO()
        rc = cli.main(['bookmarks', 'save', '--enrich', '--max-results', '1'] if args is None else args,
                      environ=self.env if env is None else env, transport=t, stdout=stdout, stderr=stderr)
        return rc, stdout.getvalue(), json.loads(stderr.getvalue()), t

    def test_capture_full_fixture_exactly_and_no_orphans(self):
        record = meta.capture(POST, INCLUDES)
        self.assertEqual(record, {
            'id': '1234567890',
            'fields': {
                'entities.urls': {'state': 'present', 'value': POST['entities']['urls']},
                'attachments.media_keys': {'state': 'present', 'value': ['3_fake1']},
                'referenced_posts': {'state': 'present', 'value': [{'id': '5555', 'type': 'quoted'}]},
                'card_uri': {'state': 'present', 'value': 'card://synthetic'},
            },
            'reference_field_name': 'referenced_posts',
            'included_media': [{k: INCLUDES['media'][0][k] for k in
                               ('media_key', 'type', 'url', 'preview_image_url', 'alt_text')}],
            'included_posts': [{'id': '5555', 'text': 'Synthetic quote'}],
        })
        self.assertNotIn('Unrelated', json.dumps(record))
        self.assertNotIn('do-not-copy', json.dumps(record))

    def test_missing_is_distinct_from_explicitly_empty_and_legacy_ref_key(self):
        empty = meta.capture({'id': '1', 'text': 'Hi', 'entities': {'urls': []},
                              'referenced_tweets': []}, {})
        self.assertEqual(empty['fields']['entities.urls'], {'state': 'present', 'value': []})
        self.assertEqual(empty['fields']['attachments.media_keys'], {'state': 'not_returned'})
        self.assertEqual(empty['fields']['referenced_posts'], {'state': 'present', 'value': []})
        self.assertEqual(empty['reference_field_name'], 'referenced_tweets')
        absent = meta.capture({'id': '1', 'text': 'Hi'}, {})
        self.assertEqual(set(f['state'] for f in absent['fields'].values()), {'not_returned'})
        self.assertIsNone(absent['reference_field_name'])

    def test_cli_requests_official_params_only_for_explicit_enrich_and_two_gets(self):
        rc, out, diag, t = self.run_cli()
        self.assertEqual(rc, 0)
        self.assertEqual(len(t.requests), 2)
        query = parse_qs(urlsplit(t.requests[1].url).query)
        self.assertEqual(query, {
            'max_results': ['1'],
            'post.fields': ['entities,attachments,card_uri'],
            'expansions': ['attachments.media_keys,referenced_posts'],
            'media.fields': ['media_key,type,url,preview_image_url,alt_text'],
        })
        self.assertEqual(diag['provider_requests_attempted'], 2)
        self.assertEqual(json.loads(out)['items'], [{'id': POST['id'], 'text': POST['text']}])
        self.assertEqual(self.sidecar.exists(), True)
        saved = json.loads(self.sidecar.read_text(encoding='utf-8'))
        self.assertEqual((saved['schema_version'], saved['subject_id']), ('1', '42'))
        self.assertEqual(list(saved['items']), [POST['id']])
        entry = saved['items'][POST['id']]
        self.assertEqual(entry['fields'], meta.capture(POST, INCLUDES)['fields'])
        self.assertEqual(entry['included_media'], meta.capture(POST, INCLUDES)['included_media'])
        self.assertEqual(entry['included_posts'], [{'id': '5555', 'text': 'Synthetic quote'}])
        self.assertEqual(entry['observed_at'], json.loads(out)['retrieved_at'])
        self.assertEqual(set(json.loads(self.primary.read_text())['items'][0]),
                         {'id', 'text', 'first_seen_at', 'last_seen_at'})
        self.assertNotIn('FAKE-SECRET', self.sidecar.read_text() + out + str(diag))

    def test_legacy_save_unchanged_does_not_create_sidecar(self):
        t = FakeTransport()
        rc, out, diag, _ = self.run_cli(['bookmarks', 'save', '--max-results', '1'], t)
        self.assertEqual(rc, 0)
        self.assertEqual(parse_qs(urlsplit(t.requests[1].url).query), {'max_results': ['1']})
        self.assertFalse(self.sidecar.exists())
        self.assertTrue(self.primary.exists())

    def test_enrich_requires_save_no_credentials_or_transport(self):
        t = FakeTransport()
        rc, out, diag, _ = self.run_cli(['bookmarks', '--enrich'], t)
        self.assertEqual((rc, out, diag['error_category']), (2, '', 'invalid_input'))
        self.assertEqual(t.requests, [])

    def test_corrupt_sidecar_or_subject_mismatch_stops_before_credentials(self):
        self.data.mkdir(parents=True)
        for raw, expected in ((b'PRIVATE INVALID', 'storage_error'),
                              (b'{"schema_version":"1","subject_id":"41","items":{}}',
                               'subject_mismatch')):
            with self.subTest(raw=raw):
                self.sidecar.write_bytes(raw)
                # Prime a valid primary bookmark store for subject-mismatch checks.
                self.primary.write_text(json.dumps({
                    'store_schema_version': '1', 'source': 'x', 'collection': 'bookmarks',
                    'subject': {'id': '42'}, 'created_at': '2026-10-12T00:00:00Z',
                    'updated_at': '2026-10-12T00:00:00Z', 'items': []
                }))
                with patch.object(cli, 'resolve_user_access_token', side_effect=AssertionError('credentials accessed')):
                    rc, out, diag, t = self.run_cli()
                self.assertEqual((rc, out, diag['error_category']), (2 if expected == 'storage_error' else 3, '', expected))
                self.assertEqual(t.requests, [])
                self.assertEqual(self.sidecar.read_bytes(), raw)

    def test_bad_provider_metadata_never_modifies_original_or_sidecar(self):
        for bad in (dict(POST, entities={'urls': [{'url': 3}]}),
                    dict(POST, attachments={'media_keys': 'wrong'}),
                    dict(POST, referenced_posts=[{'id': 'not-id', 'type': 'quoted'}])):
            with self.subTest(bad=bad):
                t = FakeTransport(posts=[bad])
                rc, out, diag, _ = self.run_cli(transport=t)
                self.assertEqual((rc, out, diag['error_category']), (3, '', 'provider_error'))
                self.assertFalse(self.primary.exists())
                self.assertFalse(self.sidecar.exists())

    def test_P1_full_page_26_posts_104_included_media_is_saved(self):
        # Reproduces the independent L2 report: four media each, 26 Posts.
        posts, media = [], []
        for n in range(26):
            keys = [f'3_synthetic_{n}_{i}' for i in range(4)]
            posts.append({'id': str(50000+n), 'text': f'Synthetic post {n}',
                          'attachments': {'media_keys': keys}})
            media += [{'media_key': k, 'type': 'photo', 'url': f'https://example.org/{k}.jpg'}
                      for k in keys]
        t = FakeTransport(posts=posts, includes={'media': media})
        rc, out, diag, _ = self.run_cli(
            ['bookmarks', 'save', '--enrich', '--max-results', '26'], t)
        self.assertEqual((rc, diag['provider_requests_attempted']), (0, 2))
        self.assertEqual(len(json.loads(self.primary.read_text())['items']), 26)
        items = json.loads(self.sidecar.read_text())['items']
        self.assertEqual(len(items), 26)
        self.assertTrue(all(len(v['included_media']) == 4 for v in items.values()))

    def test_P1_101_included_referenced_posts_in_one_page(self):
        posts, related = [], []
        for n in range(51):
            refs = [{'id': str(600000+n*2+j), 'type': 'quoted'} for j in range(2)]
            posts.append({'id': str(51000+n), 'text': f'Synthetic {n}',
                          'referenced_posts': refs})
            related.extend({'id': r['id'], 'text': f"Quoted {r['id']}"} for r in refs)
        t = FakeTransport(posts=posts, includes={'posts': related})
        rc, out, diag, _ = self.run_cli(
            ['bookmarks', 'save', '--enrich', '--max-results', '51'], t)
        self.assertEqual((rc, diag['provider_requests_attempted']), (0, 2))
        items = json.loads(self.sidecar.read_text())['items']
        self.assertEqual(len(items), 51)
        self.assertEqual(sum(len(v['included_posts']) for v in items.values()), 102)

    def test_P2_schema_nullable_media_and_url_without_url_attribute(self):
        input_post = {
            'id': '1', 'text': 'synthetic',
            'entities': {'urls': [{'title': 'Card title', 'description': 'Card description'}]},
            'attachments': {'media_keys': None}
        }
        record = meta.capture(input_post, {})
        self.assertEqual(record['fields']['entities.urls']['value'],
                         [{'title': 'Card title', 'description': 'Card description'}])
        self.assertEqual(record['fields']['attachments.media_keys'],
                         {'state': 'present', 'value': None})
        rc, out, diag, _ = self.run_cli(transport=FakeTransport(posts=[input_post], includes={}))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(self.sidecar.read_text())['items']['1']['fields'],
                         record['fields'])

    def test_P2_duplicate_expansions_and_reference_ids_rejected(self):
        for post, inc in (
            (POST, {'media': [INCLUDES['media'][0], INCLUDES['media'][0]]}),
            (POST, {'posts': [INCLUDES['posts'][0], INCLUDES['posts'][0]]}),
            (dict(POST, referenced_posts=[{'id': '5555', 'type': 'quoted'}] * 2), {}),
        ):
            with self.subTest(inc=inc):
                with self.assertRaises(ValueError):
                    meta.capture(post, inc)
        for invalid in ('evil', 'unknown', '', None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    meta.capture(dict(POST, referenced_posts=[{'id': '5555', 'type': invalid}]), {})

    def test_P2_orphan_sidecar_stops_before_creating_main_store(self):
        self.data.mkdir(parents=True)
        orphan = b'{"schema_version":"1","subject_id":"41","items":{}}'
        self.sidecar.write_bytes(orphan)
        with patch.object(cli, 'resolve_user_access_token', side_effect=AssertionError('credentials accessed')):
            rc, out, diag, t = self.run_cli()
        self.assertEqual((rc, out, diag['error_category']), (2, '', 'storage_error'))
        self.assertEqual(t.requests, [])
        self.assertFalse(self.primary.exists())
        self.assertEqual(self.sidecar.read_bytes(), orphan)

    def test_P2_existing_sidecar_size_checked_before_decoding(self):
        self.data.mkdir(parents=True)
        oversize = b'x' * (meta._LIMIT_BYTES + 1)
        self.sidecar.write_bytes(oversize)
        with patch.object(cli, 'resolve_user_access_token', side_effect=AssertionError('credentials accessed')):
            rc, out, diag, t = self.run_cli()
        self.assertEqual((rc, out, diag['error_category']), (2, '', 'storage_error'))
        self.assertEqual(t.requests, [])
        self.assertFalse(self.primary.exists())
        self.assertEqual(self.sidecar.stat().st_size, len(oversize))

    def test_repeated_save_and_enrichment_fail_does_not_destroy_original(self):
        rc, out, diag, _ = self.run_cli()
        self.assertEqual(rc, 0)
        first = json.loads(self.sidecar.read_text())
        bytes_primary = self.primary.read_bytes()
        self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual(json.loads(self.sidecar.read_text())['items'][POST['id']]['fields'],
                         first['items'][POST['id']]['fields'])
        self.assertEqual(json.loads(self.primary.read_text())['items'][0]['text'], POST['text'])
        with patch.object(meta.os, 'replace', side_effect=OSError('PRIVATE-SECRET')):
            rc, out, diag, _ = self.run_cli()
        self.assertEqual((rc, out, diag['error_category']), (2, '', 'storage_error'))
        self.assertFalse(diag.get('storage', {}).get('persistence_succeeded', False))
        self.assertEqual(self.sidecar.read_text().find('FAKE-SECRET'), -1)
        self.assertEqual(json.loads(self.primary.read_text())['items'][0]['text'], POST['text'])
        self.assertNotIn('PRIVATE-SECRET', str(diag))
        self.assertEqual(set(self.data.glob('*.tmp')), set())


if __name__ == '__main__':
    unittest.main()
