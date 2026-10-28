"""Gate R caller: synthetic inputs only; no Google or real credential access."""
import unittest
from unittest.mock import Mock
from x_context.shared_context import google_auth as auth
from x_context.shared_context import google_gate_r as gate

class CallerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def request(service, method, path, *, query=None, body=None, timeout=None):
            self.calls.append((service, method, path, query, body, timeout))
            return {'user': {'permissionId': 'FAKE-OWNER', 'me': True}}
        self.guard = gate.ReadOnlyHTTP(request, folder='FAKE-FOLDER',
             documents={'FAKE-DOC'}, monotonic=lambda: 0, deadline=120)

    def test_principal_exact_match_before_other_reads(self):
        self.assertEqual(self.guard.verify_principal('FAKE-OWNER'), None)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][:4], ('drive', 'GET', 'about', {'fields': 'user(permissionId,me)'}))
        with self.assertRaises(Exception):
            self.guard.verify_principal('FAKE-WRONG')
        self.assertEqual(len(self.calls), 1)

    def test_invalid_principal_blocks_before_document(self):
        bad = gate.ReadOnlyHTTP(lambda *a, **k: {'user': {'permissionId':'FAKE-OTHER','me':True}},
             folder='FAKE-FOLDER', documents={'FAKE-DOC'}, monotonic=lambda: 0, deadline=120)
        with self.assertRaises(Exception): bad.verify_principal('FAKE-OWNER')
        with self.assertRaises(Exception): bad.request('docs','GET','documents/FAKE-DOC',query={'includeTabsContent':'true'})

    def test_reject_mutation_extra_id_and_unexpected_query_before_network(self):
        self.guard.verify_principal('FAKE-OWNER')
        for service, method, path, query, body in [
            ('drive','POST','files',{},{}), ('drive','GET','files/FAKE-OTHER',{},None),
            ('docs','GET','documents/FAKE-DOC',{'includeTabsContent':'false'},None),
            ('docs','DELETE','documents/FAKE-DOC',{},None)]:
            with self.subTest(path=path,method=method), self.assertRaises(Exception):
                self.guard.request(service,method,path,query=query,body=body)
        self.assertEqual(len(self.calls), 1)

    def test_budgets_and_deadline_fail_closed(self):
        self.guard.verify_principal('FAKE-OWNER')
        self.guard.docs_remaining = 0
        with self.assertRaises(Exception): self.guard.request('docs','GET','documents/FAKE-DOC',query={'includeTabsContent':'true'})
        late = gate.ReadOnlyHTTP(Mock(),folder='FAKE-FOLDER',documents={'FAKE-DOC'},monotonic=lambda: 120,deadline=120)
        with self.assertRaises(Exception): late.verify_principal('FAKE-OWNER')
        self.assertEqual(len(self.calls), 1)

    def test_unexpired_token_only_and_no_refresh_or_save(self):
        credential=auth.Credential('fake.apps.googleusercontent.com','fake-secret','fake-token','fake-refresh',1000,(auth.SCOPE,))
        store=Mock(); store.load.return_value=credential
        self.assertEqual(gate.load_unexpired_token(store, now=800, lifetime=120), 'fake-token')
        store.save.assert_not_called()
        with self.assertRaises(Exception): gate.load_unexpired_token(store, now=900, lifetime=120)
        store.save.assert_not_called()



class CallerSnapshotTests(unittest.TestCase):
    def test_two_snapshots_fit_allowlist_and_measured_budget(self):
        from test_shared_context_google_reconcile import ReconcileTests
        from x_context.shared_context import google_reconcile as reconcile, google_recovery as recovery, google_api as api
        fixture = ReconcileTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        evidence = fixture.local()
        def fake_request(service, method, path, *, query=None, body=None, timeout=None):
            if path == 'about':
                return {'user': {'permissionId': evidence.original['owner'], 'me': True}}
            return fixture.http.request(service, method, path, query=query, body=body)
        guard = gate.ReadOnlyHTTP(fake_request, folder=evidence.original['folder'],
            documents=set(evidence.projected['documents'].values()), monotonic=lambda: 0, deadline=120)
        guard.verify_principal(evidence.original['owner'])
        plan = reconcile.plan_reconciliation(api.Transport(guard), fixture.state,
            recovery.Journal(fixture.sidecar_path), reviewed_code='FAKE-HEAD')
        self.assertEqual(len(plan.digest), 64)
        self.assertEqual((guard.drive_remaining, guard.docs_remaining, guard.about_remaining), (10, 4, 0))
        self.assertFalse(fixture.http.effects)

