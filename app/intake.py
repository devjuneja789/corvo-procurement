import re,uuid
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from .engine import candidates
from . import ai

def turn(state,message,data):
 state=dict(state);items=data.get('items',[]);plants=data.get('plants',[])
 if message.lower().strip() in ('restart','start over'):state={}
 if state.get('awaiting')=='item_code':
  selected=next((i for i in items if i['item_code'].lower()==message.strip().lower()),None)
  if selected:state.update(item_code=selected['item_code'],description=selected['description'],uom=selected['uom']);state.pop('awaiting',None)
 if ai.available():
  result=ai.interpret('Extract purchase request fields from this conversation update. Merge existing state. Return {"fields": {description, item_code, quantity, plant, need_by_date, urgency, estimated_unit_price, requester, department}} with only supported known values. Dates ISO YYYY-MM-DD. Resolve relative dates using today. Never invent item codes or plants; catalog is authoritative. Unknown items have item_code empty. Do not interpret confirm as data.',{'today':datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat(),'existing':state,'message':message,'items':items,'plants':plants})
  fields=result.get('fields',{})
  for key in ('description','item_code','quantity','plant','need_by_date','urgency','estimated_unit_price','requester','department'):
   if key in fields and fields[key] is not None:state[key]=str(fields[key])
 else:
  low=message.lower();today=datetime.now(ZoneInfo('Asia/Kolkata')).date()
  code=next((re.search(r'\b'+re.escape(i['item_code'])+r'\b',message,re.I) for i in items if re.search(r'\b'+re.escape(i['item_code'])+r'\b',message,re.I)),None)
  if code:state['item_code']=code[0].upper()
  for p in plants:
   aliases=[p['plant'].lower()]+[x for x in re.findall(r'[a-z]+',p['name'].lower()) if x not in ('plant','pune')]
   if any(re.search(r'\b'+re.escape(a)+r'\b',low) for a in aliases):state['plant']=p['plant']
  if 'emergency' in low:state['urgency']='Emergency'
  elif re.search(r'\b(normal|routine|not urgent)\b',low):state['urgency']='Normal'
  dt=re.search(r'\b20\d\d-\d\d-\d\d\b',message)
  if dt:state['need_by_date']=dt[0]
  elif 'tomorrow' in low:state['need_by_date']=(today+timedelta(days=1)).isoformat()
  elif re.search(r'\btoday\b',low):state['need_by_date']=today.isoformat()
  elif 'friday' in low:state['need_by_date']=(today+timedelta(days=((4-today.weekday())%7 or 7))).isoformat()
  q=re.search(r'(?:need|quantity|qty|buy|order)\s*[:=]?\s*(\d+(?:\.\d+)?)',low)
  if not q:q=re.search(r'^\s*(\d+(?:\.\d+)?)\s*(?:nos|pcs|pairs|kg|ltr|units|$)',low)
  if q:state['quantity']=q[1]
  estimate=re.search(r'(?:estimate|price|inr|rs\.?|₹)\s*[:=]?\s*([\d,.]+)',low)
  if estimate:state['estimated_unit_price']=estimate[1].replace(',','')
  if not state.get('description') and low not in ('confirm','yes','restart','start over'):
   description=low
   if q:description=description.replace(q[0],' ')
   description=re.sub(r'20\d\d-\d\d-\d\d',' ',description)
   description=re.split(r'\b(?:for chakan|for bhosari|for pun1|for chk1|by|needed by)\b',description)[0]
   if state.get('plant'):description=re.sub(r'\bfor\s+'+re.escape(state['plant'].lower())+r'\b',' ',description)
   description=re.sub(r'\b(?:need|buy|order|please|normal|emergency)\b',' ',description).strip()
   state['description']=description or message
 item=next((i for i in items if i['item_code']==state.get('item_code')),None)
 if state.get('item_code') and not item:return state,'That item code is not in the catalog. Send a valid item code or restart with a description.',False
 if not item and not state.get('new_item'):
  ranked=candidates(state.get('description',message),items)
  if ranked and ranked[0][0]>=.55:
   if ranked[0][0]>=.75 and (len(ranked)==1 or ranked[0][0]-ranked[1][0]>=.1):
    item=ranked[0][1];state['item_code']=item['item_code']
   else:
    if message.strip().lower()=='new item':state['new_item']=True
    else:
     state['awaiting']='item_code';return state,'Which item do you mean? '+ '; '.join(f'{i["item_code"]}: {i["description"]}' for score,i in ranked[:3])+'. Reply with its code, or “new item”.',False
  else:state['new_item']=True
 if item:state.update(description=item['description'],uom=item['uom'])
 for field,prompt in [('description','What do you need to purchase?'),('quantity','How many units do you need? Reply “quantity 200”, for example.'),('plant','Which plant? '+ '; '.join(p['plant']+' ('+p['name']+')' for p in plants)),('need_by_date','When do you need it? Use YYYY-MM-DD, tomorrow, or next Friday.'),('urgency','Is this Normal or Emergency?')]:
  if not state.get(field):return state,prompt,False
 if state.get('plant') not in {p['plant'] for p in plants}:state.pop('plant',None);return state,'Please choose a plant from the imported plant catalog.',False
 try:
  from .engine import dec
  if dec(state['quantity'])<=0:raise ValueError()
  date.fromisoformat(state['need_by_date'])
 except (ValueError,ArithmeticError):
  state.pop('quantity',None);state.pop('need_by_date',None);return state,'Please provide a positive quantity and a valid need-by date (YYYY-MM-DD).',False
 if not item:
  if not state.get('estimated_unit_price'):return state,'This appears to be a new item. What is the estimated price per unit in INR? Reply “estimate 500”.',False
  state.setdefault('uom','NOS')
 if message.strip().lower() in ('confirm','yes','create pr'):
  return state,'Purchase request created. Open Buyer workspace to review and approve its decision.',True
 return state,f'Please confirm: {state["quantity"]} {state.get("uom","NOS")} of {state["description"]}; {state["plant"]}; needed {state["need_by_date"]}; {state["urgency"]}.'+(' Estimated unit price ₹'+state['estimated_unit_price'] if not item else '')+' Reply “confirm” to create the PR, or tell me what to change.',False
