"""Issue #65: one incident, six fake/live-read receipts, one gated LOCAL commit.

Injected transports and exact paths only. No OAuth, Google caller, X collection, or
automatic publish invocation. The real operator caller and its separate Gate R/W
approvals are deliberately NOT supplied here.
"""
from dataclasses import asdict, dataclass, field
import copy
import os
from pathlib import Path
import re

from . import core, drive, connector as c, google_publish as pub
from . import google_recovery as recovery

_CODE_LIMIT = 200


def _module_sha():
    # Exact source bytes in the running checkout, not a caller-supplied assertion.
    return core.digest(Path(__file__).read_bytes())


@dataclass(frozen=True, repr=False)
class LocalEvidence:
    original_bytes: bytes
    sidecar_bytes: bytes
    original: dict
    manifest: dict
    projected: dict
    bodies: dict
    fixture_digest: str


@dataclass(frozen=True, repr=False)
class ReconciliationPlan:
    digest: str
    projected: dict
    original_bytes: bytes
    sidecar_bytes: bytes
    remote_digest: str
    reviewed_code: str


def _safe_path(path, *, suffix):
    p = Path(path)
    parts = p.parts[1:]
    bad = any(part in {'.', '..'} or part.endswith((' ', '.'))
              or part.split('.')[0].rstrip(' ').upper() in recovery.Journal._DEVICES
              or any(ord(ch) < 32 or ch in '<>:"|?*' for ch in part)
              for part in parts)
    if (not p.is_absolute() or p.suffix != suffix or bad
            or (os.name == 'nt' and not re.fullmatch(r'[A-Za-z]:\\', p.anchor))
            or any(x.is_symlink() or x.is_junction() for x in (p, *p.parents))):
        raise ValueError
    return p


def _read_inputs(state_store, journal):
    state_path = _safe_path(state_store.path, suffix='.json')
    journal._guard()
    sidecar_path = journal.path
    if state_path == sidecar_path or not state_path.is_file() or not sidecar_path.is_file():
        raise ValueError
    if os.path.samefile(state_path, sidecar_path):
        raise ValueError
    raw = state_path.read_bytes()
    sidecar = sidecar_path.read_bytes()
    if not raw or len(raw) > 65536 or not sidecar or len(sidecar) > journal.LIMIT:
        raise ValueError
    value = pub.validate_state(core.decode(raw))
    # State.load and Journal.load are the repository's ordinary format guards.
    if state_store.load() != value:
        raise ValueError
    events = journal.load()
    if not isinstance(events, list) or len(events) != 29:
        raise ValueError
    if state_path.read_bytes() != raw or sidecar_path.read_bytes() != sidecar:
        raise ValueError
    return raw, sidecar, value, events


def _expect(row, event_type, keys):
    if not isinstance(row, dict) or row.get('type') != event_type or set(row) != keys:
        raise ValueError
    return row


def _receipt(row, kind, role, identity, digest, *, before_revision=None):
    _expect(row, kind, {'type', 'role', 'id', 'revision', 'body_sha256'})
    if (row['role'] != role or row['id'] != identity
            or not isinstance(row['revision'], str) or not row['revision']
            or len(row['revision']) > 1024 or row['body_sha256'] != digest
            or before_revision is not None and row['revision'] == before_revision):
        raise ValueError
    return dict(role=role, id=identity, revision=row['revision'], body_sha256=digest)


def _intent(row, action, role, identity, revision, body):
    _expect(row, 'INTENT', {'type', 'action', 'role', 'id',
                             'before_revision', 'body_sha256'})
    if (row['action'] != action or row['role'] != role
            or row['id'] != identity or row['before_revision'] != revision
            or row['body_sha256'] != core.digest(body.encode('utf-8'))):
        raise ValueError


