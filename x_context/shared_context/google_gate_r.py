"""Issue #65 single-incident Gate R read caller; live use requires separate approval."""
import math
from . import connector as c, core, google_api as api, google_auth as auth

class ReadOnlyHTTP:
    """Constrain all requests before dispatch; a supplied request is not authorization."""
    def __init__(self, request, *, folder, documents, monotonic, deadline):
        c._identity(folder)
        if not documents or folder in documents:
            raise ValueError('BLOCKED')
        for identity in documents:
            c._identity(identity)
        self._request = request
        self._folder = folder
        self._documents = frozenset(documents)
        self._clock, self._deadline = monotonic, deadline
        self.drive_remaining, self.docs_remaining, self.about_remaining = 90, 28, 1
        self._verified = False

    def verify_principal(self, expected):
        c._identity(expected)
        if self._verified:
            raise ValueError('BLOCKED')
        response = self.request('drive', 'GET', 'about', query={'fields':'user(permissionId,me)'})
        try:
            user = response['user']
            if user['me'] is not True or user['permissionId'] != expected:
                raise ValueError
            c._identity(user['permissionId'])
        except Exception:
            raise core.ContextError('GOOGLE_PRINCIPAL_BLOCKED') from None
        self._verified = True

    def request(self, service, method, path, *, query=None, body=None):
        if method != 'GET' or body is not None or not isinstance(query, dict):
            raise core.ContextError('GOOGLE_READ_BLOCKED')
        expected_metadata = {'fields': api.METADATA}
        allowed = False
        kind = None
        if service == 'drive' and path == 'about':
            allowed = not self._verified and query == {'fields':'user(permissionId,me)'}
            kind = 'about'
        elif self._verified and service == 'docs' and path.startswith('documents/'):
            allowed = path[10:] in self._documents and query == {'includeTabsContent':'true'}
            kind = 'docs'
        elif self._verified and service == 'drive':
            kind = 'drive'
            ids = self._documents | {self._folder}
            if path.startswith('files/'):
                suffix = path[6:]
                if suffix.endswith('/permissions'):
                    identity = suffix[:-12]
                    base = {'fields':'nextPageToken,permissions(id,type,role,deleted)', 'pageSize':100}
                    allowed = identity in ids and _page_query(query, base)
                else:
                    allowed = suffix in ids and query == expected_metadata
            elif path == 'files':
                base = {'q': "'" + self._folder + "' in parents and trashed = false", 'corpora':'user', 'spaces':'drive',
                        'fields':'nextPageToken,incompleteSearch,files(' + api.METADATA + ')', 'pageSize':100}
                allowed = _page_query(query, base)
        remaining = self._deadline - self._clock()
        if (not allowed or not isinstance(remaining, (int, float)) or not math.isfinite(remaining) or remaining <= 0):
            raise core.ContextError('GOOGLE_READ_BLOCKED')
        attr = kind + '_remaining'
        if getattr(self, attr) <= 0:
            raise core.ContextError('GOOGLE_READ_BUDGET_EXHAUSTED')
        setattr(self, attr, getattr(self, attr) - 1)
        result = self._request(service, method, path, query=query, body=None, timeout=min(30, remaining))
        completed = self._clock()
        if (not isinstance(completed, (int, float)) or isinstance(completed, bool)
                or not math.isfinite(completed) or completed >= self._deadline):
            raise core.ContextError('GOOGLE_READ_DEADLINE_EXCEEDED')
        return result

def _page_query(query, base):
    extra = set(query) - set(base)
    if extra not in (set(), {'pageToken'}) or any(query.get(k) != v for k, v in base.items()):
        return False
    if extra:
        value = query['pageToken']
        if not isinstance(value, str) or not 1 <= len(value) <= 1024 or any(ord(ch) < 33 or ord(ch) > 126 for ch in value):
            return False
    return True

def load_unexpired_token(store, *, now, lifetime):
    record = store.load()
    if (not isinstance(record, auth.Credential) or not isinstance(now, (float, int))
            or isinstance(now, bool) or not math.isfinite(now) or now < 0
            or not isinstance(lifetime, (float, int)) or isinstance(lifetime, bool)
            or not math.isfinite(lifetime) or lifetime <= 0 or record.expires_at <= now + lifetime):
        raise core.ContextError('AUTH_EXPIRED_REAUTH_APPROVAL_REQUIRED')
    return record.access_token

class BoundedState:
    """Read-only view of an explicit incident registry, with a fixed size bound."""
    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)

    def load(self):
        from . import google_reconcile as reconcile, google_publish as pub
        return pub.validate_state(core.decode(reconcile._read_bounded(self.path, 65536)))

