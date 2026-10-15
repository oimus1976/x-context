"""REC-01..07: one incident, fake Google t.0, no actual credentials/state."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_shared_context_google import FakeAPI, MemoryState
from x_context.shared_context import core, drive, connector as c
from x_context.shared_context import google_api as api, google_publish as pub, google_recovery as recovery


class MemoryJournal:
    def __init__(self): self.records = None
    def load(self): return copy.deepcopy(self.records)
    def create(self, header):
        if self.records is not None: raise core.ContextError('JOURNAL_EXISTS')
        self.records = [copy.deepcopy(header)]
    def append(self, event):
        self.records.append(copy.deepcopy(event))


def incident():
    http, state = FakeAPI(), MemoryState()
    backend = pub.AppBackend(api.Transport(http), state)
    folder = backend.initialize()
    records = core.load_fixture('baseline')
    plan = drive.preview(backend, folder, records)
    with patch.object(api, 'parse_document', side_effect=core.ContextError('UNSUPPORTED_NATIVE_TEXT')):
        assert pub.publish(backend, records, plan).status == 'PARTIAL_UNPUBLISHED'
    http.calls.clear(); http.effects.clear()
    return http, state


class ResumeTests(unittest.TestCase):
    def prepare(self):
        http, state = incident()
        transport = api.Transport(http)
        journal = MemoryJournal()
        plan = recovery.plan_first_create(transport, state)
        return http, state, transport, journal, plan

    def run_resume(self, transport, state, journal, plan, approved=True):
        return recovery.resume_first_create(transport, state, journal, plan,
                                            approved=approved, approval_reference='FAKE-OWNER-APPROVAL')

    def test_REC01_owner_gate_before_any_access(self):
        with patch.object(recovery, 'inspect_first_create', side_effect=AssertionError('no inspection')):
            for approved in (False, None, 1, 'yes'):
                result = self.run_resume(None, None, None, None, approved)
                self.assertEqual(result, drive.Result('BLOCKED', 0))

    def test_REC02030406_same_id_order_conditional_history_and_complete(self):
        http, state, transport, journal, plan = self.prepare()
        original = copy.deepcopy(state.value)
        existing = state.value['documents'][recovery.FIRST_ROLE]
        request = http.request
        awaiting_created = []
        def checked(service, method, path, **kw):
            if awaiting_created:
                returned_id = awaiting_created.pop()
                self.assertEqual(journal.records[-1]['type'], 'CREATED')
                self.assertEqual(journal.records[-1]['id'], returned_id)
            if method == 'POST':
                self.assertEqual(journal.records[-1]['type'], 'INTENT')
                if service == 'drive' and kw['body']['name'] == drive.CURRENT:
                    self.assertEqual(sum(http.text[i] != '\n' for i in http.files if i != state.value['folder']), 5)
                if service == 'docs':
                    body = kw['body']
                    self.assertIn('requiredRevisionId', body['writeControl'])
                    self.assertEqual(body['requests'][-1]['insertText']['location']['tabId'], 't.0')
            value = request(service, method, path, **kw)
            if service == 'drive' and method == 'POST': awaiting_created.append(value['id'])
            return value
        http.request = checked
        with patch.object(state, 'save', side_effect=AssertionError('registry must stay unchanged')):
            self.assertEqual(self.run_resume(transport, state, journal, plan), drive.Result('COMPLETE', 11))
        self.assertEqual(state.value, original)
        self.assertEqual(http.effects[0], ('text', existing))
        self.assertEqual(len([e for e in http.effects if e[0] == 'create']), 5)
        self.assertEqual(http.files[http.effects[-1][1]]['name'], drive.CURRENT)
        self.assertEqual(journal.records[0]['original_state'], core.decode(core.encode(original)))
        self.assertEqual(journal.records[0]['fixture_sha256'], plan.fixture_sha256)
        self.assertEqual(journal.records[-1]['type'], 'COMPLETE')
        self.assertEqual(len(journal.records[-1]['manifest']), 6)
        current = http.effects[-1][1]
        index = drive.parse_index(http.text[current][:-1])
        self.assertEqual(index['records']['SYN-XCTX-C001']['document_id'], existing)
        self.assertEqual(len(index['records']), 5)
        with self.assertRaisesRegex(core.ContextError, 'GOOGLE_EFFECT_REQUIRES_INSPECTION'):
            pub.AppBackend(transport, state)
        before = list(http.effects)
        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'BLOCKED')
        self.assertEqual(http.effects, before)

    def test_REC01_changed_plan_intent_and_incident_block(self):
        for change in ('state', 'revision', 'body', 'parent', 'owner', 'namespace', 'intent', 'approval'):
            http, state, transport, journal, plan = self.prepare()
            identity = state.value['documents'][recovery.FIRST_ROLE]
            if change == 'state': state.value['pending'].append((identity, 'CONTENT_ATTEMPTED'))
            if change == 'revision': http.rev[identity] += '-CHANGE'
            if change == 'body': http.text[identity] = 'changed\n'
            if change == 'parent': http.files[identity]['parents'] = ['OTHER']
            if change == 'owner': http.owner = 'OTHER'
            if change == 'namespace': http.files[identity]['appProperties']['namespace'] = 'OTHER'
            if change == 'intent': plan = replace(plan, fixture_sha256='0' * 64)
            result = (recovery.resume_first_create(transport, state, journal, plan, approved=True, approval_reference='bad\n')
                      if change == 'approval' else self.run_resume(transport, state, journal, plan))
            with self.subTest(change=change):
                self.assertEqual(result.status, 'BLOCKED')
                self.assertEqual(http.effects, [])

    def test_REC01_reinspect_after_durable_intent_immediately_before_first_write(self):
        http, state, transport, journal, plan = self.prepare()
        identity = state.value['documents'][recovery.FIRST_ROLE]
        append = journal.append
        def race(event):
            append(event)
            if event['type'] == 'INTENT': http.rev[identity] += '-RACE'
        journal.append = race
        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'BLOCKED')
        self.assertEqual(http.effects, [])
        self.assertEqual(journal.records[-1]['type'], 'STOPPED')

    def test_REC05_failure_before_after_every_http_request_no_retry(self):
        http, state, transport, journal, plan = self.prepare()
        http.calls.clear()
        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'COMPLETE')
        total = len(http.calls)
        for when in ('before', 'after'):
            for failure in range(1, total + 1):
                http, state, transport, journal, plan = self.prepare()
                original_state = copy.deepcopy(state.value)
                request = http.request
                count, effects_at_failure = 0, None
                def fail(service, method, path, **kw):
                    nonlocal count, effects_at_failure
                    count += 1
                    if count == failure and when == 'before':
                        effects_at_failure = list(http.effects)
                        raise RuntimeError('FAKE-SECRET request failure')
                    value = request(service, method, path, **kw)
                    if count == failure and when == 'after':
                        effects_at_failure = list(http.effects)
                        raise RuntimeError('FAKE-SECRET ambiguous response')
                    return value
                http.request = fail
                result = self.run_resume(transport, state, journal, plan)
                with self.subTest(when=when, failure=failure):
                    self.assertNotEqual(result.status, 'COMPLETE')
                    self.assertEqual(http.effects, effects_at_failure)
                    self.assertEqual(state.value, original_state)
                    self.assertEqual(count, failure)
                    if journal.records is not None:
                        self.assertNotEqual(journal.records[-1]['type'], 'COMPLETE')
                        before = list(http.effects)
                        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'BLOCKED')
                        self.assertEqual(http.effects, before)

    def test_REC0305_failure_before_after_every_journal_write_no_later_effect(self):
        http, state, transport, journal, plan = self.prepare()
        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'COMPLETE')
        total = len(journal.records)
        for when in ('before', 'after'):
            for failure in range(1, total + 1):
                http, state, transport, journal, plan = self.prepare()
                create, append = journal.create, journal.append
                count, effects_at_failure = 0, None
                def write(event):
                    nonlocal count, effects_at_failure
                    count += 1
                    if count >= failure and when == 'before':
                        if effects_at_failure is None: effects_at_failure = list(http.effects)
                        raise RuntimeError('FAKE journal failure')
                    (create if count == 1 else append)(event)
                    if count >= failure and when == 'after':
                        if effects_at_failure is None: effects_at_failure = list(http.effects)
                        raise RuntimeError('FAKE ambiguous local save')
                journal.create = write; journal.append = write
                result = self.run_resume(transport, state, journal, plan)
                with self.subTest(when=when, failure=failure):
                    self.assertNotEqual(result.status, 'COMPLETE')
                    self.assertEqual(http.effects, effects_at_failure)
                    if journal.records is not None:
                        self.assertEqual(self.run_resume(transport, state, journal, plan).status, 'BLOCKED')

    def test_REC010305_local_journal_and_registry_race_blocks_before_next_effect(self):
        for which in ('state', 'journal', 'privacy', 'body'):
            http, state, transport, journal, plan = self.prepare()
            append = journal.append
            def race(event):
                append(event)
                if event['type'] == 'VERIFIED':
                    if which == 'state': state.value['namespace'] = 'OTHER'
                    if which == 'journal': journal.records[0]['approval_reference'] = 'OTHER'
                    if which == 'privacy': http.files[state.value['folder']]['shared'] = True
                    if which == 'body': http.text[state.value['documents'][recovery.FIRST_ROLE]] += 'changed'
            journal.append = race
            result = self.run_resume(transport, state, journal, plan)
            with self.subTest(which=which):
                self.assertEqual(result.status, 'PARTIAL_UNPUBLISHED')
                self.assertEqual(len(http.effects), 1)

    def test_REC07_file_journal_exclusive_append_readback_fresh_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'fake-first-create-v1.jsonl'
            journal = recovery.Journal(path)
            self.assertIsNone(journal.load())
            journal.create({'type': 'BEGIN', 'schema': 'first-create-recovery-v1'})
            journal.append({'type': 'INTENT'})
            expected = journal.load()
            self.assertEqual(recovery.Journal(path).load(), expected)
            before = path.read_bytes()
            with self.assertRaises(core.ContextError): recovery.Journal(path).create({'type': 'OTHER'})
            self.assertEqual(path.read_bytes(), before)
            path.write_bytes(b'{broken')
            with self.assertRaises(core.ContextError): recovery.Journal(path).load()

    def test_REC07_file_registry_preserved_byte_for_byte(self):
        http, state = incident()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'fake-state.json'
            original = core.encode(state.value)
            path.write_bytes(original)
            result = self.run_resume(api.Transport(http), pub.State(path),
                                     recovery.Journal(path.with_suffix('.recovery.jsonl')),
                                     recovery.plan_first_create(api.Transport(http), pub.State(path)))
            self.assertEqual(result.status, 'COMPLETE')
            self.assertEqual(path.read_bytes(), original)


    def test_REC07_journal_unsafe_paths_corrupt_oversize_and_fsync_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for path in (Path('relative.jsonl'), root / 'credential.dpapi', root / 'registry.json'):
                with self.assertRaises(core.ContextError): recovery.Journal(path).create({'type': 'BEGIN'})
            path = root / 'fake.jsonl'
            with patch.object(Path, 'is_junction', return_value=True):
                with self.assertRaises(core.ContextError): recovery.Journal(path).create({'type': 'BEGIN'})
            self.assertFalse(path.exists())
            bounded = recovery.Journal(root / 'bounded.jsonl')
            with patch.object(recovery.Journal, 'LIMIT', 96):
                bounded.create({'type': 'BEGIN', 'pad': 'x' * 60})
                before = bounded.path.read_bytes()
                with self.assertRaises(core.ContextError): bounded.append({'type': 'INTENT'})
                self.assertEqual(bounded.path.read_bytes(), before)
            for data in (b'', b'{}', b'[]\n', b'{}\n' * 65, b'x' * (recovery.Journal.LIMIT + 1)):
                path.write_bytes(data)
                with self.subTest(size=len(data)), self.assertRaises(core.ContextError): recovery.Journal(path).load()
                self.assertEqual(path.read_bytes(), data)
            # Use another exclusively claimed fake path: never overwrite corrupt history.
            target = root / 'fsync-failure.jsonl'
            with patch.object(recovery.os, 'fsync', side_effect=OSError('FAKE persistence failure')):
                with self.assertRaises(core.ContextError): recovery.Journal(target).create({'type': 'BEGIN'})
            retained = target.read_bytes()
            with self.assertRaises(core.ContextError): recovery.Journal(target).create({'type': 'BEGIN'})
            self.assertEqual(target.read_bytes(), retained)

    def test_REC05_post_write_readback_wrong_body_and_ambiguous_create_identity(self):
        for variant in ('body', 'created_id', 'metadata'):
            http, state, transport, journal, plan = self.prepare()
            request = http.request
            def changed(service, method, path, **kw):
                value = request(service, method, path, **kw)
                if variant == 'body' and service == 'docs' and method == 'POST':
                    identity = path.split('/')[1].split(':')[0]
                    http.text[identity] = 'FAKE unexpected body\n'
                if service == 'drive' and method == 'POST':
                    if variant == 'created_id': value['id'] = state.value['documents'][recovery.FIRST_ROLE]
                    if variant == 'metadata': http.files[value['id']]['appProperties']['namespace'] = 'OTHER'
                return value
            http.request = changed
            result = self.run_resume(transport, state, journal, plan)
            with self.subTest(variant=variant):
                self.assertEqual(result.status, 'PARTIAL_UNPUBLISHED')
                self.assertEqual(len(http.effects), 1 if variant == 'body' else 2)
                self.assertEqual(journal.records[-1]['type'], 'STOPPED')
                self.assertNotIn(drive.CURRENT, [http.files[i]['name'] for op, i in http.effects])
