"""Run the same API acceptance tests against an isolated CI PostgreSQL database."""
import os,tempfile,unittest
from unittest.mock import patch
import test_api
from test_engine import fixture
from app import store

@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'),'TEST_DATABASE_URL not configured')
class PostgresAPItests(test_api.APItests):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.env=patch.dict(os.environ,{'DATABASE_URL':os.environ['TEST_DATABASE_URL'],'APP_PASSWORD':'test-buyer','REQUESTER_PASSWORD':'test-employee','OPENROUTER_API_KEY':''})
  self.env.start();store.init()
  # TEST_DATABASE_URL must point to a disposable test database, never production.
  with store.connect() as db:
   db.execute('TRUNCATE datasets,policies,runs,actions,documents,document_lines,reservations,audit,chats RESTART IDENTITY CASCADE')
  store.init()
  with store.connect() as db:
   for kind,rows in fixture().items():store.save_data(db,kind,rows,'test')
