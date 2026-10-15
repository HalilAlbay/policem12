import os,tempfile,importlib,sys
from pathlib import Path
from datetime import date,timedelta
from fastapi.testclient import TestClient

def test_login_policy_renewal_and_reporting():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   assert client.post('/api/login',json={'username':'admin','password':'wrong'}).status_code==401
   r=client.post('/api/login',json={'username':'admin','password':'test-password-very-long'})
   assert r.status_code==200,r.text
   h={'Authorization':'Bearer '+r.json()['token']}
   assert client.get('/api/summary',headers=h).json()['total_count']==0
   today=date.today();p={'agency_id':1,'owner_user_id':1,'customer_name':'Test Kişi','policy_type':'Kasko','policy_number':'ABC-1','premium':1200,'start_date':str(today-timedelta(days=350)),'end_date':str(today+timedelta(days=15)),'issued_date':str(today-timedelta(days=350)),'tracking':True}
   r=client.post('/api/policies',headers=h,json=p);assert r.status_code==200,r.text
   old=r.json()['id'];assert client.get('/api/summary',headers=h).json()['upcoming']==1
   assert client.post('/api/policies',headers=h,json=p).status_code==409
   assert len(m.reminder_tick(today))==1
   assert len(m.reminder_tick(today))==0
   p2={**p,'policy_number':'ABC-2','premium':1400,'start_date':str(today),'end_date':str(today+timedelta(days=365)),'issued_date':str(today)}
   r=client.post(f'/api/renewals/{old}',headers=h,json={'status':'policelestirildi','new_policy':p2});assert r.status_code==200,r.text
   assert client.get('/api/summary',headers=h).json()['total_premium']==1400
   assert client.get('/api/summary',headers=h).json()['upcoming']==0
   assert client.post(f'/api/renewals/{old}',headers=h,json={'status':'kaybedildi'}).status_code==409
   assert len(m.reminder_tick(today))==0
   assert client.get('/api/audit',headers=h).status_code==200

def test_staff_cannot_manage_users_or_see_other_staff_production():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   partner=client.post('/api/login',json={'username':'admin','password':'test-password-very-long'}).json()['token']
   hp={'Authorization':'Bearer '+partner}
   r=client.post('/api/users',headers=hp,json={'username':'worker','display_name':'Worker','password':'worker-password-long','role':'staff','branch_id':1});assert r.status_code==200
   worker=client.post('/api/login',json={'username':'worker','password':'worker-password-long'}).json()['token'];hs={'Authorization':'Bearer '+worker}
   assert client.post('/api/agencies',headers=hs,json={'name':'Other'}).status_code==403
   assert client.get('/api/audit',headers=hs).status_code==403
   assert client.get('/api/summary?person_id=1',headers=hs).status_code==200

def test_branding_permissions_persistence_and_icon():
 import io
 from PIL import Image
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   hp={'Authorization':'Bearer '+client.post('/api/login',json={'username':'admin','password':'test-password-very-long'}).json()['token']}
   assert client.get('/api/branding').json()['app_name']=='Poliçem'
   assert client.put('/api/branding',headers=hp,json={'app_name':'Acente Mobil','color':'#123ABC'}).status_code==200
   assert client.get('/api/branding').json()['app_name']=='Acente Mobil'
   assert client.get('/manifest.webmanifest').json()['theme_color']=='#123ABC'
   assert client.put('/api/branding',headers=hp,json={'app_name':'','color':'#123ABC'}).status_code==422
   assert client.put('/api/branding',headers=hp,json={'app_name':'X','color':'red'}).status_code==400
   im=Image.new('RGB',(128,128),'blue');b=io.BytesIO();im.save(b,'PNG')
   assert client.post('/api/branding/icon',headers=hp,files={'file':('icon.png',b.getvalue(),'image/png')}).status_code==200
   assert client.get('/api/branding/icon').headers['content-type']=='image/png'
   assert client.get('/manifest.webmanifest').json()['icons'][0]['sizes']=='512x512'
   assert client.post('/api/branding/icon',headers=hp,files={'file':('bad.png',b'not-image','image/png')}).status_code==400
   assert client.post('/api/users',headers=hp,json={'username':'staff2','display_name':'Staff','password':'staff-password-long','role':'staff','branch_id':1}).status_code==200
   hs={'Authorization':'Bearer '+client.post('/api/login',json={'username':'staff2','password':'staff-password-long'}).json()['token']}
   assert client.put('/api/branding',headers=hs,json={'app_name':'Unauthorized','color':'#000000'}).status_code==403
   assert client.delete('/api/branding/icon',headers=hs).status_code==403
   assert client.delete('/api/branding/icon',headers=hp).status_code==200
   assert client.get('/api/branding/icon').status_code==404
   assert client.get('/api/branding').json()['app_name']=='Acente Mobil'

