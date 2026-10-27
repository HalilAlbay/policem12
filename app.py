"""Policem server: SQLite-backed operations. Run: uvicorn app:app --host 0.0.0.0 --port 8000"""
import os, sqlite3, secrets, hashlib, hmac, json, re, time, threading, smtplib, sys, base64, ssl
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import fitz
from urllib.parse import urlsplit
from webauthn import (generate_registration_options, verify_registration_response,
 generate_authentication_options, verify_authentication_response, options_to_json, base64url_to_bytes)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria, AuthenticatorAttachment,
 ResidentKeyRequirement, UserVerificationRequirement, PublicKeyCredentialDescriptor)
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

ROOT=Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
STORAGE_ROOT=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else ROOT
DATA=Path(os.environ.get('POLICEM_DATA',str(STORAGE_ROOT/'data')))
DATA.mkdir(parents=True,exist_ok=True)
(DATA/'documents').mkdir(exist_ok=True)
DB=DATA/'policem.sqlite3'
LOCK=threading.RLock()

def conn():
 c=sqlite3.connect(DB,timeout=20,check_same_thread=False)
 c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');return c

@contextmanager
def tx():
 with LOCK:
  c=conn()
  try:
   yield c;c.commit()
  except: c.rollback();raise
  finally:c.close()