class BoundedEvidenceTests(unittest.TestCase):
    def test_local_and_plan_never_use_unbounded_evidence_read_bytes(self):
        from pathlib import Path
        from unittest.mock import patch
        from test_shared_context_google_reconcile import ReconcileTests
        from x_context.shared_context import google_reconcile as reconcile, google_recovery as recovery
        fixture = ReconcileTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        real_read = Path.read_bytes
        protected = {fixture.state_path, fixture.sidecar_path}
        def reject_unbounded(path):
            if path in protected:
                raise AssertionError('unbounded evidence read')
            return real_read(path)
        with patch.object(Path, 'read_bytes', reject_unbounded):
            state = gate.BoundedState(fixture.state_path)
            evidence = reconcile.inspect_local(state, recovery.Journal(fixture.sidecar_path))
            plan = reconcile.plan_reconciliation(fixture.transport, state,
                recovery.Journal(fixture.sidecar_path), reviewed_code='FAKE-HEAD')
        self.assertEqual(evidence.original_bytes, fixture.original)
        self.assertEqual(len(plan.digest), 64)
        self.assertFalse(fixture.http.effects)

class DeadlineAfterResponseTests(unittest.TestCase):
    def test_response_after_deadline_is_rejected(self):
        ticks = iter([0, 121])
        fake = Mock(return_value={'user': {'permissionId':'FAKE-OWNER', 'me':True}})
        guard = gate.ReadOnlyHTTP(fake, folder='FAKE-FOLDER', documents={'FAKE-DOC'},
                                  monotonic=lambda: next(ticks), deadline=120)
        with self.assertRaises(Exception):
            guard.verify_principal('FAKE-OWNER')
        self.assertEqual(fake.call_count, 1)
        self.assertLessEqual(fake.call_args.kwargs['timeout'], 120)

