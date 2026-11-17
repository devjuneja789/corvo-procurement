"""Exercise the real request dispatcher without opening sockets (sandbox forbids them)."""
import base64,copy,io,json,os,tempfile,unittest
from email.message import Message
from unittest.mock import patch
from app.server import Handler
from app import store
from app.engine import export_csv,SCHEMAS
from test_engine import fixture,line

class APItests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'DATABASE_URL':'','DATABASE_PATH':self.temp.name+'/app.sqlite3','APP_PASSWORD':'test-buyer','REQUESTER_PASSWORD':'test-employee','OPENROUTER_API_KEY':''});self.env.start();store.init()
  with store.connect() as db:
   for kind,rows in fixture().items():store.save_data(db,kind,rows,'test')
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def request(self,path,body=None,user='buyer',password='test-buyer'):
  handler=object.__new__(Handler);handler.path='/api/'+path;handler.headers=Message();handler.headers['Host']='localhost';handler.headers['Authorization']='Basic '+base64.b64encode((user+':'+password).encode()).decode();raw=json.dumps(body).encode() if body is not None else b'';handler.headers['Content-Length']=str(len(raw));handler.headers['Content-Type']='application/json';handler.rfile=io.BytesIO(raw);handler.reply=lambda obj,status=200,ctype='application/json':setattr(handler,'result',(status,obj));handler.dispatch('POST' if body is not None else 'GET');return handler.result
 def post(self,path,body):
  status,obj=self.request(path,body);self.assertEqual(status,200,obj);return obj
 def batch(self,**kw):return self.post('process-batch',{'csv':export_csv([line()],SCHEMAS['prs']),'policy_id':1,**kw})
 def test_complete_amendment_workflow(self):
  first=self.batch();p=self.request('state')[1]['policies'][0]['body'];p['version']='6.0';p['effective_date']='2026-11-01';p['rules'].insert(0,{'id':'AM1','when':{'field':'plant','op':'eq','value':'SITE-A'},'route':'RFQ','suggest':3})
  draft=self.post('policy/draft',{'base_id':1,'policy':p});preview=self.post('policy/preview',{'run_id':first['id'],'policy_id':draft['id']});self.assertEqual(preview['changed_lines'],1)
  status,_=self.request('process-batch',{'csv':export_csv([line()],SCHEMAS['prs']),'policy_id':draft['id']});self.assertEqual(status,400)
  self.post('policy/activate',{'id':draft['id']});second=self.batch(policy_id=draft['id'],snapshot_run_id=first['id']);self.assertEqual(second['rows'][0]['route'],'RFQ');self.assertEqual(self.batch()['rows'],first['rows']);self.assertIn('policy_version',self.request('export?id='+str(second['id']))[1])
 def test_approval_persists_document_and_blocks_replay_duplicate(self):
  first=self.batch();self.post('action',{'run_id':first['id'],'group_id':first['groups'][0]['group_id'],'action':'approve'});self.assertEqual(len(self.request('documents')[1]),1)
  second=self.batch();status,result=self.request('action',{'run_id':second['id'],'group_id':second['groups'][0]['group_id'],'action':'approve'});self.assertEqual(status,400);self.assertIn('already exists',result['error'])
 def test_auth_and_roles(self):
  self.assertEqual(self.request('state',password='wrong')[0],401);self.assertEqual(self.request('audit',user='requester',password='test-employee')[0],401)
 def test_override_needs_comment(self):
  first=self.batch();status,_=self.request('action',{'run_id':first['id'],'group_id':first['groups'][0]['group_id'],'action':'override'});self.assertEqual(status,400)
 def test_empty_upload_rejected(self):self.assertEqual(self.request('data',{'kind':'items','csv':','.join(SCHEMAS['items'])})[0],400)
 def test_policy_dates_follow_requirement_date(self):
  p=self.request('state')[1]['policies'][0]['body'];p['version']='future';p['effective_date']='2026-11-02';p['rules'].insert(0,{'id':'F1','when':{'field':'plant','op':'eq','value':'SITE-A'},'route':'RFQ','suggest':3});d=self.post('policy/draft',{'base_id':1,'policy':p});self.post('policy/activate',{'id':d['id']})
  csv=export_csv([line(),line(2,created_at='2026-11-03 09:00',need_by_date='2027-01-01')],SCHEMAS['prs']);r=self.post('process-batch',{'csv':csv,'policy_id':d['id']});self.assertEqual([x['policy_version'] for x in r['rows']],['5.0','future'])
 def test_preferred_export(self):
  status,csv=self.request('preferred?date=2026-11-01&policy_id=1&csv=1');self.assertEqual(status,200);self.assertTrue(csv.startswith('item_code,rank,supplier_id,reference_price'))
if __name__=='__main__':unittest.main()
