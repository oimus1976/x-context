"""Issue #60 contracts against a fake transport; no cloud qualification."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_context.shared_context import core, drive, connector as c


class Transport:
    def __init__(self):
        self.root_id = 'FAKE-ROOT'
        permission = (c.Permission('user', 'owner', 'FAKE-OWNER'),)
        self.items = {
            c.SANDBOX: c.Item(c.SANDBOX, 'sandbox', (c.POC,), c.FOLDER, False, permission),
            c.SENTINEL: c.Item(c.SENTINEL, c.SENTINEL_TITLE, (c.SANDBOX,), drive.MIME,
                               False, permission, c.SENTINEL_BODY, 'FAKE-REV'),
        }
        self.calls = []
        self.complete = True
        self.fail_move = False
        self.bad_move = False
        self.root_body = '\n'
        self.crlf = False
        self.fail_replace = False

    def read(self, identity):
        item = self.items[identity]
        return replace(item, body=item.body.replace('\n', '\r\n')) if self.crlf else item

    def children(self, folder):
        return c.Inventory(tuple(i for i in self.items.values() if folder in i.parents), self.complete)

    def create_empty(self, title):
        identity = 'FAKE-DOC-' + str(len(self.items))
        self.calls.append(('create', identity))
        self.items[identity] = c.Item(identity, title, (self.root_id,), drive.MIME, False,
                                    self.items[c.SANDBOX].permissions, self.root_body, 'FAKE-REV')
        return identity

    def move(self, identity, old_parent, new_parent):
        self.calls.append(('move', identity))
        if self.fail_move:
            raise RuntimeError('FAKE sensitive exception must not leak')
        if not self.bad_move:
            self.items[identity] = replace(self.items[identity], parents=(new_parent,))

    def replace_text(self, identity, body, revision):
        self.calls.append(('text', identity))
        if self.fail_replace or self.items[identity].revision != revision:
            raise RuntimeError('FAKE revision conflict')
        self.items[identity] = replace(self.items[identity], body=body, revision=revision + '-NEXT')


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport()
        self.journal = []
        self.backend = c.Backend(self.transport, self.journal.append)
        self.records = core.normalize(core.load_fixture('baseline'))

    def publish(self, records=None):
        records = records or self.records
        try:
            plan = drive.preview(self.backend, c.SANDBOX, records)
        except core.ContextError:
            return drive.Result('BLOCKED')
        return drive.apply(self.backend, c.SANDBOX, records, plan)

    def test_CW1235_empty_move_verified_before_content_and_current_last(self):
        sentinel = self.transport.items[c.SENTINEL]
        result = self.publish()
        self.assertEqual(result, drive.Result('COMPLETE', 6))
        self.assertEqual(len(self.transport.calls), 18)
        for offset in range(0, 18, 3):
            calls = self.transport.calls[offset:offset + 3]
            self.assertEqual([v[0] for v in calls], ['create', 'move', 'text'])
            self.assertEqual(len({v[1] for v in calls}), 1)
        final_id = self.transport.calls[-1][1]
        self.assertEqual(self.transport.items[final_id].title, drive.CURRENT)
        self.assertEqual(self.transport.items[c.SENTINEL], sentinel)
        self.assertEqual(len(self.backend.list(c.SANDBOX)), 6)
        self.assertTrue(all(i.parents == (c.SANDBOX,) for i in self.transport.items.values() if i.mime == drive.MIME))
        self.assertEqual([phase for _, phase in self.journal],
                         ['CREATE_ATTEMPT', 'CREATED_EMPTY_UNVERIFIED', 'MOVE_ATTEMPTED', 'CONTENT_ATTEMPTED'] * 6)

    def test_CW5_repeat_edit_withdrawal_preserve_identity_and_unrelated_items(self):
        self.assertEqual(self.publish().status, 'COMPLETE')
        before = dict(self.transport.items)
        self.transport.calls.clear()
        self.assertEqual(self.publish().writes_attempted, 0)
        self.assertEqual(self.transport.calls, [])
        for variant in ('edited', 'withdrawn'):
            self.transport.calls.clear()
            self.assertEqual(self.publish(core.load_fixture(variant)).status, 'COMPLETE')
            changed = {key for key in before if self.transport.items[key] != before[key]}
            self.assertEqual({self.transport.items[key].title for key in changed},
                             {drive.PREFIX + 'SYN-XCTX-P001', drive.CURRENT})
            self.assertEqual([op for op, _ in self.transport.calls], ['text', 'text'])
            self.assertEqual(set(before), set(self.transport.items))
        index = drive.parse_index(next(i.body for i in self.transport.items.values() if i.title == drive.CURRENT))
        self.assertNotIn('SYN-XCTX-P001', index['active_ids'])

    def test_CW12_missing_inventory_or_permission_evidence_blocks_without_writes(self):
        for variant in ('incomplete', 'shared', 'permissions', 'group', 'wrong-owner', 'parents', 'wrong-id', 'unknown', 'duplicate'):
            with self.subTest(variant=variant):
                transport = Transport()
                folder = transport.items[c.SANDBOX]
                if variant == 'incomplete':
                    transport.complete = False
                elif variant == 'unknown':
                    transport.items['UNKNOWN'] = c.Item('UNKNOWN', 'unknown', (c.SANDBOX,), 'text/plain', False, folder.permissions)
                elif variant == 'duplicate':
                    transport.children = lambda _: c.Inventory((transport.items[c.SENTINEL],) * 2, True)
                else:
                    changes = {'shared': dict(shared=True), 'permissions': dict(permissions=None),
                               'group': dict(permissions=(c.Permission('group', 'reader', 'FAKE'),)),
                               'wrong-owner': dict(permissions=(c.Permission('user', 'owner', 'OTHER'),)),
                               'parents': dict(parents=('OTHER',)), 'wrong-id': dict(id='OTHER')}
                    target = c.SENTINEL if variant == 'wrong-owner' else c.SANDBOX
                    transport.items[target] = replace(transport.items[target], **changes[variant])
                backend = c.Backend(transport, lambda _: None)
                with self.assertRaises(core.ContextError):
                    drive.preview(backend, c.SANDBOX, self.records)
                self.assertEqual(transport.calls, [])

    def test_CW3_partial_root_failure_journal_no_content_no_retry(self):
        for variant in ('move-error', 'wrong-parent', 'nonempty-root', 'journal-error'):
            with self.subTest(variant=variant):
                transport = Transport()
                transport.fail_move = variant == 'move-error'
                transport.bad_move = variant == 'wrong-parent'
                if variant == 'nonempty-root':
                    transport.root_body = 'SYNTHETIC TEST DATA unexpected'
                def journal(entry):
                    if variant == 'journal-error' and entry[1] == 'CREATED_EMPTY_UNVERIFIED':
                        raise RuntimeError('FAKE journal failed')
                backend = c.Backend(transport, journal)
                plan = drive.preview(backend, c.SANDBOX, self.records)
                result = drive.apply(backend, c.SANDBOX, self.records, plan)
                self.assertEqual(result, drive.Result('PARTIAL_UNPUBLISHED', 1))
                self.assertNotIn('text', [op for op, _ in transport.calls])
                self.assertTrue(backend.stages)
                with self.assertRaises(core.ContextError):
                    drive.preview(backend, c.SANDBOX, self.records)
                self.assertEqual(sum(op == 'create' for op, _ in transport.calls), 1)

    def test_CW5_failed_update_preserves_old_current_and_stops(self):
        self.publish()
        before = dict(self.transport.items)
        self.transport.calls.clear()
        self.transport.fail_replace = True
        result = self.publish(core.load_fixture('edited'))
        self.assertEqual(result, drive.Result('PARTIAL_UNPUBLISHED', 1))
        self.assertEqual(before, self.transport.items)
        self.assertEqual(len(self.transport.calls), 1)

    def test_CW12_target_allowlist_and_sentinel_tampering(self):
        for folder in ('root', c.POC, 'OTHER'):
            with self.assertRaises(core.ContextError):
                drive.preview(self.backend, folder, self.records)
        plan = drive.preview(self.backend, c.SANDBOX, self.records)
        self.transport.items[c.SENTINEL] = replace(self.transport.items[c.SENTINEL], body=c.SENTINEL_BODY + '\n')
        self.assertEqual(drive.apply(self.backend, c.SANDBOX, self.records, plan).status, 'BLOCKED')
        self.assertEqual(self.transport.calls, [])

    def test_CW4_faithful_crlf_only_canonicalization(self):
        self.assertEqual(c.canonical_text('a\r\n\r\né\n'), 'a\n\né\n')
        self.assertNotEqual(c.canonical_text('é\n'), c.canonical_text('e\u0301\n'))
        for value in ('a\rb', '\ud800', 'x' * 65537, None):
            with self.assertRaises(core.ContextError):
                c.canonical_text(value)
        self.transport.crlf = True
        self.assertEqual(self.publish().status, 'COMPLETE')
        self.assertEqual(self.publish().writes_attempted, 0)

    def test_CW6_requires_verified_actual_portable_output(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(core, 'OUTPUT_ROOT', Path(tmp)):
            output = Path(tmp) / 'generated'
            core.generate(self.records, output)
            records, plan = c.prepare(self.backend, output)
            self.assertEqual(records, self.records)
            self.assertIsInstance(plan, drive.Plan)
            self.assertEqual(self.transport.calls, [])
            (output / 'records' / 'SYN-XCTX-P001.md').write_text('SYNTHETIC TEST DATA altered', encoding='utf-8')
            with self.assertRaises(core.ContextError):
                c.prepare(self.backend, output)

    def test_CW3_permission_expansion_in_root_or_after_move_never_inserts_text(self):
        for phase in ('root', 'sandbox'):
            with self.subTest(phase=phase):
                transport = Transport()
                original = transport.read
                def unsafe(identity):
                    item = original(identity)
                    if identity.startswith('FAKE-DOC') and ((phase == 'root') == (item.parents == (transport.root_id,))):
                        return replace(item, shared=True)
                    return item
                transport.read = unsafe
                backend = c.Backend(transport, lambda _: None)
                plan = drive.preview(backend, c.SANDBOX, self.records)
                self.assertEqual(drive.apply(backend, c.SANDBOX, self.records, plan).status, 'PARTIAL_UNPUBLISHED')
                self.assertNotIn('text', [op for op, _ in transport.calls])

    def test_CW3_sentinel_change_during_move_blocks_content(self):
        original = self.transport.move
        def move(identity, old, new):
            original(identity, old, new)
            self.transport.items[c.SENTINEL] = replace(self.transport.items[c.SENTINEL], body='changed')
        self.transport.move = move
        self.assertEqual(self.publish().status, 'PARTIAL_UNPUBLISHED')
        self.assertEqual([op for op, _ in self.transport.calls], ['create', 'move'])

    def test_CW5_arbitrary_marked_body_and_sentinel_update_refused(self):
        with self.assertRaises(core.ContextError):
            self.backend.create(c.SANDBOX, drive.PREFIX + 'SYN-XCTX-P001', 'SYNTHETIC TEST DATA actual content')
        with self.assertRaises(core.ContextError):
            self.backend.update(c.SENTINEL, c.SENTINEL_BODY)
        self.assertEqual(self.transport.calls, [])

    def test_CW3_no_journal_no_mutation(self):
        with self.assertRaises(core.ContextError):
            c.Backend(self.transport, None)
        self.assertEqual(self.transport.calls, [])

    def test_CW5_revision_conditional_update_conflict_does_not_write_index(self):
        self.publish()
        self.transport.calls.clear()
        original = self.transport.replace_text
        def conflict(identity, body, revision):
            self.transport.items[identity] = replace(self.transport.items[identity], revision='FAKE-CONCURRENT')
            original(identity, body, revision)
        self.transport.replace_text = conflict
        before = next(i for i in self.transport.items.values() if i.title == drive.CURRENT)
        self.assertEqual(self.publish(core.load_fixture('edited')).status, 'PARTIAL_UNPUBLISHED')
        self.assertEqual(self.transport.items[before.id], before)
        self.assertEqual(len(self.transport.calls), 1)


if __name__ == '__main__':
    unittest.main()
