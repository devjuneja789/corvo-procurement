"""Versioned, bounded policy interpreter. Uploaded rules are data, never executable code."""
import copy,math
from decimal import Decimal

DEFAULT = {
 'version':'5.0','effective_date':'2026-04-01',
 'windows':{'clubbing_days':14,'need_by_days':7,'consolidation_hours':24,'history_days':365,'preferred_days':548},
 'ranking':{'frequency':35,'recency':25,'contract':15,'delivery':15,'quality':10},
 'rules':[
  {'id':'5.1','when':{'field':'item_type','op':'eq','value':'Capex'},'route':'CAPEX_SOURCING','suggest':5},
  {'id':'5.2','when':{'field':'has_contract','op':'eq','value':True},'route':'CONTRACT_PO'},
  {'id':'5.3','when':{'all':[{'field':'emergency','op':'eq','value':True},{'field':'value','op':'lte','value':500000},{'field':'has_history','op':'eq','value':True}]},'route':'EMERGENCY_PO'},
  {'id':'5.4','when':{'all':[{'field':'value','op':'lt','value':200000},{'field':'has_history','op':'eq','value':True}]},'route':'SPOT_PO'},
  {'id':'5.5','when':{'field':'value','op':'lt','value':1000000},'route':'RFQ','suggest':3},
  {'id':'5.6','when':{'field':'value','op':'gte','value':1000000},'route':'RFP','suggest':5}
 ]}
FIELDS={'item_type','category','plant','value','quantity','emergency','has_contract','has_history','item_code'}
ROUTES={'CONTRACT_PO','EMERGENCY_PO','SPOT_PO','RFQ','RFP','CAPEX_SOURCING','NEW_ITEM_SOURCING'}
OPS={'eq','ne','lt','lte','gt','gte','in','not_in'}

def validate(policy):
 from datetime import date
 date.fromisoformat(policy['effective_date'])
 if not str(policy.get('version','')).strip(): raise ValueError('Policy version is required')
 if set(policy.get('windows',{})) != set(DEFAULT['windows']): raise ValueError('All five windows are required')
 for v in policy['windows'].values():
  if type(v) is not int or not 0 <= v <= 3650: raise ValueError('Windows must be integers between 0 and 3650')
 if set(policy.get('ranking',{})) != set(DEFAULT['ranking']): raise ValueError('All ranking weights are required')
 if any(type(v) not in (int,float) or not 0<=v<=100 for v in policy['ranking'].values()) or not sum(policy['ranking'].values()): raise ValueError('Invalid ranking weights')
 def check(node,depth=0):
  if depth>8 or not isinstance(node,dict): raise ValueError('Invalid or excessive predicate nesting')
  if 'all' in node or 'any' in node:
   key='all' if 'all' in node else 'any'
   if set(node)!={key} or not isinstance(node[key],list) or not 1<=len(node[key])<=20: raise ValueError('Invalid predicate group')
   for child in node[key]: check(child,depth+1)
  else:
   if set(node)!={'field','op','value'} or node['field'] not in FIELDS or node['op'] not in OPS: raise ValueError('Unsupported predicate')
   val=node['value']; field=node['field']; op=node['op']
   values=val if op in ('in','not_in') else [val]
   if not isinstance(values,list) or len(values)>100: raise ValueError('Membership needs a bounded list')
   for v in values:
    if field in ('value','quantity') and (type(v) not in (int,float) or not math.isfinite(v) or v<0): raise ValueError('Numeric field needs nonnegative numbers')
    if field in ('emergency','has_contract','has_history') and type(v) is not bool: raise ValueError('Boolean field needs true/false')
    if field not in ('value','quantity','emergency','has_contract','has_history') and not isinstance(v,str): raise ValueError('Text field needs strings')
 if not isinstance(policy.get('rules'),list) or not 1<=len(policy['rules'])<=100: raise ValueError('Policy needs 1–100 rules')
 ids=set()
 for rule in policy['rules']:
  if not rule.get('id') or rule['id'] in ids: raise ValueError('Rule IDs must be unique')
  ids.add(rule['id']); check(rule['when'])
  if rule.get('route') not in ROUTES: raise ValueError('Unknown outcome route')
  if type(rule.get('suggest',0)) is not int or not 0<=rule.get('suggest',0)<=10: raise ValueError('Invalid suggestion count')
 return policy

def matches(node,ctx):
 if 'all' in node:return all(matches(n,ctx) for n in node['all'])
 if 'any' in node:return any(matches(n,ctx) for n in node['any'])
 a,b,op=ctx[node['field']],node['value'],node['op']
 if node['field'] in ('value','quantity'):
  b=[Decimal(str(v)) for v in b] if op in ('in','not_in') else Decimal(str(b))
 if op=='eq':return a==b
 if op=='ne':return a!=b
 if op=='in':return a in b
 if op=='not_in':return a not in b
 if op=='lt':return a<b
 if op=='lte':return a<=b
 if op=='gt':return a>b
 return a>=b

def predicate_text(node):
 if 'all' in node:return '('+' and '.join(predicate_text(n) for n in node['all'])+')'
 if 'any' in node:return '('+' or '.join(predicate_text(n) for n in node['any'])+')'
 labels={'item_type':'item type','category':'category','plant':'plant','value':'requirement value INR','quantity':'total quantity','emergency':'emergency','has_contract':'usable contract','has_history':'recent Active-supplier purchase','item_code':'item code'}
 operators={'eq':'is','ne':'is not','lt':'is below','lte':'is at most','gt':'is above','gte':'is at least','in':'is one of','not_in':'is not one of'}
 return f"{labels[node['field']]} {operators[node['op']]} {node['value']}"

def describe_changes(old,new):
 changes=[]
 for key in ('version','effective_date'):
  if old.get(key)!=new.get(key):changes.append(f"{key.replace('_',' ').capitalize()}: {old.get(key)} → {new.get(key)}")
 for key in ('windows','ranking'):
  for field,value in new[key].items():
   if old[key].get(field)!=value:changes.append(f"{field.replace('_',' ').capitalize()} {key}: {old[key].get(field)} → {value}")
 before={r['id']:r for r in old['rules']};after={r['id']:r for r in new['rules']}
 for rid in before.keys()-after.keys():changes.append(f'Remove rule {rid}')
 for rid,r in after.items():
  if before.get(rid)!=r:changes.append(f"{'Add' if rid not in before else 'Change'} rule {rid}: when {predicate_text(r['when'])}, use {r['route'].replace('_',' ')}"+(f" and suggest up to {r['suggest']} suppliers" if r.get('suggest') else ''))
 if [r['id'] for r in old['rules']]!=[r['id'] for r in new['rules']]:changes.append('Evaluate rules in this order: '+', '.join(r['id'] for r in new['rules']))
 return changes
