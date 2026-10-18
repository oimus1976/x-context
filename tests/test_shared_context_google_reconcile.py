"""RCN-01..07: fake-only, never opens operator registry or Google credentials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_shared_context_google import FakeAPI, MemoryState
from test_shared_context_google_resume import MemoryJournal, incident
from x_context.shared_context import core, drive, connector as c
from x_context.shared_context import google_api as api
from x_context.shared_context import google_publish as pub
from x_context.shared_context import google_recovery as recovery
from x_context.shared_context import google_reconcile as reconcile


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.state_path = root / 'fake-publication-v1.json'
        self.sidecar_path = root / 'fake-completed-recovery.jsonl'
        self.backup_path = root / 'fake-original-backup.json'
        self.http, source_state = incident()
        self.original = core.encode(source_state.value)
        self.state_path.write_bytes(self.original)
        self.state = pub.State(self.state_path)
        self.transport = api.Transport(self.http)
        memory = MemoryJournal()
        first_plan = recovery.plan_first_create(self.transport, source_state)
        outcome = recovery.resume_first_create(
            self.transport, source_state, memory, first_plan,
            approved=True, approval_reference='FAKE-APPROVAL')
        self.assertEqual((outcome.status, outcome.writes_attempted), ('COMPLETE', 11))
        self.assertEqual(len(memory.records), 29)
        self.events = memory.records
        self.write_events(self.events)
        self.fake_effects = len(self.http.effects)
        self.assertEqual(self.fake_effects, 11)
        self.http.calls.clear()
        self.http.effects.clear()

    def write_events(self, events):
        raw = ''.join(json.dumps(row, ensure_ascii=True, sort_keys=True, allow_nan=False) + '\n'
                      for row in events).encode('ascii')
        self.sidecar_path.write_bytes(raw)

    def local(self):
        return reconcile.inspect_local(self.state, recovery.Journal(self.sidecar_path))

    def plan(self):
        return reconcile.plan_reconciliation(self.transport, self.state,
                                             recovery.Journal(self.sidecar_path),
                                             reviewed_code='FAKE-REVIEWED-CODE-HEAD')

    def apply(self, plan, **kwargs):
        return reconcile.commit_reconciliation(
            self.transport, self.state, recovery.Journal(self.sidecar_path),
            self.backup_path, plan, reviewed_code='FAKE-REVIEWED-CODE-HEAD',
            approved_backup_path=str(self.backup_path), **kwargs)

    def test_RCN01_valid_29_event_history_reconstructs_original_incident(self):
        local = self.local()
        self.assertEqual(len(local.manifest), 6)
        self.assertEqual(local.original_bytes, self.original)
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertEqual(self.state_path.read_bytes(), self.original)

    def test_RCN01_mutated_order_missing_extra_or_stopped_event_blocks(self):
        variants = [
            self.events[:-1], self.events + [dict(type='STOPPED', writes_attempted=0)],
            self.events + [self.events[-1]], self.events[:1] + self.events[2:],
            self.events[:2] + [self.events[3], self.events[2]] + self.events[4:],
        ]
        for events in variants:
            with self.subTest(size=len(events)):
                self.write_events(events)
                with self.assertRaises(core.ContextError):
                    self.local()
                self.assertEqual(self.http.calls, [])
        self.write_events(self.events)

    def test_RCN01_wrong_created_id_receipt_or_original_state_blocks(self):
        for index, key, value in ((4, 'id', 'FAKE-DUPLICATE'),
                                  (len(self.events)-1, 'fixture_sha256', '0'*64),
                                  (0, 'first_revision', 'WRONG-REVISION')):
            mutated = copy.deepcopy(self.events)
            mutated[index][key] = value
            self.write_events(mutated)
            with self.subTest(index=index), self.assertRaises(core.ContextError):
                self.local()
        self.write_events(self.events)
        # BEGIN stores canonical logical state, not original raw-byte SHA.
        # A whitespace-only change is valid local evidence, but must invalidate
        # any plan that was approved against the previous raw bytes.
        planned = self.plan()
        self.state_path.write_bytes(self.original + b' ')
        self.assertEqual(self.local().original_bytes, self.original + b' ')
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')
        self.assertFalse(self.backup_path.exists())
        self.state_path.write_bytes(self.original)

    def test_RCN02_exact_remote_six_docs_and_current_ok(self):
        planned = self.plan()
        self.assertEqual(len(planned.projected['documents']), 6)
        self.assertEqual(planned.projected['pending'], [])
        self.assertFalse(self.http.effects)
        self.assertTrue(self.http.calls)
        self.assertTrue(all(m == 'GET' for _, m, *_ in self.http.calls))
        self.assertEqual(self.state_path.read_bytes(), self.original)

    def test_RCN02_visible_inventory_permissions_body_and_revision_fail_closed(self):
        role = drive.PREFIX + 'SYN-XCTX-P001'
        identity = self.events[-1]['manifest'][role]['id']
        candidates = [('shared', lambda: self.http.files[identity].__setitem__('shared', True)),
                      ('revision', lambda: self.http.rev.__setitem__(identity, 'FAKE-OTHER-REV')),
                      ('body', lambda: self.http.text.__setitem__(identity, 'FAKE-TAMPERED\n')),
                      ('incomplete', lambda: setattr(self.http, 'incomplete', True))]
        for kind, change in candidates:
            original_file = copy.deepcopy(self.http.files[identity])
            original_body = self.http.text[identity]
            original_revision = self.http.rev[identity]
            try:
                change()
                with self.subTest(kind=kind), self.assertRaises(core.ContextError):
                    self.plan()
                self.assertEqual(self.http.effects, [])
            finally:
                self.http.files[identity] = original_file
                self.http.text[identity] = original_body
                self.http.rev[identity] = original_revision
                self.http.incomplete = False

    def test_RCN03_deterministic_projection_and_raw_bytes_binding(self):
        one, two = self.plan(), self.plan()
        self.assertEqual(one.digest, two.digest)
        self.assertEqual(one.projected['folder'], self.state.load()['folder'])
        self.assertEqual(one.projected['owner'], self.state.load()['owner'])
        pub.validate_state(one.projected)
        before = self.sidecar_path.read_bytes()
        self.sidecar_path.write_bytes(before + b' ')
        with self.assertRaises(core.ContextError):
            self.plan()
        self.sidecar_path.write_bytes(before)

    def test_RCN04_missing_approval_does_not_create_backup_or_commit(self):
        planned = self.plan()
        self.http.calls.clear()
        outcome = self.apply(planned, approved=False, read_authorized=False)
        self.assertEqual(outcome, 'BLOCKED')
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertFalse(self.backup_path.exists())

    def test_RCN04_exclusive_exact_backup_and_single_atomic_commit(self):
        planned = self.plan()
        sidecar_before = self.sidecar_path.read_bytes()
        self.http.calls.clear()
        outcome = self.apply(planned, approved=True, read_authorized=True,
                             approval_digest=planned.digest)
        self.assertEqual(outcome, 'RECONCILED')
        self.assertEqual(self.backup_path.read_bytes(), self.original)
        self.assertEqual(self.sidecar_path.read_bytes(), sidecar_before)
        self.assertEqual(self.state.load(), planned.projected)
        self.assertEqual(self.http.effects, [])
        with self.assertRaises(core.ContextError):
            pub.AppBackend(self.transport, pub.State(self.backup_path))
        self.assertNotEqual(self.apply(planned, approved=True, read_authorized=True,
                                       approval_digest=planned.digest), 'RECONCILED')

    def test_RCN04_wrong_explicit_backup_approval_path_blocks(self):
        planned = self.plan()
        result = reconcile.commit_reconciliation(
            self.transport, self.state, recovery.Journal(self.sidecar_path),
            self.backup_path, planned, reviewed_code='FAKE-REVIEWED-CODE-HEAD',
            approved=True, read_authorized=True, approval_digest=planned.digest,
            approved_backup_path=str(self.backup_path) + '-NOT-APPROVED')
        self.assertEqual(result, 'BLOCKED')
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)

    def test_RCN04_preexisting_claim_or_changed_plan_refuses_commit(self):
        planned = self.plan()
        self.backup_path.write_bytes(b'')
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.backup_path.unlink()
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest='0'*64), 'BLOCKED')

    def test_RCN05_failure_after_claim_requires_inspection_without_retry(self):
        planned = self.plan()
        with patch.object(pub.State, 'save', side_effect=OSError('FAKE-SECRET-PATH')):
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest),
                             'UNCERTAIN_REQUIRES_INSPECTION')
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertTrue(self.backup_path.exists())
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')

    def test_RCN06_normal_backend_remains_blocked_until_complete_projection(self):
        with self.assertRaises(core.ContextError):
            pub.AppBackend(self.transport, self.state)
        planned = self.plan()
        # Simulate committed synthetic state separately; never write owner files.
        ghost = MemoryState()
        ghost.value = copy.deepcopy(planned.projected)
        backend = pub.AppBackend(self.transport, ghost)
        self.assertEqual(drive.preview(backend, ghost.value['folder'],
                                       core.load_fixture('baseline')).folder,
                         ghost.value['folder'])
        self.assertEqual(self.http.effects, [])


    def test_RCN01_duplicate_manifest_and_wrong_c001_mapping_block(self):
        role = recovery.FIRST_ROLE
        bad = copy.deepcopy(self.events)
        bad[-1]['manifest'][role]['id'] = 'FAKE-FORGED-ID'
        self.write_events(bad)
        with self.assertRaises(core.ContextError):
            self.local()
        self.write_events(self.events)
        self.state_path.write_bytes(self.original.replace(b'CREATED_EMPTY_UNVERIFIED',
                                                          b'CONTENT_ATTEMPTED'))
        with self.assertRaises(core.ContextError):
            self.local()
        self.state_path.write_bytes(self.original)

    def test_RCN02_extra_visible_child_and_concurrent_snapshot_block(self):
        fake_id = 'FAKE-UNREGISTERED'
        self.http.files[fake_id] = dict(copy.deepcopy(self.http.files[next(
            identity for identity, item in self.http.files.items()
            if item['name'] == drive.CURRENT)]), id=fake_id)
        self.http.text[fake_id] = '\n'
        self.http.rev[fake_id] = 'REV-NEW'
        with self.assertRaises(core.ContextError):
            self.plan()
        del self.http.files[fake_id], self.http.text[fake_id], self.http.rev[fake_id]
        original = self.transport.children
        count = 0
        role = drive.PREFIX + 'SYN-XCTX-P002'
        identity = self.events[-1]['manifest'][role]['id']
        def racing(folder):
            nonlocal count
            result = original(folder)
            count += 1
            if count == 2:
                self.http.rev[identity] += '-RACE'
            return result
        with patch.object(self.transport, 'children', side_effect=racing):
            with self.assertRaises(core.ContextError):
                self.plan()
        self.assertEqual(self.http.effects, [])

    def test_RCN03_remote_revision_change_invalidates_prior_approved_plan(self):
        planned = self.plan()
        role = drive.PREFIX + 'SYN-XCTX-C002'
        identity = planned.projected['documents'][role]
        self.http.rev[identity] += '-EDITED'
        result = self.apply(planned, approved=True, read_authorized=True,
                            approval_digest=planned.digest)
        self.assertEqual(result, 'BLOCKED')
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)

    def test_RCN05_after_commit_uncertainty_never_claims_old_state(self):
        planned = self.plan()
        original_save = self.state.save
        def save_then_ambiguous(new_value):
            original_save(new_value)
            raise RuntimeError('FAKE-SECRET after atomic replace')
        with patch.object(self.state, 'save', side_effect=save_then_ambiguous):
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest),
                             'UNCERTAIN_REQUIRES_INSPECTION')
        self.assertEqual(self.state.load(), planned.projected)
        self.assertEqual(self.backup_path.read_bytes(), self.original)
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')

    def test_RCN05_changed_remote_snapshot_after_backup_never_commits(self):
        planned = self.plan()
        original_plan = reconcile.plan_reconciliation
        count = 0
        def stop_after_claim(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise core.ContextError('FAKE stale plan')
            return original_plan(*args, **kwargs)
        with patch.object(reconcile, 'plan_reconciliation', side_effect=stop_after_claim):
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest),
                             'UNCERTAIN_REQUIRES_INSPECTION')
        self.assertTrue(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.http.effects, [])

    def test_RCN05_backup_fsync_failure_preserves_old_registry_and_claim(self):
        planned = self.plan()
        with patch.object(reconcile.os, 'fsync',
                          side_effect=OSError('FAKE-SECRET fsync error')):
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest),
                             'UNCERTAIN_REQUIRES_INSPECTION')
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertTrue(self.backup_path.exists())
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')

    def test_RCN07_redacted_errors_and_no_authentication_or_network(self):
        from x_context.shared_context import google_auth as auth
        sentinel = 'FAKE-SECRET-CREDENTIAL-DO-NOT-LOG'
        with patch.object(auth.Store, 'load', side_effect=AssertionError('auth forbidden')), \
             patch.object(auth.Provider, 'access_token', side_effect=AssertionError('refresh forbidden')), \
             patch.object(auth, 'token_request', side_effect=AssertionError('token forbidden')):
            local = self.local()
            self.assertEqual(len(local.manifest), 6)
            planned = self.plan()
            self.assertTrue(planned.digest)
        with patch.object(self.transport, 'metadata',
                          side_effect=RuntimeError(sentinel)):
            try:
                self.plan()
            except core.ContextError as error:
                self.assertNotIn(sentinel, str(error))
                self.assertNotIn(sentinel, repr(error))
            else:
                self.fail('hostile provider error must fail closed')
        self.assertNotIn(sentinel, repr(planned))
        self.assertNotIn(self.original.decode('utf-8'), repr(planned))
        self.assertEqual(self.http.effects, [])


if __name__ == '__main__':
    unittest.main()