# The injected seam is for synthetic tests; it is not an authorization mechanism.
from dataclasses import dataclass, field
from pathlib import Path
import sys
from . import google_reconcile as reconcile, google_recovery as recovery

@dataclass(frozen=True, repr=False)
class Preparation:
    digest: str
    registry: Path = field(repr=False)
    sidecar: Path = field(repr=False)
    credential: Path = field(repr=False)
    selected_user: str = field(repr=False)
    approval_reference: str = field(repr=False)
    registry_sha: str = field(repr=False)
    sidecar_sha: str = field(repr=False)

@dataclass(frozen=True)
class Result:
    status: str
    digest: str = ''
    reason: str = ''

def _source_binding():
    root = Path(__file__).resolve().parents[1]
    files = sorted(root.rglob('*.py'))
    if not files:
        raise ValueError
    return core.digest(core.encode({'python':sys.version, 'runtime':_runtime_binding(), 'sources':[
        (p.relative_to(root).as_posix(), core.digest(reconcile._read_bounded(p, 1048576)))
        for p in files]}))

def _runtime_binding():
    """Bind interpreter, standard-library source and extension binaries."""
    import hashlib, os, sysconfig
    library = Path(sysconfig.get_path('stdlib'))
    if not library.is_dir():
        raise ValueError
    files = []
    for parent, directories, names in os.walk(library, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in
            {'site-packages', 'dist-packages', '__pycache__', 'test', 'tests'}
            and not (Path(parent) / d).is_symlink())
        for name in names:
            p = Path(parent) / name
            if p.suffix.lower() in {'.py', '.pyd', '.so', '.dll'}:
                files.append(p)
    native = Path(sys.base_prefix) / 'DLLs'
    if native.is_dir():
        files.extend(p for p in native.iterdir() if p.suffix.lower() in {'.pyd', '.dll'})
    files.append(Path(sys.executable).resolve(strict=True))
    if os.name == 'nt':
        files.append(Path(sys.base_prefix) / ('python' + str(sys.version_info.major) + str(sys.version_info.minor) + '.dll'))
        root = Path(os.environ['SystemRoot']) / 'System32'
        files.extend((root / 'whoami.exe', root / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'))
    rows = []
    for p in sorted(set(files), key=lambda x: str(x).casefold()):
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1048576), b''):
                h.update(block)
        rows.append((str(p), h.hexdigest()))
    if not rows:
        raise ValueError
    return core.digest(core.encode(rows))
def prepare(registry, sidecar, *, credential_path, selected_user, approval_reference, platform):
    """Local proof and deterministic pre-read binding. Does not authorize a read."""
    registry, sidecar, credential = Path(registry), Path(sidecar), Path(credential_path)
    c._identity(approval_reference)
    if not isinstance(selected_user, str) or not selected_user:
        raise core.ContextError('GOOGLE_LOCAL_BLOCKED')
    if platform.validate((registry, sidecar, credential), selected_user) != selected_user:
        raise core.ContextError('GOOGLE_LOCAL_BLOCKED')
    state, journal = BoundedState(registry), recovery.Journal(sidecar)
    evidence = reconcile.inspect_local(state, journal)
    binding = {'registry':str(registry), 'sidecar':str(sidecar), 'credential':str(credential),
        'user':selected_user, 'approval':approval_reference, 'source':_source_binding(),
        'registry_sha':core.digest(evidence.original_bytes), 'sidecar_sha':core.digest(evidence.sidecar_bytes),
        'fixture_sha':evidence.fixture_digest, 'owner':evidence.original['owner'],
        'folder':evidence.original['folder'], 'documents':evidence.projected['documents'],
        'limits':{'drive':90,'about':1,'docs':28,'seconds':120}}
    return Preparation(core.digest(core.encode(binding)), registry, sidecar, credential,
                       selected_user, approval_reference, binding['registry_sha'], binding['sidecar_sha'])

