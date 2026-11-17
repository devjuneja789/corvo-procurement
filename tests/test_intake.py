import os,unittest
from unittest.mock import patch
from app.intake import turn
from test_engine import fixture

class IntakeTests(unittest.TestCase):
 def setUp(self):self.env=patch.dict(os.environ,{'OPENROUTER_API_KEY':''});self.env.start();self.data=fixture()
 def tearDown(self):self.env.stop()
 def test_catalog_request_followup_and_confirmation(self):
  state,reply,done=turn({},'Need 20 industrial widget 20mm for SITE-A by 2026-12-01',self.data)
  self.assertEqual(state.get('quantity'),'20');self.assertEqual(state.get('item_code'),'DEMO-A');self.assertFalse(done)
  state,reply,done=turn(state,'Normal',self.data);self.assertFalse(done);self.assertIn('confirm',reply)
  state,reply,done=turn(state,'confirm',self.data);self.assertTrue(done)
 def test_ambiguous_choice_requires_confirmation(self):
  other=dict(self.data['items'][0]);other['item_code']='DEMO-B';other['description']='Industrial widget 20mm premium';self.data['items'].append(other)
  state,reply,done=turn({},'Need 20 industrial widget 20mm for SITE-A by 2026-12-01',self.data);self.assertFalse(done)
 def test_new_item_asks_estimate(self):
  s={'description':'Uncatalogued appliance','new_item':True,'quantity':'1','plant':'SITE-A','need_by_date':'2026-12-01','urgency':'Normal'}
  state,reply,done=turn(s,'confirm',self.data);self.assertFalse(done);self.assertIn('estimated',reply)
