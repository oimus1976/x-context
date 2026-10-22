"""First-create recovery design prerequisites; fake provider only."""
import copy
import unittest
from unittest.mock import patch

from test_shared_context_google import FakeAPI, MemoryState
from x_context.shared_context import core, drive, connector as c
from x_context.shared_context import google_api as api, google_publish as pub, google_recovery as recovery


class RecoveryInspectionTests(unittest.TestCase):
    def setUp(self):
        self.http, self.state = FakeAPI(), MemoryState()
        self.transport = api.Transport(self.http)
        backend = pub.AppBackend(self.transport, self.state)
        self.folder = backend.initialize()
        records = core.load_fixture('baseline')
        plan = drive.preview(backend, self.folder, records)
        with patch.object(api, 'parse_document', side_effect=core.ContextError('UNSUPPORTED_NATIVE_TEXT')):
            self.assertEqual(pub.publish(backend, records, plan), drive.Result('PARTIAL_UNPUBLISHED', 1))
        self.identity = self.state.value['documents'][recovery.FIRST_ROLE]
        self.http.calls.clear()
        self.http.effects.clear()

    def inspect(self):
        before = copy.deepcopy(self.state.value)
        with patch.object(self.state, 'save', side_effect=AssertionError('must stay read-only')):
            try:
                return recovery.inspect_first_create(self.transport, self.state)
            finally:
                self.assertEqual(self.state.value, before)
                self.assertEqual(self.http.effects, [])
                self.assertTrue(all(method == 'GET' for _, method, *_ in self.http.calls))

    def test_exact_pending_id_private_parent_empty_revision_receipt_only(self):
        receipt = self.inspect()
        self.assertEqual(receipt.document.id, self.identity)
        self.assertEqual(receipt.document.parents, (self.folder,))
        self.assertEqual(receipt.document.body, '')
        self.assertEqual(receipt.state_sha256, core.digest(core.encode(self.state.value)))
        self.assertNotIn(self.identity, repr(receipt))
        self.assertNotIn(self.folder, repr(receipt))
        with self.assertRaisesRegex(core.ContextError, 'GOOGLE_EFFECT_REQUIRES_INSPECTION'):
            pub.AppBackend(self.transport, self.state)
        # Even deleting pending would not make ordinary preview accept no CURRENT.
        # Use a separate fake copy to prove that barrier, never edit actual state.
        separate = MemoryState()
        separate.value = dict(copy.deepcopy(self.state.value), pending=[])
        with self.assertRaises(core.ContextError):
            drive.preview(pub.AppBackend(self.transport, separate), self.folder, core.load_fixture('baseline'))

    def test_journal_unknown_order_ambiguous_or_content_attempt_blocks(self):
        good = copy.deepcopy(self.state.value)
        variants = [[], [('', 'CREATE_ATTEMPT')], list(reversed(good['pending'])),
                    [('', 'CREATE_ATTEMPT'), ('OTHER', 'CREATED_EMPTY_UNVERIFIED')],
                    good['pending'] + [(self.identity, 'CONTENT_ATTEMPTED')],
                    good['pending'] * 2]
        for pending in variants:
            self.state.value = dict(copy.deepcopy(good), pending=pending)
            self.http.calls.clear()
            with self.subTest(pending=pending), self.assertRaisesRegex(core.ContextError, '^GOOGLE_RECOVERY_INSPECTION_BLOCKED$'):
                self.inspect()
            self.assertEqual(self.http.calls, [])
        self.state.value = good

    def test_wrong_ids_namespace_role_parent_owner_privacy_and_content_block(self):
        for file_id in (self.folder, self.identity):
            original = copy.deepcopy(self.http.files[file_id])
            cases = [('id', 'OTHER'), ('shared', True), ('trashed', True), ('isAppAuthorized', False),
                     ('parents', ['OTHER']), ('appProperties', {}), ('name', 'same-title-is-not-authority'),
                     ('appProperties', dict(original['appProperties'], namespace='OTHER')),
                     ('appProperties', dict(original['appProperties'], role='OTHER'))]
            for key, value in cases:
                self.http.files[file_id] = dict(copy.deepcopy(original), **{key: value})
                with self.subTest(file_id=file_id, key=key), self.assertRaises(core.ContextError): self.inspect()
            self.http.files[file_id] = original
        self.http.owner = 'OTHER'
        with self.assertRaises(core.ContextError): self.inspect()
        self.http.owner = 'FAKE-OWNER'
        for text in ('not empty\n', '\n\n'):
            self.http.text[self.identity] = text
            with self.subTest(text=text), self.assertRaises(core.ContextError): self.inspect()
        self.http.text[self.identity] = '\n'
        self.http.rev[self.identity] = ''
        with self.assertRaises(core.ContextError): self.inspect()

    def test_unknown_child_current_missing_page_and_changed_snapshot_block(self):
        self.http.incomplete = True
        with self.assertRaises(core.ContextError): self.inspect()
        self.http.incomplete = False
        unknown = dict(self.http.files[self.identity], id='UNKNOWN', name=drive.CURRENT)
        self.http.files['UNKNOWN'] = unknown
        self.http.text['UNKNOWN'], self.http.rev['UNKNOWN'] = '\n', 'R'
        with self.assertRaises(core.ContextError): self.inspect()
        del self.http.files['UNKNOWN']
        original = self.transport.children
        count = 0
        def changed(folder):
            nonlocal count
            result = original(folder)
            count += 1
            if count == 1: self.http.rev[self.identity] += '-CHANGED'
            return result
        with patch.object(self.transport, 'children', side_effect=changed):
            with self.assertRaises(core.ContextError): self.inspect()

    def test_local_concurrent_change_and_wrong_registry_binding_block(self):
        original = copy.deepcopy(self.state.value)
        other = copy.deepcopy(original)
        other['namespace'] = 'CHANGED'
        with patch.object(self.state, 'load', side_effect=[original, other]):
            with self.assertRaises(core.ContextError): self.inspect()
        for docs in ({recovery.FIRST_ROLE: 'OTHER'}, {drive.CURRENT: self.identity}, {},
                     {recovery.FIRST_ROLE: self.identity, drive.CURRENT: 'OTHER'}):
            self.state.value = dict(copy.deepcopy(original), documents=docs)
            with self.subTest(docs=docs), self.assertRaises(core.ContextError): self.inspect()