class CallerIntegrationTests(unittest.TestCase):
    def setUp(self):
        from test_shared_context_google_reconcile import ReconcileTests
        from contextlib import nullcontext
        self.fixture = ReconcileTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.platform = Mock()
        self.platform.lock.return_value = nullcontext()
        self.platform.validate.return_value = 'FAKE-USER-SID'
        self.store = Mock()
        self.store.load.return_value = auth.Credential('fake.apps.googleusercontent.com', 'secret',
            'access', 'refresh', 1000, (auth.SCOPE,))
        self.calls = []
        def request_factory(token, **bindings):
            self.assertEqual(token, 'access')
            def request(service, method, path, *, query=None, body=None, timeout=None):
                self.calls.append((service, method, path))
                if path == 'about':
                    return {'user': {'permissionId': 'FAKE-OWNER', 'me': True}}
                return self.fixture.http.request(service, method, path, query=query, body=body)
            return request
        self.request_factory = request_factory

    def preflight(self):
        return gate.prepare(self.fixture.state_path, self.fixture.sidecar_path,
            credential_path=self.fixture.state_path.parent / 'fake-credential.dpapi',
            selected_user='FAKE-USER-SID', approval_reference='FAKE-APPROVAL',
            platform=self.platform)

    def test_synthetic_caller_complete_and_redacted(self):
        preparation = self.preflight()
        self.store.load.assert_not_called()
        result = gate.execute(preparation, approved_digest=preparation.digest,
            platform=self.platform, store=self.store, request_factory=self.request_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'PASS')
        self.assertEqual(len(result.digest), 64)
        self.assertEqual(sum(s == 'drive' for s, _, _ in self.calls), 81)
        self.assertEqual(sum(s == 'docs' for s, _, _ in self.calls), 24)
        self.assertNotIn('FAKE-OWNER', repr(result))
        self.assertFalse(self.fixture.http.effects)
        self.store.save.assert_not_called()
        self.assertEqual(self.fixture.state_path.read_bytes(), self.fixture.original)

    def test_preflight_or_approval_mismatch_never_loads_credential_or_calls_network(self):
        preparation = self.preflight()
        self.fixture.state_path.write_bytes(self.fixture.original + b' ')
        result = gate.execute(preparation, approved_digest=preparation.digest,
            platform=self.platform, store=self.store, request_factory=self.request_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.store.load.assert_not_called()
        self.assertEqual(self.calls, [])
        self.store.save.assert_not_called()

    def test_selected_user_mismatch_blocks_before_local_evidence(self):
        self.platform.validate.return_value = 'FAKE-OTHER-SID'
        with self.assertRaises(Exception): self.preflight()
        self.store.load.assert_not_called()
        self.assertEqual(self.calls, [])

class WindowsBoundaryTests(unittest.TestCase):
    def test_same_process_mutex_rejects_second_caller_and_releases(self):
        import os
        if os.name != 'nt': self.skipTest('Windows only')
        platform = gate.WindowsPlatform()
        with platform.lock():
            with self.assertRaises(Exception):
                with platform.lock(): pass
        with platform.lock(): pass

    def test_windows_user_sid_is_real_and_mismatch_blocks(self):
        import os
        if os.name != 'nt': self.skipTest('Windows only')
        platform = gate.WindowsPlatform()
        sid = platform.current_user()
        self.assertRegex(sid, r'^S-1-\d+(?:-\d+)+$')
        with self.assertRaises(Exception):
            platform.validate((), 'S-1-0-0')

    def test_private_synthetic_paths_validated_and_duplicate_rejected(self):
        import os, tempfile
        from pathlib import Path
        from unittest.mock import patch
        if os.name != 'nt': self.skipTest('Windows only')
        platform = gate.WindowsPlatform()
        sid = platform.current_user()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = (root/'fake.json', root/'fake.jsonl', root/'fake.dpapi')
            for path in paths: path.write_bytes(b'fake')
            with patch.object(platform, '_check_private_acl', return_value=True) as check:
                self.assertEqual(platform.validate(paths, sid), sid)
                check.assert_called_once()
                self.assertIn(Path(os.environ['USERPROFILE']).resolve(), check.call_args.args[0])
                with self.assertRaises(Exception):
                    platform.validate((paths[0], paths[1], paths[0]), sid)
            with patch.object(platform, '_check_private_acl', return_value=False):
                with self.assertRaises(Exception): platform.validate(paths, sid)

class CredentialBoundTests(unittest.TestCase):
    def test_existing_store_load_does_not_use_unbounded_read(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from dataclasses import asdict
        from x_context.shared_context import core
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fake.dpapi'
            record = auth.Credential('fake.apps.googleusercontent.com', 'secret', 'access', 'refresh', 1000, (auth.SCOPE,))
            path.write_bytes(core.encode({'schema':'1', 'provider':'google-drive', 'credential':asdict(record)}))
            store = auth.Store(path, unprotect=lambda value: value)
            original = Path.read_bytes
            def no_unbounded(p):
                if p == path: raise AssertionError('unbounded credential read')
                return original(p)
            with patch.object(Path, 'read_bytes', no_unbounded):
                self.assertEqual(gate.load_unexpired_token(store, now=800, lifetime=120), 'access')

class HttpExitTests(unittest.TestCase):
    def test_worker_transport_never_puts_token_in_arguments_and_rejects_write(self):
        from unittest.mock import patch
        import subprocess
        result = subprocess.CompletedProcess([], 0, stdout=b'{"user":{"permissionId":"FAKE-OWNER","me":true}}', stderr=b'')
        with patch('subprocess.run', return_value=result) as run:
            request = gate.worker_request('FAKE-ACCESS-TOKEN', folder='FAKE-FOLDER', documents={'FAKE-DOC'})
            response = request('drive','GET','about',query={'fields':'user(permissionId,me)'},timeout=3)
            self.assertTrue(response['user']['me'])
            self.assertNotIn('FAKE-ACCESS-TOKEN', repr(run.call_args.args[0]))
            with self.assertRaises(Exception):
                request('drive','POST','files',query={},body={},timeout=3)
            self.assertEqual(run.call_count, 1)

    def test_worker_timeout_blocks_without_retry(self):
        from unittest.mock import patch
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('fake', 1)) as run:
            with self.assertRaises(Exception):
                gate.worker_request('FAKE-ACCESS-TOKEN', folder='FAKE-FOLDER', documents={'FAKE-DOC'})('drive','GET','about',
                    query={'fields':'user(permissionId,me)'},timeout=1)
            self.assertEqual(run.call_count, 1)

class CallerDriftTests(unittest.TestCase):
    setUp = CallerIntegrationTests.setUp
    preflight = CallerIntegrationTests.preflight
    def test_drift_between_preflight_and_second_inspection_blocks_before_credential(self):
        from unittest.mock import patch
        from x_context.shared_context import google_reconcile as reconcile
        preparation = self.preflight()
        original = reconcile.inspect_local
        count = 0
        def drift(*args):
            nonlocal count
            result = original(*args)
            count += 1
            if count == 1:
                self.fixture.state_path.write_bytes(self.fixture.original + b' ')
            return result
        with patch.object(reconcile, 'inspect_local', side_effect=drift):
            result = gate.execute(preparation, approved_digest=preparation.digest,
                platform=self.platform, store=self.store, request_factory=self.request_factory,
                monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.store.load.assert_not_called()
        self.assertEqual(self.calls, [])

class OperatorEntryTests(unittest.TestCase):
    setUp = CallerIntegrationTests.setUp
    preflight = CallerIntegrationTests.preflight
    def test_cli_prepare_then_fake_read_reports_only_status_and_digest(self):
        import io
        from unittest.mock import patch
        args = ['--registry', str(self.fixture.state_path), '--sidecar', str(self.fixture.sidecar_path),
                '--credential', str(self.fixture.state_path.parent/'fake-credential.dpapi'),
                '--user-sid','FAKE-USER-SID','--approval-reference','FAKE-APPROVAL']
        output = io.StringIO()
        with patch.object(gate, 'WindowsPlatform', return_value=self.platform), \
             patch.object(auth, 'Store', return_value=self.store), \
             patch.object(gate, 'worker_request', side_effect=self.request_factory), \
             patch('time.monotonic', return_value=0), patch('time.time', return_value=800):
            self.assertEqual(gate.main(['prepare', *args], stdout=output), 0)
            digest = output.getvalue().strip().split()[-1]
            output = io.StringIO()
            self.assertEqual(gate.main(['execute', *args, '--approval-digest', digest], stdout=output), 0)
        printed = output.getvalue()
        self.assertTrue(printed.startswith('PASS '))
        self.assertNotIn('FAKE-OWNER', printed)
        self.assertNotIn(str(self.fixture.state_path), printed)
        self.assertNotIn('access', printed)
        self.store.save.assert_not_called()

class AdditionalFailureTests(unittest.TestCase):
    setUp = CallerIntegrationTests.setUp
    preflight = CallerIntegrationTests.preflight
    def test_expired_token_causes_no_network_and_no_save(self):
        preparation = self.preflight()
        self.store.load.return_value = auth.Credential('fake.apps.googleusercontent.com',
            'secret','access','refresh',900,(auth.SCOPE,))
        result = gate.execute(preparation, approved_digest=preparation.digest,
            platform=self.platform, store=self.store, request_factory=self.request_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(self.calls, [])
        self.store.save.assert_not_called()

    def test_owner_mismatch_stops_after_about_without_documents(self):
        preparation = self.preflight()
        def fake_factory(token, **bindings):
            def mismatch(service, method, path, **kwargs):
                self.calls.append((service, method, path))
                return {'user':{'permissionId':'FAKE-OTHER','me':True}}
            return mismatch
        result = gate.execute(preparation, approved_digest=preparation.digest,
            platform=self.platform, store=self.store, request_factory=fake_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(self.calls, [('drive','GET','about')])
        self.store.save.assert_not_called()

    def test_approval_mismatch_stops_before_credential(self):
        preparation = self.preflight()
        result = gate.execute(preparation, approved_digest='0'*64,
            platform=self.platform, store=self.store, request_factory=self.request_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.store.load.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_exit_rejects_unrelated_id_before_child_process(self):
        from unittest.mock import patch
        with patch('subprocess.run') as run:
            request = gate.worker_request('FAKE-ACCESS-TOKEN', folder='FAKE-FOLDER', documents={'FAKE-DOC'})
            with self.assertRaises(Exception):
                request('docs','GET','documents/FAKE-OTHER',query={'includeTabsContent':'true'},timeout=3)
            run.assert_not_called()

    def test_changed_dependency_binding_stops_before_credential(self):
        from unittest.mock import patch
        preparation = self.preflight()
        with patch.object(gate, '_source_binding', return_value='0'*64):
            result = gate.execute(preparation, approved_digest=preparation.digest,
                platform=self.platform, store=self.store, request_factory=self.request_factory,
                monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.store.load.assert_not_called()
        self.assertEqual(self.calls, [])

    def test_changed_interpreter_or_standard_library_binding_blocks(self):
        from unittest.mock import patch
        preparation = self.preflight()
        with patch.object(gate, '_runtime_binding', return_value='0'*64):
            result = gate.execute(preparation, approved_digest=preparation.digest,
                platform=self.platform, store=self.store, request_factory=self.request_factory,
                monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.store.load.assert_not_called()

    def test_expiry_reports_safe_explicit_stop_reason(self):
        preparation = self.preflight()
        self.store.load.return_value = auth.Credential('fake.apps.googleusercontent.com',
            'secret','access','refresh',900,(auth.SCOPE,))
        result = gate.execute(preparation, approved_digest=preparation.digest,
            platform=self.platform, store=self.store, request_factory=self.request_factory,
            monotonic=lambda: 0, wall_clock=lambda: 800)
        self.assertEqual(result.status, 'BLOCKED')
        self.assertEqual(result.reason, 'AUTH_EXPIRED_REAUTH_APPROVAL_REQUIRED')
        self.assertNotIn('access', repr(result))

class WorkerDecodeTests(unittest.TestCase):
    def test_duplicate_provider_keys_fail_closed(self):
        import io, json
        from unittest.mock import patch
        from x_context.shared_context import google_gate_r_worker as worker
        payload = json.dumps({'service':'drive','path':'about','query':{'fields':'user(permissionId,me)'},
                              'token':'FAKE-TOKEN','timeout':1}).encode()
        fake_input = Mock(buffer=io.BytesIO(payload))
        fake_output = Mock(buffer=io.BytesIO())
        response = Mock(status=200)
        response.read.return_value = b'{"user":{"me":true,"me":false,"permissionId":"FAKE-OWNER"}}'
        opener = Mock()
        opener.open.return_value.__enter__ = Mock(return_value=response)
        opener.open.return_value.__exit__ = Mock(return_value=False)
        with patch.object(worker.sys, 'stdin', fake_input), patch.object(worker.sys, 'stdout', fake_output), \
             patch.object(worker, 'build_opener', return_value=opener):
            self.assertEqual(worker.main(), 1)
        self.assertEqual(fake_output.buffer.getvalue(), b'')

class WindowsAclTests(unittest.TestCase):
    def test_real_synthetic_acl_accepts_owner_only_and_rejects_everyone(self):
        import os, tempfile, subprocess, base64, json
        from pathlib import Path
        if os.name != 'nt': self.skipTest('Windows only')
        platform = gate.WindowsPlatform()
        sid = platform.current_user()
        powershell = Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
        script = r'''$d=[Console]::In.ReadToEnd() | ConvertFrom-Json; $p=$d.path; $sid=$d.sid; $extra=$d.extra
$acl=[System.IO.File]::GetAccessControl($p)
$acl.SetAccessRuleProtection($true,$false)
$who=New-Object System.Security.Principal.SecurityIdentifier($sid)
$rule=New-Object System.Security.AccessControl.FileSystemAccessRule($who,'FullControl','Allow')
$acl.AddAccessRule($rule)
if ($extra -eq 'yes') {
  $every=New-Object System.Security.Principal.SecurityIdentifier('S-1-1-0')
  $acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($every,'Read','Allow')))
}
[System.IO.File]::SetAccessControl($p,$acl)'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fake-evidence.json'
            path.write_bytes(b'fake')
            def change(extra):
                encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
                payload = json.dumps({'path':str(path),'sid':sid,'extra':extra}).encode('utf-8')
                result = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                    input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
                if result.returncode:
                    raise RuntimeError('synthetic ACL setup failed')
            change('no')
            self.assertTrue(platform._check_private_acl([path], sid))
            change('yes')
            self.assertFalse(platform._check_private_acl([path], sid))

class PaginationBudgetTests(unittest.TestCase):
    def test_extra_pages_stop_at_drive_cap_before_dispatch(self):
        calls = []
        def request(service, method, path, **kwargs):
            calls.append(path)
            return {'user':{'permissionId':'FAKE-OWNER','me':True}}
        guard = gate.ReadOnlyHTTP(request, folder='FAKE-FOLDER', documents={'FAKE-DOC'},
                                  monotonic=lambda: 0, deadline=120)
        guard.verify_principal('FAKE-OWNER')
        guard.drive_remaining = 1
        query = {'q':"'FAKE-FOLDER' in parents and trashed = false", 'corpora':'user', 'spaces':'drive',
                 'fields':'nextPageToken,incompleteSearch,files(' + gate.api.METADATA + ')', 'pageSize':100}
        guard.request('drive','GET','files',query=query)
        with self.assertRaises(Exception):
            guard.request('drive','GET','files',query=dict(query, pageToken='FAKE-NEXT'))
        self.assertEqual(calls, ['about','files'])

class PreparationLockTests(unittest.TestCase):
    setUp = CallerIntegrationTests.setUp
    preflight = CallerIntegrationTests.preflight
    def test_cli_preparation_is_also_guarded_against_concurrent_callers(self):
        import io
        from unittest.mock import patch
        args = ['prepare', '--registry', str(self.fixture.state_path),
                '--sidecar', str(self.fixture.sidecar_path),
                '--credential', str(self.fixture.state_path.parent/'fake-credential.dpapi'),
                '--user-sid','FAKE-USER-SID','--approval-reference','FAKE-APPROVAL']
        with patch.object(gate, 'WindowsPlatform', return_value=self.platform):
            self.assertEqual(gate.main(args, stdout=io.StringIO()), 0)
        self.platform.lock.assert_called_once()
