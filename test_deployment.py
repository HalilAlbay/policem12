import os, tempfile, importlib, sys
from pathlib import Path
from fastapi.testclient import TestClient

def test_first_account_requires_configured_setup_key():
 with tempfile.TemporaryDirectory() as d:
  os.environ['POLICEM_DATA']=d
  os.environ.pop('POLICEM_ADMIN_PASSWORD',None)
  os.environ['POLICEM_SETUP_KEY']='example-very-long-private-setup-key'
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
  sys.modules.pop('app',None)
  m=importlib.import_module('app')
  try:
   with TestClient(m.app) as client:
    assert client.get('/api/health').json()=={'ok':True}
    assert client.get('/api/setup/status').json()=={'needs_setup':True,'requires_setup_key':True}
    payload={'username':'owner','display_name':'Owner Test','password':'long-password-for-test'}
    assert client.post('/api/setup',json=payload).status_code==403
    assert client.post('/api/setup',json={**payload,'setup_key':'incorrect'}).status_code==403
    assert client.post('/api/setup',json={**payload,'setup_key':'example-very-long-private-setup-key'}).status_code==200
    assert client.post('/api/setup',json={**payload,'setup_key':'example-very-long-private-setup-key'}).status_code==409
    assert client.post('/api/login',json={'username':'owner','password':'long-password-for-test'}).status_code==200
  finally:
   os.environ.pop('POLICEM_SETUP_KEY',None)
