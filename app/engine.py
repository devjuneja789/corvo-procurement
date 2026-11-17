"""Pure procurement engine: all state is scoped to a single replay."""
import csv,io,re,hashlib,json
from datetime import date,datetime,timedelta
from decimal import Decimal, ROUND_HALF_UP
from .policy import matches,validate
D=Decimal
COLUMNS=['pr_no','pr_line','resolved_item_code','group_id','po_id','decision','route','supplier_id','unit_price','group_value_inr','suggested_supplier_ids','policy_version','reason']
SCHEMAS={
 'items':['item_code','description','uom','category','item_type','standard_price'],
 'suppliers':['supplier_id','name','city','categories','status','on_time_pct','quality_rating'],
 'history':['po_number','po_date','supplier_id','item_code','quantity','uom','unit_price','plant','delivered_on_time'],
 'plants':['plant','name'],
 'contracts':['contract_id','supplier_id','supplier_name','start_date','end_date','value_cap','consumed_value'],
 'contract_lines':['contract_id','item_code','description','uom','rate'],
 'prs':['pr_no','pr_line','created_at','requester','department','plant','item_code','description','quantity','uom','estimated_unit_price','need_by_date','urgency']}

def money(v):return str(D(v).quantize(D('.01'),rounding=ROUND_HALF_UP))
def day(v):return date.fromisoformat(str(v)[:10])
def stamp(v):
 parsed=datetime.fromisoformat(v)
 if parsed.tzinfo is not None:raise ValueError('created_at must use company-local timestamps without an offset')
 return parsed
def dec(v):
 n=D(str(v))
 if not n.is_finite():raise ValueError('Number must be finite')
 return n

def read_csv(text,kind):
 reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')))
 missing=set(SCHEMAS[kind])-set(reader.fieldnames or [])
 if missing:raise ValueError('Missing columns: '+', '.join(sorted(missing)))
 rows=[]; errors=[]
 for index,row in enumerate(reader,2):
  if None in row or any(v is None for v in row.values()):errors.append(f'Row {index}: column count mismatch');continue
  rows.append({k:v.strip() for k,v in row.items()})
 if errors:raise ValueError('; '.join(errors[:20]))
 if not rows:raise ValueError('CSV has no data rows')
 return rows

def normalize(text):
 text=text.lower().replace('×','x').replace('–','-')
 for a,b in {'brg':'bearing','hyd':'hydraulic','pneu':'pneumatic','assy':'assembly','ss':'stainless steel','ms':'mild steel'}.items():text=re.sub(r'\b'+a+r'\b',b,text)
 text=re.sub(r'\b(?:as per sample|for maintenance|repeat|urgent)\b',' ',text)
 return re.sub(r'[^a-z0-9]+',' ',text).strip()

def candidates(description,items):
 tokens=set(normalize(description).split()); numbers={t for t in tokens if any(c.isdigit() for c in t)}
 result=[]
 for item in items:
  other=set(normalize(item['description']).split()); nums={t for t in other if any(c.isdigit() for c in t)}
  if numbers and not numbers.issubset(nums):continue
  score=len(tokens&other)/max(1,len(tokens))*.7+len(tokens&other)/max(1,len(other))*.3
  result.append((score,item))
 return sorted(result,key=lambda x:(-x[0],x[1]['item_code']))[:5]

def resolve(line,items):
 if line.get('item_code'):
  found=next((i for i in items if i['item_code']==line['item_code']),None)
  if not found:raise ValueError('Explicit item code is not in the item master')
  return found
 ranked=candidates(line['description'],items)
 if ranked and ranked[0][0]>=.66 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.08):return ranked[0][1]
 return None

