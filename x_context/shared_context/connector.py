"""Synthetic-only injected connected transport. No auth or network implementation.

Missing complete inventory is a blocker, never a reason to guess a safe folder.
The product's disconnected CLI is unchanged. Fake tests are not cloud evidence.
"""
from dataclasses import dataclass, replace
import re
from typing import Protocol

from . import core, drive, fixtures

SANDBOX = '1T8L_dbk2uuKxL3UfgY5Vt418o9lvNnq4'
POC = '1s8a8dD9_av7h2IVVGn8AvFKgx45AN5tt'
SENTINEL = '1gD_t5AJu6JB-KvNMi9J7rqexqbV_pPOBdIOg7zVRYlg'
SENTINEL_TITLE = 'SYNTHETIC-XCTX-PUBLISH-ISSUE60-SENTINEL'
SENTINEL_BODY = ('SYNTHETIC TEST DATA\nSYN-XCTX-ISSUE60-CONNECTOR-SENTINEL\n'
                 'source=synthetic://x-context/connector-test\nphase=v2\n'
                 'This document contains fictional connector validation data only.\n\n')
FOLDER = 'application/vnd.google-apps.folder'


@dataclass(frozen=True)
class Permission:
    type: str
    role: str
    principal: str


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    parents: tuple[str, ...]
    mime: str
    shared: bool
    permissions: tuple[Permission, ...] | None
    body: str = ''
    revision: str = ''
    trashed: bool = False


@dataclass(frozen=True)
class Inventory:
    items: tuple[Item, ...]
    complete: bool  # trusted transport observation: all types/pages, no incompleteSearch


class Transport(Protocol):
    root_id: str  # observed My Drive root identity from the authorized connection
    def read(self, identity: str) -> Item: ...
    def children(self, folder: str) -> Inventory: ...
    def create_empty(self, title: str) -> str: ...
    def move(self, identity: str, old_parent: str, new_parent: str): ...
    def replace_text(self, identity: str, body: str, revision: str): ...


def canonical_text(body):
    try:
        if not isinstance(body, str) or len(body.encode('utf-8')) > 65536:
            raise ValueError
        text = body.replace('\r\n', '\n')
        if '\r' in text:
            raise ValueError
        return text
    except (ValueError, UnicodeError):
        raise core.ContextError('UNSUPPORTED_NATIVE_TEXT') from None


