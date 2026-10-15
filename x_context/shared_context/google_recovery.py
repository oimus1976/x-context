"""Read-only first-create inspection. No credential loader, CLI or write executor.

Receipts describe observations, never authorize publish or clear pending state.
The proposed owner-gated continuation is specified in the recovery design.
"""
import copy
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