def test_financial_reporting_is_partner_only():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   def auth(name,pw):
    return {'Authorization':'Bearer '+client.post('/api/login',json={'username':name,'password':pw}).json()['token']}
   hp=auth('admin','test-password-very-long')
   for role in ('manager','staff'):
    assert client.post('/api/users',headers=hp,json={'username':role,'display_name':role,'password':'strong-password-'+role,'role':role,'branch_id':1}).status_code==200
   hm=auth('manager','strong-password-manager')
   hs=auth('staff','strong-password-staff')
   assert client.get('/api/finance/summary',headers=hp).status_code==200
   assert client.get('/api/finance/summary',headers=hm).status_code==403
   assert client.get('/api/finance/summary',headers=hs).status_code==403
   assert 'total_premium' not in client.get('/api/summary',headers=hm).json()
   assert client.get('/api/summary?person_id=2',headers=hm).status_code==403
   assert 'total_premium' in client.get('/api/summary',headers=hs).json()
   assert client.get('/api/summary',headers=hp).status_code==200

def test_atomic_pdf_owner_uploader_and_insurer_summary():
 import json,fitz
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   def auth(n,p):return {'Authorization':'Bearer '+client.post('/api/login',json={'username':n,'password':p}).json()['token']}
   hp=auth('admin','test-password-very-long')
   for n in ('ali','ayse'):
    assert client.post('/api/users',headers=hp,json={'username':n,'display_name':n,'password':'strong-password-'+n,'role':'staff','branch_id':1}).status_code==200
   ha=auth('ali','strong-password-ali')
   pdf=fitz.open();page=pdf.new_page();page.insert_text((40,40),'Police No: TEST-1');blob=pdf.tobytes();pdf.close()
   today=str(date.today())
   for idx,owner in enumerate((2,3),1):
    payload={'agency_id':1,'owner_user_id':owner,'customer_name':'Test','policy_type':'Kasko','policy_number':f'NO-{idx}','insurer':'AXA','premium':100*idx,'start_date':today,'end_date':str(date.today()+timedelta(days=365)),'issued_date':today}
    r=client.post('/api/policies/with-document',headers=ha,data={'payload':json.dumps(payload)},files={'file':('test.pdf',blob,'application/pdf')})
    assert r.status_code==200,r.text
    assert r.json()['uploader_user_id']==2 and r.json()['owner_user_id']==owner
   rows=client.get('/api/policies',headers=hp).json()
   assert {r['owner_name'] for r in rows}=={'ali','ayse'}
   assert all(r['uploader_name']=='ali' and r['document_path'] for r in rows)
   assert client.get('/api/insurers/summary',headers=hp).json()['items'][0]['premium']==300
   own=client.get('/api/insurers/summary',headers=ha).json()['items']
   assert own[0]['count']==1
   bad=client.post('/api/policies/with-document',headers=ha,data={'payload':json.dumps({**payload,'policy_number':'BAD'})},files={'file':('bad.pdf',b'%PDF broken','application/pdf')})
   assert bad.status_code>=400
   assert len(client.get('/api/policies',headers=hp).json())==2

def test_insurer_drilldown_scoped_to_own_production():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ['POLICEM_ADMIN_PASSWORD']='test-password-very-long'
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   hp={'Authorization':'Bearer '+client.post('/api/login',json={'username':'admin','password':'test-password-very-long'}).json()['token']}
   assert client.post('/api/users',headers=hp,json={'username':'agent','display_name':'Agent','password':'worker-password-long','role':'staff','branch_id':1}).status_code==200
   hs={'Authorization':'Bearer '+client.post('/api/login',json={'username':'agent','password':'worker-password-long'}).json()['token']}
   today=str(date.today())
   base={'agency_id':1,'customer_name':'Müşteri','policy_type':'Kasko','insurer':'Marka A','premium':123,'start_date':today,'end_date':str(date.today()+timedelta(days=365)),'issued_date':today}
   assert client.post('/api/policies',headers=hp,json={**base,'policy_number':'PARTNER-1','owner_user_id':1}).status_code==200
   agent_id=client.get('/api/me',headers=hs).json()['id']
   assert client.post('/api/policies',headers=hp,json={**base,'policy_number':'AGENT-1','owner_user_id':agent_id}).status_code==200
   rows=client.get('/api/policies?kind=issued&insurer=Marka%20A',headers=hs).json()
   assert len(rows)==1 and rows[0]['policy_number']=='AGENT-1'
   assert client.get('/api/policies?kind=issued&insurer=Marka%20A&person_id=1',headers=hs).status_code==403
   assert len(client.get('/api/policies?kind=issued&insurer=Marka%20A',headers=hp).json())==2


def test_first_account_setup_only_once_and_login():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ.pop('POLICEM_ADMIN_PASSWORD',None)
  if 'app' in sys.modules:del sys.modules['app']
  m=importlib.import_module('app')
  with TestClient(m.app) as client:
   assert client.get('/api/setup/status').json()['needs_setup'] is True
   payload={'username':'sahip','display_name':'Acente Sahibi','password':'guclu-sifre-12345'}
   assert client.post('/api/setup',json={**payload,'password':'123'}).status_code==422
   r=client.post('/api/setup',json=payload);assert r.status_code==200,r.text
   assert client.get('/api/setup/status').json()['needs_setup'] is False
   assert client.post('/api/setup',json=payload).status_code==409
   r=client.post('/api/login',json={'username':'sahip','password':payload['password']})
   assert r.status_code==200 and r.json()['user']['role']=='partner'
