"""Quick login PIN and refresh regression checks (isolated SQLite)."""
from test_device_sessions import client, auth

def test_pin_refresh_and_lockout(client):
    owner=auth(client)
    d=client.post('/api/security/devices',headers=owner,json={'label':'iPhone','password':'Password12345'})
    assert d.status_code==200,d.text
    did=d.json()['id']
    assert client.post('/api/security/pin/enroll',headers=owner,json={'device_id':did,'password':'Password12345','pin':'1234'}).status_code==200
    r=client.post('/api/security/refresh/enroll',headers=owner,json={'device_id':did,'password':'Password12345'})
    assert r.status_code==200,r.text
    headers={'origin':'http://localhost:8000','host':'localhost:8000'}
    # Host and Origin must match the configured local test origin.
    good=client.post('/api/security/refresh',headers=headers,json={'pin':'1234'})
    assert good.status_code==200,good.text
    assert client.get('/api/me',headers={'Authorization':'Bearer '+good.json()['token']}).status_code==200
    for _ in range(5):
        bad=client.post('/api/security/refresh',headers=headers,json={'pin':'0000'})
        assert bad.status_code==403
    locked=client.post('/api/security/refresh',headers=headers,json={'pin':'1234'})
    assert locked.status_code==403

def test_revoke_disables_refresh(client):
    owner=auth(client)
    did=client.post('/api/security/devices',headers=owner,json={'label':'iPhone','password':'Password12345'}).json()['id']
    client.post('/api/security/pin/enroll',headers=owner,json={'device_id':did,'password':'Password12345','pin':'1234'})
    client.post('/api/security/refresh/enroll',headers=owner,json={'device_id':did,'password':'Password12345'})
    assert client.post(f'/api/security/devices/{did}/revoke',headers=owner,json={'password':'Password12345'}).status_code==200
    assert client.post('/api/security/refresh',headers={'origin':'http://localhost:8000','host':'localhost:8000'},json={'pin':'1234'}).status_code==401
