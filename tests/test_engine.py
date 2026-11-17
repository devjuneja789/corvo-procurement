import copy,unittest
from app.engine import process,preferred,read_csv,validate_data
from app.policy import DEFAULT,validate
from app.intake import turn

def fixture():
 return {'items':[{'item_code':'DEMO-A','description':'Industrial widget 20mm','uom':'NOS','category':'Parts','item_type':'Material','standard_price':'100'}], 'suppliers':[{'supplier_id':'V-A','name':'Vendor A','city':'Delhi','categories':'Parts','status':'Active','on_time_pct':'90','quality_rating':'4.5'},{'supplier_id':'V-B','name':'Vendor B','city':'Mumbai','categories':'Parts','status':'Active','on_time_pct':'95','quality_rating':'4'}], 'plants':[{'plant':'SITE-A','name':'Alpha'},{'plant':'SITE-B','name':'Beta'}], 'history':[{'po_number':'H1','po_date':'2026-10-01','supplier_id':'V-A','item_code':'DEMO-A','quantity':'2','uom':'NOS','unit_price':'100','plant':'SITE-A','delivered_on_time':'True'}], 'contracts':[],'contract_lines':[]}
def line(n=1,**kw):
 r={'pr_no':f'P-{n}','pr_line':'1','created_at':'2026-11-01 09:00','requester':'Tester','department':'Ops','plant':'SITE-A','item_code':'DEMO-A','description':'Industrial widget 20mm','quantity':'1','uom':'NOS','estimated_unit_price':'100','need_by_date':'2026-11-20','urgency':'Normal'};r.update(kw);return r

def contract(data,cid='C1',rate='80',cap='1000',consumed='0',supplier='V-A'):
 data['contracts'].append({'contract_id':cid,'supplier_id':supplier,'supplier_name':supplier,'start_date':'2026-01-01','end_date':'2026-12-31','value_cap':cap,'consumed_value':consumed})
 data['contract_lines'].append({'contract_id':cid,'item_code':'DEMO-A','description':'Industrial widget 20mm','uom':'NOS','rate':rate})

