"""Issue62 synthetic API/lifecycle contracts; no Google credentials/network."""
import copy
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from x_context.shared_context import core, drive, connector as c
from x_context.shared_context import google_api as api, google_auth as auth, google_publish as pub


class FakeAPI:
    def __init__(self):
        self.files = {}
        self.text = {}
        self.rev = {}
        self.calls = []
        self.effects = []
        self.incomplete = False
        self.extra_page = False
        self.fail = False
        self.owner = 'FAKE-OWNER'

    def request(self, service, method, path, *, query=None, body=None):
        query = query or {}
        self.calls.append((service, method, path, query, body))
        if self.fail:
            raise RuntimeError('FAKE-SECRET provider details')
        if service == 'drive':
            if method == 'POST':
                identity = 'FAKE-' + str(len(self.files) + 1)
                item = dict(id=identity, name=body['name'], mimeType=body['mimeType'],
                            parents=body.get('parents', ['FAKE-ROOT']), shared=False,
                            trashed=False, isAppAuthorized=True, appProperties=body['appProperties'])
                self.files[identity] = item
                self.text[identity] = '\n'
                self.rev[identity] = 'REV-1'
                self.effects.append(('create', identity))
                return copy.deepcopy(item)
            if path == 'files':
                folder = query['q'].split("'")[1]
                children = [copy.deepcopy(v) for v in self.files.values() if folder in v['parents']]
                if self.extra_page and 'pageToken' not in query:
                    return dict(files=[], nextPageToken='FAKE-PAGE', incompleteSearch=self.incomplete)
                return dict(files=children, incompleteSearch=self.incomplete)
            identity = path.split('/')[1]
            if path.endswith('/permissions'):
                return dict(permissions=[dict(id=self.owner, type='user', role='owner')])
            return copy.deepcopy(self.files[identity])
        identity = path.split('/')[1].split(':')[0]
        if method == 'GET':
            text = self.text[identity]
            end = len(text.encode('utf-16-le')) // 2 + 1
            return dict(documentId=identity, title=self.files[identity]['name'], revisionId=self.rev[identity],
                        tabs=[dict(tabProperties=dict(tabId='TAB'), documentTab=dict(body=dict(content=[
                            dict(startIndex=0, endIndex=1, sectionBreak={}),
                            dict(startIndex=1, endIndex=end, paragraph=dict(elements=[
                                dict(startIndex=1, endIndex=end, textRun=dict(content=text))]))])))] )
        if body['writeControl']['requiredRevisionId'] != self.rev[identity]:
            raise RuntimeError('FAKE revision conflict')
        inserted = next(v['insertText']['text'] for v in body['requests'] if 'insertText' in v)
        self.text[identity] = inserted + '\n'
        self.rev[identity] += '-NEXT'
        self.effects.append(('text', identity))
        return {}