def validate_data(data,kind,rows):
 ids={'items':'item_code','suppliers':'supplier_id','plants':'plant','contracts':'contract_id'}
 seen=set();errors=[]
 refs={k:{r[ids[k]] for r in data.get(k,[])} for k in ids}
 for n,r in enumerate(rows,2):
  try:
   key=tuple(r[k] for k in ({'history':['po_number','item_code','plant'],'contract_lines':['contract_id','item_code'],'prs':['pr_no','pr_line']}.get(kind,[ids.get(kind,'pr_no') ])))
   if key in seen:raise ValueError('duplicate identity '+str(key))
   seen.add(key)
   for k in SCHEMAS[kind]:
    if k not in r:raise ValueError('Missing '+k)
   for k in ('quantity','standard_price','unit_price','rate','value_cap','consumed_value','estimated_unit_price'):
    if k in r and r[k]!='' and dec(r[k])<0:raise ValueError(k+' cannot be negative')
   for field in {'items':['standard_price'],'history':['quantity','unit_price'],'contracts':['value_cap','consumed_value'],'contract_lines':['rate'],'prs':['quantity']}.get(kind,[]):
    dec(r[field])
   if kind in ids and not r[ids[kind]]:raise ValueError('Identifier cannot be empty')
   if kind=='items' and any(not r[k] for k in ('description','uom','category','item_type')):raise ValueError('Item description, unit, category and type are required')
   if 'quantity' in r and dec(r['quantity'])<=0:raise ValueError('quantity must be positive')
   for k in ('po_date','start_date','end_date','need_by_date'):
    if k in r:day(r[k])
   if 'created_at' in r:stamp(r['created_at'])
   if kind=='prs':
    if not r['pr_no'] or not r['pr_line'].isdigit():raise ValueError('PR identity is invalid')
    if r['urgency'] not in ('Normal','Emergency'):raise ValueError('Urgency must be Normal or Emergency')
   if kind=='suppliers':
    if r['status'] not in ('Active','Inactive','Blocked'):raise ValueError('Invalid supplier status')
    if not 0<=dec(r['on_time_pct'])<=100 or not 0<=dec(r['quality_rating'])<=5:raise ValueError('Invalid supplier ratings')
   if kind=='contracts' and day(r['start_date'])>day(r['end_date']):raise ValueError('Contract dates reversed')
   for field,table in [('item_code','items'),('supplier_id','suppliers'),('plant','plants'),('contract_id','contracts')]:
    if field in r and table!=kind and r[field] and r[field] not in refs[table]:raise ValueError('Unknown '+field+': '+r[field])
  except (ValueError,ArithmeticError,KeyError) as e:errors.append(f'Row {n}: {e}')
 if errors:raise ValueError('; '.join(errors[:30]))
 return rows

def preferred(data,item,asof,policy):
 asof=day(asof);days=policy['windows']['preferred_days']; suppliers={s['supplier_id']:s for s in data['suppliers'] if s['status']=='Active'}
 history=[h for h in data['history'] if h['item_code']==item['item_code'] and asof-timedelta(days=days)<=day(h['po_date'])<asof and h['supplier_id'] in suppliers]
 contracts={c['contract_id']:c for c in data['contracts'] if day(c['start_date'])<=asof and c['supplier_id'] in suppliers}
 lines=[(contracts[l['contract_id']],l) for l in data['contract_lines'] if l['item_code']==item['item_code'] and l['contract_id'] in contracts]
 ids={h['supplier_id'] for h in history}|{c['supplier_id'] for c,l in lines}; maximum=max([sum(h['supplier_id']==s for h in history) for s in ids]+[1]);result=[]
 for sid in ids:
  hs=sorted([h for h in history if h['supplier_id']==sid],key=lambda h:(h['po_date'],h['po_number']),reverse=True)
  cs=sorted([(c,l) for c,l in lines if c['supplier_id']==sid],key=lambda cl:(cl[0]['start_date'],cl[0]['contract_id']),reverse=True)
  age=(asof-day(hs[0]['po_date'])).days if hs else 99999;s=suppliers[sid]
  parts={'frequency':len(hs)/maximum,'recency':1 if age<=90 else .5 if age<=365 else 0,'contract':int(bool(cs)),'delivery':float(s['on_time_pct'])/100,'quality':float(s['quality_rating'])/5}
  score=sum(policy['ranking'][k]*v for k,v in parts.items())
  result.append({'item_code':item['item_code'],'supplier_id':sid,'name':s['name'],'reference_price':money(hs[0]['unit_price'] if hs else cs[0][1]['rate']),'score':round(score,4),'components':parts,'last_po':hs[0]['po_date'] if hs else '', 'evidence':hs[0]['po_number'] if hs else cs[0][0]['contract_id']})
 result.sort(key=lambda r:(-r['score'],-day(r['last_po']).toordinal() if r['last_po'] else 0,r['supplier_id']))
 for rank,r in enumerate(result,1):r['rank']=rank
 return result

