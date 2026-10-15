"""One empty-C001 incident: inspect, explicitly approve, execute once, stop.

No credential loader/CLI, ordinary-publish bypass or interrupted-run recovery.
The original v1 registry remains untouched; the sidecar is operational evidence.
"""
import copy
import json
import os
from pathlib import Path
from dataclasses import dataclass, field

from . import core, drive, connector as c, google_publish as pub

FIRST_ROLE = drive.PREFIX + 'SYN-XCTX-C001'


@dataclass(frozen=True)
class Inspection:
    # IDs/revisions/state are local operational data, never normal log output.
    state_sha256: str = field(repr=False)
    folder: c.Item = field(repr=False)
    document: c.Item = field(repr=False)
    status: str = 'INSPECTED_EMPTY_FIRST_CREATE_NOT_AUTHORIZED'


def inspect_first_create(transport, state_store):
    """Recognize only the exact registered-empty-first-create interruption.

    Caller supplies an already authorized read transport; this function cannot
    load/refresh credentials or initiate any remote/local write. No title search,
    adoption, pending bypass, inferred completion or reusable write permission.
    """
    try:
        state = copy.deepcopy(pub.validate_state(state_store.load()))
        docs = state['documents']
        if set(docs) != {FIRST_ROLE}:
            raise ValueError
        identity = docs[FIRST_ROLE]
        if [tuple(e) for e in state['pending']] != [
                ('', 'CREATE_ATTEMPT'), (identity, 'CREATED_EMPTY_UNVERIFIED')]:
            raise ValueError

        def observed(file_id, role):
            metadata = transport.metadata(file_id)
            if (metadata.get('id') != file_id or metadata.get('isAppAuthorized') is not True
                    or metadata.get('appProperties') != dict(
                        x_context='synthetic_v1', namespace=state['namespace'], role=role)):
                raise ValueError
            item = transport.read(file_id)
            if item.id != file_id or c._owner(item) != state['owner']:
                raise ValueError
            return item

        def snapshot():
            folder = observed(state['folder'], 'folder')
            if (folder.title != pub.FOLDER_TITLE or folder.mime != c.FOLDER
                    or folder.parents != (state['parent'],)):
                raise ValueError
            doc = observed(identity, FIRST_ROLE)
            if (doc.title != FIRST_ROLE or doc.mime != drive.MIME
                    or doc.parents != (folder.id,) or doc.body != ''
                    or not isinstance(doc.revision, str) or not doc.revision):
                raise ValueError
            inventory = transport.children(folder.id)
            if (not isinstance(inventory, c.Inventory) or inventory.complete is not True
                    or inventory.items != (doc,)):
                raise ValueError
            return folder, doc

        before = snapshot()
        # State/remote changes during inspection invalidate the receipt.
        if snapshot() != before or pub.validate_state(state_store.load()) != state:
            raise ValueError
        return Inspection(core.digest(core.encode(state)), *before)
    except Exception:
        raise core.ContextError('GOOGLE_RECOVERY_INSPECTION_BLOCKED') from None


@dataclass(frozen=True)
class FirstCreatePlan:
    inspection: Inspection = field(repr=False)
    fixture_sha256: str


def plan_first_create(transport, state_store):
    """Read-only, baseline-only intent bound to current incident observations."""
    return FirstCreatePlan(inspect_first_create(transport, state_store),
                           core.digest(core.encode(core.normalize(core.load_fixture('baseline')))))


