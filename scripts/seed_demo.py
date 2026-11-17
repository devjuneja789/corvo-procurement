"""Seed entirely synthetic, public-safe demo data. Does not read the task kit."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.engine import read_csv,validate_data
store.init()
with store.connect() as db:
 data=store.data(db)
 for kind in ('items','suppliers','plants','contracts','contract_lines','history'):
  if data.get(kind):raise SystemExit('Refusing to overwrite existing data. Use a fresh DATABASE_PATH for the demo.')
  rows=read_csv((Path(__file__).resolve().parents[1]/'demo'/(kind+'.csv')).read_text(),kind)
  validate_data(data,kind,rows);data[kind]=rows;store.save_data(db,kind,rows,'demo-seed')
print('Synthetic demo imported. Start with python3 -m app.server')
