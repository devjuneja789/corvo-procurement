import base64,copy,hashlib,hmac,json,os,re,secrets,traceback,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
from . import store,ai,intake
from .engine import read_csv,validate_data,process,preferred,export_csv,COLUMNS,SCHEMAS,dec
from .policy import validate,describe_changes,DEFAULT
from .documents import extract
ROOT=Path(__file__).resolve().parent.parent
MAX_BODY=12*1024*1024

def with_timeline(selected,policies):
 policy=copy.deepcopy(selected['body'])
 older=[p for p in policies if p['status']=='active' and p['id']<=selected['id'] and p['body']['effective_date']<=policy['effective_date']]
 policy['_timeline']=[p['body'] for p in sorted(older,key=lambda p:(p['body']['effective_date'],p['id'])) if p['id']!=selected['id']]+[copy.deepcopy(selected['body'])]
 return policy

def run_save(db,lines,policy,label,snapshot,actor):
 result=process(snapshot,lines,policy)
 result['input_lines']=lines
 cur=db.execute('INSERT INTO runs(label,body,snapshot,policy,created_at) VALUES(?,?,?,?,?)',(label,json.dumps(result),json.dumps(snapshot),json.dumps(policy),store.now()))
 store.audit(db,'batch_processed',actor,{'run_id':cur.lastrowid,'policy':policy['version'],'summary':result['summary']})
 return {'id':cur.lastrowid,**result}

def contract_draft(text,data):
 flat=re.sub(r'\s+',' ',text);cid=re.search(r'RC-\d{4}-\d+',flat);sid=re.search(r'Supplier ID\s+(S\d+)',flat);dates=re.search(r'valid from\s+(\d{4}-\d\d-\d\d)\s+to\s+(\d{4}-\d\d-\d\d)',flat,re.I);cap=re.search(r'not exceed\s+INR\s+([\d,]+)',flat,re.I)
 if not all((cid,sid,dates,cap)):raise ValueError('Could not extract all contract fields. Use manual JSON entry after reviewing the PDF text.')
 supplier=next((s for s in data.get('suppliers',[]) if s['supplier_id']==sid[1]),None)
 if not supplier:raise ValueError('Import suppliers before extracting this contract')
 lines=[]
 for item in data.get('items',[]):
  m=re.search(re.escape(item['item_code'])+r'\s+(.+?)\s+'+re.escape(item['uom'])+r'\s+([\d,]+(?:\.\d+)?)',flat)
  if m:lines.append({'contract_id':cid[0],'item_code':item['item_code'],'description':item['description'],'uom':item['uom'],'rate':m[2].replace(',','')})
 if not lines:raise ValueError('No contract item rates extracted; enter them manually')
 return {'contract':{'contract_id':cid[0],'supplier_id':sid[1],'supplier_name':supplier['name'],'start_date':dates[1],'end_date':dates[2],'value_cap':cap[1].replace(',',''),'consumed_value':'0'},'lines':lines}

