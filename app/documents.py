"""Document extraction: pypdf when installed; local fallback handles the kit's PDFs."""
import re,zlib,io

def extract(raw,name='document.txt'):
 if not raw.startswith(b'%PDF'):return raw.decode('utf-8-sig')
 try:
  from pypdf import PdfReader
  text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(raw)).pages)
  if text.strip():return text
 except ImportError:pass
 except Exception:pass
 objs={int(m[1]):m[2] for m in re.finditer(rb'(\d+) 0 obj\b(.*?)endobj',raw,re.S)}
 def stream(o):
  m=re.search(rb'stream\r?\n(.*?)endstream',o,re.S)
  if not m:return b''
  length=re.search(rb'/Length (\d+)\b',o);s=m[1][:int(length[1])] if length else m[1]
  if b'/FlateDecode' in o:
   dz=zlib.decompressobj();s=dz.decompress(s,8_000_000)
   if dz.unconsumed_tail:raise ValueError('PDF stream is too large')
  return s
 maps={};widths={}
 for n,o in objs.items():
  ref=re.search(rb'/ToUnicode (\d+) 0 R',o)
  if not ref:continue
  s=stream(objs[int(ref[1])]);d={}
  for block in re.findall(rb'beginbfchar(.*?)endbfchar',s,re.S):
   for a,b in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>',block):d[int(a,16)]=bytes.fromhex(b.decode()).decode('utf-16-be')
  for block in re.findall(rb'beginbfrange(.*?)endbfrange',s,re.S):
   for a,b,c in re.findall(rb'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>',block):
    if int(b,16)-int(a,16)>65536:raise ValueError('Invalid PDF character range')
    for k in range(int(a,16),int(b,16)+1):d[k]=chr(int(c,16)+k-int(a,16))
  maps[n]=d;widths[n]=2 if b'<0000>' in s else 1
 out=[]
 for n,o in objs.items():
  if not re.search(rb'/Type /Page\b',o):continue
  fonts={a.decode():int(b) for a,b in re.findall(rb'/(F\d+) (\d+) 0 R',o)}
  refs=re.search(rb'/Contents (\d+) 0 R',o)
  if not refs:continue
  s=stream(objs[int(refs[1])]);font=None
  for m in re.finditer(rb'/(F\d+) [\d.]+ Tf|<([0-9A-Fa-f]+)>\s*Tj|\(([^()]*)\)\s*Tj|\bET\b',s):
   if m[1]:font=fonts[m[1].decode()]
   elif m[2]:
    width=widths.get(font,2)*2
    out.append(''.join(maps.get(font,{}).get(int(m[2][i:i+width],16),'�') for i in range(0,len(m[2]),width)))
   elif m[3]:out.append(m[3].decode('latin1'))
   else:out.append('\n')
 text=''.join(out)
 # Chromium's embedded punctuation uses these private-use glyphs.
 for a,b in {'\ue082':'(', '\ue083':')','\ue088':'-','\ue092':':','\ue099':'≤','\ue09f':'×'}.items():text=text.replace(a,b)
 if not text.strip() or text.count('�')>max(5,len(text)*.01):raise ValueError('PDF extraction incomplete. Install pypdf, or upload extracted text / enter the contract manually. Scanned PDFs need OCR outside this app.')
 return text
