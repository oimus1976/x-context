"""App-created synthetic-only Drive publisher. Explicit one-shot operations."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import uuid

from . import core, drive, fixtures, connector as c, google_api as api, google_auth as auth

FOLDER_TITLE = 'SYNTHETIC-XCTX-APP-v1'
ROLES = {drive.CURRENT, *(drive.PREFIX+rid for rid in fixtures.IDS)}


def empty_state():
    return dict(schema='1',namespace='',folder='',parent='',owner='',documents={},pending=[])


def validate_state(value):
    try:
        if not isinstance(value,dict) or set(value) != set(empty_state()) or value['schema'] != '1':
            raise ValueError
        if not isinstance(value['documents'],dict) or not isinstance(value['pending'],list) or len(value['pending']) > 100:
            raise ValueError
        if len(value['documents']) > 6 or not set(value['documents']) <= ROLES:
            raise ValueError
        ids=list(value['documents'].values())
        if len(set(ids)) != len(ids):
            raise ValueError
        for identity in ids:
            c._identity(identity)
        if value['folder']:
            for key in ('folder','parent','owner','namespace'):
                c._identity(value[key])
            if value['folder'] in {value['parent'], c.SANDBOX, c.POC, c.SENTINEL} or value['folder'] in ids or value['parent'] in ids:
                raise ValueError
        elif value['documents'] or value['parent'] or value['owner'] or value['namespace'] and not value['pending']:
            raise ValueError
        for entry in value['pending']:
            if (not isinstance(entry,(tuple,list)) or len(entry) != 2 or not isinstance(entry[0],str)
                    or entry[1] not in {'FOLDER_CREATE_ATTEMPT','CREATED_EMPTY_UNVERIFIED','CREATE_ATTEMPT','CONTENT_ATTEMPTED','UPDATE_ATTEMPT'}):
                raise ValueError
            if entry[0]:
                c._identity(entry[0])
        return value
    except Exception:
        raise core.ContextError('GOOGLE_PUBLICATION_STATE_ERROR') from None


class State:
    def __init__(self,path):
        self.path=Path(path)

    def load(self):
        try:
            if any(p.is_symlink() or p.is_junction() for p in (self.path,*self.path.parents)):
                raise ValueError
            if not self.path.exists():
                return empty_state()
            data=self.path.read_bytes()
            if len(data)>65536:
                raise ValueError
            return validate_state(core.decode(data))
        except Exception:
            raise core.ContextError('GOOGLE_PUBLICATION_STATE_ERROR') from None

    def save(self,value):
        auth.atomic_write(self.path,core.encode(validate_state(value)))


class AppBackend(c.Backend):
    """Reuse synthetic body/receipt/conditional update checks, new target contract.

    Registry is authoritative local app identity, not a global folder inventory.
    Single publisher; pending journal must be inspected before another instance.
    """
    def __init__(self,transport,state):
        self.state_store=state
        self.state=copy.deepcopy(validate_state(state.load()))
        if self.state['pending']:
            raise core.ContextError('GOOGLE_EFFECT_REQUIRES_INSPECTION')
        super().__init__(transport,self._journal)
        self.target=self.state['folder']
        self.owner=self.state['owner'] or None

    def _save(self):
        self.state_store.save(copy.deepcopy(validate_state(self.state)))

    def _journal(self,entry):
        self.state['pending'].append(entry)
        self._save()

    def _properties(self,role):
        return dict(x_context='synthetic_v1',namespace=self.state['namespace'],role=role)

    def _managed(self,identity,role):
        metadata=self.transport.metadata(identity)
        if metadata.get('appProperties') != self._properties(role) or metadata.get('isAppAuthorized') is not True:
            raise core.ContextError('UNMANAGED_GOOGLE_ID')
        if role != 'folder' and self.state['documents'].get(role) != identity:
            raise core.ContextError('UNMANAGED_GOOGLE_ID')

    def folder(self,folder_id):
        if self.failed or not self.target or folder_id != self.target:
            raise core.ContextError('UNSUPPORTED_GOOGLE_TARGET')
        self._managed(folder_id,'folder')
        item=self.transport.read(folder_id)
        if (c._owner(item) != self.state['owner'] or item.id != folder_id or item.title != FOLDER_TITLE
                or item.parents != (self.state['parent'],) or item.mime != c.FOLDER):
            raise core.ContextError('UNSAFE_GOOGLE_TARGET')
        self.owner=self.state['owner']
        return folder_id,True

    def initialize(self):
        """Explicit new sandbox create. No adoption by title or connector target."""
        if self.target:
            self.folder(self.target)
            return self.target
        try:
            self.state['namespace']=uuid.uuid4().hex
            self._stage('','FOLDER_CREATE_ATTEMPT')
            identity=self.transport.create(FOLDER_TITLE,c.FOLDER,self._properties('folder'))
            self._stage(identity,'CREATED_EMPTY_UNVERIFIED')
            item=self.transport.read(identity)
            owner=c._owner(item)
            if item.id != identity or item.mime != c.FOLDER or item.title != FOLDER_TITLE or len(item.parents)!=1:
                raise core.ContextError('UNSAFE_GOOGLE_TARGET')
            self.state.update(folder=identity,parent=item.parents[0],owner=owner)
            self.target=identity
            self._managed(identity,'folder')
            self.folder(identity)
            if self.transport.children(identity).items:
                raise core.ContextError('UNEXPECTED_GOOGLE_CHILD')
            self.state['pending']=[]
            self._save()
            return identity
        except Exception:
            self.failed=True
            raise core.ContextError('GOOGLE_EFFECT_REQUIRES_INSPECTION') from None

    def _read(self,identity,parent):
        role=next((title for title,known in self.state['documents'].items() if known==identity),None)
        if role is None or parent != self.target:
            raise core.ContextError('UNMANAGED_GOOGLE_ID')
        self._managed(identity,role)
        doc,revision=super()._read(identity,parent)
        if doc.title != role:
            raise core.ContextError('UNMANAGED_GOOGLE_ID')
        return doc,revision

    def list(self,folder_id):
        self.folder(folder_id)
        inventory=self.transport.children(folder_id)
        if not isinstance(inventory,c.Inventory) or inventory.complete is not True or not isinstance(inventory.items,tuple):
            raise core.ContextError('APP_VISIBLE_INVENTORY_UNAVAILABLE')
        ids=[v.id for v in inventory.items]
        if len(set(ids))!=len(ids) or set(ids)!=set(self.state['documents'].values()):
            raise core.ContextError('UNEXPECTED_GOOGLE_CHILD')
        docs=[]
        for item in inventory.items:
            doc,revision=self._read(item.id,folder_id)
            if self.transport.read(item.id)!=item:
                raise core.ContextError('CONCURRENT_DRIVE_CHANGE')
            docs.append(doc)
        return docs

    def create(self,folder_id,title,body):
        self.folder(folder_id)
        self._allowed(title,body)
        if title in self.state['documents'] or any(d.title==title for d in self.list(folder_id)):
            raise core.ContextError('UNEXPECTED_GOOGLE_CHILD')
        try:
            self._stage('','CREATE_ATTEMPT')
            identity=self.transport.create(title,drive.MIME,self._properties(title),folder_id)
            self._stage(identity,'CREATED_EMPTY_UNVERIFIED')
            if identity in {self.target,self.state['parent'],c.SANDBOX,c.POC,c.SENTINEL,*self.state['documents'].values()}:
                raise core.ContextError('UNMANAGED_GOOGLE_ID')
            self.state['documents'][title]=identity
            self._save()
            empty,revision=self._read(identity,folder_id)
            if empty.body != '' or empty.title != title:
                raise core.ContextError('GOOGLE_CREATED_DOC_NOT_EMPTY')
            self.list(folder_id)
            self._stage(identity,'CONTENT_ATTEMPTED')
            self.transport.replace_text(identity,body,revision)
            actual=self.read(identity)
            if actual.body!=body or actual.title!=title:
                raise core.ContextError('DRIVE_READBACK_MISMATCH')
            return actual
        except Exception:
            self.failed=True
            raise core.ContextError('GOOGLE_EFFECT_REQUIRES_INSPECTION') from None


def publish(backend,records,plan):
    result=drive.apply(backend,backend.target,records,plan)
    if result.status=='COMPLETE' and backend.state['pending']:
        try:
            # drive.apply already performed final inventory/body/current readback.
            backend.state['pending']=[]
            backend._save()
        except Exception:
            backend.failed=True
            return drive.Result('PARTIAL_UNPUBLISHED',result.writes_attempted)
    return result


def default_paths():
    if os.name!='nt':
        raise core.ContextError('GOOGLE_WINDOWS_REQUIRED')
    root=os.environ.get('LOCALAPPDATA')
    if not root or not Path(root).is_absolute() or not Path(root).is_dir():
        raise core.ContextError('INVALID_GOOGLE_CONFIGURATION')
    folder=Path(root)/'x-context'/'google-drive'
    return folder/'credential-v1.dpapi',folder/'publication-v1.json'


class Parser(argparse.ArgumentParser):
    def error(self,message):
        raise core.ContextError('INVALID_COMMAND')


def main(argv=None):
    try:
        parser=Parser(description='Synthetic-only app-scoped Google Drive publisher. Initial OAuth needs separate owner approval.')
        parser.add_argument('mode',choices=('plan-auth','login','init-sandbox','publish'))
        parser.add_argument('--synthetic-fixtures',choices=fixtures.NAMES)
        parser.add_argument('--dry-run',action='store_true')
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--approve-new-auth',action='store_true')
        parser.add_argument('--reauthorize',action='store_true')
        parser.add_argument('--client-config')
        args=parser.parse_args(argv)
        records=None
        if args.mode=='publish':
            if not args.synthetic_fixtures or args.dry_run==args.apply or args.approve_new_auth or args.client_config or args.reauthorize:
                raise core.ContextError('INVALID_COMMAND')
            records=core.normalize(core.load_fixture(args.synthetic_fixtures))
        elif args.mode=='login':
            if not args.approve_new_auth or not args.client_config or args.apply or args.dry_run or args.synthetic_fixtures:
                raise core.ContextError('GOOGLE_BOOTSTRAP_OWNER_APPROVAL_REQUIRED')
        elif args.mode=='init-sandbox':
            if not args.apply or args.dry_run or args.approve_new_auth or args.client_config or args.synthetic_fixtures or args.reauthorize:
                raise core.ContextError('INVALID_COMMAND')
        elif args.apply or args.dry_run or args.approve_new_auth or args.client_config or args.synthetic_fixtures or args.reauthorize:
            raise core.ContextError('INVALID_COMMAND')
        if args.mode=='plan-auth':
            result=dict(status='LIVE_GOOGLE_AUTH_PENDING',scope=auth.SCOPE,account_project='OWNER_SELECTION_REQUIRED',
                        credential_storage='%LOCALAPPDATA%/x-context/google-drive/credential-v1.dpapi',
                        guide='docs/specs/0008-unattended-drive-publisher.md',external_testing_refresh_days=7)
        elif args.mode=='login':
            # Explicit consent renews auth only; never open the publication journal.
            credential_path,_=default_paths()
            auth.bootstrap(auth.Store(credential_path),args.client_config,
                           approved=args.approve_new_auth,reauthorize=args.reauthorize)
            result=dict(status='GOOGLE_AUTHORIZED',scope=auth.SCOPE)
        else:
            credential_path,state_path=default_paths()
            state=State(state_path)
            # Drive operations must stop before auth load/refresh or network.
            validated=state.load()
            if validated['pending']:
                raise core.ContextError('GOOGLE_EFFECT_REQUIRES_INSPECTION')
            store=auth.Store(credential_path)
            if args.mode=='publish' and not validated['folder']:
                raise core.ContextError('GOOGLE_SANDBOX_INITIALIZATION_REQUIRED')
            if store.load() is None:
                raise core.ContextError('LIVE_GOOGLE_AUTH_PENDING')
            backend=AppBackend(api.Transport(api.HTTP(auth.Provider(store).access_token)),state)
            if args.mode=='init-sandbox':
                result=dict(status='GOOGLE_SANDBOX_INITIALIZED',folder=backend.initialize(),inventory_scope='APP_VISIBLE')
            else:
                plan=drive.preview(backend,backend.target,records)
                if args.dry_run:
                    result=dict(status='PREVIEW',folder=backend.target,inventory_scope='APP_VISIBLE',remote_content_writes=0)
                else:
                    outcome=publish(backend,records,plan)
                    result=dict(status=outcome.status,folder=backend.target,writes_attempted=outcome.writes_attempted,inventory_scope='APP_VISIBLE')
                    if outcome.status!='COMPLETE':
                        print(json.dumps(result,sort_keys=True),file=sys.stderr)
                        return 2
        print(json.dumps(dict(x_requests_attempted=0,**result),sort_keys=True))
        return 0
    except core.ContextError as error:
        print(json.dumps(dict(error=str(error),x_requests_attempted=0)),file=sys.stderr)
        return 2
    except Exception:
        print(json.dumps(dict(error='GOOGLE_OPERATION_UNAVAILABLE',x_requests_attempted=0)),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
