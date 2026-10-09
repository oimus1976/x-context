"""SPEC-0007 plaintext, single-writer bookmark store; no provider access.

Freshness detects only differences observed on the final read. Replacement is
not compare-and-swap and does not protect against after-read races or ABA.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

from .canonical import CanonicalEnvelope


class BookmarkStoreError(RuntimeError):
    """Allow-listed category and effect state only; never private/OS prose."""
    def __init__(self, category: str = 'storage_error', *, may_have_occurred: bool = False):
        super().__init__(category)
        self.category = category
        self.may_have_occurred = may_have_occurred


@dataclass(frozen=True)
class StoreSnapshot:
    path: Path = field(repr=False)
    raw: bytes | None = field(repr=False)
    value: dict | None = field(repr=False)


def _numeric(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value.isascii() and value.isdigit()


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value, flags=re.ASCII):
        return False
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return True


def _validate(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        'store_schema_version', 'source', 'collection', 'subject', 'created_at', 'updated_at', 'items'
    }:
        raise ValueError('invalid store')
    if (value['store_schema_version'], value['source'], value['collection']) != ('1', 'x', 'bookmarks'):
        raise ValueError('invalid store')
    subject = value['subject']
    if not isinstance(subject, dict) or set(subject) not in ({'id'}, {'id', 'username'}) or not _numeric(subject['id']):
        raise ValueError('invalid store')
    if 'username' in subject and (not isinstance(subject['username'], str) or not subject['username']):
        raise ValueError('invalid store')
    if 'username' in subject:
        subject['username'].encode('utf-8')
    if not all(_timestamp(value[key]) for key in ('created_at', 'updated_at')) or not isinstance(value['items'], list):
        raise ValueError('invalid store')
    seen = set()
    for item in value['items']:
        if not isinstance(item, dict) or set(item) != {'id', 'text', 'first_seen_at', 'last_seen_at'}:
            raise ValueError('invalid store')
        if not _numeric(item['id']) or item['id'] in seen or not isinstance(item['text'], str):
            raise ValueError('invalid store')
        item['text'].encode('utf-8')
        if not all(_timestamp(item[key]) for key in ('first_seen_at', 'last_seen_at')):
            raise ValueError('invalid store')
        seen.add(item['id'])


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('invalid store')
        value[key] = item
    return value


def _decode(raw: bytes) -> dict:
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    _validate(value)
    return value


def _read_snapshot(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def preflight(environ: Mapping[str, str]) -> StoreSnapshot:
    """Read/validate only: no mkdir, credential resolution or provider traffic."""
    root = environ.get('LOCALAPPDATA')
    category = 'configuration_error'
    try:
        if not isinstance(root, str) or not root.strip() or not Path(root).is_absolute():
            raise ValueError('invalid local root')
        path = (Path(root) / 'x-context' / 'data' / 'bookmarks-v1.json').resolve()
        # Reject storage under any ancestor repository/worktree, including a
        # LOCALAPPDATA misconfiguration. No Git command or trust bypass needed.
        if any((parent / '.git').exists() for parent in path.parents):
            raise ValueError('repository local root')
        category = 'storage_error'
        raw = _read_snapshot(path)
        value = None if raw is None else _decode(raw)
        return StoreSnapshot(path, raw, value)
    except Exception:
        pass
    raise BookmarkStoreError(category) from None


def _serialize(value: dict) -> bytes:
    _validate(value)
    raw = (json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    _decode(raw)
    return raw


def _write_temp(fd: int, raw: bytes) -> None:
    with os.fdopen(fd, 'wb') as stream:
        if stream.write(raw) != len(raw):
            raise OSError('short write')
        stream.flush()
        os.fsync(stream.fileno())


def save(snapshot: StoreSnapshot, envelope: CanonicalEnvelope) -> dict[str, int]:
    """Merge one successful canonical page; verify bytes before success.

    Never repair an invalid store or roll back an already replaced store.
    Cleanup is limited to this call's own temporary file.
    """
    category = 'storage_error'
    replaced = False
    temp_path = None
    fd = None
    try:
        if not isinstance(envelope, CanonicalEnvelope) or envelope.operation != 'bookmarks':
            raise ValueError('invalid envelope')
        incoming = envelope.to_dict()
        subject = incoming['subject']
        if snapshot.value is not None and snapshot.value['subject']['id'] != subject['id']:
            category = 'subject_mismatch'
            raise ValueError('subject mismatch')
        at = incoming['retrieved_at']
        value = copy.deepcopy(snapshot.value) if snapshot.value is not None else {
            'store_schema_version': '1', 'source': 'x', 'collection': 'bookmarks',
            'subject': subject, 'created_at': at, 'updated_at': at, 'items': []
        }
        value['subject'] = subject
        value['updated_at'] = at
        by_id = {item['id']: item for item in value['items']}
        old_ids = set(by_id)
        observed_ids = set()
        for post in incoming['items']:
            observed_ids.add(post['id'])
            item = by_id.get(post['id'])
            if item is None:
                item = {'id': post['id'], 'text': post['text'], 'first_seen_at': at, 'last_seen_at': at}
                by_id[post['id']] = item
                value['items'].append(item)
            else:
                item['text'] = post['text']
                item['last_seen_at'] = at
        raw = _serialize(value)
        snapshot.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.bookmarks-', suffix='.tmp', dir=snapshot.path.parent)
        temp_path = Path(name)
        _write_temp(fd, raw)
        fd = None
        # Verify the prepared temporary image too; never truncate the target.
        if temp_path.read_bytes() != raw:
            raise OSError('temporary image mismatch')
        if _read_snapshot(snapshot.path) != snapshot.raw:
            raise OSError('observed store difference')
        os.replace(temp_path, snapshot.path)
        replaced = True
        if _read_snapshot(snapshot.path) != raw:
            raise OSError('committed image mismatch')
        return {'new_item_count': len(observed_ids - old_ids),
                'updated_item_count': len(observed_ids & old_ids), 'stored_item_count': len(value['items'])}
    except Exception:
        pass
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    raise BookmarkStoreError(category, may_have_occurred=replaced) from None