def inspect_local(state_store, journal):
    """Purely LOCAL strict RCN-01 inspection of explicit, existing files."""
    try:
        raw, sidecar, old, events = _read_inputs(state_store, journal)
        original_id = old['documents'].get(recovery.FIRST_ROLE)
        if (set(old['documents']) != {recovery.FIRST_ROLE}
                or [tuple(row) for row in old['pending']] != [
                    ('', 'CREATE_ATTEMPT'),
                    (original_id, 'CREATED_EMPTY_UNVERIFIED')]):
            raise ValueError
        records = core.normalize(core.load_fixture('baseline'))
        fixture_digest = core.digest(core.encode(records))
        original_digest = core.digest(core.encode(old))
        begin = _expect(events[0], 'BEGIN',
                        {'type', 'schema', 'original_state', 'state_sha256',
                         'fixture_sha256', 'approval_reference', 'first_revision'})
        approval = begin['approval_reference']
        if (begin['schema'] != 'first-create-recovery-v1'
                or begin['original_state'] != old or begin['state_sha256'] != original_digest
                or begin['fixture_sha256'] != fixture_digest
                or not isinstance(approval, str) or not 1 <= len(approval) <= 80
                or not isinstance(begin['first_revision'], str)
                or not begin['first_revision']):
            raise ValueError
        c._identity(approval)
        seen = {old['folder'], old['parent'], c.SANDBOX, c.POC, c.SENTINEL, original_id}
        current_revision = begin['first_revision']
        bodies = {}
        manifest = {}
        pos = 1
        for row in records:
            role = drive.PREFIX + row['record_id']
            text = core.markdown(row).decode('utf-8')
            bodies[role] = text
            if role == recovery.FIRST_ROLE:
                identity = original_id
            else:
                _intent(events[pos], 'CREATE', role, '', '', '')
                pos += 1
                created = _expect(events[pos], 'CREATED', {'type', 'role', 'id'})
                identity = created['id']
                if created['role'] != role:
                    raise ValueError
                c._identity(identity)
                if identity in seen:
                    raise ValueError
                seen.add(identity)
                pos += 1
                empty = _receipt(events[pos], 'VERIFIED_EMPTY', role, identity,
                                 core.digest(b''))
                current_revision = empty['revision']
                pos += 1
            _intent(events[pos], 'WRITE_TEXT', role, identity, current_revision, text)
            pos += 1
            receipt = _receipt(events[pos], 'VERIFIED', role, identity,
                               core.digest(text.encode('utf-8')),
                               before_revision=current_revision)
            manifest[role] = receipt
            pos += 1
            current_revision = receipt['revision']

        # CURRENT's body must bind the actual five verified IDs, not a title search.
        docmap = {
            role: drive.Document(receipt['id'],
                                 'https://docs.google.com/document/d/' + receipt['id'] + '/edit',
                                 role, old['folder'], True, bodies[role])
            for role, receipt in manifest.items()
        }
        current_text = drive._index(records, docmap)
        role = drive.CURRENT
        bodies[role] = current_text
        _intent(events[pos], 'CREATE', role, '', '', '')
        pos += 1
        created = _expect(events[pos], 'CREATED', {'type', 'role', 'id'})
        identity = created['id']
        if created['role'] != role:
            raise ValueError
        c._identity(identity)
        if identity in seen:
            raise ValueError
        seen.add(identity)
        pos += 1
        empty = _receipt(events[pos], 'VERIFIED_EMPTY', role, identity, core.digest(b''))
        pos += 1
        _intent(events[pos], 'WRITE_TEXT', role, identity, empty['revision'], current_text)
        pos += 1
        manifest[role] = _receipt(events[pos], 'VERIFIED', role, identity,
                                   core.digest(current_text.encode('utf-8')),
                                   before_revision=empty['revision'])
        pos += 1
        complete = _expect(events[pos], 'COMPLETE',
                           {'type', 'state_sha256', 'fixture_sha256', 'manifest'})
        if (pos != len(events)-1 or complete['state_sha256'] != original_digest
                or complete['fixture_sha256'] != fixture_digest
                or complete['manifest'] != manifest):
            raise ValueError
        projected = copy.deepcopy(old)
        projected['documents'] = {role: receipt['id'] for role, receipt in manifest.items()}
        projected['pending'] = []
        pub.validate_state(projected)
        if state_store.path.read_bytes() != raw or journal.path.read_bytes() != sidecar:
            raise ValueError
        return LocalEvidence(raw, sidecar, old, manifest, projected, bodies, fixture_digest)
    except Exception:
        raise core.ContextError('GOOGLE_RECONCILIATION_LOCAL_BLOCKED') from None


def _snapshot(transport, evidence):
    """Single stable app-visible snapshot: NO credential handling or writes."""
    state = evidence.original
    def observed(identity, role):
        props = dict(x_context='synthetic_v1', namespace=state['namespace'], role=role)
        metadata = transport.metadata(identity)
        if (not isinstance(metadata, dict) or metadata.get('id') != identity
                or metadata.get('isAppAuthorized') is not True
                or metadata.get('appProperties') != props):
            raise ValueError
        item = transport.read(identity)
        if not isinstance(item, c.Item) or item.id != identity or c._owner(item) != state['owner']:
            raise ValueError
        return item

    folder = observed(state['folder'], 'folder')
    if (folder.title != pub.FOLDER_TITLE or folder.mime != c.FOLDER
            or folder.parents != (state['parent'],)):
        raise ValueError
    inventory = transport.children(folder.id)
    expected = set(evidence.projected['documents'].values())
    if (not isinstance(inventory, c.Inventory) or inventory.complete is not True
            or not isinstance(inventory.items, tuple) or len(inventory.items) != 6):
        raise ValueError
    items = {}
    for item in inventory.items:
        if not isinstance(item, c.Item) or item.id in items:
            raise ValueError
        items[item.id] = item
    if set(items) != expected:
        raise ValueError
    received = {}
    for role, receipt in evidence.manifest.items():
        item = observed(receipt['id'], role)
        if (item != items[item.id] or item.title != role or item.mime != drive.MIME
                or item.parents != (state['folder'],)
                or item.body != evidence.bodies[role]
                or not item.revision or item.revision != receipt['revision']
                or core.digest(item.body.encode('utf-8')) != receipt['body_sha256']):
            raise ValueError
        received[role] = item
    index = drive.parse_index(received[drive.CURRENT].body)
    records = core.normalize(core.load_fixture('baseline'))
    if (set(index['records']) != {row['record_id'] for row in records}
            or index['active_ids'] != sorted(row['record_id'] for row in records)
            or len(index['active_links']) != 5):
        raise ValueError
    docmap = {
        role: drive.Document(item.id, 'https://docs.google.com/document/d/' + item.id + '/edit',
                             role, state['folder'], True, item.body)
        for role, item in received.items() if role != drive.CURRENT
    }
    if received[drive.CURRENT].body != drive._index(records, docmap):
        raise ValueError
    payload = dict(folder=asdict(folder),
                   documents={role: asdict(received[role]) for role in sorted(received)})
    return core.digest(core.encode(payload))