class MemoryState:
    def __init__(self):
        self.value = pub.empty_state()
    def save(self, value):
        self.value = copy.deepcopy(value)
    def load(self):
        return copy.deepcopy(self.value)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.http = FakeAPI()
        self.state = MemoryState()
        self.backend = pub.AppBackend(api.Transport(self.http), self.state)
        self.folder = self.backend.initialize()
        self.records = core.normalize(core.load_fixture('baseline'))

    def publish(self, name='baseline', backend=None):
        backend = backend or self.backend
        records = core.normalize(core.load_fixture(name))
        plan = drive.preview(backend, self.folder, records)
        return pub.publish(backend, records, plan)

    def test_A030506_first_repeat_edit_withdraw_restore_new_process(self):
        self.assertEqual(self.publish(), drive.Result('COMPLETE', 6))
        original_ids = dict(self.state.value['documents'])
        for name in ('baseline', 'edited', 'withdrawn', 'baseline'):
            # Every invocation has a fresh backend/transport with persisted registry.
            fresh = pub.AppBackend(api.Transport(self.http), self.state)
            self.http.effects.clear()
            result = self.publish(name, fresh)
            self.assertEqual(result.status, 'COMPLETE')
            self.assertEqual(result.writes_attempted, 0 if name == 'baseline' and not self.http.effects else 2)
            self.assertEqual(self.state.value['documents'], original_ids)
            if name != 'baseline':
                titles = [self.http.files[i]['name'] for op, i in self.http.effects]
                self.assertEqual(titles, [drive.PREFIX + 'SYN-XCTX-P001', drive.CURRENT])
            if name == 'withdrawn':
                index = drive.parse_index(self.http.text[original_ids[drive.CURRENT]][:-1])
                self.assertNotIn('SYN-XCTX-P001', index['active_ids'])
                self.assertNotIn('fictional process-transcription', self.http.text[original_ids[drive.PREFIX+'SYN-XCTX-P001']])
        self.assertEqual(self.state.value['pending'], [])

    def test_A05_current_last_and_preview_zero_effect(self):
        self.http.effects.clear()
        plan = drive.preview(self.backend, self.folder, self.records)
        self.assertEqual(self.http.effects, [])
        self.assertEqual(pub.publish(self.backend, self.records, plan).status, 'COMPLETE')
        self.assertEqual(self.http.files[self.http.effects[-1][1]]['name'], drive.CURRENT)
        self.assertTrue(all(v['parents'] == [self.folder] for v in self.http.files.values() if v['mimeType'] == drive.MIME))
        for service, method, path, query, body in self.http.calls:
            if method == 'POST' and service == 'docs':
                self.assertIn('requiredRevisionId', body['writeControl'])

    def test_A04_empty_page_next_token_and_all_mime(self):
        self.http.extra_page = True
        drive.preview(self.backend, self.folder, self.records)
        lists = [q for s,m,p,q,b in self.http.calls if p == 'files' and m == 'GET']
        self.assertTrue(any(q.get('pageToken') == 'FAKE-PAGE' for q in lists))
        self.assertTrue(all('mimeType' not in q['q'] and q['corpora'] == 'user' for q in lists))

    def test_A0304_bad_scope_metadata_unknown_children_block(self):
        for key, value in [('shared',True),('isAppAuthorized',False),('appProperties',{}),('parents',['OTHER']),('trashed',True)]:
            with self.subTest(key=key):
                old = copy.deepcopy(self.http.files[self.folder])
                self.http.files[self.folder][key] = value
                self.http.effects.clear()
                with self.assertRaises(core.ContextError):
                    drive.preview(self.backend,self.folder,self.records)
                self.assertEqual(self.http.effects,[])
                self.http.files[self.folder] = old
        self.http.incomplete = True
        with self.assertRaises(core.ContextError):
            drive.preview(self.backend,self.folder,self.records)
        self.http.incomplete = False
        self.http.files['UNKNOWN'] = dict(self.http.files[self.folder],id='UNKNOWN',parents=[self.folder],mimeType='text/plain')
        with self.assertRaises(core.ContextError):
            drive.preview(self.backend,self.folder,self.records)

    def test_A05_race_rejected_no_adopt_revision(self):
        self.publish()
        plan = drive.preview(self.backend,self.folder,core.load_fixture('edited'))
        identity = self.state.value['documents'][drive.PREFIX+'SYN-XCTX-P001']
        self.http.text[identity] = 'SYNTHETIC TEST DATA concurrent\n'
        self.http.rev[identity] += '-RACE'
        self.http.effects.clear()
        self.assertEqual(pub.publish(self.backend,core.load_fixture('edited'),plan).status,'BLOCKED')
        self.assertEqual(self.http.effects,[])

    def test_A05_ambiguous_effect_pending_blocks_new_process(self):
        plan = drive.preview(self.backend,self.folder,self.records)
        original = self.http.request
        def fail_after_create(service,method,path,**kwargs):
            value = original(service,method,path,**kwargs)
            if method == 'POST':
                raise RuntimeError('FAKE secret timeout after effect')
            return value
        self.http.request = fail_after_create
        self.assertEqual(pub.publish(self.backend,self.records,plan).status,'PARTIAL_UNPUBLISHED')
        self.assertTrue(self.state.value['pending'])
        with self.assertRaises(core.ContextError):
            pub.AppBackend(api.Transport(self.http),self.state)
        self.assertEqual(len(self.http.effects),2) # folder plus ambiguous Doc

    def test_A03_registry_id_replacement_rejected(self):
        self.publish()
        identity = self.state.value['documents'][drive.CURRENT]
        item = self.http.files.pop(identity)
        self.http.files['STOLEN'] = dict(item,id='STOLEN')
        with self.assertRaises(core.ContextError):
            drive.preview(self.backend,self.folder,self.records)

    def test_A05_nonfixture_content_zero_write(self):
        self.http.effects.clear()
        with self.assertRaises(core.ContextError):
            self.backend.create(self.folder,drive.PREFIX+'SYN-XCTX-P001','SYNTHETIC TEST DATA unapproved')
        self.assertEqual(self.http.effects,[])