def execute(preparation, *, approved_digest, platform, store, request_factory, monotonic, wall_clock):
    """One bounded read; injected seams are not live authority or a public CLI."""
    try:
        if not isinstance(preparation, Preparation) or approved_digest != preparation.digest:
            raise ValueError
        with platform.lock():
            start = monotonic()
            deadline = start + 120
            fresh = prepare(preparation.registry, preparation.sidecar,
                credential_path=preparation.credential, selected_user=preparation.selected_user,
                approval_reference=preparation.approval_reference, platform=platform)
            if fresh.digest != preparation.digest or monotonic() >= deadline:
                raise ValueError
            state, journal = BoundedState(preparation.registry), recovery.Journal(preparation.sidecar)
            evidence = reconcile.inspect_local(state, journal)
            if (core.digest(evidence.original_bytes) != preparation.registry_sha
                    or core.digest(evidence.sidecar_bytes) != preparation.sidecar_sha):
                raise ValueError
            token = load_unexpired_token(store, now=wall_clock(), lifetime=120)
            guarded = ReadOnlyHTTP(request_factory(token, folder=evidence.original['folder'],
                documents=set(evidence.projected['documents'].values())), folder=evidence.original['folder'],
                documents=set(evidence.projected['documents'].values()), monotonic=monotonic, deadline=deadline)
            guarded.verify_principal(evidence.original['owner'])
            plan = reconcile.plan_reconciliation(api.Transport(guarded), state, journal,
                                                  reviewed_code=preparation.digest)
            final = prepare(preparation.registry, preparation.sidecar,
                credential_path=preparation.credential, selected_user=preparation.selected_user,
                approval_reference=preparation.approval_reference, platform=platform)
            if final.digest != preparation.digest or monotonic() >= deadline:
                raise ValueError
            return Result('PASS', core.digest(core.encode({'preparation':preparation.digest, 'plan':plan.digest})))
    except core.ContextError as exc:
        allowed = {'AUTH_EXPIRED_REAUTH_APPROVAL_REQUIRED', 'GOOGLE_PRINCIPAL_BLOCKED',
                   'GOOGLE_LOCAL_LOCK_BLOCKED', 'GOOGLE_RECONCILIATION_LOCAL_BLOCKED',
                   'GOOGLE_RECONCILIATION_READ_BLOCKED', 'GOOGLE_WINDOWS_IDENTITY_BLOCKED',
                   'GOOGLE_PRIVATE_PATH_BLOCKED', 'GOOGLE_API_UNAVAILABLE',
                   'GOOGLE_READ_DEADLINE_EXCEEDED', 'GOOGLE_READ_BUDGET_EXHAUSTED'}
        category = str(exc)
        return Result('BLOCKED', reason=category if category in allowed else 'LOCAL_OR_READ_BLOCKED')
    except Exception:
        return Result('BLOCKED', reason='LOCAL_OR_READ_BLOCKED')

class WindowsPlatform:
    """Same-user local process guard; does not lock remote Google state."""
    def current_user(self):
        import csv, io, os, re, subprocess
        if os.name != 'nt':
            raise core.ContextError('GOOGLE_WINDOWS_REQUIRED')
        try:
            result = subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32' / 'whoami.exe'), '/user', '/fo', 'csv', '/nh'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW)
            row = next(csv.reader(io.StringIO(result.stdout.decode('utf-8-sig', errors='replace'))))
            sid = row[-1].strip()
            if not re.fullmatch(r'S-1-\d+(?:-\d+)+', sid):
                raise ValueError
            return sid
        except Exception:
            raise core.ContextError('GOOGLE_WINDOWS_IDENTITY_BLOCKED') from None

    def lock(self):
        from contextlib import contextmanager
        import ctypes, os
        @contextmanager
        def acquire():
            if os.name != 'nt':
                raise core.ContextError('GOOGLE_WINDOWS_REQUIRED')
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            kernel.CreateMutexW.restype = ctypes.c_void_p
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel.CloseHandle.restype = ctypes.c_int
            ctypes.set_last_error(0)
            handle = kernel.CreateMutexW(None, False, 'Global\\x-context-issue65-gate-r-v1')
            if not handle:
                raise core.ContextError('GOOGLE_LOCAL_LOCK_BLOCKED')
            if ctypes.get_last_error() == 183:
                kernel.CloseHandle(handle)
                raise core.ContextError('GOOGLE_LOCAL_LOCK_BLOCKED')
            try:
                yield
            finally:
                kernel.CloseHandle(handle)
        return acquire()

    def _check_private_acl(self, paths, sid):
        import base64, json, os, subprocess
        script = r'''$ErrorActionPreference = "Stop"
$inputData = [Console]::In.ReadToEnd() | ConvertFrom-Json
$allowed = @($inputData.sid, "S-1-5-18", "S-1-5-32-544")
foreach ($item in $inputData.paths) {
  if ([System.IO.Directory]::Exists($item)) { $acl = [System.IO.Directory]::GetAccessControl($item) } else { $acl = [System.IO.File]::GetAccessControl($item) }
  $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  if ($owner -ne $inputData.sid) { exit 2 }
  $rules = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
  foreach ($rule in $rules) {
    if ($rule.AccessControlType -eq [System.Security.AccessControl.AccessControlType]::Allow -and
        $rule.IdentityReference.Value -notin $allowed) { exit 3 }
  }
}
[Console]::Out.Write("OK")'''
        try:
            encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            payload = json.dumps({'sid':sid, 'paths':[str(p) for p in paths]}).encode('utf-8')
            result = subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'), '-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode == 0 and result.stdout == b'OK'
        except Exception:
            return False

    def validate(self, paths, selected_user):
        import os
        if self.current_user() != selected_user or len(paths) != 3:
            raise core.ContextError('GOOGLE_WINDOWS_IDENTITY_BLOCKED')
        try:
            profile = Path(os.environ['USERPROFILE']).resolve(strict=True)
            safe = tuple(reconcile._safe_path(path, suffix=suffix) for path, suffix in
                         zip(paths, ('.json', '.jsonl', '.dpapi')))
            if any(not p.is_file() or not p.resolve(strict=True).is_relative_to(profile) for p in safe):
                raise ValueError
            if any(os.path.samefile(safe[i], safe[j]) for i in range(3) for j in range(i)):
                raise ValueError
            if any((ancestor / '.git').exists() for p in safe for ancestor in p.parents):
                raise ValueError
            checked_paths = list(safe)
            for p in safe:
                for parent in p.parents:
                    checked_paths.append(parent)
                    if parent == profile:
                        break
            checked = tuple(dict.fromkeys(checked_paths))
            if not self._check_private_acl(checked, selected_user):
                raise ValueError
            return selected_user
        except Exception:
            raise core.ContextError('GOOGLE_PRIVATE_PATH_BLOCKED') from None