def init():
 with tx() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS agencies(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS branches(id INTEGER PRIMARY KEY,agency_id INTEGER NOT NULL REFERENCES agencies(id),name TEXT NOT NULL,active INTEGER DEFAULT 1);
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('partner','manager','staff')),password_hash TEXT NOT NULL,branch_id INTEGER REFERENCES branches(id),active INTEGER DEFAULT 1,theme TEXT DEFAULT '#1755a2',email TEXT);
  CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS trusted_devices(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),label TEXT NOT NULL,created_at INTEGER NOT NULL,last_seen INTEGER NOT NULL,revoked_at INTEGER,UNIQUE(id,user_id));
  CREATE INDEX IF NOT EXISTS idx_trusted_devices_user ON trusted_devices(user_id,revoked_at);
  CREATE TABLE IF NOT EXISTS device_sessions(token_hash TEXT PRIMARY KEY REFERENCES sessions(token_hash) ON DELETE CASCADE,device_id TEXT NOT NULL REFERENCES trusted_devices(id));
  CREATE TABLE IF NOT EXISTS refresh_sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),device_id TEXT REFERENCES trusted_devices(id),expires INTEGER NOT NULL,created_at INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS device_pin(device_id TEXT PRIMARY KEY REFERENCES trusted_devices(id),pin_hash TEXT NOT NULL,failures INTEGER NOT NULL DEFAULT 0,locked_at INTEGER);
  CREATE TABLE IF NOT EXISTS policies(id INTEGER PRIMARY KEY,agency_id INTEGER NOT NULL REFERENCES agencies(id),branch_id INTEGER REFERENCES branches(id),owner_user_id INTEGER REFERENCES users(id),seller_user_id INTEGER REFERENCES users(id),uploader_user_id INTEGER NOT NULL REFERENCES users(id),customer_name TEXT NOT NULL,policy_type TEXT NOT NULL,policy_number TEXT NOT NULL,insurer TEXT DEFAULT '',premium REAL NOT NULL DEFAULT 0,start_date TEXT NOT NULL,end_date TEXT NOT NULL,issued_date TEXT NOT NULL,tracking INTEGER NOT NULL DEFAULT 0,external INTEGER NOT NULL DEFAULT 0,document_path TEXT,renewed_from INTEGER REFERENCES policies(id),created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(agency_id,insurer,policy_number));
  CREATE TABLE IF NOT EXISTS renewals(id INTEGER PRIMARY KEY,policy_id INTEGER NOT NULL UNIQUE REFERENCES policies(id),status TEXT NOT NULL DEFAULT 'bekliyor',updated_by INTEGER REFERENCES users(id),updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
  CREATE TABLE IF NOT EXISTS reminders(id INTEGER PRIMARY KEY,policy_id INTEGER NOT NULL REFERENCES policies(id),days_before INTEGER NOT NULL,channel TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(policy_id,days_before,channel));
  CREATE TABLE IF NOT EXISTS branding(id INTEGER PRIMARY KEY CHECK(id=1),app_name TEXT NOT NULL DEFAULT 'Parantez Poliçem',color TEXT NOT NULL DEFAULT '#1755a2',icon_mime TEXT,icon_bytes BLOB);
  INSERT OR IGNORE INTO branding(id,app_name,color) VALUES (1,'Parantez Poliçem','#1755a2');
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER REFERENCES users(id),action TEXT NOT NULL,entity TEXT NOT NULL,entity_id INTEGER,payload TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
  ''')
  session_cols={x['name'] for x in c.execute('PRAGMA table_info(sessions)')}
  added_activity='last_activity' not in session_cols
  if added_activity:
   c.execute('ALTER TABLE sessions ADD COLUMN last_activity INTEGER NOT NULL DEFAULT 0')
  security_meta_exists=bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='auth_schema_meta'").fetchone())
  c.execute('''CREATE TABLE IF NOT EXISTS auth_schema_meta(
    id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL)''')
  c.execute('INSERT OR IGNORE INTO auth_schema_meta(id,version) VALUES (1,1)')
  user_cols={x['name'] for x in c.execute('PRAGMA table_info(users)')}
  if 'webauthn_user_handle' not in user_cols:
   c.execute('ALTER TABLE users ADD COLUMN webauthn_user_handle TEXT')
  for urow in c.execute('SELECT id FROM users WHERE webauthn_user_handle IS NULL').fetchall():
   c.execute('UPDATE users SET webauthn_user_handle=? WHERE id=?',(secrets.token_urlsafe(32),urow['id']))
  c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_webauthn_handle ON users(webauthn_user_handle) WHERE webauthn_user_handle IS NOT NULL')
  device_cols={x['name'] for x in c.execute('PRAGMA table_info(trusted_devices)')}
  if 'installation_id' not in device_cols:
   c.execute('ALTER TABLE trusted_devices ADD COLUMN installation_id TEXT')
   c.execute('UPDATE trusted_devices SET installation_id=id WHERE installation_id IS NULL')
  c.execute('''CREATE TABLE IF NOT EXISTS webauthn_credentials(
   credential_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
   device_id TEXT NOT NULL REFERENCES trusted_devices(id),public_key BLOB NOT NULL,
   sign_count INTEGER NOT NULL DEFAULT 0,device_type TEXT NOT NULL DEFAULT 'single_device',
   backed_up INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,last_used_at INTEGER,
   revoked_at INTEGER)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_webauthn_user ON webauthn_credentials(user_id,revoked_at)')
  c.execute('''CREATE TABLE IF NOT EXISTS webauthn_challenges(
   id TEXT PRIMARY KEY,purpose TEXT NOT NULL CHECK(purpose IN ('register','login')),
   user_id INTEGER REFERENCES users(id),session_hash TEXT,challenge BLOB NOT NULL,
   label TEXT,created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,consumed_at INTEGER)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_webauthn_challenge_expiry ON webauthn_challenges(expires_at,consumed_at)')
  challenge_cols={x['name'] for x in c.execute('PRAGMA table_info(webauthn_challenges)')}
  if 'installation_id' not in challenge_cols:c.execute('ALTER TABLE webauthn_challenges ADD COLUMN installation_id TEXT')
  c.execute('''CREATE TABLE IF NOT EXISTS pin_device_keys(
   device_id TEXT PRIMARY KEY REFERENCES trusted_devices(id),user_id INTEGER NOT NULL REFERENCES users(id),
   public_key TEXT NOT NULL,created_at INTEGER NOT NULL,revoked_at INTEGER)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_pin_keys_user ON pin_device_keys(user_id,revoked_at)')
  c.execute('''CREATE TABLE IF NOT EXISTS pin_challenges(
   id TEXT PRIMARY KEY,purpose TEXT NOT NULL CHECK(purpose IN ('enroll','login')),
   device_id TEXT NOT NULL,user_id INTEGER,session_hash TEXT,challenge BLOB NOT NULL,label TEXT,
   created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,consumed_at INTEGER)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_pin_challenge_expiry ON pin_challenges(expires_at,consumed_at)')
  pin_challenge_cols={x['name'] for x in c.execute('PRAGMA table_info(pin_challenges)')}
  if 'installation_id' not in pin_challenge_cols:c.execute('ALTER TABLE pin_challenges ADD COLUMN installation_id TEXT')
  c.execute('''CREATE TABLE IF NOT EXISTS device_login_settings(
   installation_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
   device_id TEXT NOT NULL UNIQUE REFERENCES trusted_devices(id),method TEXT NOT NULL CHECK(method IN ('pin','webauthn')),
   updated_at INTEGER NOT NULL)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_device_login_user ON device_login_settings(user_id)')
  c.execute('UPDATE auth_schema_meta SET version=4 WHERE id=1 AND version<4')
  user_cols={x['name'] for x in c.execute('PRAGMA table_info(users)')}
  if 'must_change_password' not in user_cols:c.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0')
  if 'email_verified_at' not in user_cols:c.execute('ALTER TABLE users ADD COLUMN email_verified_at INTEGER')
  if 'pending_email' not in user_cols:c.execute('ALTER TABLE users ADD COLUMN pending_email TEXT')
  c.execute('''CREATE TABLE IF NOT EXISTS account_tokens(
   token_hash TEXT PRIMARY KEY,purpose TEXT NOT NULL CHECK(purpose IN ('verify_email','password_reset')),
   user_id INTEGER NOT NULL REFERENCES users(id),email TEXT,created_at INTEGER NOT NULL,
   expires_at INTEGER NOT NULL,consumed_at INTEGER)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_account_tokens_expiry ON account_tokens(expires_at,consumed_at)')
  c.execute('DELETE FROM account_tokens WHERE expires_at<?',(int(time.time())-86400,))
  c.execute('UPDATE auth_schema_meta SET version=5 WHERE id=1 AND version<5')
  c.execute('DELETE FROM webauthn_challenges WHERE expires_at<? OR consumed_at IS NOT NULL',(int(time.time())-86400,))
  c.execute('DELETE FROM pin_challenges WHERE expires_at<? OR consumed_at IS NOT NULL',(int(time.time())-86400,))
  c.execute('''CREATE TABLE IF NOT EXISTS auth_attempts(
    scope_hash TEXT PRIMARY KEY,attempts INTEGER NOT NULL CHECK(attempts>=0),
    window_started INTEGER NOT NULL,updated_at INTEGER NOT NULL)''')
  c.execute('CREATE INDEX IF NOT EXISTS idx_auth_attempts_updated ON auth_attempts(updated_at)')
  if added_activity:
   c.execute('UPDATE sessions SET last_activity=? WHERE expires>?',(int(time.time()),int(time.time())))
  if not security_meta_exists:
   revoked=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE revoked_at IS NULL').fetchone()[0]
   c.execute('UPDATE trusted_devices SET revoked_at=? WHERE revoked_at IS NULL',(int(time.time()),))
   c.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM device_sessions)')
   c.execute('DELETE FROM refresh_sessions')
   c.execute('DELETE FROM device_pin')
   if revoked:audit(c,None,'legacy_quick_login_revoked','trusted_device',None,{'count':revoked})
  c.execute('DELETE FROM auth_attempts WHERE updated_at<?',(int(time.time())-86400,))
  c.execute("UPDATE branding SET app_name='Parantez Poliçem' WHERE id=1 AND app_name='Poliçem'")
  cols={x['name'] for x in c.execute('PRAGMA table_info(users)')}
  if 'phone' not in cols:c.execute('ALTER TABLE users ADD COLUMN phone TEXT')
  if 'start_date' not in cols:c.execute('ALTER TABLE users ADD COLUMN start_date TEXT')
  if 'job_title' not in cols:c.execute("ALTER TABLE users ADD COLUMN job_title TEXT NOT NULL DEFAULT 'technical'")
  c.execute("UPDATE users SET job_title=CASE role WHEN 'partner' THEN 'agency_authority' WHEN 'manager' THEN 'agency_manager' ELSE 'technical' END WHERE job_title='technical' AND role IN ('partner','manager')")
  if not c.execute('SELECT 1 FROM agencies').fetchone():
   c.execute('INSERT INTO agencies(name) VALUES (?)',('Ana Acente',))
   c.execute('INSERT INTO branches(agency_id,name) VALUES (1,?)',('Merkez',))
  if not c.execute('SELECT 1 FROM users').fetchone():
   pw=os.environ.get('POLICEM_ADMIN_PASSWORD')
   if pw: c.execute('INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES (?,?,?,?,1)',('admin','İlk Yönetici','partner',password_hash(pw)))

def password_hash(pw):
 salt=secrets.token_bytes(16);dk=hashlib.pbkdf2_hmac('sha256',pw.encode(),salt,350000)
 return salt.hex()+':'+dk.hex()

def check_pw(pw,stored):
 try:
  salt,expected=stored.split(':');actual=hashlib.pbkdf2_hmac('sha256',pw.encode(),bytes.fromhex(salt),350000)
  return hmac.compare_digest(actual,bytes.fromhex(expected))
 except: return False

def pin_hash(pin):
 salt=secrets.token_bytes(16);derived=hashlib.scrypt(pin.encode('ascii'),salt=salt,n=2**15,r=8,p=1,dklen=32,maxmem=64*1024*1024)
 return 'scrypt$32768$8$1$'+base64.urlsafe_b64encode(salt).decode().rstrip('=')+'$'+base64.urlsafe_b64encode(derived).decode().rstrip('=')

def check_pin_hash(pin,stored):
 try:
  kind,n,r,p,salt_text,expected_text=stored.split('$')
  if kind!='scrypt' or (int(n),int(r),int(p))!=(32768,8,1) or not re.fullmatch(r'\d{4}',pin):return False
  salt=base64.urlsafe_b64decode(salt_text+'='*((4-len(salt_text)%4)%4));expected=base64.urlsafe_b64decode(expected_text+'='*((4-len(expected_text)%4)%4))
  actual=hashlib.scrypt(pin.encode('ascii'),salt=salt,n=32768,r=8,p=1,dklen=32,maxmem=64*1024*1024)
  return hmac.compare_digest(actual,expected)
 except Exception:return False

DUMMY_PASSWORD_HASH=password_hash('constant-time-login-placeholder')

def audit(c,user,action,entity,eid,payload=None):
 c.execute('INSERT INTO audit(actor,action,entity,entity_id,payload) VALUES (?,?,?,?,?)',(user,action,entity,eid,json.dumps(payload,ensure_ascii=False,default=str) if payload is not None else None))

app=FastAPI(title='Poliçem API',docs_url=None,redoc_url=None)
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.on_event('startup')
def startup():
 init()
 if os.getenv("RENDER_SERVICE_NAME") == "policem12-push-test":
  import logging
  from push_service import vapid_diagnostic
  logging.getLogger("uvicorn.error").warning("VAPID startup diagnostic: %s", vapid_diagnostic())
  # Test-only scheduler. Runs while the web process is alive; no iPhone login required.
  def expiry_push_loop():
   from datetime import datetime
   from zoneinfo import ZoneInfo
   from push_job import tick
   import logging
   while True:
    try:
     result=tick(datetime.now(ZoneInfo('Europe/Istanbul')).date())
     logging.getLogger("uvicorn.error").info("Policy expiry push tick: %s",result)
    except Exception:
     logging.getLogger("uvicorn.error").exception("Policy expiry push tick failed")
    time.sleep(900)
  threading.Thread(target=expiry_push_loop,daemon=True,name="policem-expiry-push").start()
@app.get('/api/health')
def health():
 with conn() as c: c.execute('SELECT 1').fetchone()
 return {'ok':True}

@app.get('/')
def home(): return FileResponse(ROOT/'static/index.html')

class FirstAccount(BaseModel):
 setup_key:str|None=None
 username:str=Field(min_length=3,max_length=40,pattern=r'^[a-zA-Z0-9_.-]+$')
 display_name:str=Field(min_length=2,max_length=100)
 password:str=Field(min_length=12,max_length=256)

@app.get('/api/setup/status')
def setup_status():
 with tx() as c:
  return {'needs_setup':c.execute('SELECT 1 FROM users LIMIT 1').fetchone() is None,'requires_setup_key':bool(os.environ.get('POLICEM_SETUP_KEY'))}

@app.post('/api/setup')
def setup_account(data:FirstAccount):
 # Public deployments require a one-time secret to prevent account takeover.
 expected=os.environ.get('POLICEM_SETUP_KEY','')
 if expected and not hmac.compare_digest(data.setup_key or '',expected):
  raise HTTPException(403,'Kurulum anahtarı hatalı')
 with tx() as c:
  if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
   raise HTTPException(409,'İlk hesap zaten oluşturulmuş')
  branch=c.execute('SELECT id FROM branches ORDER BY id LIMIT 1').fetchone()
  if not branch:raise HTTPException(500,'Kurulum verisi eksik')
  cur=c.execute('INSERT INTO users(username,display_name,role,password_hash,branch_id) VALUES (?,?,?,?,?)',
    (data.username.strip(),data.display_name.strip(),'partner',password_hash(data.password),branch['id']))
  audit(c,cur.lastrowid,'initial_setup','user',cur.lastrowid)
 return {'ok':True,'message':'İlk ortak hesabı oluşturuldu. Giriş yapabilirsiniz.'}

class Login(BaseModel): username:str=Field(min_length=1,max_length=128);password:str=Field(min_length=1,max_length=256)
class PasswordChange(BaseModel):old:str;new:str=Field(min_length=12)
class DeviceRegister(BaseModel):label:str=Field(min_length=1,max_length=80);password:str
class DeviceRevoke(BaseModel):password:str
class WebAuthnRegisterOptions(BaseModel):label:str=Field(min_length=1,max_length=80);password:str=Field(min_length=1,max_length=256);installation_id:str=Field(min_length=20,max_length=64)
class WebAuthnRegisterVerify(BaseModel):ceremony_id:str=Field(min_length=20,max_length=64);installation_id:str=Field(min_length=20,max_length=64);credential:dict
class WebAuthnLoginOptions(BaseModel):installation_id:str=Field(min_length=20,max_length=64)
class WebAuthnLoginVerify(BaseModel):ceremony_id:str=Field(min_length=20,max_length=64);installation_id:str=Field(min_length=20,max_length=64);credential:dict
class PinEnrollOptions(BaseModel):label:str=Field(min_length=1,max_length=80);password:str=Field(min_length=1,max_length=256);installation_id:str=Field(min_length=20,max_length=64)
class PinEnrollVerify(BaseModel):ceremony_id:str=Field(min_length=20,max_length=64);device_id:str=Field(min_length=20,max_length=64);installation_id:str=Field(min_length=20,max_length=64);public_key:dict;pin:str=Field(min_length=4,max_length=4);pin_confirm:str=Field(min_length=4,max_length=4);signature:str=Field(min_length=80,max_length=128)
class PinLoginOptions(BaseModel):installation_id:str=Field(min_length=20,max_length=64)
class PinLoginVerify(BaseModel):ceremony_id:str=Field(min_length=20,max_length=64);device_id:str=Field(min_length=20,max_length=64);installation_id:str=Field(min_length=20,max_length=64);pin:str=Field(min_length=4,max_length=4);signature:str=Field(min_length=80,max_length=128)
def current(request:Request):
 auth=request.headers.get('Authorization','')
 if not auth.startswith('Bearer '): raise HTTPException(401,'Oturum açın')
 token=hashlib.sha256(auth[7:].encode()).hexdigest();now=int(time.time())
 with tx() as c:
  row=c.execute('''SELECT s.last_activity,s.expires,s.user_id,u.* FROM sessions s
   JOIN users u ON u.id=s.user_id LEFT JOIN device_sessions ds ON ds.token_hash=s.token_hash
   LEFT JOIN trusted_devices d ON d.id=ds.device_id WHERE s.token_hash=? AND s.expires>?
   AND u.active=1 AND (ds.token_hash IS NULL OR (d.id IS NOT NULL AND d.revoked_at IS NULL AND d.user_id=s.user_id))''',(token,now)).fetchone()
  if not row:raise HTTPException(401,'Oturum geçersiz')
  last_activity=int(row['last_activity'] or 0)
  if last_activity and now-last_activity>=IDLE_SECONDS:raise HTTPException(401,detail={'code':'SESSION_IDLE'})
  if not last_activity:
   last_activity=now;c.execute('UPDATE sessions SET last_activity=? WHERE token_hash=?',(now,token))
  elif request.headers.get('X-User-Interaction')=='1':
   changed=c.execute('UPDATE sessions SET last_activity=? WHERE token_hash=? AND expires>? AND last_activity>?',(now,token,now,now-IDLE_SECONDS)).rowcount
   if not changed:raise HTTPException(401,detail={'code':'SESSION_IDLE'})
   last_activity=now
  user=dict(row);user['auth_last_activity']=last_activity
  if user.get('must_change_password') and request.url.path not in ('/api/me','/api/password','/api/logout'):
   raise HTTPException(403,detail={'code':'PASSWORD_CHANGE_REQUIRED'})
 return user

def webauthn_config():
 origin=os.getenv('POLICEM_PUBLIC_ORIGIN','')
 rp_id=os.getenv('WEBAUTHN_RP_ID','').lower().rstrip('.')
 try:
  parsed=urlsplit(origin);host=(parsed.hostname or '').lower().rstrip('.')
  if parsed.scheme=='https' and parsed.netloc and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment and parsed.path in ('','/'):
   canonical=f'https://{parsed.netloc}'
   origin_ok=(canonical==origin)
  elif os.getenv('POLICEM_DEV_MODE')=='1' and parsed.scheme=='http' and host in ('localhost','127.0.0.1') and parsed.port==8000 and parsed.path in ('','/') and not parsed.query and not parsed.fragment:
   canonical=f'http://{parsed.netloc}';origin_ok=(canonical==origin)
  else:origin_ok=False
 except ValueError:origin_ok=False;host=''
 if not origin_ok or not rp_id or not host or not (host==rp_id or host.endswith('.'+rp_id)):
  raise HTTPException(503,detail={'code':'METHOD_UNAVAILABLE'})
 return canonical, rp_id

def checked_credential(value):
 try:
  if len(json.dumps(value,separators=(',',':'))) > 65536:raise ValueError()
  if value.get('type')!='public-key' or not isinstance(value.get('response'),dict):raise ValueError()
  raw=base64url_to_bytes(value.get('rawId',''))
  if not raw or len(raw)>1024 or base64url_to_bytes(value.get('id',''))!=raw:raise ValueError()
  return raw
 except Exception:raise HTTPException(400,detail={'code':'INVALID_CEREMONY'})

def consume_webauthn_challenge(ceremony_id,purpose,user_id=None,session_hash=None,installation_id=None):
 now=int(time.time())
 with tx() as c:
  row=c.execute('''SELECT * FROM webauthn_challenges WHERE id=? AND purpose=? AND expires_at>? AND consumed_at IS NULL
    AND ((user_id IS NULL AND ? IS NULL) OR user_id=?) AND ((session_hash IS NULL AND ? IS NULL) OR session_hash=?)
    AND ((installation_id IS NULL AND ? IS NULL) OR installation_id=?)''',
    (ceremony_id,purpose,now,user_id,user_id,session_hash,session_hash,installation_id,installation_id)).fetchone()
  if not row:raise HTTPException(401 if purpose=='login' else 400,detail={'code':'INVALID_CEREMONY'})
  changed=c.execute('UPDATE webauthn_challenges SET consumed_at=? WHERE id=? AND consumed_at IS NULL AND expires_at>?',(now,ceremony_id,now)).rowcount
  if changed!=1:raise HTTPException(401,detail={'code':'INVALID_CEREMONY'})
  return dict(row)

def check_webauthn_rate(request:Request):
 now=int(time.time());ip=request.client.host if request.client else 'unknown'
 key=hashlib.sha256(('webauthn-ip:'+ip).encode()).hexdigest()
 with tx() as c:
  row=c.execute('SELECT attempts,window_started FROM auth_attempts WHERE scope_hash=?',(key,)).fetchone()
  if row and now-int(row['window_started'])<900 and int(row['attempts'])>=30:
   raise HTTPException(429,detail={'code':'RATE_LIMITED'})
  c.execute('''INSERT INTO auth_attempts(scope_hash,attempts,window_started,updated_at) VALUES (?,1,?,?)
   ON CONFLICT(scope_hash) DO UPDATE SET attempts=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN 1 ELSE auth_attempts.attempts+1 END,
   window_started=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN excluded.updated_at ELSE auth_attempts.window_started END,
   updated_at=excluded.updated_at''',(key,now,now))

def json_credential_json(data):
 try:return json.loads(json.dumps(data,ensure_ascii=False))
 except Exception:raise HTTPException(400,detail={'code':'INVALID_CEREMONY'})

@app.post('/api/security/webauthn/register/options')
def webauthn_register_options(data:WebAuthnRegisterOptions,request:Request,u=Depends(current)):
 origin,rp_id=webauthn_config()
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,detail={'code':'STEP_UP_REQUIRED'})
 label=data.label.strip()
 if not label:raise HTTPException(422,'Cihaz adı gerekli')
 now=int(time.time());session_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest()
 ceremony_id=secrets.token_urlsafe(24);challenge=secrets.token_bytes(32)
 with tx() as c:
  prior=c.execute('SELECT device_id,user_id FROM device_login_settings WHERE installation_id=?',(data.installation_id,)).fetchone()
  if prior and int(prior['user_id'])!=int(u['id']):raise HTTPException(409,detail={'code':'INSTALLATION_IN_USE'})
  count=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE user_id=? AND revoked_at IS NULL AND id<>COALESCE(?,\'\')',(u['id'],prior['device_id'] if prior else '')).fetchone()[0]
  if count>=10:raise HTTPException(409,detail={'code':'DEVICE_LIMIT'})
  row=c.execute('SELECT webauthn_user_handle FROM users WHERE id=? AND active=1',(u['id'],)).fetchone()
  if not row:raise HTTPException(401,detail={'code':'AUTH_REQUIRED'})
  excludes=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(x['credential_id'])) for x in c.execute('SELECT credential_id FROM webauthn_credentials WHERE user_id=? AND revoked_at IS NULL',(u['id'],))]
  options=generate_registration_options(rp_id=rp_id,rp_name='Poliçem',user_name=u['username'],user_display_name=u['display_name'],user_id=row['webauthn_user_handle'].encode(),challenge=challenge,timeout=300000,authenticator_selection=AuthenticatorSelectionCriteria(authenticator_attachment=AuthenticatorAttachment.PLATFORM,resident_key=ResidentKeyRequirement.REQUIRED,require_resident_key=True,user_verification=UserVerificationRequirement.REQUIRED),exclude_credentials=excludes)
  c.execute('INSERT INTO webauthn_challenges(id,purpose,user_id,session_hash,challenge,label,created_at,expires_at,installation_id) VALUES (?,?,?,?,?,?,?,?,?)',(ceremony_id,'register',u['id'],session_hash,challenge,label,now,now+300,data.installation_id))
 return {'ceremony_id':ceremony_id,'publicKey':json.loads(options_to_json(options))}

@app.post('/api/security/webauthn/register/verify')
def webauthn_register_verify(data:WebAuthnRegisterVerify,request:Request,u=Depends(current)):
 origin,rp_id=webauthn_config()
 session_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest()
 challenge=consume_webauthn_challenge(data.ceremony_id,'register',u['id'],session_hash,data.installation_id)
 raw_id=checked_credential(data.credential)
 try:
  verified=verify_registration_response(credential=json_credential_json(data.credential),expected_challenge=bytes(challenge['challenge']),expected_rp_id=rp_id,expected_origin=origin,require_user_verification=True)
  if not hmac.compare_digest(verified.credential_id,raw_id) or not verified.user_verified:raise ValueError('credential mismatch')
 except Exception:raise HTTPException(400,detail={'code':'INVALID_CEREMONY'})
 now=int(time.time());device_id=secrets.token_urlsafe(24);credential_id=bytes_to_base64url(verified.credential_id)
 with tx() as c:
  prior=c.execute('SELECT device_id,user_id FROM device_login_settings WHERE installation_id=?',(challenge['installation_id'],)).fetchone()
  if prior and int(prior['user_id'])!=int(u['id']):raise HTTPException(409,detail={'code':'INSTALLATION_IN_USE'})
  count=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE user_id=? AND revoked_at IS NULL AND id<>COALESCE(?,\'\')',(u['id'],prior['device_id'] if prior else '')).fetchone()[0]
  if count>=10:raise HTTPException(409,detail={'code':'DEVICE_LIMIT'})
  try:
   c.execute('INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen,installation_id) VALUES (?,?,?,?,?,?)',(device_id,u['id'],challenge['label'],now,now,challenge['installation_id']))
   c.execute('INSERT INTO webauthn_credentials(credential_id,user_id,device_id,public_key,sign_count,device_type,backed_up,created_at) VALUES (?,?,?,?,?,?,?,?)',(credential_id,u['id'],device_id,verified.credential_public_key,verified.sign_count,verified.credential_device_type.value,int(verified.credential_backed_up),now))
   switch_installation_device(c,challenge['installation_id'],u['id'],device_id,'webauthn',session_hash,now)
  except sqlite3.IntegrityError:raise HTTPException(409,detail={'code':'CREDENTIAL_EXISTS'})
  audit(c,u['id'],'webauthn_register','trusted_device',None,{'device_id':device_id})
 return {'ok':True,'device':{'id':device_id,'label':challenge['label'],'method':'webauthn'}}

@app.post('/api/security/webauthn/login/options')
def webauthn_login_options(data:WebAuthnLoginOptions,request:Request):
 origin,rp_id=webauthn_config();now=int(time.time());ceremony_id=secrets.token_urlsafe(24);challenge=secrets.token_bytes(32)
 check_webauthn_rate(request)
 with tx() as c:
  selected=c.execute('''SELECT s.user_id,s.device_id,w.credential_id FROM device_login_settings s
   JOIN trusted_devices d ON d.id=s.device_id JOIN webauthn_credentials w ON w.device_id=d.id
   JOIN users u ON u.id=s.user_id WHERE s.installation_id=? AND s.method='webauthn' AND u.active=1
   AND d.revoked_at IS NULL AND d.installation_id=s.installation_id AND w.revoked_at IS NULL''',(data.installation_id,)).fetchone()
  if not selected:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
  allow=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(selected['credential_id']))]
  options=generate_authentication_options(rp_id=rp_id,challenge=challenge,timeout=300000,allow_credentials=allow,user_verification=UserVerificationRequirement.REQUIRED)
  c.execute("INSERT INTO webauthn_challenges(id,purpose,challenge,created_at,expires_at,installation_id) VALUES (?,'login',?,?,?,?)",(ceremony_id,challenge,now,now+300,data.installation_id))
 return {'ceremony_id':ceremony_id,'publicKey':json.loads(options_to_json(options))}

@app.post('/api/security/webauthn/login/verify')
def webauthn_login_verify(data:WebAuthnLoginVerify,request:Request):
 origin,rp_id=webauthn_config()
 challenge=consume_webauthn_challenge(data.ceremony_id,'login',session_hash=None,installation_id=data.installation_id)
 raw_id=checked_credential(data.credential)
 credential_id=bytes_to_base64url(raw_id)
 with tx() as c:
   row=c.execute('''SELECT wc.*,u.username,u.active,u.display_name,u.role,u.branch_id,u.theme,u.email,u.email_verified_at,u.must_change_password,u.phone,u.start_date,u.job_title,u.webauthn_user_handle,d.label
    FROM webauthn_credentials wc JOIN users u ON u.id=wc.user_id JOIN trusted_devices d ON d.id=wc.device_id
   JOIN device_login_settings s ON s.device_id=d.id AND s.method='webauthn'
   WHERE wc.credential_id=? AND wc.revoked_at IS NULL AND d.revoked_at IS NULL AND d.user_id=wc.user_id
    AND s.installation_id=? AND d.installation_id=s.installation_id''',(credential_id,data.installation_id)).fetchone()
 if not row or not row['active']:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
 try:
  response=data.credential['response'];handle=response.get('userHandle')
  if not handle or not hmac.compare_digest(base64url_to_bytes(handle),row['webauthn_user_handle'].encode()):raise ValueError('user handle mismatch')
  verified=verify_authentication_response(credential=json_credential_json(data.credential),expected_challenge=bytes(challenge['challenge']),expected_rp_id=rp_id,expected_origin=origin,credential_public_key=bytes(row['public_key']),credential_current_sign_count=int(row['sign_count']),require_user_verification=True)
  if not verified.user_verified or not hmac.compare_digest(verified.credential_id,raw_id):raise ValueError('credential mismatch')
 except Exception:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
 now=int(time.time());token=secrets.token_urlsafe(40);token_hash=hashlib.sha256(token.encode()).hexdigest()
 with tx() as c:
  changed=c.execute('UPDATE webauthn_credentials SET sign_count=?,device_type=?,backed_up=?,last_used_at=? WHERE credential_id=? AND revoked_at IS NULL AND sign_count=?',(verified.new_sign_count,verified.credential_device_type.value,int(verified.credential_backed_up),now,credential_id,row['sign_count'])).rowcount
  active=c.execute("SELECT 1 FROM users u JOIN trusted_devices d ON d.user_id=u.id JOIN device_login_settings s ON s.device_id=d.id AND s.method='webauthn' WHERE u.id=? AND u.active=1 AND d.id=? AND d.revoked_at IS NULL AND s.installation_id=?",(row['user_id'],row['device_id'],data.installation_id)).fetchone()
  if changed!=1 or not active:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
  c.execute('INSERT INTO sessions(token_hash,user_id,expires,last_activity) VALUES (?,?,?,?)',(token_hash,row['user_id'],now+86400,now))
  c.execute('INSERT INTO device_sessions(token_hash,device_id) VALUES (?,?)',(token_hash,row['device_id']))
  c.execute('UPDATE trusted_devices SET last_seen=? WHERE id=?',(now,row['device_id']))
  audit(c,row['user_id'],'webauthn_login','trusted_device',None,{'device_id':row['device_id']})
 user={'id':row['user_id'],'username':row['username'],'display_name':row['display_name'],'role':row['role'],'branch_id':row['branch_id'],'theme':row['theme'],'email':row['email'],'email_verified_at':row['email_verified_at'],'must_change_password':row['must_change_password'],'phone':row['phone'],'start_date':row['start_date'],'job_title':row['job_title'],'active':row['active']}
 user['must_change_password']=bool(user['must_change_password'])
 return {'token':token,'user':user,'idle_expires_at':now+IDLE_SECONDS}

def pin_signing_message(purpose,ceremony_id,device_id,challenge):
 return b'policem-pin-v1\0'+purpose.encode('ascii')+b'\0'+ceremony_id.encode('ascii')+b'\0'+device_id.encode('ascii')+b'\0'+bytes(challenge)

def verify_pin_signature(public_key,signature,message):
 try:
  if len(json.dumps(public_key,separators=(',',':'))) > 2048:raise ValueError()
  if public_key.get('kty')!='EC' or public_key.get('crv')!='P-256' or set(public_key)!={'kty','crv','x','y','ext','key_ops'}:raise ValueError()
  x=int.from_bytes(base64url_to_bytes(public_key['x']),'big');y=int.from_bytes(base64url_to_bytes(public_key['y']),'big')
  if len(base64url_to_bytes(public_key['x']))!=32 or len(base64url_to_bytes(public_key['y']))!=32:raise ValueError()
  key=ec.EllipticCurvePublicNumbers(x,y,ec.SECP256R1()).public_key()
  sig=base64url_to_bytes(signature)
  if len(sig)!=64:raise ValueError()
  key.verify(encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big')),message,ec.ECDSA(hashes.SHA256()))
  return key
 except Exception:return None

def consume_pin_challenge(c,ceremony_id,purpose,device_id,user_id=None,session_hash=None,installation_id=None):
 now=int(time.time())
 row=c.execute('''SELECT * FROM pin_challenges WHERE id=? AND purpose=? AND device_id=? AND expires_at>? AND consumed_at IS NULL
   AND ((user_id IS NULL AND ? IS NULL) OR user_id=?) AND ((session_hash IS NULL AND ? IS NULL) OR session_hash=?)
   AND ((installation_id IS NULL AND ? IS NULL) OR installation_id=?)''',
   (ceremony_id,purpose,device_id,now,user_id,user_id,session_hash,session_hash,installation_id,installation_id)).fetchone()
 if not row:return None
 changed=c.execute('UPDATE pin_challenges SET consumed_at=? WHERE id=? AND consumed_at IS NULL AND expires_at>?',(now,ceremony_id,now)).rowcount
 return dict(row) if changed==1 else None

def switch_installation_device(c,installation_id,user_id,new_device_id,method,current_token_hash,now):
 old=c.execute('SELECT * FROM device_login_settings WHERE installation_id=?',(installation_id,)).fetchone()
 bound=c.execute('SELECT ds.device_id,d.installation_id FROM device_sessions ds JOIN trusted_devices d ON d.id=ds.device_id WHERE ds.token_hash=?',(current_token_hash,)).fetchone()
 if old and int(old['user_id'])!=int(user_id):raise HTTPException(409,detail={'code':'INSTALLATION_IN_USE'})
 if bound and (not old or bound['device_id']!=old['device_id']):raise HTTPException(409,detail={'code':'INSTALLATION_MISMATCH'})
 if old:
  old_id=old['device_id']
  c.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM device_sessions WHERE device_id=? AND token_hash<>?)',(old_id,current_token_hash))
  c.execute('DELETE FROM device_sessions WHERE device_id=? AND token_hash<>?',(old_id,current_token_hash))
  c.execute('DELETE FROM refresh_sessions WHERE device_id=?',(old_id,))
  c.execute('DELETE FROM device_pin WHERE device_id=?',(old_id,))
  c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL',(now,old_id))
  c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL',(now,old_id))
  c.execute('UPDATE trusted_devices SET revoked_at=? WHERE id=? AND user_id=?',(now,old_id,user_id))
  c.execute('DELETE FROM device_login_settings WHERE installation_id=?',(installation_id,))
 c.execute('INSERT OR REPLACE INTO device_sessions(token_hash,device_id) VALUES (?,?)',(current_token_hash,new_device_id))
 c.execute('INSERT INTO device_login_settings(installation_id,user_id,device_id,method,updated_at) VALUES (?,?,?,?,?)',(installation_id,user_id,new_device_id,method,now))

@app.get('/api/security/login-method')
def get_login_method(installation_id:str=Query(min_length=20,max_length=64)):
 with tx() as c:
  row=c.execute('''SELECT s.method,d.id FROM device_login_settings s JOIN trusted_devices d ON d.id=s.device_id
   WHERE s.installation_id=? AND d.revoked_at IS NULL AND d.installation_id=s.installation_id
   AND ((s.method='pin' AND EXISTS(SELECT 1 FROM pin_device_keys k JOIN device_pin p ON p.device_id=k.device_id WHERE k.device_id=d.id AND k.revoked_at IS NULL AND p.locked_at IS NULL))
    OR (s.method='webauthn' AND EXISTS(SELECT 1 FROM webauthn_credentials w WHERE w.device_id=d.id AND w.revoked_at IS NULL)))''',(installation_id,)).fetchone()
 return {'method':row['method'] if row else 'password'}

@app.post('/api/security/pin/enroll/options')
def pin_enroll_options(data:PinEnrollOptions,request:Request,u=Depends(current)):
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,detail={'code':'STEP_UP_REQUIRED'})
 label=data.label.strip()
 if not label:raise HTTPException(422,'Cihaz adı gerekli')
 now=int(time.time());device_id=secrets.token_urlsafe(24);ceremony_id=secrets.token_urlsafe(24);challenge=secrets.token_bytes(32)
 session_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest()
 with tx() as c:
  prior=c.execute('SELECT device_id,user_id FROM device_login_settings WHERE installation_id=?',(data.installation_id,)).fetchone()
  if prior and int(prior['user_id'])!=int(u['id']):raise HTTPException(409,detail={'code':'INSTALLATION_IN_USE'})
  count=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE user_id=? AND revoked_at IS NULL AND id<>COALESCE(?,\'\')',(u['id'],prior['device_id'] if prior else '')).fetchone()[0]
  if count>=10:raise HTTPException(409,detail={'code':'DEVICE_LIMIT'})
  c.execute("INSERT INTO pin_challenges(id,purpose,device_id,user_id,session_hash,challenge,label,created_at,expires_at,installation_id) VALUES (?,'enroll',?,?,?,?,?,?,?,?)",
   (ceremony_id,device_id,u['id'],session_hash,challenge,label,now,now+300,data.installation_id))
 return {'ceremony_id':ceremony_id,'device_id':device_id,'challenge':bytes_to_base64url(challenge),'expires_at':now+300}

@app.post('/api/security/pin/enroll/verify')
def pin_enroll_verify(data:PinEnrollVerify,request:Request,u=Depends(current)):
 session_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest();now=int(time.time())
 with tx() as c:challenge=consume_pin_challenge(c,data.ceremony_id,'enroll',data.device_id,u['id'],session_hash,data.installation_id)
 if not challenge:raise HTTPException(400,detail={'code':'INVALID_CEREMONY'})
 if not re.fullmatch(r'\d{4}',data.pin) or not hmac.compare_digest(data.pin,data.pin_confirm):raise HTTPException(422,detail={'code':'PIN_INVALID'})
 message=pin_signing_message('enroll',data.ceremony_id,data.device_id,challenge['challenge'])
 if not verify_pin_signature(data.public_key,data.signature,message):raise HTTPException(400,detail={'code':'INVALID_CEREMONY'})
 now=int(time.time())
 with tx() as c:
  prior=c.execute('SELECT device_id,user_id FROM device_login_settings WHERE installation_id=?',(data.installation_id,)).fetchone()
  if prior and int(prior['user_id'])!=int(u['id']):raise HTTPException(409,detail={'code':'INSTALLATION_IN_USE'})
  count=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE user_id=? AND revoked_at IS NULL AND id<>COALESCE(?,\'\')',(u['id'],prior['device_id'] if prior else '')).fetchone()[0]
  if count>=10:raise HTTPException(409,detail={'code':'DEVICE_LIMIT'})
  try:
   c.execute('INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen,installation_id) VALUES (?,?,?,?,?,?)',(data.device_id,u['id'],challenge['label'],now,now,data.installation_id))
   c.execute('INSERT INTO pin_device_keys(device_id,user_id,public_key,created_at) VALUES (?,?,?,?)',(data.device_id,u['id'],json.dumps(data.public_key,separators=(',',':')),now))
   c.execute('INSERT INTO device_pin(device_id,pin_hash,failures,locked_at) VALUES (?,?,0,NULL)',(data.device_id,pin_hash(data.pin)))
   switch_installation_device(c,data.installation_id,u['id'],data.device_id,'pin',session_hash,now)
  except sqlite3.IntegrityError:raise HTTPException(409,detail={'code':'DEVICE_EXISTS'})
  audit(c,u['id'],'pin_enroll','trusted_device',None,{'device_id':data.device_id})
 return {'ok':True,'device':{'id':data.device_id,'label':challenge['label'],'method':'pin'}}

@app.post('/api/security/pin/login/options')
def pin_login_options(data:PinLoginOptions,request:Request):
 check_webauthn_rate(request);now=int(time.time());ceremony_id=secrets.token_urlsafe(24);challenge=secrets.token_bytes(32)
 with tx() as c:
  selected=c.execute('''SELECT s.device_id FROM device_login_settings s JOIN trusted_devices d ON d.id=s.device_id
   JOIN pin_device_keys k ON k.device_id=d.id JOIN device_pin p ON p.device_id=d.id JOIN users u ON u.id=s.user_id
   WHERE s.installation_id=? AND s.method='pin' AND u.active=1 AND d.revoked_at IS NULL
   AND d.installation_id=s.installation_id AND k.revoked_at IS NULL AND p.locked_at IS NULL''',(data.installation_id,)).fetchone()
  if not selected:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
  c.execute("INSERT INTO pin_challenges(id,purpose,device_id,challenge,created_at,expires_at,installation_id) VALUES (?,'login',?,?,?,?,?)",
   (ceremony_id,selected['device_id'],challenge,now,now+300,data.installation_id))
 return {'ceremony_id':ceremony_id,'device_id':selected['device_id'],'challenge':bytes_to_base64url(challenge),'expires_at':now+300}

@app.post('/api/security/pin/login/verify')
def pin_login_verify(data:PinLoginVerify):
 now=int(time.time())
 with tx() as c:
  challenge=consume_pin_challenge(c,data.ceremony_id,'login',data.device_id,installation_id=data.installation_id)
  if not challenge:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
  row=c.execute('''SELECT k.user_id,k.public_key,d.label,d.revoked_at,p.pin_hash,p.failures,p.locked_at,u.username,u.active,u.display_name,u.role,u.branch_id,u.theme,u.email,u.email_verified_at,u.must_change_password,u.phone,u.start_date,u.job_title
   FROM pin_device_keys k JOIN trusted_devices d ON d.id=k.device_id JOIN device_pin p ON p.device_id=k.device_id
   JOIN users u ON u.id=k.user_id WHERE k.device_id=? AND k.user_id=d.user_id AND p.device_id=d.id''',(data.device_id,)).fetchone()
 if not row or row['revoked_at'] is not None or not row['active'] or row['locked_at'] is not None:
  raise HTTPException(401,detail={'code':'AUTH_FAILED'})
 message=pin_signing_message('login',data.ceremony_id,data.device_id,challenge['challenge'])
 try:key_json=json.loads(row['public_key'])
 except Exception:key_json={}
 if not verify_pin_signature(key_json,data.signature,message):raise HTTPException(401,detail={'code':'AUTH_FAILED'})
 if not re.fullmatch(r'\d{4}',data.pin) or not check_pin_hash(data.pin,row['pin_hash']):
  with tx() as c:
   current_row=c.execute('SELECT failures,locked_at FROM device_pin WHERE device_id=?',(data.device_id,)).fetchone()
   if current_row and current_row['locked_at'] is None:
    failures=int(current_row['failures'])+1;locked=now if failures>=5 else None
    c.execute('UPDATE device_pin SET failures=?,locked_at=? WHERE device_id=?',(failures,locked,data.device_id))
    audit(c,row['user_id'],'pin_failure','trusted_device',None,{'device_id':data.device_id,'failures':failures})
  raise HTTPException(401,detail={'code':'AUTH_FAILED'})
 token=secrets.token_urlsafe(40);token_hash=hashlib.sha256(token.encode()).hexdigest()
 with tx() as c:
  active=c.execute("SELECT 1 FROM users u JOIN trusted_devices d ON d.user_id=u.id JOIN pin_device_keys k ON k.device_id=d.id JOIN device_pin p ON p.device_id=d.id JOIN device_login_settings s ON s.device_id=d.id AND s.method='pin' WHERE u.id=? AND u.active=1 AND d.id=? AND d.revoked_at IS NULL AND k.revoked_at IS NULL AND p.locked_at IS NULL AND s.installation_id=?",(row['user_id'],data.device_id,data.installation_id)).fetchone()
  if not active:raise HTTPException(401,detail={'code':'AUTH_FAILED'})
  c.execute('UPDATE device_pin SET failures=0 WHERE device_id=?',(data.device_id,))
  c.execute('INSERT INTO sessions(token_hash,user_id,expires,last_activity) VALUES (?,?,?,?)',(token_hash,row['user_id'],now+86400,now))
  c.execute('INSERT INTO device_sessions(token_hash,device_id) VALUES (?,?)',(token_hash,data.device_id))
  c.execute('UPDATE trusted_devices SET last_seen=? WHERE id=?',(now,data.device_id))
  audit(c,row['user_id'],'pin_login','trusted_device',None,{'device_id':data.device_id})
 user={k:row[k] for k in ('username','display_name','role','branch_id','theme','email','email_verified_at','must_change_password','phone','start_date','job_title','active')};user['id']=row['user_id']
 user['must_change_password']=bool(user['must_change_password'])
 return {'token':token,'user':user,'idle_expires_at':now+IDLE_SECONDS}
class RefreshEnroll(BaseModel):device_id:str;password:str
class PinEnroll(BaseModel):device_id:str;password:str;pin:str
class PinRefresh(BaseModel):pin:str
class AdminPasswordReset(BaseModel):password:str=Field(min_length=12)
class EmailVerificationRequest(BaseModel):email:str=Field(min_length=3,max_length=254);password:str=Field(min_length=1,max_length=256)
class PasswordResetRequest(BaseModel):email:str=Field(min_length=3,max_length=254)
class PasswordResetComplete(BaseModel):token:str=Field(min_length=32,max_length=128);password:str=Field(min_length=12,max_length=256)
class OneTimeToken(BaseModel):token:str=Field(min_length=32,max_length=128)
class NewAgency(BaseModel):name:str
class NewBranch(BaseModel):name:str;agency_id:int
class NewUser(BaseModel):username:str;display_name:str;password:str=Field(min_length=12);role:str;branch_id:int|None=None;email:str|None=None;phone:str|None=None;start_date:date|None=None;job_title:str|None=None
class UserEdit(BaseModel):display_name:str=Field(min_length=2);phone:str;start_date:date;job_title:str;active:bool
class PolicyInput(BaseModel):agency_id:int;branch_id:int|None=None;owner_user_id:int|None=None;customer_name:str;policy_type:str;policy_number:str;insurer:str='';premium:float=Field(ge=0);start_date:date;end_date:date;issued_date:date;tracking:bool=True;external:bool=False;seller_user_id:int|None=None
class RenewalUpdate(BaseModel):status:str;new_policy:PolicyInput|None=None
class Transfer(BaseModel):from_user_id:int;to_user_id:int;policy_ids:list[int]|None=None
class Theme(BaseModel):theme:str
class BrandingUpdate(BaseModel):app_name:str=Field(min_length=1,max_length=48);color:str

IDLE_SECONDS=900

def trusted_origin(request:Request):
 origin=request.headers.get('origin','')
 expected=os.getenv('POLICEM_PUBLIC_ORIGIN','').rstrip('/')
 if expected and hmac.compare_digest(origin,expected):return True
 return os.getenv('POLICEM_DEV_MODE')=='1' and origin in ('http://localhost:8000','http://127.0.0.1:8000')

def require(*roles):
 def f(u=Depends(current)):
  if u['role'] not in roles:raise HTTPException(403,'Yetkisiz işlem')
  return u
 return f

@app.post('/api/login')
def login(data:Login,request:Request):
 now=int(time.time())
 username_key=hashlib.sha256(('login-user:'+data.username.strip().casefold()).encode()).hexdigest()
 ip=(request.client.host if request.client else 'unknown')
 ip_key=hashlib.sha256(('login-ip:'+ip).encode()).hexdigest()
 with tx() as c:
  blocked=False
  for key,limit in ((username_key,5),(ip_key,30)):
   bucket=c.execute('SELECT attempts,window_started FROM auth_attempts WHERE scope_hash=?',(key,)).fetchone()
   if bucket and now-int(bucket['window_started'])<900 and int(bucket['attempts'])>=limit:blocked=True
  if blocked:
   c.commit()
   raise HTTPException(429,detail={'code':'RATE_LIMITED'})
  u=c.execute('SELECT * FROM users WHERE username=? AND active=1',(data.username,)).fetchone()
  password_ok=check_pw(data.password,u['password_hash'] if u else DUMMY_PASSWORD_HASH)
  if not u or not password_ok:
   for key in (username_key,ip_key):
    c.execute('''INSERT INTO auth_attempts(scope_hash,attempts,window_started,updated_at)
     VALUES (?,1,?,?) ON CONFLICT(scope_hash) DO UPDATE SET
     attempts=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN 1 ELSE auth_attempts.attempts+1 END,
     window_started=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN excluded.updated_at ELSE auth_attempts.window_started END,
     updated_at=excluded.updated_at''',(key,now,now))
   c.commit()
   raise HTTPException(401,'Kullanıcı adı veya şifre hatalı')
  c.execute('DELETE FROM auth_attempts WHERE scope_hash=?',(username_key,))
  token=secrets.token_urlsafe(40)
  c.execute('INSERT INTO sessions(token_hash,user_id,expires,last_activity) VALUES (?,?,?,?)',
   (hashlib.sha256(token.encode()).hexdigest(),u['id'],now+86400,now))
 return {'token':token,'user':public_user(dict(u)),'idle_expires_at':now+IDLE_SECONDS}

def public_user(u):
 out={k:u.get(k) for k in ['id','username','display_name','role','branch_id','theme','email','email_verified_at','active','phone','start_date','job_title','must_change_password']}
 out['must_change_password']=bool(out['must_change_password'])
 return out
@app.get('/api/me')
def me(u=Depends(current)):return public_user(u)|{'idle_expires_at':u['auth_last_activity']+IDLE_SECONDS}
@app.post('/api/logout')
def logout(request:Request,response:Response,u=Depends(current)):
 token_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest()
 with tx() as c:
  device=c.execute('SELECT device_id FROM device_sessions WHERE token_hash=?',(token_hash,)).fetchone()
  if device:
   c.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM device_sessions WHERE device_id=?)',(device['device_id'],))
   c.execute('DELETE FROM device_sessions WHERE device_id=?',(device['device_id'],))
   c.execute('DELETE FROM refresh_sessions WHERE device_id=?',(device['device_id'],))
  else:c.execute('DELETE FROM sessions WHERE token_hash=?',(token_hash,))
  audit(c,u['id'],'logout','session',u['id'])
 response.delete_cookie('policem_refresh',path='/api/security/refresh',secure=True,samesite='strict',httponly=True)
 return {'ok':True}
@app.post('/api/password')
def change_password(data:PasswordChange,u=Depends(current)):
 if not check_pw(data.old,u['password_hash']):raise HTTPException(400,'Mevcut şifre yanlış')
 with tx() as c:
  c.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',(password_hash(data.new),u['id']))
  c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
  c.execute('DELETE FROM refresh_sessions WHERE user_id=?',(u['id'],))
  c.execute('DELETE FROM device_pin WHERE device_id IN (SELECT id FROM trusted_devices WHERE user_id=?)',(u['id'],))
  c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),u['id']))
  c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),u['id']))
  c.execute('DELETE FROM device_login_settings WHERE user_id=?',(u['id'],))
  c.execute('UPDATE trusted_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),u['id']))
  audit(c,u['id'],'password_change','user',u['id'])
 return {'ok':True,'message':'Şifre değiştirildi; yeniden giriş yapın'}

def valid_email(value):
 return bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value or '')) and len(value)<=254

def mail_security_config():
 origin=os.getenv('POLICEM_PUBLIC_ORIGIN','')
 try:
  parsed=urlsplit(origin)
  if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port not in (None,443) or origin!=f'https://{parsed.netloc}':return None
  port=int(os.getenv('SMTP_PORT','587'))
  if not 1<=port<=65535:return None
 except (ValueError,TypeError):return None
 names=('SMTP_HOST','SMTP_FROM','SMTP_USER','SMTP_PASSWORD')
 if not all(os.getenv(name) for name in names):return None
 return origin,os.environ['SMTP_HOST'],port,os.environ['SMTP_FROM'],os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']

def send_security_email(recipient,subject,token,purpose):
 cfg=mail_security_config()
 if not cfg:raise HTTPException(503,detail={'code':'EMAIL_UNAVAILABLE'})
 origin,host,port,sender,username,password=cfg
 fragment='verify-email=' if purpose=='verify_email' else 'reset-password='
 url=origin+'/#'+fragment+token
 body=('Verify your Poliçem email address using this one-time link (valid for 24 hours):\n' if purpose=='verify_email'
       else 'Reset your Poliçem password using this one-time link (valid for 30 minutes):\n')+url+'\n\nIf you did not request this, ignore this message.'
 message=EmailMessage();message['Subject']=subject;message['From']=sender;message['To']=recipient;message.set_content(body)
 try:
  with smtplib.SMTP(host,port,timeout=15) as smtp:
   smtp.ehlo();smtp.starttls(context=ssl.create_default_context());smtp.ehlo();smtp.login(username,password);smtp.send_message(message)
 except Exception:
  raise HTTPException(503,detail={'code':'EMAIL_UNAVAILABLE'})

def check_mail_rate(request):
 now=int(time.time());ip=request.client.host if request.client else 'unknown';key=hashlib.sha256(('account-mail-ip:'+ip).encode()).hexdigest()
 with tx() as c:
  row=c.execute('SELECT attempts,window_started FROM auth_attempts WHERE scope_hash=?',(key,)).fetchone()
  if row and now-int(row['window_started'])<900 and int(row['attempts'])>=10:raise HTTPException(429,detail={'code':'RATE_LIMITED'})
  c.execute('''INSERT INTO auth_attempts(scope_hash,attempts,window_started,updated_at) VALUES (?,1,?,?)
   ON CONFLICT(scope_hash) DO UPDATE SET attempts=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN 1 ELSE auth_attempts.attempts+1 END,
   window_started=CASE WHEN excluded.updated_at-auth_attempts.window_started>=900 THEN excluded.updated_at ELSE auth_attempts.window_started END,updated_at=excluded.updated_at''',(key,now,now))

def create_account_token(c,user_id,purpose,email,now,ttl):
 c.execute('UPDATE account_tokens SET consumed_at=? WHERE user_id=? AND purpose=? AND consumed_at IS NULL',(now,user_id,purpose))
 raw=secrets.token_urlsafe(32);digest=hashlib.sha256(raw.encode()).hexdigest()
 c.execute('INSERT INTO account_tokens(token_hash,purpose,user_id,email,created_at,expires_at) VALUES (?,?,?,?,?,?)',(digest,purpose,user_id,email,now,now+ttl))
 return raw

@app.get('/api/account/email/status')
def email_status(u=Depends(current)):
 return {'email':u.get('email'),'verified':bool(u.get('email_verified_at')),'email_available':bool(mail_security_config())}

@app.post('/api/account/email/verification/request')
def request_email_verification(data:EmailVerificationRequest,request:Request,u=Depends(current)):
 if not valid_email(data.email):raise HTTPException(422,detail={'code':'INVALID_EMAIL'})
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,detail={'code':'STEP_UP_REQUIRED'})
 cfg=mail_security_config()
 if not cfg:raise HTTPException(503,detail={'code':'EMAIL_UNAVAILABLE'})
 check_mail_rate(request)
 email=data.email.strip().casefold();now=int(time.time())
 with tx() as c:
  if c.execute('SELECT 1 FROM users WHERE email=? AND email_verified_at IS NOT NULL AND id<>?',(email,u['id'])).fetchone():raise HTTPException(409,detail={'code':'EMAIL_IN_USE'})
  raw=create_account_token(c,u['id'],'verify_email',email,now,86400)
  c.execute('UPDATE users SET pending_email=? WHERE id=?',(email,u['id']))
 try:send_security_email(email,'Verify your Poliçem email',raw,'verify_email')
 except HTTPException:
  with tx() as c:c.execute('UPDATE account_tokens SET consumed_at=? WHERE token_hash=?',(int(time.time()),hashlib.sha256(raw.encode()).hexdigest()))
  raise
 return {'ok':True,'message':'Doğrulama bağlantısı e-posta adresine gönderildi.'}

@app.post('/api/account/email/verification/complete')
def complete_email_verification(data:OneTimeToken):
 raw=data.token;digest=hashlib.sha256(raw.encode()).hexdigest();now=int(time.time())
 with tx() as c:
  row=c.execute("SELECT t.*,u.pending_email FROM account_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_hash=? AND t.purpose='verify_email' AND t.consumed_at IS NULL AND t.expires_at>?",(digest,now)).fetchone()
  if not row or not row['pending_email'] or not hmac.compare_digest(row['pending_email'],row['email']):raise HTTPException(400,detail={'code':'INVALID_OR_EXPIRED_TOKEN'})
  changed=c.execute('UPDATE account_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL',(now,digest)).rowcount
  if changed!=1:raise HTTPException(400,detail={'code':'INVALID_OR_EXPIRED_TOKEN'})
  duplicate=c.execute('SELECT 1 FROM users WHERE email=? AND email_verified_at IS NOT NULL AND id<>?',(row['email'],row['user_id'])).fetchone()
  if duplicate:raise HTTPException(409,detail={'code':'EMAIL_IN_USE'})
  c.execute('UPDATE users SET email=?,email_verified_at=?,pending_email=NULL WHERE id=?',(row['email'],now,row['user_id']))
  audit(c,row['user_id'],'email_verified','user',row['user_id'])
 return {'ok':True}

@app.post('/api/account/password-reset/request')
def request_password_reset(data:PasswordResetRequest,request:Request):
 if not valid_email(data.email):raise HTTPException(422,detail={'code':'INVALID_EMAIL'})
 if not mail_security_config():raise HTTPException(503,detail={'code':'EMAIL_UNAVAILABLE'})
 check_mail_rate(request);email=data.email.strip().casefold();now=int(time.time());raw=None
 with tx() as c:
  row=c.execute('SELECT id FROM users WHERE email=? AND email_verified_at IS NOT NULL AND active=1',(email,)).fetchone()
  if row:raw=create_account_token(c,row['id'],'password_reset',email,now,1800)
 if raw:
  try:send_security_email(email,'Reset your Poliçem password',raw,'password_reset')
  except HTTPException:
   with tx() as c:c.execute('UPDATE account_tokens SET consumed_at=? WHERE token_hash=?',(int(time.time()),hashlib.sha256(raw.encode()).hexdigest()))
   # Keep status and body indistinguishable from unknown or unverified addresses.
 return {'ok':True,'message':'Eğer bu adres doğrulanmış bir hesaba aitse sıfırlama bağlantısı gönderildi.'}

@app.post('/api/account/password-reset/complete')
def complete_password_reset(data:PasswordResetComplete):
 digest=hashlib.sha256(data.token.encode()).hexdigest();now=int(time.time())
 with tx() as c:
  row=c.execute("SELECT user_id FROM account_tokens WHERE token_hash=? AND purpose='password_reset' AND consumed_at IS NULL AND expires_at>?",(digest,now)).fetchone()
  if not row:raise HTTPException(400,detail={'code':'INVALID_OR_EXPIRED_TOKEN'})
  if c.execute('UPDATE account_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL',(now,digest)).rowcount!=1:raise HTTPException(400,detail={'code':'INVALID_OR_EXPIRED_TOKEN'})
  user_id=row['user_id'];c.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?',(password_hash(data.password),user_id))
  c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,));c.execute('DELETE FROM refresh_sessions WHERE user_id=?',(user_id,))
  c.execute('DELETE FROM device_pin WHERE device_id IN (SELECT id FROM trusted_devices WHERE user_id=?)',(user_id,))
  c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(now,user_id))
  c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(now,user_id))
  c.execute('UPDATE trusted_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(now,user_id))
  c.execute('DELETE FROM device_login_settings WHERE user_id=?',(user_id,))
  audit(c,user_id,'email_password_reset','user',user_id)
 return {'ok':True}
# Device inventory is NOT an authentication factor yet. No device bearer credentials are issued.
@app.get('/api/security/devices')
def list_trusted_devices(u=Depends(current)):
 with tx() as c:
  rows=c.execute("SELECT d.id,d.label,d.created_at,d.last_seen,CASE WHEN EXISTS(SELECT 1 FROM webauthn_credentials w WHERE w.device_id=d.id AND w.revoked_at IS NULL) THEN 'webauthn' WHEN EXISTS(SELECT 1 FROM pin_device_keys p WHERE p.device_id=d.id AND p.revoked_at IS NULL) THEN 'pin' ELSE 'unverified' END AS method,EXISTS(SELECT 1 FROM device_login_settings s WHERE s.device_id=d.id AND s.user_id=d.user_id) AS selected FROM trusted_devices d WHERE d.user_id=? AND d.revoked_at IS NULL ORDER BY d.created_at DESC",(u['id'],)).fetchall()
 return {'devices':[dict(row) for row in rows]}

@app.post('/api/security/devices')
def register_trusted_device(data:DeviceRegister,u=Depends(current)):
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,'Şifre doğrulanamadı')
 label=data.label.strip()
 if not label:raise HTTPException(400,'Cihaz adı gerekli')
 device_id=secrets.token_urlsafe(24)
 now=int(time.time())
 with tx() as c:
  count=c.execute('SELECT COUNT(*) FROM trusted_devices WHERE user_id=? AND revoked_at IS NULL',(u['id'],)).fetchone()[0]
  if count>=10:raise HTTPException(409,'En fazla 10 güvenilir cihaz kaydedilebilir')
  c.execute('INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen) VALUES (?,?,?,?,?)',(device_id,u['id'],label,now,now))
  audit(c,u['id'],'register','trusted_device',0,{'device_id':device_id})
 return {'id':device_id,'label':label,'created_at':now,'note':'Cihaz kaydı yapıldı; hızlı giriş henüz etkin değil'}

@app.post('/api/security/pin/enroll')
def enroll_pin(data:PinEnroll,u=Depends(current)):
 raise HTTPException(503,detail={'code':'METHOD_UNAVAILABLE'})

@app.post('/api/security/refresh/enroll')
def enroll_refresh(data:RefreshEnroll,request:Request,response:Response,u=Depends(current)):
 raise HTTPException(503,detail={'code':'METHOD_UNAVAILABLE'})

@app.post('/api/security/refresh/logout')
def logout_refresh(request:Request,response:Response):
 if not trusted_origin(request):raise HTTPException(403,detail={'code':'ORIGIN_DENIED'})
 raw=request.cookies.get('policem_refresh','')
 if raw:
  with tx() as c:c.execute('DELETE FROM refresh_sessions WHERE token_hash=?',(hashlib.sha256(raw.encode()).hexdigest(),))
 response.delete_cookie('policem_refresh',path='/api/security/refresh',secure=True,samesite='strict',httponly=True)
 return {'ok':True}

@app.post('/api/security/refresh')
def refresh_session(data:PinRefresh,request:Request,response:Response):
 raise HTTPException(503,detail={'code':'METHOD_UNAVAILABLE'})

@app.post('/api/security/devices/{device_id}/bind')
def bind_device_session(device_id:str,data:DeviceRevoke,request:Request,u=Depends(current)):
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,'Şifre doğrulanamadı')
 token_hash=hashlib.sha256(request.headers['Authorization'][7:].encode()).hexdigest()
 with tx() as c:
  device=c.execute('SELECT id FROM trusted_devices WHERE id=? AND user_id=? AND revoked_at IS NULL',(device_id,u['id'])).fetchone()
  if not device:raise HTTPException(404,'Cihaz bulunamadı')
  c.execute('INSERT INTO device_sessions(token_hash,device_id) VALUES (?,?) ON CONFLICT(token_hash) DO UPDATE SET device_id=excluded.device_id',(token_hash,device_id))
  c.execute('UPDATE trusted_devices SET last_seen=? WHERE id=?',(int(time.time()),device_id))
  audit(c,u['id'],'bind','trusted_device',0,{'device_id':device_id})
 return {'ok':True}

@app.post('/api/security/devices/{device_id}/revoke')
def revoke_trusted_device(device_id:str,data:DeviceRevoke,u=Depends(current)):
 if not check_pw(data.password,u['password_hash']):raise HTTPException(403,'Şifre doğrulanamadı')
 with tx() as c:
  row=c.execute('SELECT id FROM trusted_devices WHERE id=? AND user_id=? AND revoked_at IS NULL',(device_id,u['id'])).fetchone()
  if not row:raise HTTPException(404,'Cihaz bulunamadı')
  c.execute('UPDATE trusted_devices SET revoked_at=? WHERE id=? AND user_id=?',(int(time.time()),device_id,u['id']))
  c.execute('DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM device_sessions WHERE device_id=?)',(device_id,))
  c.execute('DELETE FROM device_sessions WHERE device_id=?',(device_id,))
  c.execute('DELETE FROM refresh_sessions WHERE device_id=?',(device_id,))
  c.execute('DELETE FROM device_pin WHERE device_id=?',(device_id,))
  c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL',(int(time.time()),device_id))
  c.execute('DELETE FROM device_login_settings WHERE device_id=?',(device_id,))
  c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE device_id=? AND revoked_at IS NULL',(int(time.time()),device_id))
  audit(c,u['id'],'revoke','trusted_device',0,{'device_id':device_id})
 return {'ok':True,'note':'Cihaz ve bağlı oturumları iptal edildi; bağlanmamış eski oturumlar etkilenmez'}

@app.post('/api/theme')
def theme(data:Theme,u=Depends(current)):
 if not re.fullmatch(r'#[0-9a-fA-F]{6}',data.theme):raise HTTPException(400,'Renk geçersiz')
 with tx() as c:c.execute('UPDATE users SET theme=? WHERE id=?',(data.theme,u['id']))
 return {'ok':True}
@app.get('/api/branding')
def get_branding():
 with tx() as c:
  b=c.execute('SELECT app_name,color,icon_mime FROM branding WHERE id=1').fetchone()
 return {'app_name':b['app_name'],'color':b['color'],'has_icon':bool(b['icon_mime']),'icon_url':'/api/branding/icon'}

@app.put('/api/branding')
def set_branding(data:BrandingUpdate,u=Depends(require('partner','manager'))):
 name=data.app_name.strip()
 if not name or any(ord(c)<32 for c in name):raise HTTPException(400,'Uygulama adı geçersiz')
 if not re.fullmatch(r'#[0-9a-fA-F]{6}',data.color):raise HTTPException(400,'Renk geçersiz')
 with tx() as c:
  c.execute('UPDATE branding SET app_name=?,color=? WHERE id=1',(name,data.color))
  audit(c,u['id'],'update','branding',1,{'app_name':name,'color':data.color})
 return {'ok':True}

@app.post('/api/branding/icon')
async def upload_brand_icon(file:UploadFile=File(...),u=Depends(require('partner','manager'))):
 blob=await file.read(2*1024*1024+1)
 if len(blob)>2*1024*1024:raise HTTPException(413,'Simge en fazla 2 MB olabilir')
 mime=None
 if blob.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
 elif blob.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
 elif blob[:4]==b'RIFF' and blob[8:12]==b'WEBP':mime='image/webp'
 if not mime:raise HTTPException(400,'PNG, JPEG veya WebP dosyası yükleyin')
 # Decode and normalize the actual image, rejecting corrupt or oversized pixel payloads.
 try:
  from PIL import Image,ImageOps
  import io
  Image.MAX_IMAGE_PIXELS=16_000_000
  im=Image.open(io.BytesIO(blob));im.load()
  if im.width<64 or im.height<64:raise ValueError('Simge en az 64×64 piksel olmalı')
  im=ImageOps.fit(im.convert('RGBA'),(512,512),method=Image.Resampling.LANCZOS)
  out=io.BytesIO();im.save(out,format='PNG');blob=out.getvalue()
 except Exception:raise HTTPException(400,'Görsel okunamadı; geçerli bir PNG/JPEG/WebP yükleyin')
 with tx() as c:
  c.execute('UPDATE branding SET icon_mime=?,icon_bytes=? WHERE id=1',('image/png',blob))
  audit(c,u['id'],'update_icon','branding',1)
 return {'ok':True}

@app.delete('/api/branding/icon')
def delete_brand_icon(u=Depends(require('partner','manager'))):
 with tx() as c:
  c.execute('UPDATE branding SET icon_mime=NULL,icon_bytes=NULL WHERE id=1')
  audit(c,u['id'],'remove_icon','branding',1)
 return {'ok':True}

@app.get('/api/branding/icon')
def brand_icon():
 with tx() as c:b=c.execute('SELECT icon_bytes FROM branding WHERE id=1').fetchone()
 if not b or not b['icon_bytes']:raise HTTPException(404,'Simge bulunamadı')
 return Response(content=b['icon_bytes'],media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

@app.get('/manifest.webmanifest')
def manifest():
 with tx() as c:b=c.execute('SELECT app_name,color,icon_mime FROM branding WHERE id=1').fetchone()
 result={'name':b['app_name'],'short_name':b['app_name'][:12],'start_url':'/','scope':'/','display':'standalone','background_color':'#f2f5fa','theme_color':b['color']}
 if b['icon_mime']:result['icons']=[{'src':'/api/branding/icon','sizes':'512x512','type':'image/png','purpose':'any maskable'}]
 return JSONResponse(result,headers={'Cache-Control':'no-store'})

@app.get('/api/organization')
def organization(u=Depends(current)):
 with tx() as c:
  return {k:[dict(x) for x in c.execute(f'SELECT * FROM {k} WHERE active=1')] for k in ('agencies','branches')} | {'users':[public_user(dict(x)) for x in c.execute('SELECT * FROM users WHERE active=1')]}
@app.post('/api/agencies')
def add_agency(data:NewAgency,u=Depends(require('partner'))):
 with tx() as c:
  cur=c.execute('INSERT INTO agencies(name) VALUES (?)',(data.name.strip(),));audit(c,u['id'],'create','agency',cur.lastrowid)
 return {'id':cur.lastrowid}
@app.post('/api/branches')
def add_branch(data:NewBranch,u=Depends(require('partner','manager'))):
 with tx() as c:
  cur=c.execute('INSERT INTO branches(agency_id,name) VALUES (?,?)',(data.agency_id,data.name.strip()));audit(c,u['id'],'create','branch',cur.lastrowid)
 return {'id':cur.lastrowid}
JOB_ROLES={'agency_authority':'partner','agency_manager':'manager','technical':'staff','assistant_technical':'staff'}
def check_job_permission(actor,title):
 if title not in JOB_ROLES:raise HTTPException(400,'Unvan geçersiz')
 if actor['role']=='manager' and title not in ('technical','assistant_technical'):raise HTTPException(403,'Bu unvanı yönetme yetkiniz yok')

@app.get('/api/users/manage')
def manage_users(u=Depends(require('partner','manager'))):
 with tx() as c:
  return [public_user(dict(x)) for x in c.execute('SELECT * FROM users ORDER BY active DESC,display_name')]

@app.post('/api/users')
def add_user(data:NewUser,u=Depends(require('partner','manager'))):
 if data.email and not valid_email(data.email):raise HTTPException(422,detail={'code':'INVALID_EMAIL'})
 title=data.job_title or {'partner':'agency_authority','manager':'agency_manager','staff':'technical'}.get(data.role)
 check_job_permission(u,title)
 if JOB_ROLES[title]!=data.role:raise HTTPException(400,'Rol ve unvan uyuşmuyor')
 if not data.phone or not data.phone.strip() or not data.start_date:raise HTTPException(400,'Telefon ve işe başlama tarihi zorunlu')
 try:
  with tx() as c:
   cur=c.execute('INSERT INTO users(username,display_name,role,password_hash,branch_id,email,phone,start_date,job_title) VALUES (?,?,?,?,?,?,?,?,?)',(data.username,data.display_name.strip(),data.role,password_hash(data.password),data.branch_id,data.email.strip().casefold() if data.email else None,data.phone.strip(),str(data.start_date),title))
   audit(c,u['id'],'create','user',cur.lastrowid,{'job_title':title})
  return {'id':cur.lastrowid}
 except sqlite3.IntegrityError:raise HTTPException(409,'Kullanıcı adı zaten kayıtlı')

@app.put('/api/users/{user_id}')
def edit_user(user_id:int,data:UserEdit,u=Depends(require('partner','manager'))):
 check_job_permission(u,data.job_title)
 if not data.phone.strip():raise HTTPException(400,'Telefon zorunlu')
 with tx() as c:
  old=c.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
  if not old:raise HTTPException(404,'Personel bulunamadı')
  if u['role']=='manager' and old['role']!='staff':raise HTTPException(403,'Üst unvanı değiştiremezsiniz')
  if user_id==u['id'] and not data.active:raise HTTPException(400,'Kendinizi pasife alamazsınız')
  if old['role']=='partner' and (JOB_ROLES[data.job_title]!='partner' or not data.active):
   count=c.execute("SELECT COUNT(*) FROM users WHERE role='partner' AND active=1").fetchone()[0]
   if old['active'] and count<=1:raise HTTPException(409,'Son aktif acente yetkilisi değiştirilemez')
  if not data.active and old['active']:
   count=c.execute('SELECT COUNT(*) FROM policies WHERE owner_user_id=?',(user_id,)).fetchone()[0]
   if count:raise HTTPException(409,f'Önce {count} poliçeyi başka personele devredin')
  c.execute('UPDATE users SET display_name=?,phone=?,start_date=?,job_title=?,role=?,active=? WHERE id=?',(data.display_name.strip(),data.phone.strip(),str(data.start_date),data.job_title,JOB_ROLES[data.job_title],int(data.active),user_id))
  if not data.active:
   c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
   c.execute('DELETE FROM refresh_sessions WHERE user_id=?',(user_id,))
   c.execute('DELETE FROM device_pin WHERE device_id IN (SELECT id FROM trusted_devices WHERE user_id=?)',(user_id,))
   c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
   c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
   c.execute('DELETE FROM device_login_settings WHERE user_id=?',(user_id,))
   c.execute('UPDATE trusted_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
  audit(c,u['id'],'update','user',user_id,{'from_title':old['job_title'],'to_title':data.job_title,'active':data.active})
 return {'ok':True}

@app.post('/api/users/{user_id}/reset-password')
def reset_staff_password(user_id:int,data:AdminPasswordReset,u=Depends(require('partner','manager'))):
 with tx() as c:
  target=c.execute('SELECT id,role,active,branch_id FROM users WHERE id=?',(user_id,)).fetchone()
  if not target or not target['active']:raise HTTPException(404,'Aktif kullanıcı bulunamadı')
  if user_id==u['id']:raise HTTPException(400,'Kendi şifrenizi Ayarlar bölümünden değiştirin')
  if u['role']=='manager' and target['role']!='staff':raise HTTPException(403,'Bu hesabın şifresini değiştirme yetkiniz yok')
  actor_agency=c.execute('SELECT agency_id FROM branches WHERE id=?',(u['branch_id'],)).fetchone() if u.get('branch_id') else None
  target_agency=c.execute('SELECT agency_id FROM branches WHERE id=?',(target['branch_id'],)).fetchone() if target['branch_id'] else None
  if not actor_agency or not target_agency or actor_agency['agency_id']!=target_agency['agency_id']:
   raise HTTPException(403,'Aynı acente sınırı doğrulanamadı')
  c.execute('UPDATE users SET password_hash=?,must_change_password=1 WHERE id=?',(password_hash(data.password),user_id))
  c.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
  c.execute('DELETE FROM refresh_sessions WHERE user_id=?',(user_id,))
  c.execute('DELETE FROM device_pin WHERE device_id IN (SELECT id FROM trusted_devices WHERE user_id=?)',(user_id,))
  c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
  c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
  c.execute('UPDATE trusted_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),user_id))
  c.execute('DELETE FROM device_login_settings WHERE user_id=?',(user_id,))
  audit(c,u['id'],'reset_password','user',user_id,{'temporary_password_change_required':True})
 return {'ok':True,'must_change_password':True}

@app.delete('/api/{kind}/{item_id}')
def deactivate(kind:str,item_id:int,u=Depends(require('partner','manager'))):
 if kind not in ('agencies','branches','users'):raise HTTPException(404)
 if kind=='agencies' and u['role']!='partner':raise HTTPException(403)
 if kind=='users' and item_id==u['id']:raise HTTPException(400,'Kendinizi kapatamazsınız')
 with tx() as c:
  if kind=='users' and u['role']=='manager':
   target=c.execute('SELECT role FROM users WHERE id=?',(item_id,)).fetchone()
   if not target or target['role']!='staff':raise HTTPException(403)
  if kind=='users':
   old=c.execute('SELECT role,active FROM users WHERE id=?',(item_id,)).fetchone()
   if not old:raise HTTPException(404,'Personel bulunamadı')
   if old['role']=='partner' and old['active'] and c.execute("SELECT COUNT(*) FROM users WHERE role='partner' AND active=1").fetchone()[0]<=1:raise HTTPException(409,'Son aktif acente yetkilisi kapatılamaz')
   if c.execute('SELECT COUNT(*) FROM policies WHERE owner_user_id=?',(item_id,)).fetchone()[0]:raise HTTPException(409,'Önce poliçeleri başka personele devredin')
   c.execute('DELETE FROM sessions WHERE user_id=?',(item_id,))
   c.execute('DELETE FROM refresh_sessions WHERE user_id=?',(item_id,))
   c.execute('DELETE FROM device_pin WHERE device_id IN (SELECT id FROM trusted_devices WHERE user_id=?)',(item_id,))
   c.execute('UPDATE webauthn_credentials SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),item_id))
   c.execute('UPDATE pin_device_keys SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),item_id))
   c.execute('DELETE FROM device_login_settings WHERE user_id=?',(item_id,))
   c.execute('UPDATE trusted_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(int(time.time()),item_id))
  c.execute(f'UPDATE {kind} SET active=0 WHERE id=?',(item_id,));audit(c,u['id'],'deactivate',kind,item_id)
 return {'ok':True}

def insert_policy(c,p:PolicyInput,uploader:int,renewed_from=None):
 if p.end_date<p.start_date:raise HTTPException(400,'Bitiş başlangıçtan önce')
 cur=c.execute('''INSERT INTO policies(agency_id,branch_id,owner_user_id,seller_user_id,uploader_user_id,customer_name,policy_type,policy_number,insurer,premium,start_date,end_date,issued_date,tracking,external,renewed_from) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(p.agency_id,p.branch_id,p.owner_user_id,p.seller_user_id or p.owner_user_id,uploader,p.customer_name,p.policy_type,p.policy_number,p.insurer,p.premium,str(p.start_date),str(p.end_date),str(p.issued_date),int(p.tracking),int(p.external),renewed_from))
 pid=cur.lastrowid
 if p.tracking:c.execute('INSERT INTO renewals(policy_id) VALUES (?)',(pid,))
 audit(c,uploader,'create','policy',pid,{'renewed_from':renewed_from})
 return pid
@app.post('/api/policies')
def create_policy(p:PolicyInput,u=Depends(current)):
 try:
  with tx() as c:pid=insert_policy(c,p,u['id'])
 except sqlite3.IntegrityError:raise HTTPException(409,'Aynı acente, şirket ve numarayla poliçe mevcut')
 return {'id':pid}

def period_bounds(period:str,anchor:str|None):
 try:d=date.fromisoformat(anchor) if anchor else date.today()
 except:raise HTTPException(400,'Tarih geçersiz')
 if period=='day':start=d;end=d+timedelta(days=1)
 elif period=='week':start=d-timedelta(days=d.weekday());end=start+timedelta(days=7)
 elif period=='month':start=d.replace(day=1);end=date(start.year+1,1,1) if start.month==12 else date(start.year,start.month+1,1)
 elif period=='year':start=d.replace(month=1,day=1);end=date(start.year+1,1,1)
 else:raise HTTPException(400,'Dönem geçersiz')
 return str(start),str(end)

def fetch_policies(c,kind,period,anchor,ptype=None,person=None):
 start,end=period_bounds(period,anchor);today=str(date.today())
 q='''SELECT p.*,r.status AS renewal_status,a.name AS agency_name,own.display_name AS owner_name,up.display_name AS uploader_name FROM policies p LEFT JOIN renewals r ON r.policy_id=p.id JOIN agencies a ON a.id=p.agency_id LEFT JOIN users own ON own.id=p.owner_user_id JOIN users up ON up.id=p.uploader_user_id WHERE 1=1''';params=[]
 if kind=='issued':q+=' AND p.issued_date>=? AND p.issued_date<? AND p.external=0';params += [start,end]
 elif kind=='active':q+=' AND p.start_date<=? AND p.end_date>=?';params += [today,today]
 elif kind=='upcoming':q+=" AND p.tracking=1 AND p.end_date>=? AND p.end_date<=? AND COALESCE(r.status,'bekliyor') NOT IN ('policelestirildi','kaybedildi')";params += [today,str(date.today()+timedelta(days=15))]
 elif kind=='offer':q+=" AND COALESCE(r.status,'')='teklif'" 
 elif kind=='worked':q+=" AND COALESCE(r.status,'') IN ('bekliyor','arandi','teklif')"
 elif kind!='all':raise HTTPException(400,'Liste türü geçersiz')
 if ptype:q+=' AND p.policy_type=?';params.append(ptype)
 if person:q+=' AND p.seller_user_id=?';params.append(person)
 q+=' ORDER BY p.end_date ASC,p.id DESC'
 return [dict(x) for x in c.execute(q,params)]
@app.get('/api/policies')
def list_policies(kind:str='all',period:str='month',anchor:str|None=None,policy_type:str|None=None,person_id:int|None=None,insurer:str|None=None,u=Depends(current)):
 if u['role']=='staff':
  if person_id is not None and person_id!=u['id']:raise HTTPException(403,'Başka personelin üretimine erişim yasak')
  if kind=='issued' or insurer is not None:person_id=u['id']
 if u['role']=='manager' and person_id is not None:raise HTTPException(403,'Personel üretim raporlarına erişim yok')
 with tx() as c:
  rows=fetch_policies(c,kind,period,anchor,policy_type,person_id)
  return [p for p in rows if (p['insurer'].strip() or 'Belirtilmemiş')==insurer] if insurer is not None else rows
@app.get('/api/summary')
def summary(period:str='month',anchor:str|None=None,policy_type:str|None=None,person_id:int|None=None,u=Depends(current)):
 # Operational counts remain available; financial totals and cross-employee
 # production reports are restricted to partners at the API boundary.
 if u['role']=='staff': person_id=u['id']
 if u['role']=='manager' and person_id is not None:
  raise HTTPException(403,'Personel üretim raporları yalnızca ortaklara açıktır')
 with tx() as c:
  issued=fetch_policies(c,'issued',period,anchor,policy_type,person_id)
  result={'total_count':len(issued)}
  if u['role']=='partner' or u['role']=='staff':
   result['total_premium']=round(sum(x['premium'] for x in issued),2)
  for k in ('active','upcoming','offer','issued','worked'):
   result[k]=len(fetch_policies(c,k,period,anchor,policy_type,person_id))
 return result

@app.get('/api/finance/summary')
def finance_summary(period:str='month',anchor:str|None=None,policy_type:str|None=None,person_id:int|None=None,u=Depends(require('partner'))):
 with tx() as c:
  issued=fetch_policies(c,'issued',period,anchor,policy_type,person_id)
  return {'total_premium':round(sum(x['premium'] for x in issued),2),
          'total_count':len(issued),'person_id':person_id}

@app.post('/api/renewals/{policy_id}')
def update_renewal(policy_id:int,data:RenewalUpdate,u=Depends(current)):
 valid=('bekliyor','arandi','teklif','policelestirildi','kaybedildi')
 if data.status not in valid:raise HTTPException(400,'Durum geçersiz')
 if data.status=='policelestirildi' and not data.new_policy:raise HTTPException(400,'Yeni poliçe bilgileri zorunlu')
 try:
  with tx() as c:
   old=c.execute('SELECT * FROM policies WHERE id=?',(policy_id,)).fetchone()
   if not old:raise HTTPException(404,'Poliçe bulunamadı')
   if not c.execute('SELECT 1 FROM renewals WHERE policy_id=?',(policy_id,)).fetchone():raise HTTPException(400,'Vade takibi açık değil')
   status=c.execute('SELECT status FROM renewals WHERE policy_id=?',(policy_id,)).fetchone()['status']
   if status in ('policelestirildi','kaybedildi'):raise HTTPException(409,'Yenileme kapanmış')
   new_id=None
   if data.status=='policelestirildi':
    if data.new_policy.customer_name.strip()!=old['customer_name'].strip():raise HTTPException(400,'Müşteri farklı; kontrol edin')
    new_id=insert_policy(c,data.new_policy,u['id'],policy_id)
   c.execute('UPDATE renewals SET status=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE policy_id=?',(data.status,u['id'],policy_id))
   audit(c,u['id'],'renewal_'+data.status,'policy',policy_id,{'new_id':new_id})
 except sqlite3.IntegrityError:raise HTTPException(409,'Yeni poliçe numarası zaten kayıtlı')
 return {'ok':True,'new_policy_id':new_id}
@app.get('/api/transfer/staff')
def transfer_staff(u=Depends(require('partner','manager'))):
 with tx() as c:
  return [{'id':r['id'],'display_name':r['display_name'],'active':bool(r['active']),'policy_count':r['policy_count']} for r in c.execute('''SELECT u.id,u.display_name,u.active,COUNT(p.id) policy_count FROM users u LEFT JOIN policies p ON p.owner_user_id=u.id GROUP BY u.id ORDER BY u.display_name''').fetchall()]
@app.post('/api/transfer')
def transfer(data:Transfer,u=Depends(require('partner','manager'))):
 with tx() as c:
  if data.from_user_id == data.to_user_id: raise HTTPException(400,'Kaynak ve hedef personel aynı olamaz')
  target=c.execute('SELECT id,active FROM users WHERE id=?',(data.to_user_id,)).fetchone()
  if not target or not target['active']: raise HTTPException(400,'Hedef personel aktif olmalı')
  source=c.execute('SELECT id FROM users WHERE id=?',(data.from_user_id,)).fetchone()
  if not source: raise HTTPException(404,'Kaynak personel bulunamadı')
  ids=data.policy_ids if data.policy_ids is not None else [x['id'] for x in c.execute('SELECT id FROM policies WHERE owner_user_id=?',(data.from_user_id,))]
  ids=[i for i in ids if c.execute('SELECT 1 FROM policies WHERE id=? AND owner_user_id=?',(i,data.from_user_id)).fetchone()]
  for pid in ids:c.execute('UPDATE policies SET owner_user_id=?,seller_user_id=CASE WHEN seller_user_id=? THEN ? ELSE seller_user_id END WHERE id=?',(data.to_user_id,data.from_user_id,data.to_user_id,pid))
  audit(c,u['id'],'transfer','policies',None,{'from':data.from_user_id,'to':data.to_user_id,'ids':ids})
 return {'count':len(ids)}
@app.get('/api/audit')
def audits(u=Depends(require('partner','manager'))):
 with tx() as c:return [dict(x) for x in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]

FIELDS={'customer_name':[r'(?:sigortal[ıi]|ad[ıi]\s*soyad[ıi]|ad\s*soyad)\s*[:\-]\s*([^\n]{4,100})'], 'policy_number':[r'(?:poliçe\s*(?:no|numaras[ıi])|policy\s*(?:no|number))\s*[:\-]\s*([A-Za-z0-9\-/]{3,60})'], 'premium':[r'(?:toplam\s*prim|brüt\s*prim|prim\s*tutar[ıi])\s*[:\-]?\s*([\d.,]+)'], 'start_date':[r'(?:(?:poliçe\s*)?başlang[ıi]ç\s*tarihi|vade\s*başlang[ıi]c[ıi])\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})'], 'end_date':[r'(?:(?:poliçe\s*)?bitiş\s*tarihi|vade\s*bitişi)\s*[:\-]?\s*(\d{2}[./-]\d{2}[./-]\d{4})']}
TYPES={'DASK':['dask','zorunlu deprem'],'Kasko':['kasko'],'Konut':['konut'],'TSS':['tamamlayıcı sağlık','tss'],'Trafik':['zorunlu trafik','trafik sigortası']}
def parse_pdf(blob):
 try:
  with fitz.open(stream=blob,filetype='pdf') as doc:
   if doc.page_count>100:raise ValueError('PDF 100 sayfadan uzun')
   txt='\n'.join(page.get_text() for page in doc)
 except Exception as e:raise HTTPException(422,f'PDF okunamadı: {str(e)[:100]}')
 out={};low=txt.lower()
 for key,patterns in FIELDS.items():
  for pattern in patterns:
   match=re.search(pattern,txt,re.IGNORECASE)
   if match:out[key]=match.group(1).strip();break
 for kind,words in TYPES.items():
  if any(w in low for w in words):out['policy_type']=kind;break
 for key in ('start_date','end_date'):
  if key in out:
   try:out[key]=str(datetime.strptime(out[key].replace('/','.').replace('-','.'),'%d.%m.%Y').date())
   except:out.pop(key,None)
 if 'premium' in out:
  raw=out['premium'].replace('.','').replace(',','.')
  try:out['premium']=float(raw)
  except:out.pop('premium',None)
 return out
@app.post('/api/pdf/extract')
async def extract(files:list[UploadFile]=File(...),u=Depends(current)):
 if len(files)>50:raise HTTPException(400,'En fazla 50 PDF')
 result=[]
 for file in files:
  blob=await file.read(12*1024*1024+1)
  if len(blob)>12*1024*1024 or not blob.startswith(b'%PDF'):result.append({'filename':file.filename,'error':'Geçersiz veya 12 MB üzeri PDF'});continue
  try:result.append({'filename':file.filename,'fields':parse_pdf(blob),'needs_review':True})
  except HTTPException as e:result.append({'filename':file.filename,'error':e.detail})
 return result
@app.post('/api/policies/with-document')
async def create_with_document(payload:str=Form(...),file:UploadFile=File(...),u=Depends(current)):
 try:p=PolicyInput.model_validate_json(payload)
 except Exception:raise HTTPException(422,'Poliçe alanları geçersiz')
 blob=await file.read(12*1024*1024+1)
 if len(blob)>12*1024*1024 or not blob.startswith(b'%PDF'):raise HTTPException(400,'Geçersiz veya büyük PDF')
 parse_pdf(blob)  # Invalid/unreadable PDFs must fail before a policy is created.
 filename=secrets.token_hex(24)+'.pdf';path=DATA/'documents'/filename
 try:
  with tx() as c:
   pid=insert_policy(c,p,u['id'])
   path.write_bytes(blob)
   c.execute('UPDATE policies SET document_path=? WHERE id=?',(filename,pid))
   audit(c,u['id'],'document','policy',pid)
 except sqlite3.IntegrityError:
  path.unlink(missing_ok=True)
  raise HTTPException(409,'Aynı poliçe zaten mevcut')
 except Exception:
  path.unlink(missing_ok=True)
  raise
 return {'id':pid,'owner_user_id':p.owner_user_id,'uploader_user_id':u['id']}

@app.get('/api/insurers/summary')
def insurers_summary(period:str='month',anchor:str|None=None,policy_type:str|None=None,person_id:int|None=None,u=Depends(current)):
 if u['role']=='manager' and person_id is not None:raise HTTPException(403,'Personel üretim raporlarına erişim yok')
 if u['role']=='staff':person_id=u['id']
 with tx() as c:
  issued=fetch_policies(c,'issued',period,anchor,policy_type,person_id)
  grouped={}
  for p in issued:
   name=p['insurer'].strip() or 'Belirtilmemiş'
   item=grouped.setdefault(name,{'insurer':name,'count':0})
   item['count']+=1
   if u['role']!='manager':item['premium']=round(item.get('premium',0)+p['premium'],2)
  return {'items':sorted(grouped.values(),key=lambda x:(-x['count'],x['insurer'])),'scope':'own' if u['role']=='staff' else 'all'}

@app.post('/api/policies/{policy_id}/document')
async def attach(policy_id:int,file:UploadFile=File(...),u=Depends(current)):
 blob=await file.read(12*1024*1024+1)
 if len(blob)>12*1024*1024 or not blob.startswith(b'%PDF'):raise HTTPException(400,'PDF geçersiz veya çok büyük')
 parse_pdf(blob)
 with tx() as c:
  if not c.execute('SELECT 1 FROM policies WHERE id=?',(policy_id,)).fetchone():raise HTTPException(404)
  filename=f'{policy_id}_{secrets.token_hex(8)}.pdf';path=DATA/'documents'/filename;path.write_bytes(blob)
  c.execute('UPDATE policies SET document_path=? WHERE id=?',(filename,policy_id));audit(c,u['id'],'document','policy',policy_id)
 return {'ok':True}
@app.get('/api/policies/{policy_id}/document')
def document(policy_id:int,u=Depends(current)):
 with tx() as c:p=c.execute('SELECT document_path FROM policies WHERE id=?',(policy_id,)).fetchone()
 if not p or not p['document_path']:raise HTTPException(404)
 return FileResponse(DATA/'documents'/p['document_path'],media_type='application/pdf',filename='police.pdf')

def reminder_tick(today=None):
 """Idempotent reminder enqueue/delivery. Call from cron once a day."""
 today=today or date.today();sent=[]
 with tx() as c:
  for p in c.execute("""SELECT p.id,p.end_date,p.owner_user_id,u.email,r.status FROM policies p JOIN renewals r ON r.policy_id=p.id LEFT JOIN users u ON u.id=p.owner_user_id WHERE p.tracking=1 AND r.status NOT IN ('policelestirildi','kaybedildi')""").fetchall():
   remaining=(date.fromisoformat(p['end_date'])-today).days
   if remaining not in (15,7,1):continue
   channel='email' if p['email'] and os.environ.get('SMTP_HOST') else 'queue'
   try:c.execute('INSERT INTO reminders(policy_id,days_before,channel) VALUES (?,?,?)',(p['id'],remaining,channel))
   except sqlite3.IntegrityError:continue
   sent.append({'policy_id':p['id'],'days':remaining,'email':p['email'],'channel':channel})
 # email is best effort; production should use retryable outbox
 for x in sent:
  if x['channel']=='email':
   try:
    msg=EmailMessage();msg['Subject']=f'Poliçem: {x["days"]} gün sonra vade';msg['From']=os.environ['SMTP_FROM'];msg['To']=x['email'];msg.set_content(f'{x["policy_id"]} numaralı kayıt {x["days"]} gün sonra sona eriyor. Poliçem üzerinden kontrol edin.')
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ.get('SMTP_PORT','587')),timeout=15) as smtp:
     smtp.starttls();smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);smtp.send_message(msg)
   except Exception as exc:print('E-posta gönderimi başarısız:',str(exc))
 return sent
@app.get('/api/reminders')
def reminders(u=Depends(current)):
 with tx() as c:return [dict(x) for x in c.execute('SELECT * FROM reminders ORDER BY id DESC LIMIT 100')]

# Additive customer experience; existing agency endpoints and database tables remain unchanged.
from customer_portal import register as register_customer_portal
register_customer_portal(app,conn,tx,password_hash,check_pw,DATA,ROOT)

# Optional Web Push API. Existing policy and login endpoints are unchanged.
from push_service import build_router
app.include_router(build_router(tx,current))
