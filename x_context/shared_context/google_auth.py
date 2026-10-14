"""Separate Google credential lifecycle; initial consent is explicitly gated.

No use of X tokens/stores. DPAPI primitive is reused, not X refresh policy.
"""
from dataclasses import dataclass, field, asdict
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, build_opener
import webbrowser

from ..credential_lifecycle import _dpapi_protect, _dpapi_unprotect
from . import core
from .google_api import NoRedirect, LIMIT

SCOPE = 'https://www.googleapis.com/auth/drive.file'
TOKEN = 'https://oauth2.googleapis.com/token'
AUTHORIZE = 'https://accounts.google.com/o/oauth2/v2/auth'
# Downloaded Desktop metadata may use the older official URL. Requests stay v2.
CLIENT_AUTH_URIS = ('https://accounts.google.com/o/oauth2/auth', AUTHORIZE)


def safe(value):
    return isinstance(value, str) and 0 < len(value) <= 16384 and all(33 <= ord(c) <= 126 for c in value)


@dataclass(frozen=True)
class Credential:
    client_id: str
    client_secret: str = field(repr=False)
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: int
    scopes: tuple[str, ...]

    def __post_init__(self):
        if (not all(safe(v) for v in (self.client_id, self.client_secret, self.access_token, self.refresh_token))
                or not self.client_id.endswith('.apps.googleusercontent.com')
                or type(self.expires_at) is not int or self.expires_at <= 0
                or self.scopes != (SCOPE,)):
            raise core.ContextError('UNSAFE_GOOGLE_CREDENTIAL')


def atomic_write(path, data):
    """One whole-record replacement; no plaintext credential temporary file."""
    temporary = None
    try:
        path = Path(path)
        if not path.is_absolute() or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
            raise ValueError
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix='.'+path.name+'.', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        if path.read_bytes() != data:
            raise ValueError
    except Exception:
        raise core.ContextError('GOOGLE_LOCAL_STATE_ERROR') from None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


class Store:
    def __init__(self, path, *, protect=None, unprotect=None):
        self.path = Path(path)
        self.protect = _dpapi_protect if protect is None else protect
        self.unprotect = _dpapi_unprotect if unprotect is None else unprotect

    def load(self):
        try:
            if any(p.is_symlink() or p.is_junction() for p in (self.path, *self.path.parents)):
                raise ValueError
            if not self.path.exists():
                return None
            blob = self.path.read_bytes()
            if not blob or len(blob) > LIMIT:
                raise ValueError
            value = core.decode(self.unprotect(blob))
            if set(value) != {'schema', 'provider', 'credential'} or value['schema'] != '1' or value['provider'] != 'google-drive':
                raise ValueError
            record = value['credential']
            record['scopes'] = tuple(record['scopes'])
            return Credential(**record)
        except Exception:
            raise core.ContextError('GOOGLE_CREDENTIAL_STORAGE_ERROR') from None

    def save(self, record):
        try:
            if not isinstance(record, Credential):
                raise ValueError
            blob = self.protect(core.encode(dict(schema='1',provider='google-drive',credential=asdict(record))))
            if not isinstance(blob, bytes) or not blob:
                raise ValueError
            atomic_write(self.path, blob)
        except Exception:
            raise core.ContextError('GOOGLE_CREDENTIAL_STORAGE_ERROR') from None


