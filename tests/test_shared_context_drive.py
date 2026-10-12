"""Fake-boundary tests; none establish authenticated Google Drive success."""
from dataclasses import replace
import unittest

from x_context.shared_context import core, drive


class DriveTests(unittest.TestCase):
    def setUp(self):
        self.records = core.normalize(core.load_fixture('baseline'))
        self.backend = drive.FakeDrive('FICTIONAL-SANDBOX')
        self.folder = self.backend.folder_id

    def publish(self, records=None):
        try:
            plan = drive.preview(self.backend, self.folder, records or self.records)
        except core.ContextError:
            return drive.Result('BLOCKED')
        return drive.apply(self.backend, self.folder, records or self.records, plan)

    def test_AC06_preview_first_repeat_stable_ids(self):
        plan = drive.preview(self.backend, self.folder, self.records)
        self.assertEqual(self.backend.writes, [])
        self.assertEqual(drive.apply(self.backend, self.folder, self.records, plan).status, 'COMPLETE')
        docs = dict(self.backend.docs)
        self.assertEqual(len(docs), 6)
        self.backend.writes.clear()
        self.assertEqual(self.publish().status, 'COMPLETE')
        self.assertEqual(self.backend.docs, docs)
        self.assertEqual(self.backend.writes, [])

    def test_AC06_edit_only_record_and_index(self):
        self.publish()
        ids = {doc.title: doc.id for doc in self.backend.docs.values()}
        self.backend.writes.clear()
        self.publish(core.normalize(core.load_fixture('edited')))
        self.assertEqual(ids, {doc.title: doc.id for doc in self.backend.docs.values()})
        self.assertEqual(self.backend.writes, [drive.PREFIX + 'SYN-XCTX-P001', drive.CURRENT])

    def test_AC07_partial_index_last(self):
        self.backend.fail_at = 3
        result = self.publish()
        self.assertEqual(result.status, 'PARTIAL_UNPUBLISHED')
        self.assertEqual(len(self.backend.docs), 2)
        self.assertFalse(any(d.title == drive.CURRENT for d in self.backend.docs.values()))
        self.assertEqual(len(self.backend.writes), 2)
        self.assertEqual(self.publish().status, 'BLOCKED')  # no blind orphan adoption

    def test_AC07_old_index_preserved_on_failure(self):
        self.publish()
        old = self.backend.find(self.folder, drive.CURRENT)[0]
        self.backend.fail_at = len(self.backend.writes) + 2
        changed = core.normalize(core.load_fixture('withdrawn'))
        self.assertEqual(self.publish(changed).status, 'PARTIAL_UNPUBLISHED')
        self.assertEqual(self.backend.docs[old.id], old)

    def test_AC07_duplicate_and_unmanaged_documents(self):
        for variant in ['duplicate', 'marker', 'parent', 'sharing', 'title', 'url', 'mime']:
            with self.subTest(variant=variant):
                backend = drive.FakeDrive(self.folder)
                plan = drive.preview(backend, self.folder, self.records)
                drive.apply(backend, self.folder, self.records, plan)
                doc = backend.find(self.folder, drive.PREFIX + 'SYN-XCTX-P001')[0]
                if variant == 'duplicate':
                    backend.docs['FAKE-DUPLICATE'] = replace(doc, id='FAKE-DUPLICATE')
                else:
                    changes = {'marker': dict(body='unmanaged'), 'parent': dict(parent='OTHER'),
                               'sharing': dict(restricted=False), 'title': dict(title='OTHER'),
                               'url': dict(url='https://example.invalid/unsafe'),
                               'mime': dict(mime='text/plain')}[variant]
                    backend.docs[doc.id] = replace(doc, **changes)
                before = len(backend.writes)
                with self.assertRaises(core.ContextError):
                    drive.preview(backend, self.folder, self.records)
                self.assertEqual(len(backend.writes), before)

    def test_AC07_concurrent_edit_after_preview(self):
        self.publish()
        new = core.normalize(core.load_fixture('edited'))
        plan = drive.preview(self.backend, self.folder, new)
        doc = self.backend.find(self.folder, drive.PREFIX + 'SYN-XCTX-P001')[0]
        self.backend.docs[doc.id] = replace(doc, body=doc.body + '\nconcurrent synthetic edit')
        before = len(self.backend.writes)
        self.assertEqual(drive.apply(self.backend, self.folder, new, plan).status, 'BLOCKED')
        self.assertEqual(len(self.backend.writes), before)

    def test_AC07_permissions_change_after_preview(self):
        plan = drive.preview(self.backend, self.folder, self.records)
        self.backend.restricted = False
        self.assertEqual(drive.apply(self.backend, self.folder, self.records, plan).status, 'BLOCKED')
        self.assertEqual(self.backend.writes, [])

    def test_AC07_readback_mismatch(self):
        self.backend.bad_readback = True
        self.assertEqual(self.publish().status, 'PARTIAL_UNPUBLISHED')
        self.assertEqual(len(self.backend.writes), 1)
        self.assertFalse(any(d.title == drive.CURRENT for d in self.backend.docs.values()))

    def test_AC07_requires_preview_and_exact_sandbox(self):
        self.assertEqual(drive.apply(self.backend, self.folder, self.records, None).status, 'BLOCKED')
        plan = drive.preview(self.backend, self.folder, self.records)
        self.assertEqual(drive.apply(self.backend, 'OTHER', self.records, plan).status, 'BLOCKED')
        self.assertEqual(self.backend.writes, [])

    def test_AC08_withdrawal_and_current_index(self):
        self.publish()
        doc = self.backend.find(self.folder, drive.PREFIX + 'SYN-XCTX-P001')[0]
        self.publish(core.normalize(core.load_fixture('withdrawn')))
        new = self.backend.read(doc.id)
        self.assertEqual((new.id, new.url), (doc.id, doc.url))
        self.assertIn('SYNTHETIC WITHDRAWN', new.body)
        self.assertNotIn(self.records[0]['content'], new.body)
        current = drive.parse_index(self.backend.find(self.folder, drive.CURRENT)[0].body)
        self.assertNotIn('SYN-XCTX-P001', current['active_ids'])
        self.assertNotIn(doc.url, str(current['active_links']))

    def test_AC05_remote_omission_is_not_withdrawal(self):
        self.publish()
        before = dict(self.backend.docs)
        self.assertEqual(self.publish(self.records[:-1]).status, 'BLOCKED')
        self.assertEqual(before, self.backend.docs)


if __name__ == '__main__':
    unittest.main()