class NativeTests(unittest.TestCase):
    def doc(self,text):
        fake = FakeAPI()
        fake.files['DOC'] = dict(name='test')
        fake.text['DOC'],fake.rev['DOC'] = text,'R'
        return fake.request('docs','GET','documents/DOC')

    def test_A05_unicode_blank_and_trailing_newlines_utf16(self):
        for text in ('\n','hello\n\n','日本語😀\n\n\n'):
            self.assertEqual(api.parse_document(self.doc(text),'DOC')[0],text[:-1])
        http = FakeAPI()
        http.files['DOC'] = dict(name='test')
        http.text['DOC'],http.rev['DOC'] = '😀\n\n','R'
        api.Transport(http).replace_text('DOC','日本語😀\n\n','R')
        reqs = http.calls[-1][-1]['requests']
        self.assertEqual(reqs[0]['deleteContentRange']['range']['endIndex'],4)
        self.assertEqual(http.text['DOC'],'日本語😀\n\n\n')

    def test_A05_unsupported_structure_rejected(self):
        for kind in ('tabs','headers','table','suggestion','inline'):
            value = self.doc('hello\n')
            tab = value['tabs'][0]['documentTab']
            if kind == 'tabs': value['tabs'].append(copy.deepcopy(value['tabs'][0]))
            if kind == 'headers': tab['headers'] = {'bad':{}}
            if kind == 'table': tab['body']['content'].append(dict(table={}))
            if kind == 'suggestion': tab['body']['content'][1]['paragraph']['elements'][0]['suggestedInsertionIds']=['BAD']
            if kind == 'inline': tab['body']['content'][1]['paragraph']['elements'][0]={'inlineObjectElement':{}}
            with self.subTest(kind=kind),self.assertRaises(core.ContextError): api.parse_document(value,'DOC')

    def test_A04_pagination_duplicate_cycle_missing_receipt(self):
        for variant in ('cycle','duplicate','missing','incomplete'):
            class Bad:
                def request(self,*args,**kwargs):
                    if variant == 'cycle': return dict(files=[],incompleteSearch=False,nextPageToken='SAME')
                    if variant == 'duplicate': return dict(files=[dict(id='D'),dict(id='D')],incompleteSearch=False)
                    if variant == 'missing': return dict(files=[])
                    return dict(files=[],incompleteSearch=True)
            with self.subTest(variant=variant),self.assertRaises(core.ContextError):
                api.Transport(Bad()).children('FOLDER')

    def test_A02_http_fixed_hosts_redirection_size_errors_redacted(self):
        client = api.HTTP(lambda:'FAKE-TOKEN')
        with self.assertRaises(core.ContextError): client.request('evil','GET','files')
        with self.assertRaises(core.ContextError): client.request('drive','GET','../evil')
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self,n): return b'x'*n
        with patch('x_context.shared_context.google_api.build_opener') as opener:
            opener.return_value.open.return_value = Response()
            with self.assertRaises(core.ContextError): client.request('drive','GET','files')
        self.assertEqual(api.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.invalid'),None)


class MemoryCredential:
    def __init__(self, value): self.value = value
    def load(self): return self.value
    def save(self,value): self.value=value


class AuthTests(unittest.TestCase):
    def record(self):
        return auth.Credential('FAKE-ID.apps.googleusercontent.com','FAKE-CLIENT','FAKE-ACCESS','FAKE-REFRESH',1000,(auth.SCOPE,))

    def test_A0207_refresh_new_instance_no_browser_retains_refresh(self):
        store = MemoryCredential(self.record())
        calls=[]
        def token(form):
            calls.append(form)
            return dict(access_token='FAKE-NEW',expires_in=3600,token_type='Bearer',scope=auth.SCOPE)
        provider = auth.Provider(store,token,clock=lambda:900)
        self.assertEqual(provider.access_token(),'FAKE-NEW')
        self.assertEqual(store.value.refresh_token,'FAKE-REFRESH')
        self.assertEqual(len(calls),1)
        self.assertEqual(auth.Provider(store,token,clock=lambda:901).access_token(),'FAKE-NEW')
        self.assertEqual(len(calls),1)
        self.assertNotIn('FAKE-REFRESH',repr(store.value))

    def test_A02_scope_widen_failure_preserves_credentials_redacted(self):
        store=MemoryCredential(self.record()); old=store.value
        for payload in (dict(access_token='FAKE',expires_in=3600,token_type='Bearer',scope='https://www.googleapis.com/auth/drive'),{},dict(error='invalid_grant')):
            with self.assertRaises(core.ContextError) as caught:
                auth.Provider(store,lambda f:payload,clock=lambda:900).access_token()
            self.assertNotIn('invalid_grant',str(caught.exception))
            self.assertIs(store.value,old)
        with self.assertRaises(core.ContextError): replace(old,scopes=('drive',))

    def test_A02_protected_roundtrip_and_no_plaintext(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'google.dpapi'
            # Real Windows DPAPI for synthetic credential only; fake elsewhere.
            if os.name == 'nt': store=auth.Store(path)
            else: store=auth.Store(path,protect=lambda b:b[::-1],unprotect=lambda b:b[::-1])
            store.save(self.record())
            self.assertEqual(store.load(),self.record())
            self.assertNotIn(b'FAKE-REFRESH',path.read_bytes())
            before=path.read_bytes()
            with patch.object(store,'protect',side_effect=RuntimeError('FAKE-SECRET')):
                with self.assertRaises(core.ContextError):store.save(replace(self.record(),access_token='FAKE-NEW'))
            self.assertEqual(path.read_bytes(),before)

    def test_A02_authorization_plan_exact_scope_pkce_offline(self):
        plan=auth.authorization(self.record().client_id,'http://127.0.0.1:12345/','STATE','V'*43)
        from urllib.parse import urlparse,parse_qs
        values=parse_qs(urlparse(plan).query)
        self.assertEqual(values['scope'],[auth.SCOPE])
        self.assertEqual(values['access_type'],['offline'])
        self.assertEqual(values['code_challenge_method'],['S256'])
        self.assertEqual(values['include_granted_scopes'],['false'])
        self.assertEqual(values['state'],['STATE'])

    def test_A0102_cli_invalid_and_missing_auth_no_network(self):
        for argv in (['publish','--synthetic-fixtures','real','--apply'],['publish','--synthetic-fixtures','baseline','--apply'],['login']):
            with patch.object(pub,'default_paths',return_value=(Path('/nonexistent-google-credentials'),Path('/nonexistent-google-state'))),patch.object(auth,'bootstrap',side_effect=AssertionError('must not login')),patch.object(api.HTTP,'request',side_effect=AssertionError('must not network')),patch('sys.stdout',new_callable=io.StringIO),patch('sys.stderr',new_callable=io.StringIO) as err:
                self.assertEqual(pub.main(argv),2)
                self.assertNotIn('FAKE-SECRET',err.getvalue())

    def test_A03_state_unknown_schema_pending_or_duplicate_ids_reject(self):
        with tempfile.TemporaryDirectory() as root:
            state=pub.State(Path(root)/'state.json')
            state.save(pub.empty_state())
            self.assertEqual(state.load(),pub.empty_state())
            for data in ({'schema':'bad'},dict(pub.empty_state(),pending=[['','CREATE_ATTEMPT']]),dict(pub.empty_state(),documents={'a':'ID','b':'ID'})):
                state.path.write_text(json.dumps(data),encoding='utf-8')
                with self.assertRaises(core.ContextError):pub.AppBackend(api.Transport(FakeAPI()),state)




class AbuseAndProcessTests(unittest.TestCase):
    def test_A04_permission_pagination_rejects_extra_owner_and_cycle(self):
        for variant in ('extra','cycle','missing','deleted'):
            class Permissions:
                def request(self,s,m,p,*,query=None,body=None):
                    owner=dict(id='OWNER',type='user',role='owner')
                    if variant=='missing': return {}
                    if variant=='cycle': return dict(permissions=[],nextPageToken='SAME')
                    if variant=='deleted': return dict(permissions=[dict(owner,deleted=True)])
                    if not query.get('pageToken'): return dict(permissions=[owner],nextPageToken='NEXT')
                    return dict(permissions=[dict(id='SECOND',type='user',role='reader')])
            with self.subTest(variant=variant),self.assertRaises(core.ContextError):
                api.Transport(Permissions()).permissions('ID')

    def test_A05_journal_write_failure_prevents_effect(self):
        fake=FakeAPI(); state=MemoryState(); backend=pub.AppBackend(api.Transport(fake),state)
        backend.initialize(); fake.effects.clear()
        plan=drive.preview(backend,backend.target,core.load_fixture('baseline'))
        state.save=lambda _: (_ for _ in ()).throw(RuntimeError('FAKE private path'))
        result=pub.publish(backend,core.load_fixture('baseline'),plan)
        self.assertEqual(result.status,'PARTIAL_UNPUBLISHED') # attempt counted, journal stops network effect
        self.assertEqual(fake.effects,[])

    def test_A05_final_readback_mismatch_preserves_pending(self):
        fake=FakeAPI(); state=MemoryState(); backend=pub.AppBackend(api.Transport(fake),state)
        backend.initialize()
        original=fake.request
        def corrupt(s,m,p,**kwargs):
            result=original(s,m,p,**kwargs)
            if s=='docs' and m=='POST':
                identity=p.split('/')[1].split(':')[0]
                fake.text[identity]='SYNTHETIC TEST DATA mismatch\n'
            return result
        fake.request=corrupt
        plan=drive.preview(backend,backend.target,core.load_fixture('baseline'))
        self.assertEqual(pub.publish(backend,core.load_fixture('baseline'),plan).status,'PARTIAL_UNPUBLISHED')
        self.assertTrue(state.value['pending'])
        with self.assertRaises(core.ContextError):pub.AppBackend(api.Transport(fake),state)

    def test_A05_revision_only_race_inside_update(self):
        fake=FakeAPI(); state=MemoryState(); backend=pub.AppBackend(api.Transport(fake),state)
        backend.initialize()
        records=core.load_fixture('baseline')
        pub.publish(backend,records,drive.preview(backend,backend.target,records))
        records=core.load_fixture('edited'); plan=drive.preview(backend,backend.target,records)
        original=backend.update
        def race(identity,body):
            fake.rev[identity]+='-RACE'
            return original(identity,body)
        backend.update=race; fake.effects.clear()
        self.assertEqual(pub.publish(backend,records,plan).status,'PARTIAL_UNPUBLISHED')
        self.assertEqual(fake.effects,[])

    def test_A0207_fresh_subprocess_refresh_noop_and_edit(self):
        import subprocess
        import sys
        script = '''
import sys,json
from pathlib import Path
sys.path.insert(0,'tests')
from test_shared_context_google import FakeAPI
from x_context.shared_context import google_auth as auth,google_publish as pub,google_api as api,core,drive
root=Path(sys.argv[1]); variant=sys.argv[2]
fake=FakeAPI()
cloud=root/'fake-cloud.json'
if cloud.exists():
    value=json.loads(cloud.read_text()); fake.files=value['files']; fake.text=value['text']; fake.rev=value['rev']
store=auth.Store(root/'fake.dpapi',protect=lambda b:b[::-1],unprotect=lambda b:b[::-1])
refresh=[]
def token(form):
    refresh.append(form['grant_type'])
    return dict(access_token='FAKE-NEW',expires_in=3600,token_type='Bearer',scope=auth.SCOPE)
provider=auth.Provider(store,token,clock=lambda:900)
provider.access_token()
backend=pub.AppBackend(api.Transport(fake),pub.State(root/'registry.json'))
folder=backend.initialize()
records=core.load_fixture(variant)
result=pub.publish(backend,records,drive.preview(backend,folder,records))
cloud.write_text(json.dumps(dict(files=fake.files,text=fake.text,rev=fake.rev)))
print(json.dumps(dict(status=result.status,writes=result.writes_attempted,refresh=len(refresh),ids=backend.state['documents'])))
'''
        with tempfile.TemporaryDirectory() as root:
            store=auth.Store(Path(root)/'fake.dpapi',protect=lambda b:b[::-1],unprotect=lambda b:b[::-1])
            store.save(AuthTests().record())
            results=[]
            for name in ('baseline','baseline','edited','withdrawn','baseline'):
                # Force expired access token before EACH independent process.
                store.save(replace(store.load(),expires_at=1000))
                completed=subprocess.run([sys.executable,'-c',script,root,name],capture_output=True,text=True,timeout=30)
                self.assertEqual(completed.returncode,0,completed.stderr)
                results.append(json.loads(completed.stdout))
            self.assertEqual([r['writes'] for r in results],[6,0,2,2,2])
            self.assertTrue(all(r['status']=='COMPLETE' and r['refresh']==1 for r in results))
            self.assertTrue(all(r['ids']==results[0]['ids'] for r in results))

    def test_A0102_cli_whole_flow_synthetic_stores_fake_api(self):
        fake=FakeAPI()
        with tempfile.TemporaryDirectory() as root:
            cp,sp=Path(root)/'credential.dpapi',Path(root)/'state.json'
            original=auth.Store
            def synthetic_store(path):return original(path,protect=lambda b:b[::-1],unprotect=lambda b:b[::-1])
            synthetic_store(cp).save(replace(AuthTests().record(),expires_at=9999999999))
            with patch.object(pub,'default_paths',return_value=(cp,sp)),patch.object(auth,'Store',side_effect=synthetic_store),patch.object(api,'HTTP',return_value=fake):
                commands=[['init-sandbox','--apply']]
                for name in ('baseline','edited','withdrawn'):
                    commands.extend([['publish','--synthetic-fixtures',name,'--dry-run'],['publish','--synthetic-fixtures',name,'--apply']])
                for command in commands:
                    before=len(fake.effects)
                    with patch('sys.stdout',new_callable=io.StringIO) as out:
                        self.assertEqual(pub.main(command),0)
                        self.assertEqual(json.loads(out.getvalue())['x_requests_attempted'],0)
                    if '--dry-run' in command:self.assertEqual(len(fake.effects),before)

    def test_A02_bootstrap_unapproved_stops_before_client_read(self):
        with patch.object(auth.Path,'read_bytes',side_effect=AssertionError('no client config read')),patch.object(auth.webbrowser,'open',side_effect=AssertionError('no browser')):
            with self.assertRaises(core.ContextError) as caught:
                auth.bootstrap(MemoryCredential(None),'/fake-config',approved=False)
            self.assertEqual(str(caught.exception),'GOOGLE_BOOTSTRAP_OWNER_APPROVAL_REQUIRED')




class BootstrapTests(unittest.TestCase):
    def run_bootstrap(self,callback='valid',payload=None,token_error=False,store_error=False,
                      client_values=None,metadata_rejected=False,callback_query=None,callback_suffix=''):
        from urllib.parse import parse_qs,urlparse,urlencode
        accepted=[]; codes=[]; token_calls=[]
        class Store:
            def load(self):return None
            def save(self,record):
                if store_error:raise RuntimeError('FAKE-SECRET store failure')
                accepted.append(record)
        url=[]
        class Server:
            def __init__(self,address,handler):self.handler=handler;self.server_port=12345;self.count=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def handle_request(self):
                self.count+=1
                fields=parse_qs(urlparse(url[0]).query)
                state=fields['state'][0]
                if callback=='wrong-state' or callback=='wrong-then-valid' and self.count==1:state='WRONG'
                query={'state':state,'code':'FAKE-CODE','iss':'https://accounts.google.com'}
                if callback=='denied':query={'state':state,'error':'access_denied'}
                if callback_query is not None:query=callback_query(query)
                handler=self.handler.__new__(self.handler)
                handler.path='/?'+urlencode(query,doseq=True)+callback_suffix
                handler.send_response=lambda code:codes.append(code)
                handler.end_headers=lambda:None
                handler.wfile=io.BytesIO()
                handler.do_GET()
        def exchange(form):
            token_calls.append(form)
            if token_error:raise RuntimeError('FAKE-SECRET provider failure')
            return payload if payload is not None else dict(access_token='FAKE-ACCESS',refresh_token='FAKE-REFRESH',expires_in=3600,token_type='Bearer',scope=auth.SCOPE)
        # Every input/output is fiction; fake server and browser perform no HTTP/UI.
        with tempfile.TemporaryDirectory() as root:
            client=Path(root)/'desktop.json'
            # Literal provider-shaped metadata deliberately does not use app constants.
            values=dict(client_id='FAKE-ID.apps.googleusercontent.com',project_id='FAKE-PROJECT',
                        client_secret='FAKE-CLIENT',auth_uri='https://accounts.google.com/o/oauth2/auth',
                        token_uri='https://oauth2.googleapis.com/token',
                        auth_provider_x509_cert_url='https://www.googleapis.com/oauth2/v1/certs',
                        redirect_uris=['http://localhost']) if client_values is None else client_values
            client.write_text(json.dumps({'installed':values}))
            with patch.object(auth,'HTTPServer',side_effect=Server) as server,patch.object(auth.webbrowser,'open',side_effect=lambda value:url.append(value) or True) as browser,patch.object(auth,'token_request',side_effect=exchange) as token,patch.object(auth.time,'monotonic',side_effect=[0,1,2,200]),patch.object(auth.time,'time',return_value=1000),patch.object(auth,'os',__import__('types').SimpleNamespace(name='nt')):
                try:
                    auth.bootstrap(Store(),str(client),approved=True)
                    error=None
                except core.ContextError as caught:
                    error=str(caught)
                if metadata_rejected:
                    server.assert_not_called();browser.assert_not_called();token.assert_not_called()
                    self.assertEqual(accepted,[])
                if error is None:
                    self.assertEqual(urlparse(url[0])._replace(query='').geturl(),
                                     'https://accounts.google.com/o/oauth2/v2/auth')
                    self.assertEqual(parse_qs(urlparse(url[0]).query)['scope'],
                                     ['https://www.googleapis.com/auth/drive.file'])
        return accepted,codes,token_calls,error

    def test_A02_bootstrap_google_issuer_callback(self):
        # Fictional Google-shaped response, independent of production constants.
        accepted,codes,calls,error=self.run_bootstrap(callback_query=lambda query:dict(
            query,iss='https://accounts.google.com',
            scope='https://www.googleapis.com/auth/drive.file',authuser='0',prompt='consent'))
        self.assertIsNone(error)
        self.assertEqual(codes,[200]);self.assertEqual(len(calls),1)
        self.assertEqual(len(accepted),1)
        self.assertEqual(calls[0]['code'],'FAKE-CODE')
        self.assertEqual(calls[0]['grant_type'],'authorization_code')
        self.assertEqual(calls[0]['redirect_uri'],'http://127.0.0.1:12345/')
        self.assertNotIn('iss',calls[0])
        self.assertEqual(accepted[0].scopes,('https://www.googleapis.com/auth/drive.file',))

    def assert_callback_rejected(self,**kwargs):
        accepted,codes,calls,error=self.run_bootstrap(**kwargs)
        self.assertEqual(codes,[400,400])
        self.assertEqual(calls,[]);self.assertEqual(accepted,[])
        self.assertEqual(error,'GOOGLE_BOOTSTRAP_FAILED')

    def test_A02_bootstrap_missing_or_hostile_issuer_no_exchange_or_save(self):
        self.assert_callback_rejected(callback_query=lambda query:{k:v for k,v in query.items() if k!='iss'})
        for issuer in ('','https://evil.example','http://accounts.google.com',
                       'HTTPS://accounts.google.com','https://ACCOUNTS.google.com',
                       'accounts.google.com','https://accounts.google.com/',
                       'https://accounts.google.com.evil.example','https://accounts.google.com.',
                       'https://accounts.google.com:443','https://user@accounts.google.com',
                       'https://accounts.google.com@evil.example','https://accounts.google.com/path',
                       'https://accounts.google.com?','https://accounts.google.com#',
                       ' https://accounts.google.com','https://accounts.google.com\n',
                       'https://accounts.google.com\x00','https%3A%2F%2Faccounts.google.com'):
            with self.subTest(issuer=issuer):
                self.assert_callback_rejected(callback_query=lambda query:dict(query,iss=issuer))

    def test_A02_bootstrap_duplicate_callback_parameters_no_exchange_or_save(self):
        for key,value in (('state',None),('code','FAKE-CODE'),('iss','https://accounts.google.com'),
                          ('scope','https://www.googleapis.com/auth/drive.file'),('authuser','0'),
                          ('prompt','consent')):
            for blank in (False,True):
                with self.subTest(key=key,blank=blank):
                    def duplicate(query):
                        first=query['state'] if key=='state' else value
                        return dict(query,**{key:[first,'' if blank else first]})
                    self.assert_callback_rejected(callback_query=duplicate)
        # Encoded names must collapse before duplicate-key validation.
        self.assert_callback_rejected(callback_suffix='&%69ss=https%3A%2F%2Faccounts.google.com')

    def test_A02_bootstrap_unknown_callback_parameters_no_exchange_or_save(self):
        for suffix in ('&unknown=FAKE','&unknown=','&unknown','&ISS=https%3A%2F%2Faccounts.google.com'):
            with self.subTest(suffix=suffix):
                self.assert_callback_rejected(callback_suffix=suffix)

    def test_A02_bootstrap_official_auth_uri_metadata(self):
        for uri in ('https://accounts.google.com/o/oauth2/auth',
                    'https://accounts.google.com/o/oauth2/v2/auth'):
            with self.subTest(auth_uri=uri):
                values=dict(client_id='FAKE-ID.apps.googleusercontent.com',client_secret='FAKE-CLIENT',
                            auth_uri=uri,token_uri='https://oauth2.googleapis.com/token',
                            project_id='FAKE-PROJECT',redirect_uris=['http://localhost'])
                accepted,codes,calls,error=self.run_bootstrap(client_values=values)
                self.assertIsNone(error)
                self.assertEqual(codes,[200]);self.assertEqual(len(calls),1)
                self.assertEqual(len(accepted),1)
                self.assertEqual(accepted[0].scopes,('https://www.googleapis.com/auth/drive.file',))

    def test_A02_bootstrap_hostile_auth_uri_metadata_zero_effects(self):
        for suffix in ('auth','v2/auth'):
            good='https://accounts.google.com/o/oauth2/'+suffix
            bad=[None,False,42,[],{},'',good.replace('https:','http:'),
                 good.replace('accounts.google.com','accounts.google.com.evil.example'),
                 good.replace('accounts.google.com','evil.example'),
                 good.replace('accounts.google.com','accounts.google.com:443'),
                 good.replace('accounts.google.com','user@accounts.google.com'),
                 good.replace('accounts.google.com','accounts.google.com@evil.example'),
                 good.replace('accounts.google.com','accounts.google.com.'),
                 good.replace('/o/oauth2/','/unknown/'),good+'/',good+'?scope=evil',
                 good+'?',good+'#fragment',good+'#',' '+good,good+'\n',
                 good.replace('/auth','/%61uth')]
            for uri in bad:
                with self.subTest(auth_uri=uri):
                    values=dict(client_id='FAKE-ID.apps.googleusercontent.com',client_secret='FAKE-CLIENT',
                                auth_uri=uri,token_uri='https://oauth2.googleapis.com/token')
                    accepted,codes,calls,error=self.run_bootstrap(client_values=values,metadata_rejected=True)
                    self.assertEqual(error,'GOOGLE_BOOTSTRAP_FAILED')
                    self.assertEqual(codes,[]);self.assertEqual(calls,[]);self.assertEqual(accepted,[])
        values=dict(client_id='FAKE-ID.apps.googleusercontent.com',client_secret='FAKE-CLIENT',
                    token_uri='https://oauth2.googleapis.com/token')
        self.assertEqual(self.run_bootstrap(client_values=values,metadata_rejected=True)[3],
                         'GOOGLE_BOOTSTRAP_FAILED')

    def test_A02_bootstrap_nonexact_token_uri_metadata_zero_effects(self):
        good='https://oauth2.googleapis.com/token'
        bad=[None,False,42,[],{},'',good.replace('https:','http:'),
             'https://accounts.google.com/o/oauth2/token',
             good.replace('oauth2.googleapis.com','oauth2.googleapis.com.evil.example'),
             good.replace('oauth2.googleapis.com','oauth2.googleapis.com:443'),
             good.replace('oauth2.googleapis.com','user@oauth2.googleapis.com'),
             good.replace('/token','/unknown'),good+'/',good+'?code=FAKE',good+'?',
             good+'#fragment',good+'#',' '+good,good+'\n']
        for uri in bad:
            with self.subTest(token_uri=uri):
                values=dict(client_id='FAKE-ID.apps.googleusercontent.com',client_secret='FAKE-CLIENT',
                            auth_uri='https://accounts.google.com/o/oauth2/auth',token_uri=uri)
                self.assertEqual(self.run_bootstrap(client_values=values,metadata_rejected=True)[3],
                                 'GOOGLE_BOOTSTRAP_FAILED')
        values=dict(client_id='FAKE-ID.apps.googleusercontent.com',client_secret='FAKE-CLIENT',
                    auth_uri='https://accounts.google.com/o/oauth2/auth')
        self.assertEqual(self.run_bootstrap(client_values=values,metadata_rejected=True)[3],
                         'GOOGLE_BOOTSTRAP_FAILED')

    def test_A02_bootstrap_approved_success_and_wrong_state_then_valid(self):
        for callback in ('valid','wrong-then-valid'):
            accepted,codes,calls,error=self.run_bootstrap(callback)
            self.assertIsNone(error)
            self.assertEqual(len(accepted),1)
            self.assertEqual(accepted[0].scopes,(auth.SCOPE,))
            self.assertEqual(accepted[0].refresh_token,'FAKE-REFRESH')
            self.assertEqual(codes,[200] if callback=='valid' else [400,200])
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['code'],'FAKE-CODE')
            self.assertEqual(calls[0]['grant_type'],'authorization_code')
            self.assertGreaterEqual(len(calls[0]['code_verifier']),43)
            self.assertEqual(calls[0]['redirect_uri'],'http://127.0.0.1:12345/')

    def test_A02_bootstrap_wrong_state_and_denial_no_exchange_or_save(self):
        for callback in ('wrong-state','denied'):
            accepted,codes,calls,error=self.run_bootstrap(callback)
            self.assertEqual(accepted,[]);self.assertEqual(calls,[])
            self.assertTrue(all(code==400 for code in codes))
            self.assertEqual(error,'GOOGLE_BOOTSTRAP_FAILED')

    def test_A02_bootstrap_scope_widen_missing_refresh_exchange_fail_no_save(self):
        good=dict(access_token='FAKE-ACCESS',refresh_token='FAKE-REFRESH',expires_in=3600,token_type='Bearer',scope=auth.SCOPE)
        bad=[dict(good,scope='https://www.googleapis.com/auth/drive'),dict(good,scope=None),dict(good,refresh_token=None),dict(good,token_type='Other')]
        for payload in bad:
            accepted,codes,calls,error=self.run_bootstrap(payload=payload)
            self.assertEqual(accepted,[]);self.assertEqual(len(calls),1)
            self.assertEqual(error,'GOOGLE_AUTH_REAUTHORIZE_OR_RETRY_LATER')
        accepted,codes,calls,error=self.run_bootstrap(token_error=True)
        self.assertEqual(accepted,[]);self.assertEqual(error,'GOOGLE_BOOTSTRAP_FAILED')
        self.assertNotIn('FAKE-SECRET',error)

    def test_A02_bootstrap_persistence_fail_safe_category(self):
        accepted,codes,calls,error=self.run_bootstrap(store_error=True)
        self.assertEqual(accepted,[]);self.assertEqual(len(calls),1)
        self.assertEqual(error,'GOOGLE_BOOTSTRAP_FAILED')


if __name__ == '__main__': unittest.main()