class Journal:
    """Exclusive first claim, bounded append-only JSONL, fsync and readback.

    Single writer, no locking/automatic reconciliation. Any existing file, even
    empty/corrupt/COMPLETE, blocks a second executor. Never truncate or replace.
    No default path: callers must explicitly select a private operational path.
    """
    LIMIT = 262144

    def __init__(self, path):
        self.path = Path(path)

    def _guard(self):
        if (not self.path.is_absolute() or self.path.suffix != '.jsonl'
                or any(p.is_symlink() or p.is_junction() for p in (self.path, *self.path.parents))):
            raise core.ContextError('GOOGLE_RECOVERY_JOURNAL_ERROR')

    def load(self):
        try:
            self._guard()
            if not self.path.exists():
                return None
            with self.path.open('rb') as handle:
                data = handle.read(self.LIMIT + 1)
            if not data or len(data) > self.LIMIT or not data.endswith(b'\n'):
                raise ValueError
            rows = [core.decode(line) for line in data.splitlines()]
            if not 1 <= len(rows) <= 64 or any(not isinstance(r, dict) or 'type' not in r for r in rows):
                raise ValueError
            return rows
        except Exception:
            raise core.ContextError('GOOGLE_RECOVERY_JOURNAL_ERROR') from None

    def _write(self, event, *, create):
        try:
            self._guard()
            before = None if create else self.load()
            if not create and (before is None or len(before) >= 64):
                raise ValueError
            data = (json.dumps(event, ensure_ascii=True, sort_keys=True, allow_nan=False) + '\n').encode('ascii')
            current_size = 0 if create else self.path.stat().st_size
            if len(data) + current_size > self.LIMIT:
                raise ValueError
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # xb is the claim: an old/partial sidecar can never be overwritten.
            with self.path.open('xb' if create else 'ab') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if self.load() != (before or []) + [core.decode(data)]:
                raise ValueError
        except Exception:
            raise core.ContextError('GOOGLE_RECOVERY_JOURNAL_ERROR') from None

    def create(self, header):
        self._write(header, create=True)

    def append(self, event):
        self._write(event, create=False)