def worker_request(token, *, folder, documents):
    """Run each GET in an isolated process so the remaining deadline is hard."""
    import json, os, subprocess
    if not auth.safe(token):
        raise core.ContextError('GOOGLE_READ_BLOCKED')
    def request(service, method, path, *, query=None, body=None, timeout=None):
        checker = ReadOnlyHTTP(lambda *a, **k: None, folder=folder, documents=documents,
                               monotonic=lambda: 0, deadline=1)
        checker._verified = path != 'about'
        checker.request(service, method, path, query=query, body=body)
        if (method != 'GET' or body is not None or service not in ('drive', 'docs')
                or not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or timeout <= 0 or timeout > 30):
            raise core.ContextError('GOOGLE_READ_BLOCKED')
        try:
            payload = core.encode({'service':service, 'path':path, 'query':query,
                                   'token':token, 'timeout':timeout})
            kwargs = {'input':payload, 'stdout':subprocess.PIPE, 'stderr':subprocess.PIPE,
                      'timeout':timeout, 'check':True}
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
            worker = Path(__file__).with_name('google_gate_r_worker.py')
            result = subprocess.run([sys.executable, '-I', str(worker)], **kwargs)
            if len(result.stdout) > api.LIMIT:
                raise ValueError
            value = core.decode(result.stdout)
            if not isinstance(value, dict):
                raise ValueError
            return value
        except Exception:
            raise core.ContextError('GOOGLE_API_UNAVAILABLE') from None
    return request

def main(argv=None, *, stdout=None):
    import argparse, re, time
    stdout = sys.stdout if stdout is None else stdout
    class SafeParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError
    try:
        parser = SafeParser(add_help=False, exit_on_error=False)
        parser.add_argument('operation', choices=('prepare','execute'))
        for flag in ('registry','sidecar','credential','user-sid','approval-reference'):
            parser.add_argument('--' + flag, required=True)
        parser.add_argument('--approval-digest')
        args = parser.parse_args(argv)
        if ((args.operation == 'prepare' and args.approval_digest is not None)
                or (args.operation == 'execute' and
                    (not args.approval_digest or not re.fullmatch(r'[0-9a-f]{64}', args.approval_digest)))):
            raise ValueError
        platform = WindowsPlatform()
        with platform.lock():
            preparation = prepare(args.registry, args.sidecar, credential_path=args.credential,
                                  selected_user=args.user_sid, approval_reference=args.approval_reference,
                                  platform=platform)
        if args.operation == 'prepare':
            print('PREPARED ' + preparation.digest, file=stdout)
            return 0
        result = execute(preparation, approved_digest=args.approval_digest, platform=platform,
                         store=auth.Store(preparation.credential), request_factory=worker_request,
                         monotonic=time.monotonic, wall_clock=time.time)
        if result.status == 'PASS':
            print('PASS ' + result.digest, file=stdout)
            return 0
        print('BLOCKED ' + result.reason, file=stdout)
        return 1
    except Exception:
        pass
    print('BLOCKED LOCAL_OR_READ_BLOCKED', file=stdout)
    return 1

if __name__ == '__main__':
    sys.exit(main())
