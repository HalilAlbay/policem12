"""Agency-scoped temporary password reset and verified-email recovery tests."""
import re
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def recovery_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv('POLICEM_DATA', tmp)
        monkeypatch.delenv('POLICEM_ADMIN_PASSWORD', raising=False)
        for name in ('SMTP_HOST','SMTP_PORT','SMTP_FROM','SMTP_USER','SMTP_PASSWORD','POLICEM_PUBLIC_ORIGIN'):
            monkeypatch.delenv(name, raising=False)
        sys.modules.pop('app', None)
        import app
        from fastapi.testclient import TestClient
        app.DATA=Path(tmp);app.DB=Path(tmp)/'recovery.sqlite3';app.init()
        with app.tx() as c:
            c.execute("INSERT INTO agencies(name) VALUES ('Other Agency')")
            c.execute("INSERT INTO branches(agency_id,name) VALUES (2,'Other Branch')")
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title,email) VALUES (?,?,?,?,1,?,?)",
                      ('owner','Agency Owner','partner',app.password_hash('OwnerPassword123'),'agency_authority','owner@example.test'))
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ('staff','Staff','staff',app.password_hash('StaffPassword123'),'technical'))
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,2,?)",
                      ('foreign','Foreign Staff','staff',app.password_hash('ForeignPassword123'),'technical'))
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ('manager','Manager','manager',app.password_hash('ManagerPassword123'),'agency_manager'))
        with TestClient(app.app) as http:
            yield app, http


def auth(http, username='owner', password='OwnerPassword123'):
    response=http.post('/api/login',json={'username':username,'password':password})
    assert response.status_code==200,response.text
    return {'Authorization':'Bearer '+response.json()['token']},response.json()


def test_officer_reset_is_same_agency_revokes_sessions_and_forces_password_change(recovery_client):
    app,http=recovery_client
    owner,_=auth(http)
    staff,old_login=auth(http,'staff','StaffPassword123')
    device_id='staff-device-test-1234567890'
    with app.tx() as c:
        now=1_800_000_000
        c.execute('INSERT INTO trusted_devices(id,user_id,label,created_at,last_seen,installation_id) VALUES (?,?,?,?,?,?)',
                  (device_id,2,'Staff phone',now,now,'staff-installation-test-123456'))
        c.execute('INSERT INTO pin_device_keys(device_id,user_id,public_key,created_at) VALUES (?,?,?,?)',
                  (device_id,2,'{}',now))
        c.execute('INSERT INTO device_pin(device_id,pin_hash,failures) VALUES (?,?,0)',(device_id,app.pin_hash('1234')))
        c.execute("INSERT INTO device_login_settings(installation_id,user_id,device_id,method,updated_at) VALUES (?,?,?,'pin',?)",
                  ('staff-installation-test-123456',2,device_id,now))
    reset=http.post('/api/users/2/reset-password',headers=owner,json={'password':'TemporaryStaff123'})
    assert reset.status_code==200,reset.text
    assert reset.json()['must_change_password'] is True
    with app.tx() as c:
        assert c.execute('SELECT revoked_at FROM trusted_devices WHERE id=?',(device_id,)).fetchone()[0] is not None
        assert c.execute('SELECT revoked_at FROM pin_device_keys WHERE device_id=?',(device_id,)).fetchone()[0] is not None
        assert c.execute('SELECT 1 FROM device_pin WHERE device_id=?',(device_id,)).fetchone() is None
        assert c.execute('SELECT 1 FROM device_login_settings WHERE installation_id=?',('staff-installation-test-123456',)).fetchone() is None
    assert http.get('/api/me',headers=staff).status_code==401
    assert http.post('/api/login',json={'username':'staff','password':'StaffPassword123'}).status_code==401
    fresh,fresh_login=auth(http,'staff','TemporaryStaff123')
    assert fresh_login['user']['must_change_password'] is True
    assert http.get('/api/me',headers=fresh).status_code==200
    blocked=http.get('/api/organization',headers=fresh)
    assert blocked.status_code==403 and blocked.json()['detail']['code']=='PASSWORD_CHANGE_REQUIRED'
    changed=http.post('/api/password',headers=fresh,json={'old':'TemporaryStaff123','new':'NewStaffPassword123'})
    assert changed.status_code==200,changed.text
    assert http.get('/api/me',headers=fresh).status_code==401
    _,new_login=auth(http,'staff','NewStaffPassword123')
    assert new_login['user']['must_change_password'] is False
    denied=http.post('/api/users/3/reset-password',headers=owner,json={'password':'TemporaryForeign123'})
    assert denied.status_code==403
    assert http.post('/api/login',json={'username':'foreign','password':'ForeignPassword123'}).status_code==200
    with app.tx() as c:
        audit=c.execute("SELECT actor,entity_id,payload FROM audit WHERE action='reset_password'").fetchone()
        assert audit['actor']==1 and audit['entity_id']==2
        assert 'TemporaryStaff123' not in (audit['payload'] or '')