def _identity(identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', identity):
        raise core.ContextError('UNSAFE_CONNECTOR_METADATA')


def _owner(item):
    if (not isinstance(item, Item) or item.shared is not False or item.trashed is not False
            or not isinstance(item.permissions, tuple) or len(item.permissions) != 1):
        raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
    permission = item.permissions[0]
    if (not isinstance(permission, Permission) or permission.type != 'user'
            or permission.role != 'owner' or not isinstance(permission.principal, str)
            or not permission.principal):
        raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
    _identity(item.id)
    return permission.principal


class Backend:
    """Small implementation of drive.Backend, limited to the exact Issue60 folder.

    journal(entry) must durably record nonsecret (ID, phase) before returning.
    Entries stay in stages as well for partial/ambiguous-effect inspection.
    After any failed effect the instance is poisoned; recovery is manual.
    """
    def __init__(self, transport: Transport, journal):
        if not callable(journal):
            raise core.ContextError('STAGE_JOURNAL_REQUIRED')
        self.transport = transport
        self.journal = journal
        self.stages = []
        self.failed = False
        self.owner = None
        self.receipts = {}

    def folder(self, folder_id):
        if self.failed or folder_id != SANDBOX:
            raise core.ContextError('UNSUPPORTED_CONNECTOR_TARGET')
        item = self.transport.read(SANDBOX)
        owner = _owner(item)
        if item.id != SANDBOX or item.parents != (POC,) or item.mime != FOLDER:
            raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
        if self.owner is not None and self.owner != owner:
            raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
        self.owner = owner
        return folder_id, True

    def _read(self, identity, parent):
        item = self.transport.read(identity)
        if (_owner(item) != self.owner or item.id != identity or item.parents != (parent,)
                or item.mime != drive.MIME or not isinstance(item.revision, str) or not item.revision):
            raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
        return drive.Document(item.id, f'https://docs.google.com/document/d/{item.id}/edit',
                              item.title, parent, True, canonical_text(item.body)), item.revision

    def read(self, document_id):
        self.folder(SANDBOX)
        receipt = self._read(document_id, SANDBOX)
        # Only this public read path, used by drive._inventory to compare its
        # expected snapshot, captures the pre-effect receipt. Internal fresh
        # listings and CURRENT validation must never adopt a concurrent edit.
        self.receipts[document_id] = receipt
        return receipt[0]

    def list(self, folder_id):
        self.folder(folder_id)
        inventory = self.transport.children(folder_id)
        if (not isinstance(inventory, Inventory) or inventory.complete is not True
                or not isinstance(inventory.items, tuple) or len(inventory.items) > 7):
            raise core.ContextError('COMPLETE_INVENTORY_UNAVAILABLE')
        docs, seen = [], set()
        for item in inventory.items:
            if not isinstance(item, Item) or item.id in seen:
                raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
            seen.add(item.id)
            doc, _ = self._read(item.id, SANDBOX)
            # The listing must agree with a fresh read, including body/revision.
            observed = self.transport.read(item.id)
            if replace(item, body=canonical_text(item.body)) != replace(observed, body=canonical_text(observed.body)):
                raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
            if doc.id == SENTINEL:
                if doc.title != SENTINEL_TITLE or doc.body != SENTINEL_BODY:
                    raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
            else:
                if doc.title not in {drive.CURRENT, *(drive.PREFIX + rid for rid in fixtures.IDS)}:
                    raise core.ContextError('UNEXPECTED_CONNECTOR_CHILD')
                docs.append(doc)
        if SENTINEL not in seen:
            raise core.ContextError('MISSING_CONNECTOR_SENTINEL')
        return docs

    def _stage(self, identity, phase):
        entry = (identity, phase)
        self.stages.append(entry)
        self.journal(entry)

    def _allowed(self, title, body):
        if title == drive.CURRENT:
            # Only allow a CURRENT constructed from the verified record docs.
            index = drive.parse_index(body)
            records = core.normalize([e['record'] for e in index['records'].values()])
            docs = {d.title: d for d in self.list(SANDBOX)}
            for record in records:
                doc = docs.get(drive.PREFIX + record['record_id'])
                if doc is None or doc.body != core.markdown(record).decode('utf-8'):
                    raise core.ContextError('UNSAFE_CONNECTOR_BODY')
            if body != drive._index(records, docs):
                raise core.ContextError('UNSAFE_CONNECTOR_BODY')
        else:
            rid = title.removeprefix(drive.PREFIX)
            if (title != drive.PREFIX + rid or rid not in fixtures.IDS
                    or body not in {core.markdown(r).decode('utf-8') for name in fixtures.NAMES
                                    for r in core.normalize(core.load_fixture(name)) if r['record_id'] == rid}):
                raise core.ContextError('UNSAFE_CONNECTOR_BODY')

    def create(self, folder_id, title, body):
        self.folder(folder_id)
        self._allowed(title, body)
        if any(d.title == title for d in self.list(folder_id)):
            raise core.ContextError('UNEXPECTED_CONNECTOR_CHILD')
        root = self.transport.root_id
        _identity(root)
        if root in (SANDBOX, POC, SENTINEL):
            raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
        try:
            self._stage('', 'CREATE_ATTEMPT')
            identity = self.transport.create_empty(title)
            self._stage(identity, 'CREATED_EMPTY_UNVERIFIED')
            _identity(identity)
            if identity in {SANDBOX, POC, SENTINEL, *(d.id for d in self.list(folder_id))}:
                raise core.ContextError('UNSAFE_CONNECTOR_METADATA')
            empty, _ = self._read(identity, root)
            if empty.title != title or empty.body not in ('', '\n'):
                raise core.ContextError('ROOT_DOC_NOT_EMPTY')
            self._stage(identity, 'MOVE_ATTEMPTED')
            self.transport.move(identity, root, folder_id)
            moved, revision = self._read(identity, folder_id)
            if moved.title != title or moved.body != empty.body:
                raise core.ContextError('DRIVE_READBACK_MISMATCH')
            # Refresh folder/sentinel/whole inventory before inserting any text.
            self.list(folder_id)
            self._stage(identity, 'CONTENT_ATTEMPTED')
            self.transport.replace_text(identity, body, revision)
            actual = self.read(identity)
            if actual.title != title or actual.body != body:
                raise core.ContextError('DRIVE_READBACK_MISMATCH')
            return actual
        except Exception:
            self.failed = True
            raise core.ContextError('CONNECTOR_EFFECT_REQUIRES_INSPECTION') from None

    def update(self, document_id, body):
        authorized = self.receipts.get(document_id)
        docs = self.list(SANDBOX)
        old = next((doc for doc in docs if doc.id == document_id), None)
        if old is None:
            raise core.ContextError('UNEXPECTED_CONNECTOR_CHILD')
        self._allowed(old.title, body)
        fresh, revision = self._read(document_id, SANDBOX)
        if fresh != old or (fresh, revision) != authorized:
            raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
        try:
            self._stage(document_id, 'UPDATE_ATTEMPT')
            self.transport.replace_text(document_id, body, revision)
            actual = self.read(document_id)
            if actual.title != old.title or actual.body != body:
                raise core.ContextError('DRIVE_READBACK_MISMATCH')
            return actual
        except Exception:
            self.failed = True
            raise core.ContextError('CONNECTOR_EFFECT_REQUIRES_INSPECTION') from None


def prepare(backend, output):
    """Read-only; validate every generated file before obtaining a remote plan."""
    records = core.verify(output)
    return records, drive.preview(backend, SANDBOX, records)
