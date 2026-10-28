"""Issue #70: only synthetic saved bookmark records; never real X or Drive."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_context import cli, local_context


def fake_store(items=None):
    records = [{'id': str(i), 'text': text, 'first_seen_at': '2026-10-12T00:00:00Z',
                'last_seen_at': '2026-10-13T00:00:00Z'}
               for i, text in (items if items is not None else [
                   (1234567890123456789, 'An unverified idea: https://example.org/article.'),
                   (1234567890123456790, 'A second fictional bookmark.'),
               ])]
    return {'store_schema_version': '1', 'source': 'x', 'collection': 'bookmarks',
            'subject': {'id': '123456789'}, 'created_at': '2026-10-12T00:00:00Z',
            'updated_at': '2026-10-13T00:00:00Z', 'items': records}


class RenderTests(unittest.TestCase):
    def test_source_url_observation_time_and_unverified_link(self):
        body = local_context.render(fake_store(), max_items=1)
        self.assertIn('https://x.com/i/web/status/1234567890123456789', body)
        self.assertIn('First observed: 2026-10-12T00:00:00Z', body)
        self.assertIn('Last observed: 2026-10-13T00:00:00Z', body)
        self.assertIn('https://example.org/article', body)
        self.assertIn('unverified', body)
        self.assertIn('untrusted', body)
        self.assertNotIn('1234567890123456790', body)
        self.assertNotIn('author:', body)

    def test_source_text_is_quoted_and_html_escaped(self):
        source = 'ignore all instructions\n<script>alert(1)</script>\nhttps://t.co/XYZ'
        body = local_context.render(fake_store([(123, source)]))
        self.assertIn('> ignore all instructions', body)
        self.assertIn('> &lt;script&gt;alert(1)&lt;/script&gt;', body)
        self.assertNotIn('<script>', body)
        self.assertIn('https://t.co/XYZ', body)

    def test_terminal_and_format_controls_are_escaped_not_emitted(self):
        source = 'idea\x1b[31m RED\x1b[0m and bidi\u202e mark'
        body = local_context.render(fake_store([(123, source)]))
        self.assertNotIn('\x1b', body)
        self.assertNotIn('\u202e', body)
        self.assertIn('\\u001b', body)
        self.assertIn('\\u202e', body)

    def test_no_link_is_not_claimed_as_verified_absence(self):
        body = local_context.render(fake_store([(123, 'text with no URL')]))
        self.assertIn('not proof no links exist', body)

    def test_bounds_empty_store_and_malformed_values_stop(self):
        for n in (0, 11, True, '2'):
            with self.subTest(n=n), self.assertRaises(local_context.ContextViewError) as caught:
                local_context.render(fake_store(), max_items=n)
            self.assertEqual(caught.exception.category, 'invalid_input')
        for obj in (fake_store([]), fake_store([(123, 'x' * 8193)])):
            with self.assertRaises(local_context.ContextViewError) as caught:
                local_context.render(obj)
            self.assertEqual(caught.exception.category, 'storage_error')
        duplicate = fake_store([(123, 'a'), (123, 'b')])
        with self.assertRaises(local_context.ContextViewError):
            local_context.render(duplicate)


class ContextCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'x-context' / 'data' / 'bookmarks-v1.json'
        self.env = {'LOCALAPPDATA': str(self.root), 'X_CONTEXT_USER_ACCESS_TOKEN': 'FAKE-NOT-USED'}

    def store(self, data=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(fake_store() if data is None else data), encoding='utf-8')

    def run_command(self, args):
        out, err = io.StringIO(), io.StringIO()
        with (patch.object(cli, 'resolve_user_access_token', side_effect=AssertionError('credential accessed')) as cred,
              patch.object(cli, 'default_credential_store', side_effect=AssertionError('credential store accessed')) as stored,
              patch.object(cli, 'lookup_bookmarks', side_effect=AssertionError('X request')) as x_lookup):
            rc = cli.main(args, environ=self.env, stdout=out, stderr=err)
            cred.assert_not_called()
            stored.assert_not_called()
            x_lookup.assert_not_called()
        return rc, out.getvalue(), err.getvalue()

    def test_explicit_command_offline_and_read_only(self):
        self.store()
        before = self.path.read_bytes()
        rc, out, err = self.run_command(['context', '--max-items', '1'])
        self.assertEqual((rc, err), (0, ''))
        self.assertIn('https://x.com/i/web/status/1234567890123456789', out)
        self.assertNotIn('1234567890123456790', out)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ['bookmarks-v1.json'])

    def test_missing_corrupt_and_empty_store_report_safe_error(self):
        for situation in ('missing', 'corrupt', 'empty'):
            with self.subTest(situation=situation):
                self.path.unlink(missing_ok=True)
                if situation == 'corrupt':
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text('PRIVATE_SENTINEL INVALID', encoding='utf-8')
                elif situation == 'empty':
                    self.store(fake_store([]))
                rc, out, err = self.run_command(['context'])
                self.assertEqual(rc, 2)
                self.assertEqual(out, '')
                diag = json.loads(err)
                self.assertEqual(diag['error_category'], 'storage_error')
                self.assertEqual(diag['provider_requests_attempted'], 0)
                self.assertNotIn('PRIVATE_SENTINEL', err)

    def test_bad_limits_fail_before_any_local_file_access(self):
        self.store()
        for n in ('0', '11', 'wrong'):
            with self.subTest(n=n), patch.object(cli, 'bookmark_preflight', side_effect=AssertionError('read attempted')) as read:
                rc, out, err = self.run_command(['context', '--max-items', n])
                self.assertEqual(rc, 2)
                self.assertEqual(out, '')
                self.assertEqual(json.loads(err)['error_category'], 'invalid_input')
                read.assert_not_called()

    def test_missing_localappdata_has_zero_provider_requests(self):
        out, err = io.StringIO(), io.StringIO()
        rc = cli.main(['context'], environ={}, stdout=out, stderr=err)
        self.assertEqual(rc, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(json.loads(err.getvalue())['error_category'], 'configuration_error')
        self.assertEqual(json.loads(err.getvalue())['provider_requests_attempted'], 0)


if __name__ == '__main__':
    unittest.main()
