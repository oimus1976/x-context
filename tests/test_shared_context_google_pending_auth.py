"""Issue #67: consent-only login is independent of publication journals.

All paths/credentials are fictional; effect boundaries are explicit tripwires.
"""
from contextlib import ExitStack
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from x_context.shared_context import google_auth as auth, google_publish as pub


class PendingAuthenticationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.credential = self.root / 'fictional-credential.dpapi'
        self.registry = self.root / 'fictional-publication.json'
        self.client = self.root / 'fictional-desktop.json'
        self.credential.write_bytes(b'FAKE-SECRET existing credential sentinel')
        self.pending = json.dumps(dict(pub.empty_state(), pending=[['', 'CREATE_ATTEMPT']])).encode()
        self.registry.write_bytes(self.pending)

    def login(self, reauthorize=True):
        return ['login', '--approve-new-auth', '--client-config', str(self.client)] + (
            ['--reauthorize'] if reauthorize else [])

    def invoke(self, argv, *, deny_state=False, bootstrap_impl=None):
        store = Mock(name='fictional_store')
        store.load.return_value = object()  # Existing credential; never a real DPAPI store.
        out, err = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            mocks = {}
            mocks['paths'] = stack.enter_context(patch.object(
                pub, 'default_paths', return_value=(self.credential, self.registry)))
            state_type = pub.State
            mocks['state_save'] = stack.enter_context(patch.object(
                state_type, 'save', side_effect=AssertionError('FAKE-SECRET registry write')))
            mocks['state'] = stack.enter_context(patch.object(
                pub, 'State', **({'side_effect': AssertionError('FAKE-SECRET registry access')}
                               if deny_state else {'wraps': state_type})))
            mocks['store'] = stack.enter_context(patch.object(auth, 'Store', return_value=store))
            mocks['bootstrap'] = stack.enter_context(patch.object(
                auth, 'bootstrap', side_effect=bootstrap_impl))
            for name, module, attribute in (
                ('provider', auth, 'Provider'), ('token', auth, 'token_request'),
                ('server', auth, 'HTTPServer'), ('browser', auth.webbrowser, 'open'),
                ('auth_http', auth, 'build_opener'), ('http', pub.api, 'HTTP'),
                ('transport', pub.api, 'Transport'), ('backend', pub, 'AppBackend'),
                ('publish', pub, 'publish'), ('preview', pub.drive, 'preview'),
            ):
                mocks[name] = stack.enter_context(patch.object(
                    module, attribute, side_effect=AssertionError('FAKE-SECRET forbidden ' + name)))
            stack.enter_context(patch.object(auth, 'os', SimpleNamespace(name='nt')))
            stack.enter_context(patch('sys.stdout', out))
            stack.enter_context(patch('sys.stderr', err))
            code = pub.main(argv)
        self.assertLess(len(out.getvalue()) + len(err.getvalue()), 512)
        self.assertNotIn('FAKE-SECRET', out.getvalue() + err.getvalue())
        for name in ('state_save', 'provider', 'token', 'server', 'browser', 'auth_http',
                     'http', 'transport', 'backend', 'publish', 'preview'):
            mocks[name].assert_not_called()
        store.save.assert_not_called()
        return code, out.getvalue(), err.getvalue(), mocks, store

    def assert_authorized(self, result, reauthorize):
        code, out, err, mocks, store = result
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out), dict(
            status='GOOGLE_AUTHORIZED', scope=auth.SCOPE, x_requests_attempted=0))
        mocks['store'].assert_called_once_with(self.credential)
        mocks['bootstrap'].assert_called_once_with(
            store, str(self.client), approved=True, reauthorize=reauthorize)
        mocks['state'].assert_not_called()
        store.load.assert_not_called()

    def test_P1_01_approved_login_and_reauth_ignore_pending_preserve_bytes(self):
        before = self.credential.read_bytes()
        for reauthorize in (False, True):
            with self.subTest(reauthorize=reauthorize):
                self.assert_authorized(self.invoke(self.login(reauthorize)), reauthorize)
                self.assertEqual(self.registry.read_bytes(), self.pending)
                self.assertEqual(self.credential.read_bytes(), before)

    def test_P1_01_login_never_opens_missing_corrupt_or_unsafe_registry(self):
        for value in (b'{FAKE-SECRET malformed', b'{"schema":"unknown"}', None, 'directory'):
            with self.subTest(registry=value):
                # Separate fictional paths avoid restoring any operational state.
                self.registry = self.root / ('registry-' + str(len(list(self.root.iterdir()))))
                if value == 'directory':
                    self.registry.mkdir()
                elif value is not None:
                    self.registry.write_bytes(value)
                self.assert_authorized(self.invoke(self.login(), deny_state=True), True)
                if isinstance(value, bytes):
                    self.assertEqual(self.registry.read_bytes(), value)
                elif value is None:
                    self.assertFalse(self.registry.exists())
                else:
                    self.assertEqual(list(self.registry.iterdir()), [])

    def test_P1_03_missing_unapproved_and_invalid_login_have_zero_effects(self):
        for argv in (
            [], ['login'], ['login', '--approve-new-auth'],
            ['login', '--client-config', str(self.client)],
            ['login', '--reauthorize', '--client-config', str(self.client)],
            self.login() + ['--apply'], self.login() + ['--dry-run'],
            self.login() + ['--synthetic-fixtures', 'baseline'],
            self.login() + ['--unknown', 'FAKE-SECRET'],
        ):
            with self.subTest(argv=argv):
                code, out, err, mocks, store = self.invoke(argv, deny_state=True)
                self.assertEqual((code, out), (2, ''))
                self.assertIn(json.loads(err)['error'], (
                    'INVALID_COMMAND', 'GOOGLE_BOOTSTRAP_OWNER_APPROVAL_REQUIRED'))
                for name in ('paths', 'state', 'store', 'bootstrap'):
                    mocks[name].assert_not_called()
                store.load.assert_not_called()
                self.assertEqual(self.registry.read_bytes(), self.pending)

    def test_P1_02_pending_drive_commands_stop_before_auth_or_remote_effects(self):
        for argv in (['init-sandbox', '--apply'],
                     ['publish', '--synthetic-fixtures', 'baseline', '--dry-run'],
                     ['publish', '--synthetic-fixtures', 'baseline', '--apply']):
            with self.subTest(argv=argv):
                code, out, err, mocks, store = self.invoke(argv)
                self.assertEqual((code, out), (2, ''))
                self.assertEqual(json.loads(err), dict(
                    error='GOOGLE_EFFECT_REQUIRES_INSPECTION', x_requests_attempted=0))
                mocks['store'].assert_not_called()
                mocks['bootstrap'].assert_not_called()
                store.load.assert_not_called()
                self.assertEqual(self.registry.read_bytes(), self.pending)

    def test_P1_02_corrupt_or_unsafe_registry_still_blocks_drive_commands(self):
        for value in (b'{FAKE-SECRET malformed', b'{"schema":"unknown"}', 'directory'):
            for mode in ('init', 'preview', 'apply'):
                with self.subTest(value=value, mode=mode):
                    self.registry = self.root / ('bad-' + str(len(list(self.root.iterdir()))))
                    if value == 'directory':
                        self.registry.mkdir()
                    else:
                        self.registry.write_bytes(value)
                    argv = (['init-sandbox', '--apply'] if mode == 'init' else
                            ['publish', '--synthetic-fixtures', 'baseline',
                             '--dry-run' if mode == 'preview' else '--apply'])
                    code, out, err, mocks, store = self.invoke(argv)
                    self.assertEqual((code, out), (2, ''))
                    self.assertEqual(json.loads(err)['error'], 'GOOGLE_PUBLICATION_STATE_ERROR')
                    mocks['store'].assert_not_called()
                    mocks['bootstrap'].assert_not_called()
                    store.load.assert_not_called()

    def test_P1_03_existing_credential_without_reauthorize_stays_protected(self):
        original_bootstrap = auth.bootstrap
        before = self.credential.read_bytes()
        code, out, err, mocks, store = self.invoke(
            self.login(False), bootstrap_impl=original_bootstrap)
        self.assertEqual((code, out), (2, ''))
        self.assertEqual(json.loads(err)['error'], 'GOOGLE_CREDENTIAL_EXISTS')
        store.load.assert_called_once_with()
        self.assertEqual(self.credential.read_bytes(), before)
        self.assertEqual(self.registry.read_bytes(), self.pending)

    def test_P1_03_bootstrap_failure_is_bounded_and_does_not_touch_registry(self):
        code, out, err, mocks, store = self.invoke(
            self.login(), deny_state=True,
            bootstrap_impl=RuntimeError('FAKE-SECRET provider details'))
        self.assertEqual((code, out), (2, ''))
        self.assertEqual(json.loads(err)['error'], 'GOOGLE_OPERATION_UNAVAILABLE')
        mocks['bootstrap'].assert_called_once_with(
            store, str(self.client), approved=True, reauthorize=True)
        mocks['state'].assert_not_called()
        self.assertEqual(self.registry.read_bytes(), self.pending)


if __name__ == '__main__':
    unittest.main()
