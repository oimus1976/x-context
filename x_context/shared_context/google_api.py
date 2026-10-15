"""Bounded Google REST transport. Synthetic adapter only; no retries/redirects."""
import json
import re
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import core, connector as c, drive

METADATA = 'id,name,mimeType,parents,shared,trashed,isAppAuthorized,appProperties'
BASES = {'drive': 'https://www.googleapis.com/drive/v3/', 'docs': 'https://docs.googleapis.com/v1/'}
LIMIT = 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HTTP:
    def __init__(self, access_token):
        self.access_token = access_token

    def request(self, service, method, path, *, query=None, body=None):
        allowed = ((service == 'drive' and method == 'GET' and re.fullmatch(r'files(?:/[A-Za-z0-9_-]{1,200}(?:/permissions)?)?', path))
                   or (service == 'drive' and method == 'POST' and path == 'files')
                   or (service == 'docs' and method == 'GET' and re.fullmatch(r'documents/[A-Za-z0-9_-]{1,200}', path))
                   or (service == 'docs' and method == 'POST' and re.fullmatch(r'documents/[A-Za-z0-9_-]{1,200}:batchUpdate', path)))
        if not allowed:
            raise core.ContextError('UNSUPPORTED_GOOGLE_REQUEST')
        try:
            token = self.access_token()
            if not isinstance(token, str) or not token or any(ord(v) < 33 or ord(v) > 126 for v in token):
                raise ValueError
            url = BASES[service] + path + ('?' + urlencode(query) if query else '')
            request = Request(url, data=None if body is None else core.encode(body), method=method,
                              headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json', 'Accept': 'application/json'})
            with build_opener(NoRedirect()).open(request, timeout=30) as response:
                data = response.read(LIMIT + 1)
                if response.status != 200 or len(data) > LIMIT:
                    raise ValueError
            result = core.decode(data)
            if not isinstance(result, dict):
                raise ValueError
            return result
        except core.ContextError:
            raise
        except Exception:
            raise core.ContextError('GOOGLE_API_UNAVAILABLE') from None


def _no_suggestions(value):
    if isinstance(value, dict):
        if any(k.startswith('suggested') and v for k, v in value.items()):
            raise ValueError
        for v in value.values():
            _no_suggestions(v)
    elif isinstance(value, list):
        for v in value:
            _no_suggestions(v)


def _tab_identity(identity):
    """Supported Docs tab IDs, not Drive IDs; never used in URL/path segments.

    Docs documents.TabProperties defines an opaque immutable string, not a
    Drive-file ID grammar. Our bounded ASCII subset includes observed `t.0`
    and existing undotted fixtures. Dots separate nonempty safe segments;
    unknown shapes fail closed. This is a local support policy, not a claim
    that Google guarantees this alphabet. Passed unchanged only in JSON.
    """
    if (not isinstance(identity, str) or not 1 <= len(identity) <= 200
            or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', identity)):
        raise core.ContextError('UNSUPPORTED_NATIVE_TEXT')


def parse_document(value, identity):
    """Only single-tab plain text. Strip one structural final LF, nothing else."""
    try:
        if value['documentId'] != identity or not isinstance(value['revisionId'], str) or not value['revisionId']:
            raise ValueError
        _no_suggestions(value)
        for name in ('headers', 'footers', 'footnotes', 'inlineObjects', 'positionedObjects'):
            if value.get(name):
                raise ValueError
        tabs = value['tabs']
        if not isinstance(tabs, list) or len(tabs) != 1 or tabs[0].get('childTabs'):
            raise ValueError
        tab = tabs[0]
        tab_id = tab['tabProperties']['tabId']
        _tab_identity(tab_id)
        document = tab['documentTab']
        for name in ('headers', 'footers', 'footnotes', 'inlineObjects', 'positionedObjects'):
            if document.get(name):
                raise ValueError
        content = document['body']['content']
        text, index = '', 1
        for position, element in enumerate(content):
            if position == 0 and 'sectionBreak' in element and element.get('startIndex', 0) == 0 and element['endIndex'] == 1:
                continue
            if 'paragraph' not in element or element.get('startIndex') != index or 'table' in element or 'tableOfContents' in element:
                raise ValueError
            for run in element['paragraph']['elements']:
                if set(run) - {'startIndex', 'endIndex', 'textRun'} or run['startIndex'] != index:
                    raise ValueError
                chunk = run['textRun']['content']
                if not isinstance(chunk, str):
                    raise ValueError
                index += len(chunk.encode('utf-16-le')) // 2
                if run['endIndex'] != index:
                    raise ValueError
                text += chunk
            if element['endIndex'] != index:
                raise ValueError
        if not text.endswith('\n') or len(text.encode('utf-8')) > 65537 or '\r' in text:
            raise ValueError
        return text[:-1], value['revisionId'], tab_id, index - 1
    except Exception:
        raise core.ContextError('UNSUPPORTED_NATIVE_TEXT') from None


class Transport:
    """All-MIME pagination is APP_VISIBLE only; never a global inventory proof."""
    def __init__(self, http):
        self.http = http

    def metadata(self, identity):
        c._identity(identity)
        value = self.http.request('drive', 'GET', 'files/' + identity, query={'fields': METADATA})
        if value.get('id') != identity:
            raise core.ContextError('UNSAFE_GOOGLE_METADATA')
        return value

    def permissions(self, identity):
        c._identity(identity)
        values, token, seen = [], None, set()
        for _ in range(100):
            query = {'fields': 'nextPageToken,permissions(id,type,role,deleted)', 'pageSize': 100}
            if token:
                query['pageToken'] = token
            page = self.http.request('drive', 'GET', 'files/' + identity + '/permissions', query=query)
            rows = page.get('permissions')
            if not isinstance(rows, list):
                raise core.ContextError('UNSAFE_GOOGLE_METADATA')
            values.extend(rows)
            token = page.get('nextPageToken')
            if token is None:
                break
            if not isinstance(token, str) or not token or token in seen:
                raise core.ContextError('UNSAFE_GOOGLE_METADATA')
            seen.add(token)
        else:
            raise core.ContextError('UNSAFE_GOOGLE_METADATA')
        if len(values) != 1:
            raise core.ContextError('UNSAFE_GOOGLE_METADATA')
        p = values[0]
        if p.get('type') != 'user' or p.get('role') != 'owner' or p.get('deleted', False) is not False:
            raise core.ContextError('UNSAFE_GOOGLE_METADATA')
        c._identity(p.get('id'))
        return (c.Permission('user', 'owner', p['id']),)

    def read(self, identity):
        try:
            value = self.metadata(identity)
            if (set(value) != set(METADATA.split(',')) or value['isAppAuthorized'] is not True
                    or value['shared'] is not False or value['trashed'] is not False
                    or not isinstance(value['parents'], list) or len(value['parents']) != 1
                    or not isinstance(value['name'], str) or not isinstance(value['appProperties'], dict)):
                raise ValueError
            c._identity(value['parents'][0])
            permission = self.permissions(identity)
            body, revision = '', ''
            if value['mimeType'] == drive.MIME:
                doc = self.http.request('docs', 'GET', 'documents/' + identity, query={'includeTabsContent': 'true'})
                if doc.get('title') != value['name']:
                    raise ValueError
                body, revision, _, _ = parse_document(doc, identity)
            elif value['mimeType'] != c.FOLDER:
                raise ValueError
            return c.Item(identity, value['name'], tuple(value['parents']), value['mimeType'], False, permission, body, revision)
        except core.ContextError:
            raise
        except Exception:
            raise core.ContextError('UNSAFE_GOOGLE_METADATA') from None

    def children(self, folder):
        c._identity(folder)
        values, ids, token, tokens = [], set(), None, set()
        for _ in range(100):
            query = {'q': "'" + folder + "' in parents and trashed = false", 'corpora': 'user', 'spaces': 'drive',
                     'fields': 'nextPageToken,incompleteSearch,files(' + METADATA + ')', 'pageSize': 100}
            if token:
                query['pageToken'] = token
            page = self.http.request('drive', 'GET', 'files', query=query)
            if page.get('incompleteSearch') is not False or not isinstance(page.get('files'), list):
                raise core.ContextError('APP_VISIBLE_INVENTORY_UNAVAILABLE')
            for value in page['files']:
                identity = value.get('id')
                c._identity(identity)
                if identity in ids or len(ids) >= 6:
                    raise core.ContextError('UNEXPECTED_GOOGLE_CHILD')
                ids.add(identity)
                if self.metadata(identity) != value:
                    raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
                values.append(self.read(identity))
            token = page.get('nextPageToken')
            if token is None:
                return c.Inventory(tuple(values), True)
            if not isinstance(token, str) or not token or token in tokens:
                raise core.ContextError('APP_VISIBLE_INVENTORY_UNAVAILABLE')
            tokens.add(token)
        raise core.ContextError('APP_VISIBLE_INVENTORY_UNAVAILABLE')

    def create(self, title, mime, properties, parent=None):
        body = dict(name=title, mimeType=mime, appProperties=properties)
        if parent:
            c._identity(parent)
            body['parents'] = [parent]
        value = self.http.request('drive', 'POST', 'files', query={'fields': METADATA}, body=body)
        identity = value.get('id')
        c._identity(identity)
        return identity

    def replace_text(self, identity, body, revision):
        c._identity(identity)
        value = self.http.request('docs', 'GET', 'documents/' + identity, query={'includeTabsContent': 'true'})
        old, fresh, tab, end = parse_document(value, identity)
        if fresh != revision:
            raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
        requests = []
        if end > 1:
            requests.append({'deleteContentRange': {'range': {'startIndex': 1, 'endIndex': end, 'tabId': tab}}})
        requests.append({'insertText': {'location': {'index': 1, 'tabId': tab}, 'text': body}})
        self.http.request('docs', 'POST', 'documents/' + identity + ':batchUpdate', body={
            'writeControl': {'requiredRevisionId': revision}, 'requests': requests})