class Handler(BaseHTTPRequestHandler):
 def log_message(self,fmt,*args):print(fmt%args,flush=True)
 def reply(self,obj,status=200,ctype='application/json'):
  body=(json.dumps(obj,ensure_ascii=False) if ctype=='application/json' else obj).encode() if not isinstance(obj,bytes) else obj
  self.send_response(status);self.send_header('Content-Type',ctype+'; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.end_headers();self.wfile.write(body)
 def identity(self):
  password=os.environ.get('APP_PASSWORD','')
  if not password:
   if os.environ.get('RENDER'):raise ValueError('APP_PASSWORD must be configured on Render')
   return 'local-buyer','buyer'
  try:
   user,pw=base64.b64decode(self.headers.get('Authorization','').removeprefix('Basic ')).decode().split(':',1)
   expected=(os.environ.get('REQUESTER_PASSWORD') or password) if user=='requester' else password
   if user not in ('buyer','requester') or not hmac.compare_digest(pw,expected):raise ValueError()
   return user,user
  except Exception:raise PermissionError('Sign in with buyer or requester and the configured password')
 def do_GET(self):self.dispatch('GET')
 def do_POST(self):self.dispatch('POST')
 def dispatch(self,method):
  try:
   url=urlparse(self.path);path=url.path;query=parse_qs(url.query)
   if path=='/health':return self.reply({'status':'ok'})
   if not path.startswith('/api/'):
    files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
    if path not in files:return self.reply({'error':'Not found'},404)
    f=ROOT/'static'/files[path];ctype={'.html':'text/html','.js':'application/javascript','.css':'text/css'}[f.suffix];return self.reply(f.read_bytes(),ctype=ctype)
   actor,role=self.identity();payload={}
   if method=='POST':
    origin=self.headers.get('Origin')
    if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise PermissionError('Cross-origin writes are not allowed')
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=MAX_BODY:raise ValueError('Request body must be between 1 byte and 12 MB')
    raw=self.rfile.read(length)
    if 'text/csv' in self.headers.get('Content-Type',''):payload={'csv':raw.decode('utf-8-sig'),'policy_id':int(query.get('policy_id',['0'])[0])}
    else:payload=json.loads(raw)
   if role!='buyer' and path not in ('/api/state','/api/chat'):raise PermissionError('Buyer access required')
   with store.connect() as db:
    if method=='POST':db.execute('BEGIN IMMEDIATE')
    data=store.data(db);policies=store.policies(db)
    if path=='/api/state' and method=='GET':
     runs=[dict(r) for r in db.execute('SELECT id,label,created_at,policy FROM runs ORDER BY id DESC LIMIT 100')]
     for r in runs:r['policy']=json.loads(r['policy'])['version']
     return self.reply({'actor':actor,'role':role,'ai':ai.available(),'datasets':[{'kind':r['kind'],'rows':len(json.loads(r['body'])),'digest':r['digest'],'updated_at':r['updated_at']} for r in db.execute('SELECT * FROM datasets')],'policies':policies if role=='buyer' else [],'runs':runs if role=='buyer' else [],'today':datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()})
    if path=='/api/data' and method=='POST':
     kind=payload['kind']
     if kind not in SCHEMAS or kind=='prs':raise ValueError('Choose a supported master data type')
     rows=read_csv(payload['csv'],kind);validate_data(data,kind,rows)
     # Revalidate existing dependents before replacing a referenced table.
     prospective={**data,kind:rows}
     for dependent in ('items','suppliers','plants','contracts','contract_lines','history'):
      if dependent in prospective:validate_data(prospective,dependent,prospective[dependent])
     store.save_data(db,kind,rows,actor);return self.reply({'rows':len(rows),'kind':kind})
    if path=='/api/document' and method=='POST':
     raw=base64.b64decode(payload['base64'],validate=True);text=extract(raw,payload.get('name',''))
     return self.reply({'text':text})
    if path=='/api/contract/draft' and method=='POST':return self.reply(contract_draft(payload['text'],data))
    if path=='/api/contract/save' and method=='POST':
     c=payload['contract'];ls=payload['lines'];cid=c['contract_id']
     if any(r['contract_id']==cid for r in data.get('contracts',[])):raise ValueError('Contract ID already exists. Replace the register explicitly if it needs correction.')
     if any(l['contract_id']!=cid for l in ls):raise ValueError('Contract line identity mismatch')
     validate_data(data,'contracts',[c]);prospective={**data,'contracts':data.get('contracts',[])+[c]};validate_data(prospective,'contract_lines',ls)
     if not ls:raise ValueError('At least one contract line is required')
     store.save_data(db,'contracts',prospective['contracts'],actor);store.save_data(db,'contract_lines',data.get('contract_lines',[])+ls,actor);store.audit(db,'contract_added',actor,{'contract_id':cid,'source':payload.get('source','Manual entry')});return self.reply({'contract_id':cid})
    if path=='/api/policy/draft' and method=='POST':
     base=next((p['body'] for p in policies if p['id']==int(payload.get('base_id',policies[0]['id']))),None)
     if not base:raise ValueError('Base policy not found')
     source=payload.get('text','')
     if 'policy' in payload:draft=payload['policy']
     else:
      try:draft=json.loads(source)
      except json.JSONDecodeError:
       draft=ai.interpret('Convert this procurement policy or amendment into a complete policy JSON object matching the base schema. Return {"policy":...}. Preserve unmodified rules and settings, update version and effective_date from the source. Require explicit effective date and version; otherwise return {"error":"Specify version and effective date"}. Rules support nested all/any and field/op/value with fields item_type,category,plant,value,quantity,emergency,has_contract,has_history,item_code; ops eq,ne,lt,lte,gt,gte,in,not_in. Only routes CONTRACT_PO,EMERGENCY_PO,SPOT_PO,RFQ,RFP,CAPEX_SOURCING,NEW_ITEM_SOURCING. New plant/category rules must be inserted before general rules. Windows and ranking are editable data. Do not assume unknown conditions are supported; return error if unrepresentable.',{'base':base,'document':source})
       if 'error' in draft:raise ValueError(draft['error'])
       draft=draft['policy']
     validate(draft)
     if any(p['version']==draft['version'] for p in policies):raise ValueError('Use a unique policy version')
     changes=describe_changes(base,draft)
     cur=db.execute('INSERT INTO policies(version,body,source,status,created_at) VALUES(?,?,?,?,?)',(draft['version'],json.dumps(draft),source or 'Structured editor','draft',store.now()));store.audit(db,'policy_drafted',actor,{'id':cur.lastrowid,'changes':changes})
     return self.reply({'id':cur.lastrowid,'policy':draft,'changes':changes})
    if path=='/api/policy/activate' and method=='POST':
     policy=next((p for p in policies if p['id']==int(payload['id'])),None)
     if not policy or policy['status']!='draft':raise ValueError('Select an unapproved draft policy')
     validate(policy['body']);db.execute("UPDATE policies SET status='active' WHERE id=?",(policy['id'],));store.audit(db,'policy_approved',actor,{'id':policy['id'],'effective_date':policy['body']['effective_date']});return self.reply({'approved':policy['version']})
    if path=='/api/policy/preview' and method=='POST':
     row=db.execute('SELECT * FROM runs WHERE id=?',(payload['run_id'],)).fetchone()
     draft_record=next((p for p in policies if p['id']==int(payload['policy_id'])),None)
     draft=with_timeline(draft_record,policies) if draft_record else None
     if not row or not draft:raise ValueError('Select a run and policy')
     previous=json.loads(row['body']);snapshot=json.loads(row['snapshot']);lines=previous.get('input_lines',[l for g in previous['groups'] for l in g['lines']])
     amended=process(snapshot,lines,draft);old={(r['pr_no'],r['pr_line']):r for r in previous['rows']}
     changes=[{'pr_no':r['pr_no'],'pr_line':r['pr_line'],'before':old.get((r['pr_no'],r['pr_line'])),'after':r} for r in amended['rows'] if any(old.get((r['pr_no'],r['pr_line']),{}).get(k)!=r[k] for k in ('route','supplier_id','unit_price','group_id','po_id','group_value_inr','suggested_supplier_ids'))]
     return self.reply({'changed_lines':len(changes),'changes':changes,'summary':amended['summary']})
    if path=='/api/process-batch' and method=='POST':
     lines=read_csv(payload['csv'],'prs')
     policy=next((p for p in policies if p['id']==int(payload.get('policy_id',0))),None)
     if not policy:raise ValueError('Choose an approved policy version')
     if policy['status']!='active':raise ValueError('Approve the policy before running a batch; use Preview for drafts')
     snapshot=data
     if payload.get('snapshot_run_id'):
      previous=db.execute('SELECT snapshot FROM runs WHERE id=?',(int(payload['snapshot_run_id']),)).fetchone()
      if not previous:raise ValueError('Snapshot run not found')
      snapshot=json.loads(previous['snapshot'])
     result=run_save(db,lines,with_timeline(policy,policies),payload.get('label','Batch run'),snapshot,actor);return self.reply(result)
    if path=='/api/run' and method=='GET':
     row=db.execute('SELECT * FROM runs WHERE id=?',(query['id'][0],)).fetchone()
     if not row:return self.reply({'error':'Run not found'},404)
     result=json.loads(row['body']);result.update(id=row['id'],label=row['label'],policy=json.loads(row['policy']),actions=[dict(r) for r in db.execute('SELECT * FROM actions WHERE run_id=?',(row['id'],))]);return self.reply(result)
    if path=='/api/export' and method=='GET':
     row=db.execute('SELECT body FROM runs WHERE id=?',(query['id'][0],)).fetchone()
     if not row:raise ValueError('Run not found')
     return self.reply(export_csv(json.loads(row['body'])['rows']),ctype='text/csv')
    if path=='/api/preferred' and method=='GET':
     asof=query.get('date',[datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()])[0];date.fromisoformat(asof)
     p=next((p for p in policies if p['id']==int(query.get('policy_id',['0'])[0])),None)
     if not p or p['status']!='active':raise ValueError('Choose an approved policy')
     snapshot=data
     if query.get('run_id'):
      row=db.execute('SELECT snapshot FROM runs WHERE id=?',(query['run_id'][0],)).fetchone()
      if not row:raise ValueError('Snapshot run not found')
      snapshot=json.loads(row['snapshot'])
     rows=[r for item in snapshot.get('items',[]) for r in preferred(snapshot,item,asof,p['body'])[:3]]
     if query.get('csv'):return self.reply(export_csv(rows,['item_code','rank','supplier_id','reference_price']),ctype='text/csv')
     return self.reply(rows)
    if path=='/api/action' and method=='POST':
     row=db.execute('SELECT body FROM runs WHERE id=?',(payload['run_id'],)).fetchone()
     if not row:raise ValueError('Run not found')
     group=next((g for g in json.loads(row['body'])['groups'] if g['group_id']==payload['group_id']),None)
     if not group:raise ValueError('Requirement not found')
     action=payload['action'];comment=payload.get('comment','').strip()
     if action not in ('approve','override'):raise ValueError('Unsupported action')
     if action=='override' and not comment:raise ValueError('An override requires a written reason')
     # Approval is for this reviewed snapshot, not a new decision or external order.
     identifier=group['po_id'] if group['po_id'] else f'SRC-{payload["run_id"]}-{group["group_id"]}'
     if action=='override':
      target=payload.get('override',{})
      if target.get('route') not in ('RFQ','RFP','CAPEX_SOURCING','NEW_ITEM_SOURCING','SPOT_PO','EMERGENCY_PO','CONTRACT_PO'):raise ValueError('Select an override route')
      if target['route']=='CONTRACT_PO':raise ValueError('Contract PO overrides require reprocessing under a valid contract policy; direct override cannot bypass ceiling checks')
      if target['route'].endswith('_PO'):
       if not any(s['supplier_id']==target.get('supplier_id') and s['status']=='Active' for s in data.get('suppliers',[])):raise ValueError('Override PO needs an Active supplier')
       if dec(target.get('unit_price','-1'))<0:raise ValueError('Override PO needs a valid price')
      comment=json.dumps({'reason':comment,'override':target,'original':group['route']})
     existing=db.execute('SELECT * FROM actions WHERE run_id=? AND group_id=?',(payload['run_id'],payload['group_id'])).fetchone()
     if existing:raise ValueError('Requirement already actioned; original action is immutable')
     members=[g for g in json.loads(row['body'])['groups'] if action=='approve' and group['po_id'] and g['po_id']==group['po_id']] or [group]
     identifier=f'DOC-{payload["run_id"]}-{identifier}'
     for member in members:
      for line in member['lines']:
       if db.execute('SELECT 1 FROM document_lines WHERE pr_no=? AND pr_line=?',(line['pr_no'],line['pr_line'])).fetchone():raise ValueError('A purchasing document already exists for '+line['pr_no']+'/'+line['pr_line'])
     reservations={}
     if action=='approve':
      for member in members:
       if member['supplier_id'] and not any(s['supplier_id']==member['supplier_id'] and s['status']=='Active' for s in data['suppliers']):raise ValueError('Supplier is no longer Active; rerun the request')
       cid=member.get('contract_id')
       if cid:reservations[cid]=reservations.get(cid,dec('0'))+sum(dec(l['quantity']) for l in member['lines'])*dec(member['unit_price'])
      for cid,amount in reservations.items():
       c=next((c for c in data['contracts'] if c['contract_id']==cid),None)
       if not c:raise ValueError('Contract no longer exists; rerun')
       committed=sum((dec(r['amount']) for r in db.execute('SELECT amount FROM reservations WHERE contract_id=?',(cid,))),dec('0'))
       if dec(c['consumed_value'])+committed+amount>dec(c['value_cap']):raise ValueError('Approval would exceed live contract ceiling; rerun or source this requirement')
     db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)',(identifier,payload['run_id'],'PO' if (payload.get('override',{}).get('route',group['route'])).endswith('_PO') else 'RFQ_RFP',json.dumps({'groups':members,'override':payload.get('override') if action=='override' else None,'reason':payload.get('comment','')}),actor,store.now()))
     for cid,amount in reservations.items():db.execute('INSERT INTO reservations VALUES(?,?,?)',(identifier,cid,str(amount)))
     for member in members:
      for line in member['lines']:db.execute('INSERT INTO document_lines VALUES(?,?,?)',(line['pr_no'],line['pr_line'],identifier))
      db.execute('INSERT INTO actions(run_id,group_id,action,comment,actor,created_at) VALUES(?,?,?,?,?,?)',(payload['run_id'],member['group_id'],action,comment,actor,store.now()))
     store.audit(db,'buyer_'+action,actor,{'run_id':payload['run_id'],'group_ids':[m['group_id'] for m in members],'document_id':identifier,'comment':comment});return self.reply({'document_id':identifier,'action':action,'requirements':len(members)})
    if path=='/api/documents' and method=='GET':return self.reply([dict(r)|{'body':json.loads(r['body'])} for r in db.execute('SELECT * FROM documents ORDER BY created_at DESC')])
    if path=='/api/audit' and method=='GET':return self.reply([dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')])
    if path=='/api/chat' and method=='POST':
     if not data.get('items') or not data.get('plants'):raise ValueError('Ask a buyer to import the item and plant catalogs first')
     sid=payload.get('session_id') or uuid.uuid4().hex;key=actor+':'+sid;row=db.execute('SELECT body FROM chats WHERE id=?',(key,)).fetchone();state=json.loads(row['body']) if row else {}
     state,message,confirmed=intake.turn(state,payload['message'],data)
     result=None
     if confirmed:
      active=[p for p in policies if p['status']=='active' and p['body']['effective_date']<=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()]
      if not active:raise ValueError('No policy is effective today')
      policy=with_timeline(max(active,key=lambda p:(p['body']['effective_date'],p['id'])),policies)
      line={k:'' for k in SCHEMAS['prs']};line.update({k:str(v) for k,v in state.items() if k in line});line.update(pr_no='CHAT-'+uuid.uuid4().hex[:10].upper(),pr_line='1',created_at=datetime.now(ZoneInfo('Asia/Kolkata')).replace(tzinfo=None,microsecond=0).isoformat(),requester=actor,department=state.get('department','Employee'))
      live_data=copy.deepcopy(data)
      for c in live_data.get('contracts',[]):
       committed=sum((dec(r['amount']) for r in db.execute('SELECT amount FROM reservations WHERE contract_id=?',(c['contract_id'],))),dec('0'))
       c['consumed_value']=str(dec(c['consumed_value'])+committed)
      result=run_save(db,[line],policy,'Chat request '+line['pr_no'],live_data,actor)
      if result['summary']['not_processed']:raise ValueError(result['rows'][0]['reason'])
      state={};store.audit(db,'pr_created',actor,{'pr_no':line['pr_no'],'run_id':result['id']})
     db.execute('INSERT OR REPLACE INTO chats VALUES(?,?)',(key,json.dumps(state)));return self.reply({'session_id':sid,'message':message,'fields':state,'run_id':result['id'] if result else None})
    return self.reply({'error':'Endpoint not found'},404)
  except PermissionError as e:self.reply({'error':str(e)},401)
  except (ValueError,KeyError,TypeError,ArithmeticError) as e:self.reply({'error':str(e)},400)
  except Exception:
   traceback.print_exc();self.reply({'error':'Unexpected server error; inspect server logs'},500)

def main():
 if os.environ.get('RENDER') and not os.environ.get('APP_PASSWORD','').strip():raise ValueError('Set APP_PASSWORD in Render before starting the service')
 ZoneInfo('Asia/Kolkata')
 store.init();port=int(os.environ.get('PORT','8000'));print(f'Procurement app: http://localhost:{port}',flush=True);ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
if __name__=='__main__':main()