class EngineTests(unittest.TestCase):
 def setUp(self):self.data=fixture();self.policy=copy.deepcopy(DEFAULT)
 def runlines(self,lines):return process(self.data,lines,self.policy)
 def test_thresholds(self):
  for qty,urgency,route in [('1999','Normal','SPOT_PO'),('2000','Normal','RFQ'),('5000','Emergency','EMERGENCY_PO'),('5000.01','Emergency','RFQ'),('10000','Normal','RFP')]:
   with self.subTest(qty=qty):self.assertEqual(self.runlines([line(quantity=qty,urgency=urgency)])['rows'][0]['route'],route)
 def test_small_without_active_history(self):
  self.data['suppliers'][0]['status']='Blocked';r=self.runlines([line()]);self.assertEqual(r['rows'][0]['route'],'RFQ');self.assertNotIn('V-A',r['rows'][0]['suggested_supplier_ids'])
 def test_new_item_is_never_clubbed(self):
  r=self.runlines([line(item_code='',description='Uncatalogued quantum appliance'),line(2,item_code='',description='Uncatalogued quantum appliance')]);self.assertEqual(len(r['groups']),2);self.assertTrue(all(x['route']=='NEW_ITEM_SOURCING' and not x['suggested_supplier_ids'] for x in r['rows']))
 def test_clubbing_anchored_windows(self):
  r=self.runlines([line(),line(2,created_at='2026-11-15 23:00',need_by_date='2026-11-27'),line(3,created_at='2026-11-16 09:00',need_by_date='2026-11-27')]);self.assertEqual([len(g['lines']) for g in r['groups']],[2,1])
 def test_needby_and_plants(self):
  r=self.runlines([line(),line(2,need_by_date='2026-11-28'),line(3,plant='SITE-B')]);self.assertEqual(len(r['groups']),3)
 def test_any_emergency(self):
  r=self.runlines([line(quantity='1500'),line(2,quantity='1500',urgency='Emergency')]);self.assertEqual(r['rows'][0]['route'],'EMERGENCY_PO')
 def test_contract_selection_and_shared_ceiling(self):
  contract(self.data,rate='80',cap='100');contract(self.data,'C2',rate='90',cap='1000',supplier='V-B')
  r=self.runlines([line(),line(2,need_by_date='2026-12-20')]);self.assertEqual([x['unit_price'] for x in r['rows']],['80.00','90.00']);self.assertEqual(r['ceiling_consumed']['C1'],'80.00')
 def test_exhausted_valuation(self):
  contract(self.data,rate='80',cap='10');r=self.runlines([line(quantity='3000')]);self.assertEqual(r['rows'][0]['group_value_inr'],'240000.00');self.assertEqual(r['rows'][0]['route'],'RFQ')
 def test_capex_before_contract(self):
  self.data['items'][0]['item_type']='Capex';contract(self.data);r=self.runlines([line()]);self.assertEqual(r['rows'][0]['route'],'CAPEX_SOURCING');self.assertEqual(r['ceiling_consumed']['C1'],'0.00')
 def test_replay_is_pure(self):
  contract(self.data);original=copy.deepcopy(self.data);self.assertEqual(self.runlines([line()]),self.runlines([line()]));self.assertEqual(self.data,original)
 def test_consolidation_24h_anchor(self):
  r=self.runlines([line(),line(2,created_at='2026-11-02 09:00',need_by_date='2026-12-01'),line(3,created_at='2026-11-03 08:00',need_by_date='2027-01-01')]);self.assertEqual([x['po_id'] for x in r['rows']],['PO-0001','PO-0001','PO-0002'])
 def test_history_boundaries(self):
  self.data['history'][0]['po_date']='2025-11-01';self.assertEqual(self.runlines([line()])['rows'][0]['route'],'SPOT_PO');self.data['history'][0]['po_date']='2025-10-31';self.assertEqual(self.runlines([line()])['rows'][0]['route'],'RFQ')
 def test_future_evidence_excluded(self):
  self.data['history'][0]['po_date']='2026-11-02';self.assertEqual(preferred(self.data,self.data['items'][0],'2026-11-01',self.policy),[])
 def test_expired_contract_preferred_eligible(self):
  self.data['history']=[];contract(self.data);self.data['contracts'][0]['end_date']='2026-09-01';r=preferred(self.data,self.data['items'][0],'2026-11-01',self.policy);self.assertEqual(r[0]['reference_price'],'80.00')
 def test_invalid_line_accounted_for(self):
  r=self.runlines([line(quantity='0'),line(2,plant='MISSING'),line(3,uom='KG')]);self.assertEqual(len(r['rows']),3);self.assertEqual(r['summary']['not_processed'],3)
 def test_plant_rule_added_without_code(self):
  self.policy['rules'].insert(0,{'id':'A1','when':{'all':[{'field':'plant','op':'eq','value':'SITE-A'},{'field':'category','op':'eq','value':'Parts'}]},'route':'RFQ','suggest':3});validate(self.policy);self.assertEqual(self.runlines([line()])['rows'][0]['route'],'RFQ')
 def test_malformed_policy_rejected(self):
  self.policy['rules'][0]['when']={'field':'__import__','op':'eq','value':'x'}
  with self.assertRaises(ValueError):validate(self.policy)
 def test_invalid_csv_rejected(self):
  with self.assertRaises(ValueError):read_csv('a,b\n1,2','prs')
 def test_numeric_spec_mismatch_is_new(self):
  r=self.runlines([line(item_code='',description='Industrial widget 30mm')]);self.assertEqual(r['rows'][0]['resolved_item_code'],'NEW')

if __name__=='__main__':unittest.main()
