import sqlite3,json,os,hashlib
from datetime import datetime,timezone
from pathlib import Path
from .policy import DEFAULT

def now():return datetime.now(timezone.utc).isoformat()
class PostgresConnection:
 """Expose the small DB interface used by the app over psycopg."""
 def __init__(self,url):
  try:
   import psycopg
   from psycopg.rows import dict_row
  except ImportError as exc:raise ValueError('Install requirements.txt to use DATABASE_URL') from exc
  self.db=psycopg.connect(url,row_factory=dict_row,connect_timeout=15)
 def __enter__(self):return self
 def __exit__(self,kind,value,tb):
  try:
   if kind:self.db.rollback()
   else:self.db.commit()
  finally:self.db.close()
 def execute(self,sql,params=()):
  if sql=='BEGIN IMMEDIATE':
   # Serialize read-modify-write purchasing actions across connections.
   return self.db.execute('SELECT pg_advisory_xact_lock(72812501)')
  sql=sql.replace('?', '%s')
  needs_id=sql.startswith(('INSERT INTO runs(', 'INSERT INTO policies(')) and 'ON CONFLICT' not in sql
  cursor=self.db.execute(sql+(' RETURNING id' if needs_id else ''),params)
  if needs_id:
   from types import SimpleNamespace
   return SimpleNamespace(lastrowid=cursor.fetchone()['id'])
  return cursor
 def executescript(self,sql):
  self.execute('BEGIN IMMEDIATE')
  sql=sql.replace('id INTEGER PRIMARY KEY','id BIGSERIAL PRIMARY KEY')
  for statement in sql.split(';'):
   if statement.strip():self.execute(statement)

def connect():
 url=os.environ.get('DATABASE_URL','').strip()
 if url:
  if not url.startswith(('postgres://','postgresql://')):raise ValueError('DATABASE_URL must be a PostgreSQL connection URL')
  return PostgresConnection(url)
 path=Path(os.environ.get('DATABASE_PATH','private_data/app.sqlite3'));path.parent.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row;db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA foreign_keys=ON');return db

def init():
 with connect() as db:
  db.executescript('''
  CREATE TABLE IF NOT EXISTS datasets(kind TEXT PRIMARY KEY, body TEXT NOT NULL, digest TEXT NOT NULL, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS policies(id INTEGER PRIMARY KEY, version TEXT UNIQUE NOT NULL, body TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, label TEXT NOT NULL, body TEXT NOT NULL, snapshot TEXT NOT NULL, policy TEXT NOT NULL, created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, group_id TEXT NOT NULL, action TEXT NOT NULL, comment TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id,group_id));
  CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, run_id INTEGER NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS document_lines(pr_no TEXT NOT NULL, pr_line TEXT NOT NULL, document_id TEXT NOT NULL, UNIQUE(pr_no,pr_line));
  CREATE TABLE IF NOT EXISTS reservations(document_id TEXT NOT NULL, contract_id TEXT NOT NULL, amount TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, event TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, body TEXT NOT NULL);
  ''')
  db.execute('INSERT INTO policies(version,body,source,status,created_at) VALUES(?,?,?,?,?) ON CONFLICT(version) DO NOTHING',(DEFAULT['version'],json.dumps(DEFAULT),'Initial policy encoded from supplied specification; review in policy workspace.','active',now()))

def audit(db,event,actor,details):db.execute('INSERT INTO audit(event,actor,details,created_at) VALUES(?,?,?,?)',(event,actor,json.dumps(details),now()))
def data(db):return {r['kind']:json.loads(r['body']) for r in db.execute('SELECT * FROM datasets')}
def save_data(db,kind,rows,actor):
 body=json.dumps(rows,sort_keys=True);digest=hashlib.sha256(body.encode()).hexdigest()
 db.execute('INSERT INTO datasets(kind,body,digest,updated_at) VALUES(?,?,?,?) ON CONFLICT(kind) DO UPDATE SET body=excluded.body,digest=excluded.digest,updated_at=excluded.updated_at',(kind,body,digest,now()));audit(db,'dataset_uploaded',actor,{'kind':kind,'rows':len(rows),'sha256':digest})
def policies(db):return [dict(r)|{'body':json.loads(r['body'])} for r in db.execute('SELECT * FROM policies ORDER BY id DESC')]