def plan_reconciliation(transport, state_store, journal, *, reviewed_code):
    """Requires a separately authorized read-only injected transport."""
    try:
        if (not isinstance(reviewed_code, str)
                or not 1 <= len(reviewed_code) <= _CODE_LIMIT):
            raise ValueError
        c._identity(reviewed_code)
        evidence = inspect_local(state_store, journal)
        first = _snapshot(transport, evidence)
        second = _snapshot(transport, evidence)
        if first != second:
            raise ValueError
        if (state_store.path.read_bytes() != evidence.original_bytes
                or journal.path.read_bytes() != evidence.sidecar_bytes):
            raise ValueError
        binding = dict(original_raw_sha256=core.digest(evidence.original_bytes),
                       original_state_sha256=core.digest(core.encode(evidence.original)),
                       sidecar_raw_sha256=core.digest(evidence.sidecar_bytes),
                       fixture_sha256=evidence.fixture_digest,
                       projected_sha256=core.digest(core.encode(evidence.projected)),
                       remote_digest=first, reviewed_code=reviewed_code,
                       module_source_sha256=_module_sha(),
                       registry_path=str(state_store.path),
                       sidecar_path=str(journal.path))
        return ReconciliationPlan(core.digest(core.encode(binding)),
                                  evidence.projected, evidence.original_bytes,
                                  evidence.sidecar_bytes, first, reviewed_code)
    except Exception:
        raise core.ContextError('GOOGLE_RECONCILIATION_READ_BLOCKED') from None


def commit_reconciliation(transport, state_store, journal, backup_path, plan, *,
                          reviewed_code, approved=False, read_authorized=False,
                          approval_digest=None, approved_backup_path=None):
    """Gate W: exclusive immutable backup then ONE local atomic registry replace.

    Never loads OAuth credentials, retries a write, or runs normal publish.
    A failed/ambiguous claim needs operator inspection; no alternate claim path.
    """
    if (approved is not True or read_authorized is not True
            or not isinstance(plan, ReconciliationPlan)
            or not isinstance(approval_digest, str)
            or approval_digest != plan.digest
            or reviewed_code != plan.reviewed_code
            or not isinstance(approved_backup_path, str)
            or not approved_backup_path):
        return 'BLOCKED'
    try:
        backup = _safe_path(backup_path, suffix='.json')
        if str(backup) != approved_backup_path:
            return 'BLOCKED'
        registry = _safe_path(state_store.path, suffix='.json')
        journal._guard()
        if backup in (registry, journal.path) or backup.exists() or backup.parent != registry.parent:
            return 'BLOCKED'
        if plan_reconciliation(transport, state_store, journal,
                               reviewed_code=reviewed_code) != plan:
            return 'BLOCKED'
    except Exception:
        return 'BLOCKED'
    claimed = False
    try:
        # Exclusive create is a one-shot claim, not a cross-process registry lock.
        with backup.open('xb') as handle:
            claimed = True
            handle.write(plan.original_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        if backup.read_bytes() != plan.original_bytes:
            raise ValueError
        # Keep the single-writer rule. A second provider snapshot is mandatory.
        if plan_reconciliation(transport, state_store, journal,
                               reviewed_code=reviewed_code) != plan:
            raise ValueError
        state_store.save(copy.deepcopy(plan.projected))
        if (registry.read_bytes() != core.encode(plan.projected)
                or backup.read_bytes() != plan.original_bytes
                or journal.path.read_bytes() != plan.sidecar_bytes
                or state_store.load() != plan.projected):
            raise ValueError
        return 'RECONCILED'
    except Exception:
        # Even a failed xb/flush/fsync may have left a claim; never retry here.
        return 'UNCERTAIN_REQUIRES_INSPECTION' if claimed or backup.exists() else 'BLOCKED'
