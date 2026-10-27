"""Legacy quick login remains unavailable until device proof is implemented."""
from test_device_sessions import client, auth

def test_legacy_pin_and_refresh_enrollment_fail_closed(client):
    owner=auth(client)
    d=client.post('/api/security/devices',headers=owner,json={'label':'iPhone','password':'Password12345'})
    assert d.status_code==200,d.text
    did=d.json()['id']
    pin=client.post('/api/security/pin/enroll',headers=owner,json={'device_id':did,'password':'Password12345','pin':'1234'})
    assert pin.status_code==503
    assert pin.json()['detail']['code']=='METHOD_UNAVAILABLE'
    r=client.post('/api/security/refresh/enroll',headers=owner,json={'device_id':did,'password':'Password12345'})
    assert r.status_code==503,r.text
    assert r.json()['detail']['code']=='METHOD_UNAVAILABLE'
    assert not client.cookies.get('policem_refresh')

def test_revoke_disables_refresh(client):
    owner=auth(client)
    did=client.post('/api/security/devices',headers=owner,json={'label':'iPhone','password':'Password12345'}).json()['id']
    assert client.post(f'/api/security/devices/{did}/revoke',headers=owner,json={'password':'Password12345'}).status_code==200
    assert client.post('/api/security/refresh',json={'pin':'1234'}).status_code==503