def test_email_recovery_requires_verified_address_and_is_one_use(recovery_client,monkeypatch):
    app,http=recovery_client
    monkeypatch.setenv('POLICEM_PUBLIC_ORIGIN','https://login.example.test')
    monkeypatch.setenv('SMTP_HOST','smtp.example.test');monkeypatch.setenv('SMTP_PORT','587')
    monkeypatch.setenv('SMTP_FROM','noreply@example.test');monkeypatch.setenv('SMTP_USER','smtp-user');monkeypatch.setenv('SMTP_PASSWORD','smtp-secret')
    sent=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def ehlo(self):pass
        def starttls(self,**kwargs):pass
        def login(self,*args):pass
        def send_message(self,message):sent.append(message)
    monkeypatch.setattr(app.smtplib,'SMTP',FakeSMTP)
    headers,_=auth(http)
    assert http.post('/api/login',json={'username':'owner','password':'OwnerPassword123'}).status_code==200
    requested=http.post('/api/account/email/verification/request',headers=headers,json={
        'email':'Owner@Example.Test','password':'OwnerPassword123'})
    assert requested.status_code==200,requested.text
    verify_token=re.search(r'#verify-email=([A-Za-z0-9_-]+)',sent[-1].get_content()).group(1)
    assert http.post('/api/account/email/verification/complete',json={'token':verify_token}).status_code==200
    assert http.post('/api/account/email/verification/complete',json={'token':verify_token}).status_code==400
    assert http.get('/api/account/email/status',headers=headers).json()['verified'] is True

    reset=http.post('/api/account/password-reset/request',json={'email':'owner@example.test'})
    unknown=http.post('/api/account/password-reset/request',json={'email':'missing@example.test'})
    assert reset.status_code==unknown.status_code==200 and reset.json()==unknown.json()
    reset_token=re.search(r'#reset-password=([A-Za-z0-9_-]+)',sent[-1].get_content()).group(1)
    completed=http.post('/api/account/password-reset/complete',json={'token':reset_token,'password':'RecoveredPassword123'})
    assert completed.status_code==200,completed.text
    assert http.post('/api/account/password-reset/complete',json={'token':reset_token,'password':'AnotherPassword123'}).status_code==400
    assert http.get('/api/me',headers=headers).status_code==401
    assert http.post('/api/login',json={'username':'owner','password':'OwnerPassword123'}).status_code==401
    assert http.post('/api/login',json={'username':'owner','password':'RecoveredPassword123'}).status_code==200


def test_unconfigured_mail_fails_closed_without_blocking_password_login(recovery_client):
    _,http=recovery_client
    unavailable=http.post('/api/account/password-reset/request',json={'email':'owner@example.test'})
    assert unavailable.status_code==503
    headers,_=auth(http)
    status=http.get('/api/account/email/status',headers=headers)
    assert status.status_code==200 and status.json()['email_available'] is False
    assert http.post('/api/login',json={'username':'owner','password':'OwnerPassword123'}).status_code==200


def test_manager_can_reset_only_same_agency_staff(recovery_client):
    _,http=recovery_client
    manager,_=auth(http,'manager','ManagerPassword123')
    allowed=http.post('/api/users/2/reset-password',headers=manager,json={'password':'ManagerIssuedPass123'})
    denied=http.post('/api/users/1/reset-password',headers=manager,json={'password':'ManagerIssuedPass123'})
    assert allowed.status_code==200
    assert denied.status_code==403
