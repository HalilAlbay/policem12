"""Session idle, durable login throttling, and additive migration checks."""
import hashlib
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def auth_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv('POLICEM_DATA', tmp)
        monkeypatch.delenv('POLICEM_ADMIN_PASSWORD', raising=False)
        if 'app' in sys.modules:
            del sys.modules['app']
        import app
        app.DATA = Path(tmp)
        app.DB = Path(tmp) / 'auth.sqlite3'
        app.init()
        with app.tx() as c:
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ('owner','Owner','partner',app.password_hash('Password12345'),'agency_authority'))
        from fastapi.testclient import TestClient
        with TestClient(app.app) as http:
            yield app, http


def login(http):
    response = http.post('/api/login', json={'username':'owner','password':'Password12345'})
    assert response.status_code == 200, response.text
    return {'Authorization':'Bearer '+response.json()['token']}, response.json()


def test_idle_deadline_is_enforced_at_900_seconds(auth_client):
    app, http = auth_client
    headers, _ = login(http)
    token_hash = hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()
    with app.tx() as c:
        c.execute('UPDATE sessions SET last_activity=? WHERE token_hash=?', (int(time.time())-900, token_hash))
    response = http.get('/api/me', headers=headers)
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'SESSION_IDLE'


def test_background_protected_reads_do_not_extend_idle_but_interaction_does(auth_client):
    app, http = auth_client
    headers, _ = login(http)
    token_hash = hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()
    before = int(time.time()) - 60
    with app.tx() as c:
        c.execute('UPDATE sessions SET last_activity=? WHERE token_hash=?', (before, token_hash))
    response = http.get('/api/me', headers=headers)
    assert response.status_code == 200
    with app.tx() as c:
        assert c.execute('SELECT last_activity FROM sessions WHERE token_hash=?',(token_hash,)).fetchone()[0] == before
    response = http.get('/api/me', headers={**headers,'X-User-Interaction':'1'})
    assert response.status_code == 200
    assert response.json()['idle_expires_at'] >= int(time.time()) + 899


def test_login_failures_are_durable_and_throttled_before_correct_password(auth_client):
    app, http = auth_client
    for _ in range(5):
        assert http.post('/api/login',json={'username':'owner','password':'wrong'}).status_code == 401
    blocked = http.post('/api/login',json={'username':'owner','password':'Password12345'})
    assert blocked.status_code == 429
    assert blocked.json()['detail']['code'] == 'RATE_LIMITED'
    with app.tx() as c:
        assert c.execute('SELECT attempts FROM auth_attempts WHERE scope_hash=?',
                         (hashlib.sha256(b'login-user:owner').hexdigest(),)).fetchone()[0] == 5
        c.execute('UPDATE auth_attempts SET window_started=?,updated_at=? WHERE scope_hash=?',
                  (int(time.time())-901,int(time.time())-901,hashlib.sha256(b'login-user:owner').hexdigest()))
    assert http.post('/api/login',json={'username':'owner','password':'Password12345'}).status_code == 200


def test_unknown_and_wrong_password_have_same_generic_response(auth_client):
    _, http = auth_client
    wrong = http.post('/api/login',json={'username':'owner','password':'wrong'})
    unknown = http.post('/api/login',json={'username':'not-a-user','password':'wrong'})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {'detail':'Kullanıcı adı veya şifre hatalı'}


def test_logout_cookie_endpoint_uses_configured_origin_not_host(auth_client, monkeypatch):
    monkeypatch.setenv('POLICEM_PUBLIC_ORIGIN','https://agency.example')
    _, http = auth_client
    denied = http.post('/api/security/refresh/logout',headers={
        'origin':'https://evil.example','host':'agency.example'})
    assert denied.status_code == 403
    accepted = http.post('/api/security/refresh/logout',headers={
        'origin':'https://agency.example','host':'attacker.example'})
    assert accepted.status_code == 200


def test_logout_invalidates_server_session(auth_client):
    app, http = auth_client
    headers, _ = login(http)
    assert http.post('/api/logout',headers=headers).status_code == 200
    assert http.get('/api/me',headers=headers).status_code == 401
    with app.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM audit WHERE action='logout'").fetchone()[0] == 1


def test_legacy_schema_migrates_additively_and_second_startup_is_safe(auth_client):
    app, _ = auth_client
    with tempfile.TemporaryDirectory() as tmp:
        legacy_db = Path(tmp) / 'legacy.sqlite3'
        old_db = app.DB
        app.DB = legacy_db
        try:
            c = sqlite3.connect(legacy_db)
            c.executescript('''
              CREATE TABLE agencies(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER DEFAULT 1);
              CREATE TABLE branches(id INTEGER PRIMARY KEY,agency_id INTEGER NOT NULL REFERENCES agencies(id),name TEXT NOT NULL,active INTEGER DEFAULT 1);
              CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL,password_hash TEXT NOT NULL,branch_id INTEGER REFERENCES branches(id),active INTEGER DEFAULT 1,theme TEXT DEFAULT '#1755a2',email TEXT);
              CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
              INSERT INTO agencies(id,name) VALUES (1,'Agency');
              INSERT INTO branches(id,agency_id,name) VALUES (1,1,'Main');
            ''')
            legacy_hash=app.password_hash('LegacyPassword123')
            c.execute('INSERT INTO users(id,username,display_name,role,password_hash,branch_id) VALUES (1,?,?,?,?,1)',
                      ('legacy','Legacy','staff',legacy_hash))
            c.execute('INSERT INTO sessions(token_hash,user_id,expires) VALUES (?,?,?)',
                      (hashlib.sha256(b'legacy-token').hexdigest(),1,int(time.time())+3600))
            c.commit(); c.close()
            app.init()
            with app.tx() as db:
                cols={r['name'] for r in db.execute('PRAGMA table_info(sessions)')}
                assert 'last_activity' in cols
                assert db.execute('SELECT last_activity FROM sessions').fetchone()[0] > 0
                assert db.execute('SELECT password_hash FROM users WHERE id=1').fetchone()[0] == legacy_hash
            app.init()
            with app.tx() as db:
                assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
                assert db.execute('SELECT version FROM auth_schema_meta WHERE id=1').fetchone()[0] == 4
        finally:
            app.DB = old_db