def suggestions(data,item,ranks,count):
 ids=[r['supplier_id'] for r in ranks[:count]]
 others=[s for s in data['suppliers'] if s['status']=='Active' and s['supplier_id'] not in ids and item['category'] in re.split(r'[;|]',s['categories'])]
 others.sort(key=lambda s:(-(float(s['on_time_pct'])/100+float(s['quality_rating'])/5),s['supplier_id']))
 return (ids+[s['supplier_id'] for s in others])[:count]

def process(data,lines,policy):
 validate(policy)
 for k in ('items','suppliers','plants','history','contracts','contract_lines'):
  if k not in data:raise ValueError('Import '+k+' before running a batch')
 items=data['items']; groups=[]; invalid=[];seen=set(); timeline=policy.get('_timeline',[policy])
 for version in timeline:validate(version)
 def invalid_row(line,error):
  row={k:'' for k in COLUMNS};row.update(pr_no=line.get('pr_no',''),pr_line=line.get('pr_line',''),route='NOT_PROCESSED',policy_version=policy['version'],reason=str(error));invalid.append(row)
 for line in sorted(lines,key=lambda l:(l.get('created_at',''),l.get('pr_no',''),int(l.get('pr_line','0')) if l.get('pr_line','').isdigit() else 0)):
  try:
   identity=(line['pr_no'],line['pr_line'])
   if identity in seen:raise ValueError('Duplicate PR identity')
   seen.add(identity);validate_data(data,'prs',[line]);item=resolve(line,items)
   applicable_versions=[p for p in timeline if p['effective_date']<=line['created_at'][:10]]
   if not applicable_versions:raise ValueError('No policy effective on this PR date')
   line_policy=max(enumerate(applicable_versions),key=lambda pair:(pair[1]['effective_date'],pair[0]))[1]
   if item and line['uom'].upper()!=item['uom'].upper():raise ValueError('Unit does not match item master; no conversion assumed')
   if item is None and not line['estimated_unit_price']:raise ValueError('New item requires estimated_unit_price')
   group=next((g for g in groups if item and g['item'] and g['item']['item_code']==item['item_code'] and g['plant']==line['plant'] and (day(line['created_at'])-day(g['first']['created_at'])).days<=g['policy']['windows']['clubbing_days'] and abs((day(line['need_by_date'])-day(g['first']['need_by_date'])).days)<=g['policy']['windows']['need_by_days']),None)
   if group:group['lines'].append(line)
   else:groups.append({'item':item,'plant':line['plant'],'first':line,'lines':[line],'policy':line_policy})
  except (ValueError,KeyError,ArithmeticError) as e:invalid_row(line,e)
 consumed={c['contract_id']:dec(c['consumed_value']) for c in data['contracts']};contracts={c['contract_id']:c for c in data['contracts']};active={s['supplier_id'] for s in data['suppliers'] if s['status']=='Active'};pos=[];results=[]
 for index,g in enumerate(groups,1):
  group_policy=g['policy'];w=group_policy['windows'];item=g['item'];first=g['first'];asof=day(first['created_at']);qty=sum(dec(l['quantity']) for l in g['lines']); gid=f'REQ-{index:04d}';supplier='';price='';poid='';suggested=[];ranks=[];evidence='';contract=None
  if item is None:
   value=qty*dec(first['estimated_unit_price']);route='NEW_ITEM_SOURCING';clause='1.2';detail='No confident item-master match; buyer must find suppliers'
  else:
   applicable=[]
   for l in data['contract_lines']:
    c=contracts[l['contract_id']]
    if l['item_code']==item['item_code'] and c['supplier_id'] in active and day(c['start_date'])<=asof<=day(c['end_date']):applicable.append((c,l))
   applicable.sort(key=lambda cl:(dec(cl[1]['rate']),cl[0]['contract_id']))
   usable=[cl for cl in applicable if consumed[cl[0]['contract_id']]+qty*dec(cl[1]['rate'])<=dec(cl[0]['value_cap'])]
   contract=usable[0] if usable else None
   hist=sorted([h for h in data['history'] if h['item_code']==item['item_code'] and asof-timedelta(days=w['history_days'])<=day(h['po_date'])<asof],key=lambda h:(h['po_date'],h['po_number']),reverse=True)
   base=contract or (applicable[0] if applicable else None)
   valuation=dec(base[1]['rate']) if base else dec(hist[0]['unit_price']) if hist else dec(item['standard_price'])
   value=qty*valuation; evidence=base[0]['contract_id'] if base else hist[0]['po_number'] if hist else 'item master standard price'
   ranks=preferred(data,item,asof,group_policy)
   ctx={'item_type':item['item_type'],'category':item['category'],'plant':g['plant'],'value':value,'quantity':qty,'emergency':any(l['urgency']=='Emergency' for l in g['lines']),'has_contract':bool(contract),'has_history':any(h['supplier_id'] in active for h in hist),'item_code':item['item_code']}
   rule=next((r for r in group_policy['rules'] if matches(r['when'],ctx)),None)
   if rule is None:raise ValueError(f'Policy has no matching rule for {gid}; add a fallback rule')
   route=rule['route'];clause=rule['id'];detail=f'Valuation {money(valuation)} × {qty}; source {evidence}'
   if route=='CONTRACT_PO':
    if not contract:raise ValueError(f'Rule {clause} requires a usable contract')
    c,l=contract;supplier=c['supplier_id'];price=money(l['rate']);consumed[c['contract_id']]+=qty*dec(l['rate']);evidence=c['contract_id']
   elif route in ('SPOT_PO','EMERGENCY_PO'):
    if not ranks:raise ValueError(f'Rule {clause} selected a PO without an eligible preferred supplier')
    supplier=ranks[0]['supplier_id'];price=ranks[0]['reference_price'];detail+=f'; preferred rank 1 evidence {ranks[0]["evidence"]}'
   else:suggested=suggestions(data,item,ranks,rule.get('suggest',0))
  decision='PO' if route.endswith('_PO') else 'SOURCING_REQUEST'
  if decision=='PO':
   timestamp=stamp(first['created_at']);existing=next((p for p in pos if p['supplier']==supplier and p['plant']==g['plant'] and p['route']==route and timestamp-p['timestamp']<=timedelta(hours=w['consolidation_hours'])),None)
   if not existing:
    existing={'id':f'PO-{len(pos)+1:04d}','supplier':supplier,'plant':g['plant'],'route':route,'timestamp':timestamp};pos.append(existing)
   poid=existing['id']
  for l in g['lines']:
   row=dict(zip(COLUMNS,['']*len(COLUMNS)));row.update(pr_no=l['pr_no'],pr_line=l['pr_line'],resolved_item_code=item['item_code'] if item else 'NEW',group_id=gid,po_id=poid,decision=decision,route=route,supplier_id=supplier,unit_price=price,group_value_inr=money(value),suggested_supplier_ids=';'.join(suggested),policy_version=group_policy['version'],reason=f'Clause {clause}; {detail}');results.append(row)
  g.update(contract_id=contract[0]['contract_id'] if contract and route=='CONTRACT_PO' else '',group_id=gid,value=money(value),route=route,po_id=poid,supplier_id=supplier,unit_price=price,suggested_supplier_ids=suggested,reason=f'Clause {clause}; {detail}',preferred=ranks)
 results+=invalid
 order={(l['pr_no'],l['pr_line']):i for i,l in enumerate(lines)};results.sort(key=lambda r:order.get((r['pr_no'],r['pr_line']),0))
 return {'rows':results,'groups':groups,'summary':{'lines':len(results),'requirements':len(groups),'purchase_orders':len(pos),'sourcing':sum(g['route'] not in ('CONTRACT_PO','SPOT_PO','EMERGENCY_PO') for g in groups),'not_processed':len(invalid)},'ceiling_consumed':{k:money(v) for k,v in consumed.items()}}

def export_csv(rows,columns=COLUMNS):
 out=io.StringIO();writer=csv.DictWriter(out,fieldnames=columns,extrasaction='ignore',lineterminator='\n');writer.writeheader();writer.writerows(rows);return out.getvalue()
