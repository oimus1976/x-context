"""RCN-01..07: fake-only, never opens operator registry or Google credentials."""
import copy
from contextlib import ExitStack
import json
import os
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
from x_context.shared_context import google_auth as auth


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).resolve()
        self.state_path = root / 'fake-publication-v1.json'
        self.sidecar_path = root / 'fake-completed-recovery.jsonl'
        self.backup_path = self.state_path.with_name(
            self.state_path.stem + '.issue65-original-claim.json')
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

    def test_RCN03_module_source_change_invalidates_approved_digest(self):
        planned = self.plan()
        with patch.object(reconcile, '_module_sha', return_value='0'*64):
            self.assertNotEqual(self.plan().digest, planned.digest)
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest), 'BLOCKED')
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)

    def test_RCN04_missing_approval_does_not_create_backup_or_commit(self):
        planned = self.plan()
        self.http.calls.clear()
        outcome = self.apply(planned, approved=False, read_authorized=False)
        self.assertEqual(outcome, 'BLOCKED')
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertFalse(self.backup_path.exists())

    def test_RCN04_alternate_backup_name_cannot_evict_existing_claim(self):
        planned = self.plan()
        self.backup_path.write_bytes(b'FAKE previous ambiguous claim')
        alternate = self.state_path.with_name('FAKE-ALTERNATE-BACKUP.json')
        result = reconcile.commit_reconciliation(
            self.transport, self.state, recovery.Journal(self.sidecar_path),
            alternate, planned, reviewed_code='FAKE-REVIEWED-CODE-HEAD',
            approved=True, read_authorized=True, approval_digest=planned.digest,
            approved_backup_path=str(alternate))
        self.assertEqual(result, 'BLOCKED')
        self.assertFalse(alternate.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)

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
        preserved = tuple(path.read_bytes() for path in
                          (self.state_path, self.backup_path, self.sidecar_path))
        self.http.calls.clear()
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')
        self.assertEqual(self.http.calls, [])
        self.assertEqual(tuple(path.read_bytes() for path in
                               (self.state_path, self.backup_path, self.sidecar_path)), preserved)

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

    def test_RCN07_guard_rejects_unsafe_paths_without_creating_files(self):
        root = Path(self.temp.name).resolve()
        for name in ('CON.json', 'COM1.json', 'bad?name.json', 'bad|name.json',
                     'alias. /safe.json', 'space /safe.json',
                     'record.json:stream', 'NUL.json', '../escape.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                reconcile._safe_path(root / name, suffix='.json')
        self.assertEqual(self.state_path.read_bytes(), self.original)

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

    def test_F1_forged_journal_events_cannot_replace_captured_bytes(self):
        planned = self.plan()
        valid_events = copy.deepcopy(self.events)
        class ForgedJournal(recovery.Journal):
            def load(self):
                return valid_events
        forged = ForgedJournal(self.sidecar_path)
        unrelated = b'{"type": "UNRELATED"}\n' * 29
        self.sidecar_path.write_bytes(unrelated)
        self.http.calls.clear()
        with patch.object(self.state, 'save') as save:
            with self.assertRaises(core.ContextError):
                reconcile.plan_reconciliation(self.transport, self.state, forged,
                                              reviewed_code='FAKE-REVIEWED-CODE-HEAD')
            self.assertEqual(reconcile.commit_reconciliation(
                self.transport, self.state, forged, self.backup_path, planned,
                reviewed_code='FAKE-REVIEWED-CODE-HEAD', approved=True,
                read_authorized=True, approval_digest=planned.digest,
                approved_backup_path=str(self.backup_path)), 'BLOCKED')
            save.assert_not_called()
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.sidecar_path.read_bytes(), unrelated)

    def test_F1_canonical_bytes_do_not_consult_overridable_load(self):
        with patch.object(recovery.Journal, 'load',
                          side_effect=AssertionError('separate evidence forbidden')) as load:
            self.assertEqual(self.local().sidecar_bytes, self.sidecar_path.read_bytes())
            self.assertTrue(self.plan().digest)
            load.assert_not_called()

    def test_F1_sidecar_change_after_capture_blocks_before_get(self):
        original_open = Path.open
        changed = False
        altered = b'{"type": "UNRELATED"}\n' * 29
        expected_read = recovery.Journal.LIMIT + 1
        def changing_open(path, mode='r', *args, **kwargs):
            nonlocal changed
            handle = original_open(path, mode, *args, **kwargs)
            if path != self.sidecar_path or mode != 'rb' or changed:
                return handle
            class CapturedThenChanged:
                def __enter__(self): return self
                def read(self, count):
                    if count != expected_read:
                        raise AssertionError('sidecar read must be bounded')
                    return handle.read(count)
                def __exit__(self, *exc):
                    nonlocal changed
                    handle.close()
                    changed = True
                    with original_open(path, 'wb') as writer:
                        writer.write(altered)
            return CapturedThenChanged()
        with patch.object(Path, 'open', changing_open):
            with self.assertRaises(core.ContextError):
                self.plan()
        self.assertTrue(changed)
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.sidecar_path.read_bytes(), altered)

    def test_F3_writer_output_is_accepted_byte_for_byte(self):
        # Exercise the authoritative file writer, not just equivalent json.dumps.
        writer = recovery.Journal(Path(self.temp.name) / 'fake-writer.jsonl')
        writer.create(self.events[0])
        for event in self.events[1:]:
            writer.append(event)
        canonical = writer.path.read_bytes()
        self.assertEqual(canonical, self.sidecar_path.read_bytes())
        self.assertEqual(reconcile.inspect_local(self.state, writer).sidecar_bytes, canonical)

    def test_F3_equivalent_noncanonical_encodings_block_before_get(self):
        canonical = self.sidecar_path.read_bytes()
        variants = {
            'bom': b'\xef\xbb\xbf' + canonical,
            'crlf': canonical.replace(b'\n', b'\r\n'),
            'cr': canonical.replace(b'\n', b'\r'),
            'escaped-key': canonical.replace(b'"type"', b'"t\\u0079pe"', 1),
            'escaped-value': canonical.replace(b'"BEGIN"', b'"BEG\\u0049N"', 1),
            'whitespace': canonical.replace(b'": ', b'":  ', 1),
            'key-order': (json.dumps(dict(reversed(list(self.events[0].items()))),
                                     ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')
                         + canonical.split(b'\n', 1)[1],
            'compact': b'\n'.join(json.dumps(e, sort_keys=True, separators=(',', ':')).encode('ascii')
                                  for e in self.events) + b'\n',
            'trailing-space': canonical + b' ',
            'blank-line': canonical + b'\n',
            'missing-final-lf': canonical[:-1],
        }
        for name, raw in variants.items():
            with self.subTest(encoding=name):
                self.assertNotEqual(raw, canonical)
                self.sidecar_path.write_bytes(raw)
                self.http.calls.clear()
                with self.assertRaises(core.ContextError):
                    self.plan()
                self.assertEqual(self.http.calls, [])
                self.assertEqual(self.http.effects, [])
                self.assertFalse(self.backup_path.exists())
                self.assertEqual(self.state_path.read_bytes(), self.original)
        self.sidecar_path.write_bytes(canonical)

    def test_F1_F6_malformed_unknown_duplicate_and_oversize_sidecar_blocks(self):
        canonical = self.sidecar_path.read_bytes()
        unknown = copy.deepcopy(self.events)
        unknown[3]['type'] = 'UNKNOWN'
        self.write_events(unknown)
        unknown_bytes = self.sidecar_path.read_bytes()
        variants = [b'{broken}\n', canonical + b'{}\n', unknown_bytes,
                    canonical.replace(b'"type": "BEGIN"', b'"type": "BEGIN", "type": "BEGIN"', 1),
                    canonical.replace(b'"type": "BEGIN"', b'"type": NaN', 1),
                    b' ' * (recovery.Journal.LIMIT + 1)]
        for raw in variants:
            with self.subTest(size=len(raw)):
                self.sidecar_path.write_bytes(raw)
                self.http.calls.clear()
                with self.assertRaises(core.ContextError):
                    self.plan()
                self.assertEqual(self.http.calls, [])
                self.assertEqual(self.http.effects, [])
                self.assertFalse(self.backup_path.exists())
        self.sidecar_path.write_bytes(canonical)

    def test_F7_claim_open_and_status_inspection_failure_returns_safe_status(self):
        planned = self.plan()
        original_exists, original_open = Path.exists, Path.open
        exists_calls = 0
        def failed_status(path):
            nonlocal exists_calls
            if path == self.backup_path:
                exists_calls += 1
                if exists_calls > 1:
                    raise PermissionError('FAKE-PRIVATE-PATH-AND-ID')
            return original_exists(path)
        def failed_open(path, mode='r', *args, **kwargs):
            if path == self.backup_path and mode == 'xb':
                # A failed open is not proof that no claim could exist.
                raise PermissionError('FAKE-PRIVATE-PATH-AND-ID')
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'exists', failed_status), patch.object(Path, 'open', failed_open):
            outcome = self.apply(planned, approved=True, read_authorized=True,
                                 approval_digest=planned.digest)
        self.assertEqual(outcome, 'UNCERTAIN_REQUIRES_INSPECTION')
        self.assertEqual(exists_calls, 1)
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.sidecar_path.read_bytes(), self.local().sidecar_bytes)
        self.assertEqual(self.http.effects, [])

    def test_F6_duplicate_created_id_colliding_with_c001_blocks_before_get(self):
        duplicate = copy.deepcopy(self.events)
        created = next(row for row in duplicate if row['type'] == 'CREATED')
        created['id'] = duplicate[-1]['manifest'][recovery.FIRST_ROLE]['id']
        self.write_events(duplicate)
        with self.assertRaises(core.ContextError):
            self.plan()
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.http.effects, [])
        self.assertFalse(self.backup_path.exists())

    def test_F6_folder_and_document_metadata_mismatch_blocks_without_backup(self):
        planned = self.plan()
        targets = [planned.projected['folder'], planned.projected['documents'][recovery.FIRST_ROLE]]
        mutations = [('appProperties', {}), ('parents', ['FAKE-WRONG-PARENT']),
                     ('mimeType', 'application/octet-stream'), ('isAppAuthorized', False)]
        for identity in targets:
            for key, value in mutations:
                before = copy.deepcopy(self.http.files[identity])
                with self.subTest(target=identity, field=key):
                    self.http.files[identity][key] = value
                    self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                                approval_digest=planned.digest), 'BLOCKED')
                    self.assertFalse(self.backup_path.exists())
                    self.assertEqual(self.state_path.read_bytes(), self.original)
                    self.assertEqual(self.http.effects, [])
                self.http.files[identity] = before
        request = self.http.request
        for identity in targets:
            def wrong_owner(service, method, path, **kwargs):
                if path == 'files/' + identity + '/permissions':
                    return {'permissions': [{'id': 'FAKE-WRONG-OWNER', 'type': 'user', 'role': 'owner'}]}
                return request(service, method, path, **kwargs)
            with self.subTest(owner=identity), patch.object(self.http, 'request', side_effect=wrong_owner):
                self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                            approval_digest=planned.digest), 'BLOCKED')
                self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.http.effects, [])

    def test_F6_missing_child_and_current_link_tampering_block(self):
        planned = self.plan()
        identity = planned.projected['documents'][recovery.FIRST_ROLE]
        current = planned.projected['documents'][drive.CURRENT]
        request = self.http.request
        def missing_child(service, method, path, **kwargs):
            result = request(service, method, path, **kwargs)
            if service == 'drive' and path == 'files':
                result['files'] = [item for item in result['files'] if item['id'] != identity]
            return result
        with patch.object(self.http, 'request', side_effect=missing_child):
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest), 'BLOCKED')
        before = self.http.text[current]
        self.assertIn('/' + identity + '/edit', before)
        self.http.text[current] = before.replace('/' + identity + '/edit', '/FAKE-WRONG-LINK/edit')
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')
        self.assertFalse(self.backup_path.exists())
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.http.effects, [])

    def test_F6_local_and_read_paths_have_true_no_auth_network_or_write_tripwires(self):
        import socket
        import urllib.request
        from x_context import credential_lifecycle, x_api
        blocked = []
        def tripwire(*args, **kwargs):
            blocked.append('forbidden capability')
            raise AssertionError('FAKE forbidden capability')
        request = self.http.request
        def read_only(service, method, path, **kwargs):
            if method != 'GET':
                return tripwire()
            return request(service, method, path, **kwargs)
        with ExitStack() as stack:
            for target, name in [(auth.Store, 'load'), (auth.Store, 'save'),
                                 (auth.Provider, 'access_token'), (auth, 'token_request'),
                                 (auth, '_dpapi_protect'), (auth, '_dpapi_unprotect'),
                                 (credential_lifecycle.DPAPIFileCredentialStore, 'load'),
                                 (socket, 'socket'), (socket, 'create_connection'),
                                 (urllib.request, 'urlopen'), (api, 'build_opener'),
                                 (api.HTTP, 'request'), (x_api, 'lookup_post'),
                                 (pub, 'publish')]:
                stack.enter_context(patch.object(target, name, side_effect=tripwire))
            stack.enter_context(patch.object(self.http, 'request', side_effect=read_only))
            self.http.calls.clear()
            self.assertEqual(len(self.local().manifest), 6)
            self.assertEqual(self.http.calls, [])
            planned = self.plan()
            self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                        approval_digest=planned.digest), 'RECONCILED')
        self.assertEqual(blocked, [])
        self.assertEqual(self.http.effects, [])
        self.assertTrue(all(row[1] == 'GET' for row in self.http.calls))

    def test_F6_backup_open_fsync_readback_replace_and_postread_failures_stop(self):
        planned = self.plan()
        sidecar = self.sidecar_path.read_bytes()
        original_open, original_read = Path.open, Path.read_bytes
        original_fsync, original_replace = os.fsync, os.replace
        for boundary in ('open-after-claim', 'backup-write', 'backup-flush', 'backup-fsync',
                         'backup-readback', 'state-fsync', 'replace-before',
                         'replace-after', 'post-replace-readback'):
            self.state_path.write_bytes(self.original)
            if self.backup_path.exists():
                self.backup_path.unlink()  # Only reset this test's disposable fake incident.
            fsync_calls = 0
            replaced = False
            def failed_open(path, mode='r', *args, **kwargs):
                handle = original_open(path, mode, *args, **kwargs)
                if path != self.backup_path or mode != 'xb':
                    return handle
                if boundary == 'open-after-claim':
                    handle.close()
                    raise PermissionError('FAKE-private claim result unknown')
                class BackupHandle:
                    def __enter__(self): return self
                    def __exit__(self, *exc): handle.close()
                    def write(self, data):
                        if boundary == 'backup-write':
                            raise OSError('FAKE-private write')
                        return handle.write(data)
                    def flush(self):
                        if boundary == 'backup-flush':
                            raise OSError('FAKE-private flush')
                        return handle.flush()
                    def fileno(self): return handle.fileno()
                return BackupHandle()
            def failed_fsync(fd):
                nonlocal fsync_calls
                fsync_calls += 1
                if (boundary == 'backup-fsync' and fsync_calls == 1
                        or boundary == 'state-fsync' and fsync_calls == 2):
                    raise OSError('FAKE-private fsync')
                return original_fsync(fd)
            def failed_replace(source, destination):
                nonlocal replaced
                if boundary == 'replace-before':
                    raise OSError('FAKE-private replace')
                result = original_replace(source, destination)
                replaced = True
                if boundary == 'replace-after':
                    raise OSError('FAKE-private post-replace')
                return result
            def failed_read(path):
                if boundary == 'backup-readback' and path == self.backup_path:
                    return b'FAKE-CORRUPT-READBACK'
                if boundary == 'post-replace-readback' and replaced and path == self.state_path:
                    raise PermissionError('FAKE-private readback')
                return original_read(path)
            with self.subTest(boundary=boundary), patch.object(Path, 'open', failed_open), \
                 patch.object(Path, 'read_bytes', failed_read), \
                 patch.object(os, 'fsync', failed_fsync), patch.object(os, 'replace', failed_replace):
                result = self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest)
                self.assertEqual(result, 'UNCERTAIN_REQUIRES_INSPECTION')
            self.assertTrue(self.backup_path.exists())
            self.assertIn(self.state_path.read_bytes(), (self.original, core.encode(planned.projected)))
            preserved = tuple(path.read_bytes() for path in
                              (self.state_path, self.backup_path, self.sidecar_path))
            self.http.calls.clear()
            with patch.object(self.state, 'save') as save:
                self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                            approval_digest=planned.digest), 'BLOCKED')
                save.assert_not_called()
            self.assertEqual(self.http.calls, [])
            self.assertEqual(tuple(path.read_bytes() for path in
                                   (self.state_path, self.backup_path, self.sidecar_path)), preserved)
            self.assertEqual(self.sidecar_path.read_bytes(), sidecar)
            self.assertEqual(self.http.effects, [])

    def test_F6_keyboard_interrupt_retains_claim_and_exact_reentry_block(self):
        planned = self.plan()
        sidecar = self.sidecar_path.read_bytes()
        with patch.object(self.state, 'save', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.apply(planned, approved=True, read_authorized=True,
                           approval_digest=planned.digest)
        self.assertEqual(self.backup_path.read_bytes(), self.original)
        self.assertEqual(self.state_path.read_bytes(), self.original)
        self.assertEqual(self.sidecar_path.read_bytes(), sidecar)
        self.http.calls.clear()
        self.assertEqual(self.apply(planned, approved=True, read_authorized=True,
                                    approval_digest=planned.digest), 'BLOCKED')
        self.assertEqual(self.http.calls, [])
        self.assertEqual(self.backup_path.read_bytes(), self.original)
        self.assertEqual(self.http.effects, [])


if __name__ == '__main__':
    unittest.main()
