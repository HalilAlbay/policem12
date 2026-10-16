"""Isolated customer portal and customer-selected quote routing. Additive module."""
import hashlib, secrets, time, sqlite3, os
from pathlib import Path
from datetime import date
from fastapi import Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

class CustomerSignup(BaseModel):
 email:str=Field(min_length=5,max_length=254)
 name:str=Field(min_length=2,max_length=100)
 password:str=Field(min_length=12,max_length=256)
class CustomerLogin(BaseModel):
 email:str
 password:str
class CustomerPolicy(BaseModel):
 policy_type:str=Field(min_length=2,max_length=100)
 insurer:str=Field(default='',max_length=120)
 policy_number:str=Field(min_length=1,max_length=100)
 end_date:date
class QuoteRequest(BaseModel):
 agency_id:int
 product:str=Field(min_length=2,max_length=100)
 message:str=Field(default='',max_length=2000)
 policy_id:int|None=None
 share_policy:bool=False

def register(app,conn,tx,password_hash,check_pw,DATA,ROOT):
 def setup():
  with tx() as c:
   c.executescript('''
   CREATE TABLE IF NOT EXISTS customer_accounts(id INTEGER PRIMARY KEY,email TEXT NOT NULL UNIQUE COLLATE NOCASE,name TEXT NOT NULL,password_hash TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS customer_sessions(token_hash TEXT PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customer_accounts(id),expires INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS customer_policies(id INTEGER PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customer_accounts(id),policy_type TEXT NOT NULL,insurer TEXT NOT NULL,policy_number TEXT NOT NULL,end_date TEXT NOT NULL,document_path TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE TABLE IF NOT EXISTS customer_quotes(id INTEGER PRIMARY KEY,customer_id INTEGER NOT NULL REFERENCES customer_accounts(id),agency_id INTEGER NOT NULL REFERENCES agencies(id),product TEXT NOT NULL,message TEXT NOT NULL,policy_id INTEGER REFERENCES customer_policies(id),share_policy INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'new',created_at TEXT DEFAULT CURRENT_TIMESTAMP);
   CREATE INDEX IF NOT EXISTS idx_customer_quotes_agency ON customer_quotes(agency_id,created_at);
   ''')
 app.router.on_startup.append(setup)
 def customer(request:Request):
  auth=request.headers.get('authorization','')
  if not auth.startswith('Bearer '):raise HTTPException(401,'Müşteri girişi gerekli')
  with tx() as c:
   row=c.execute('SELECT a.id,a.email,a.name FROM customer_sessions s JOIN customer_accounts a ON a.id=s.customer_id WHERE s.token_hash=? AND s.expires>?',(hashlib.sha256(auth[7:].encode()).hexdigest(),int(time.time()))).fetchone()
  if not row:raise HTTPException(401,'Müşteri oturumu geçersiz')
  return dict(row)
 @app.get('/musteri')
 def customer_page():return FileResponse(ROOT/'static/customer.html')
 @app.post('/api/customer/signup')
 def signup(data:CustomerSignup):
  email=data.email.strip().lower()
  if '@' not in email or email.startswith('@'):raise HTTPException(422,'E-posta geçersiz')
  try:
   with tx() as c:
    c.execute('INSERT INTO customer_accounts(email,name,password_hash) VALUES (?,?,?)',(email,data.name.strip(),password_hash(data.password)))
  except sqlite3.IntegrityError:raise HTTPException(409,'Bu e-posta zaten kayıtlı')
  return {'ok':True}
 @app.post('/api/customer/login')
 def login(data:CustomerLogin):
  with tx() as c:
   row=c.execute('SELECT * FROM customer_accounts WHERE email=?',(data.email.strip().lower(),)).fetchone()
   if not row or not check_pw(data.password,row['password_hash']):raise HTTPException(401,'E-posta veya şifre hatalı')
   token=secrets.token_urlsafe(40)
   c.execute('INSERT INTO customer_sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],int(time.time())+86400))
  return {'token':token,'customer':{'id':row['id'],'name':row['name'],'email':row['email']}}
 @app.get('/api/customer/me')
 def me(u=Depends(customer)):return u
 @app.get('/api/customer/agencies')
 def agencies(u=Depends(customer)):
  with tx() as c:return [dict(x) for x in c.execute('SELECT id,name FROM agencies WHERE active=1 ORDER BY name')]
 @app.post('/api/customer/policies')
 def create_policy(p:CustomerPolicy,u=Depends(customer)):
  with tx() as c:
   cur=c.execute('INSERT INTO customer_policies(customer_id,policy_type,insurer,policy_number,end_date) VALUES (?,?,?,?,?)',(u['id'],p.policy_type,p.insurer,p.policy_number,str(p.end_date)))
   return {'id':cur.lastrowid}
 @app.get('/api/customer/policies')
 def policies(u=Depends(customer)):
  with tx() as c:return [dict(x) for x in c.execute('SELECT id,policy_type,insurer,policy_number,end_date,document_path IS NOT NULL AS has_document FROM customer_policies WHERE customer_id=? ORDER BY end_date',(u['id'],))]
 @app.post('/api/customer/policies/{policy_id}/pdf')
 async def upload_pdf(policy_id:int,file:UploadFile=File(...),u=Depends(customer)):
  with tx() as c:
   if not c.execute('SELECT 1 FROM customer_policies WHERE id=? AND customer_id=?',(policy_id,u['id'])).fetchone():raise HTTPException(404,'Poliçe bulunamadı')
  data=await file.read(10*1024*1024+1)
  if len(data)>10*1024*1024 or not data.startswith(b'%PDF-'):raise HTTPException(400,'En fazla 10 MB geçerli PDF yükleyin')
  import fitz
  try:
   doc=fitz.open(stream=data,filetype='pdf')
   if not doc.page_count:raise ValueError('empty')
   doc.close()
  except Exception:raise HTTPException(400,'PDF okunamadı')
  folder=DATA/'customer_documents';folder.mkdir(exist_ok=True)
  path=folder/(secrets.token_hex(24)+'.pdf');path.write_bytes(data)
  with tx() as c:
   old=c.execute('SELECT document_path FROM customer_policies WHERE id=? AND customer_id=?',(policy_id,u['id'])).fetchone()
   if not old:
    path.unlink(missing_ok=True);raise HTTPException(404,'Poliçe bulunamadı')
   c.execute('UPDATE customer_policies SET document_path=? WHERE id=? AND customer_id=?',(str(path),policy_id,u['id']))
  if old['document_path']:
   try:Path(old['document_path']).unlink(missing_ok=True)
   except OSError:pass
  return {'ok':True}
 @app.get('/api/customer/policies/{policy_id}/pdf')
 def download_pdf(policy_id:int,u=Depends(customer)):
  with tx() as c:row=c.execute('SELECT document_path FROM customer_policies WHERE id=? AND customer_id=?',(policy_id,u['id'])).fetchone()
  if not row or not row['document_path']:raise HTTPException(404,'PDF bulunamadı')
  return FileResponse(row['document_path'],media_type='application/pdf',filename='police.pdf')
 @app.post('/api/customer/quotes')
 def quote(p:QuoteRequest,u=Depends(customer)):
  with tx() as c:
   if not c.execute('SELECT 1 FROM agencies WHERE id=? AND active=1',(p.agency_id,)).fetchone():raise HTTPException(404,'Acente bulunamadı')
   if p.policy_id is not None and not c.execute('SELECT 1 FROM customer_policies WHERE id=? AND customer_id=?',(p.policy_id,u['id'])).fetchone():raise HTTPException(404,'Poliçe bulunamadı')
   cur=c.execute('INSERT INTO customer_quotes(customer_id,agency_id,product,message,policy_id,share_policy) VALUES (?,?,?,?,?,?)',(u['id'],p.agency_id,p.product,p.message,p.policy_id,int(p.share_policy and p.policy_id is not None)))
  return {'id':cur.lastrowid,'agency_id':p.agency_id,'status':'new'}
 @app.get('/api/customer/quotes')
 def my_quotes(u=Depends(customer)):
  with tx() as c:return [dict(x) for x in c.execute('SELECT q.id,q.product,q.status,q.created_at,a.name AS agency FROM customer_quotes q JOIN agencies a ON a.id=q.agency_id WHERE q.customer_id=? ORDER BY q.id DESC',(u['id'],))]
 # Agency staff must authenticate through the existing agency login; only the agency's own requests are returned.
 from app import current
 @app.get('/api/agency/quote-requests')
 def agency_quotes(u=Depends(current)):
  with tx() as c:
   branch=c.execute('SELECT agency_id FROM branches WHERE id=?',(u['branch_id'],)).fetchone()
   if not branch:raise HTTPException(403,'Acente bağlantısı yok')
   rows=c.execute('''SELECT q.id,q.product,q.message,q.status,q.created_at,q.share_policy,ca.name AS customer_name,ca.email AS customer_email,
    CASE WHEN q.share_policy=1 THEN p.policy_type END AS policy_type,
    CASE WHEN q.share_policy=1 THEN p.insurer END AS insurer,
    CASE WHEN q.share_policy=1 THEN p.policy_number END AS policy_number
    FROM customer_quotes q JOIN customer_accounts ca ON ca.id=q.customer_id
    LEFT JOIN customer_policies p ON p.id=q.policy_id AND p.customer_id=q.customer_id
    WHERE q.agency_id=? ORDER BY q.id DESC''',(branch['agency_id'],)).fetchall()
   return [dict(x) for x in rows]
