"""Private local import. Reads kit files from the supplied path; never copies them into source."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import store
from app.engine import read_csv,validate_data
from app.documents import extract
from app.server import contract_draft

def load(root):
 store.init()
 files=[('items','master_data/item_master.csv'),('suppliers','master_data/supplier_master.csv'),('plants','master_data/plants.csv'),('contracts','contracts/contract_register.csv'),('contract_lines','contracts/contract_lines.csv'),('history','master_data/po_history.csv')]
 with store.connect() as db:
  data=store.data(db)
  for kind,file in files:
   rows=read_csv((root/file).read_text(encoding='utf-8-sig'),kind);validate_data(data,kind,rows);store.save_data(db,kind,rows,'local-import');data[kind]=rows;print(f'{kind}: {len(rows)} rows')
  for p in sorted((root/'contracts/pdf').glob('*.pdf')):
   draft=contract_draft(extract(p.read_bytes()),data);c=draft['contract']
   if any(r['contract_id']==c['contract_id'] for r in data['contracts']):continue
   validate_data(data,'contracts',[c]);data['contracts'].append(c);validate_data(data,'contract_lines',draft['lines']);data['contract_lines']+=draft['lines'];print('Added signed PDF contract '+c['contract_id'])
  for kind in ('contracts','contract_lines'):store.save_data(db,kind,data[kind],'local-import')
if __name__=='__main__':load(Path(sys.argv[1] if len(sys.argv)>1 else '.'))
