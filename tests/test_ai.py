import io,json,os,unittest,urllib.error
from unittest.mock import patch
from app import ai

class OpenRouterTests(unittest.TestCase):
 def test_missing_key(self):
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':''}):
   self.assertFalse(ai.available())
   with self.assertRaisesRegex(ValueError,'OPENROUTER_API_KEY'):ai.interpret('Extract',{})
 def test_openrouter_request(self):
  response=io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"fields":{"quantity":"5"}}'}}]}).encode())
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key','OPENROUTER_MODEL':'provider/test-model'}),patch('app.ai.urllib.request.urlopen',return_value=response) as send:
   self.assertEqual(ai.interpret('Extract',{}),{'fields':{'quantity':'5'}})
   request=send.call_args.args[0]
   self.assertEqual(request.full_url,'https://openrouter.ai/api/v1/chat/completions')
   self.assertEqual(request.get_header('Authorization'),'Bearer test-key')
   self.assertEqual(json.loads(request.data)['model'],'provider/test-model')
 def test_safe_provider_error(self):
  with patch.dict(os.environ,{'OPENROUTER_API_KEY':'private-test-key'}),patch('app.ai.urllib.request.urlopen',side_effect=urllib.error.URLError('failed')):
   with self.assertRaisesRegex(ValueError,'AI interpretation failed') as error:ai.interpret('Extract',{})
   self.assertNotIn('private-test-key',str(error.exception))

 def test_malformed_provider_responses(self):
  for result in ({'choices':[]},{'choices':[{'message':{'content':None}}]},{'choices':[{'message':{'content':'[]'}}]}):
   with self.subTest(result=result),patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}),patch('app.ai.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(result).encode())):
    with self.assertRaisesRegex(ValueError,'AI interpretation failed'):ai.interpret('Extract',{})