def token_request(form):
    try:
        request = Request(TOKEN, data=urlencode(form).encode('ascii'), method='POST',
                          headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            data = response.read(LIMIT+1)
            if response.status != 200 or len(data) > LIMIT:
                raise ValueError
        value = core.decode(data)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except Exception:
        raise core.ContextError('GOOGLE_AUTH_REAUTHORIZE_OR_RETRY_LATER') from None


def _result(value, client_id, client_secret, refresh, now, *, initial=False):
    try:
        # Initial grant must report EXACT scope; refresh may omit unchanged scope.
        scope = value.get('scope')
        if scope is not None and scope.split() != [SCOPE] or initial and scope != SCOPE:
            raise ValueError
        if value.get('token_type') != 'Bearer' or type(value.get('expires_in')) is not int or value['expires_in'] <= 0:
            raise ValueError
        return Credential(client_id, client_secret, value['access_token'], value.get('refresh_token',refresh),
                          now+value['expires_in'],(SCOPE,))
    except Exception:
        raise core.ContextError('GOOGLE_AUTH_REAUTHORIZE_OR_RETRY_LATER') from None


class Provider:
    def __init__(self, store, token=token_request, *, clock=time.time):
        self.store, self.token, self.clock = store, token, clock

    def access_token(self):
        try:
            current = self.store.load()
            if not isinstance(current, Credential):
                raise core.ContextError('LIVE_GOOGLE_AUTH_PENDING')
            now = self.clock()
            if not isinstance(now,(int,float)) or isinstance(now,bool) or not math.isfinite(now) or now < 0:
                raise ValueError
            now = int(now)
            if current.expires_at > now+300:
                return current.access_token
            value = self.token(dict(client_id=current.client_id,client_secret=current.client_secret,
                                    refresh_token=current.refresh_token,grant_type='refresh_token'))
            updated = _result(value,current.client_id,current.client_secret,current.refresh_token,now)
            # Google normally omits refresh_token. Retain it, unlike X policy.
            self.store.save(updated)
            return updated.access_token
        except core.ContextError:
            raise
        except Exception:
            raise core.ContextError('GOOGLE_AUTH_REAUTHORIZE_OR_RETRY_LATER') from None


def authorization(client_id, redirect, state, verifier):
    if not safe(client_id) or not safe(state) or not safe(verifier) or not redirect.startswith('http://127.0.0.1:'):
        raise core.ContextError('INVALID_GOOGLE_CONFIGURATION')
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    return AUTHORIZE+'?'+urlencode(dict(client_id=client_id,redirect_uri=redirect,response_type='code',scope=SCOPE,
                                       state=state,code_challenge=challenge,code_challenge_method='S256',
                                       access_type='offline',prompt='consent',include_granted_scopes='false'))


def bootstrap(store, client_config, *, approved=False, reauthorize=False):
    """Only explicit operator consent; never invoked by a publish/preview."""
    if not approved:
        raise core.ContextError('GOOGLE_BOOTSTRAP_OWNER_APPROVAL_REQUIRED')
    try:
        if os.name != 'nt':
            raise ValueError
        if store.load() is not None and not reauthorize:
            raise core.ContextError('GOOGLE_CREDENTIAL_EXISTS')
        path = Path(client_config)
        # Downloaded config must be outside any Git checkout, never pasted.
        if not path.is_absolute() or any((p / '.git').exists() or p.is_symlink() or p.is_junction() for p in path.parents) or path.is_symlink():
            raise ValueError
        value = core.decode(path.read_bytes())['installed']
        if value.get('auth_uri') not in CLIENT_AUTH_URIS or value.get('token_uri') != TOKEN:
            raise ValueError
        client_id, client_secret = value['client_id'],value['client_secret']
        if not safe(client_secret) or not safe(client_id) or not client_id.endswith('.apps.googleusercontent.com'):
            raise ValueError
        state, verifier = secrets.token_urlsafe(32),secrets.token_urlsafe(48)
        receipt = {}
        class Callback(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_GET(self):
                parsed=urlparse(self.path)
                args=parse_qs(parsed.query)
                if (parsed.path != '/' or set(args) - {'state','code','scope','authuser','prompt'}
                        or args.get('state') != [state] or len(args.get('code',[])) != 1 or not safe(args['code'][0])):
                    self.send_response(400); self.end_headers(); return
                receipt['code']=args['code'][0]
                self.send_response(200); self.end_headers(); self.wfile.write(b'Authorization received. You may close this window.')
        with HTTPServer(('127.0.0.1',0),Callback) as server:
            server.timeout=1
            redirect='http://127.0.0.1:'+str(server.server_port)+'/'
            if not webbrowser.open(authorization(client_id,redirect,state,verifier)):
                raise ValueError
            deadline=time.monotonic()+180
            while 'code' not in receipt and time.monotonic()<deadline:
                server.handle_request()
            if 'code' not in receipt:
                raise ValueError
        result=token_request(dict(client_id=client_id,client_secret=client_secret,code=receipt['code'],
                                  code_verifier=verifier,redirect_uri=redirect,grant_type='authorization_code'))
        credential=_result(result,client_id,client_secret,None,int(time.time()),initial=True)
        store.save(credential)
    except core.ContextError:
        raise
    except Exception:
        raise core.ContextError('GOOGLE_BOOTSTRAP_FAILED') from None