def resume_first_create(transport, state_store, journal, plan, *, approved=False, approval_reference=''):
    """One explicit approved baseline continuation; never retry any effect.

    The caller owns human approval and an already authorized transport. Boolean
    approval is not authentication. Plans/sidecars never grant authority alone.
    Returns only safe status/counts; all IDs remain in the private sidecar.
    Normal publish remains blocked by the unchanged original pending registry,
    including after COMPLETE. No further invocation may reuse this sidecar.
    """
    attempted, events = 0, None
    try:
        if (approved is not True or not isinstance(plan, FirstCreatePlan)
                or not isinstance(approval_reference, str) or not 1 <= len(approval_reference) <= 80):
            raise ValueError
        c._identity(approval_reference)
        # Reject re-entry BEFORE any remote inspection, even after COMPLETE.
        if journal.load() is not None:
            raise ValueError
        if plan_first_create(transport, state_store) != plan:
            raise ValueError
        original = copy.deepcopy(pub.validate_state(state_store.load()))
        if core.digest(core.encode(original)) != plan.inspection.state_sha256:
            raise ValueError
        records = core.normalize(core.load_fixture('baseline'))
        events = [dict(type='BEGIN', schema='first-create-recovery-v1',
                       original_state=core.decode(core.encode(original)),
                       state_sha256=plan.inspection.state_sha256, fixture_sha256=plan.fixture_sha256,
                       approval_reference=approval_reference, first_revision=plan.inspection.document.revision)]
        journal.create(events[0])
        expected = {FIRST_ROLE: plan.inspection.document}

        def local():
            if (core.digest(core.encode(pub.validate_state(state_store.load()))) != plan.inspection.state_sha256
                    or journal.load() != events):
                raise ValueError

        def record(event):
            local()
            journal.append(event)
            events.append(event)
            local()

        def observe(identity, role):
            metadata = transport.metadata(identity)
            if (metadata.get('id') != identity or metadata.get('isAppAuthorized') is not True
                    or metadata.get('appProperties') != dict(x_context='synthetic_v1',
                       namespace=original['namespace'], role=role)):
                raise ValueError
            item = transport.read(identity)
            if (item.id != identity or c._owner(item) != original['owner']
                    or item.title != (pub.FOLDER_TITLE if role == 'folder' else role)
                    or item.parents != ((original['parent'],) if role == 'folder' else (original['folder'],))
                    or item.mime != (c.FOLDER if role == 'folder' else drive.MIME)
                    or (role != 'folder' and (not isinstance(item.revision, str) or not item.revision))):
                raise ValueError
            return item

        def preflight():
            local()
            if observe(original['folder'], 'folder') != plan.inspection.folder:
                raise ValueError
            inventory = transport.children(original['folder'])
            if (not isinstance(inventory, c.Inventory) or inventory.complete is not True
                    or not isinstance(inventory.items, tuple) or len(inventory.items) != len(expected)):
                raise ValueError
            by_id = {item.id: item for item in inventory.items}
            if len(by_id) != len(expected) or set(by_id) != {item.id for item in expected.values()}:
                raise ValueError
            for role, item in expected.items():
                if by_id[item.id] != item or observe(item.id, role) != item:
                    raise ValueError
            local()

        def receipt(role):
            item = expected[role]
            return dict(role=role, id=item.id, revision=item.revision,
                        body_sha256=core.digest(item.body.encode('utf-8')))

        def intent(action, role, body=''):
            preflight()
            old = expected.get(role)
            record(dict(type='INTENT', action=action, role=role, id=old.id if old else '',
                        before_revision=old.revision if old else '',
                        body_sha256=core.digest(body.encode('utf-8'))))
            preflight()

        def write(role, body):
            nonlocal attempted
            intent('WRITE_TEXT', role, body)
            if role == FIRST_ROLE:
                # Reuse the exact incident inspector after durable intent and
                # immediately before touching the original empty document.
                if plan_first_create(transport, state_store) != plan:
                    raise ValueError
                local()
            old = expected[role]
            attempted += 1
            transport.replace_text(old.id, body, old.revision)
            actual = observe(old.id, role)
            if actual.body != body or actual.revision == old.revision:
                raise ValueError
            expected[role] = actual
            preflight()
            record(dict(type='VERIFIED', **receipt(role)))

        def create(role):
            nonlocal attempted
            if role in expected or role not in pub.ROLES:
                raise ValueError
            intent('CREATE', role)
            attempted += 1
            identity = transport.create(role, drive.MIME, dict(x_context='synthetic_v1',
                                        namespace=original['namespace'], role=role), original['folder'])
            c._identity(identity)
            if identity in {original['folder'], original['parent'], c.SANDBOX, c.POC, c.SENTINEL,
                            *(item.id for item in expected.values())}:
                raise ValueError
            # Persist returned identity before ANY further remote request.
            record(dict(type='CREATED', role=role, id=identity))
            actual = observe(identity, role)
            if actual.body != '':
                raise ValueError
            expected[role] = actual
            preflight()
            record(dict(type='VERIFIED_EMPTY', **receipt(role)))

        for row in records:
            role = drive.PREFIX + row['record_id']
            if role != FIRST_ROLE:
                create(role)
            write(role, core.markdown(row).decode('utf-8'))
        # All five records have verified receipts before CURRENT exists.
        preflight()
        docs = {role: drive.Document(item.id, 'https://docs.google.com/document/d/' + item.id + '/edit',
                    role, original['folder'], True, item.body) for role, item in expected.items()}
        index_body = drive._index(records, docs)
        create(drive.CURRENT)
        write(drive.CURRENT, index_body)
        preflight()
        record(dict(type='COMPLETE', state_sha256=plan.inspection.state_sha256,
                    fixture_sha256=plan.fixture_sha256,
                    manifest={role: receipt(role) for role in sorted(expected)}))
        return drive.Result('COMPLETE', attempted)
    except Exception:
        # A stopped process never authorizes another attempt. Even a failed
        # completion append may have reached disk; no success/retry inference.
        if events is not None:
            try:
                if journal.load() == events:
                    journal.append(dict(type='STOPPED', writes_attempted=attempted))
            except Exception:
                pass
        return drive.Result('PARTIAL_UNPUBLISHED' if attempted else 'BLOCKED', attempted)
