"""Run with: python -m pytest -q tests/test_staff_permissions.py
Uses a temporary database, never the Render TEST or production database.
"""
import os
import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("POLICEM_DATA", tmp)
        monkeypatch.delenv("POLICEM_ADMIN_PASSWORD", raising=False)
        import app
        from fastapi.testclient import TestClient
        app.DATA = Path(tmp)
        app.DB = Path(tmp) / "test.sqlite3"
        app.init()
        with app.tx() as c:
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ("owner","Owner","partner",app.password_hash("Password12345"),"agency_authority"))
            c.execute("INSERT INTO users(username,display_name,role,password_hash,branch_id,job_title) VALUES (?,?,?,?,1,?)",
                      ("manager","Manager","manager",app.password_hash("Password12345"),"agency_manager"))
        with TestClient(app.app) as http:
            def token(name):
                response=http.post("/api/login",json={"username":name,"password":"Password12345"})
                assert response.status_code==200,response.text
                return {"Authorization":"Bearer "+response.json()["token"]}
            yield http,token("owner"),token("manager")

def payload(username,title):
    role={"agency_authority":"partner","agency_manager":"manager","technical":"staff","assistant_technical":"staff"}[title]
    return {"username":username,"display_name":username.title(),"password":"Password12345",
            "role":role,"job_title":title,"phone":"05320000000","start_date":"2026-10-27"}

def test_manager_cannot_create_upper_roles(client):
    http,owner,manager=client
    for title in ("agency_authority","agency_manager"):
        assert http.post("/api/users",headers=manager,json=payload("new_"+title,title)).status_code==403

def test_manager_can_create_and_promote_staff(client):
    http,owner,manager=client
    r=http.post("/api/users",headers=manager,json=payload("junior","assistant_technical"))
    assert r.status_code==200,r.text
    uid=r.json()["id"]
    update={"display_name":"Junior","phone":"05320000000","start_date":"2026-10-27",
            "job_title":"technical","active":True}
    assert http.put(f"/api/users/{uid}",headers=manager,json=update).status_code==200
    users=http.get("/api/users/manage",headers=manager).json()
    assert next(u for u in users if u["id"]==uid)["job_title"]=="technical"
    update["job_title"]="agency_manager"
    assert http.put(f"/api/users/{uid}",headers=manager,json=update).status_code==403

def test_last_authority_cannot_be_deactivated(client):
    http,owner,manager=client
    users=http.get("/api/users/manage",headers=owner).json()
    uid=next(u["id"] for u in users if u["role"]=="partner")
    assert http.delete(f"/api/users/{uid}",headers=manager).status_code==403
    assert http.delete(f"/api/users/{uid}",headers=owner).status_code==400
    update={"display_name":"Owner","phone":"05320000000","start_date":"2026-10-27",
            "job_title":"technical","active":True}
    assert http.put(f"/api/users/{uid}",headers=owner,json=update).status_code==409

def test_deactivate_and_reactivate(client):
    http,owner,manager=client
    r=http.post("/api/users",headers=manager,json=payload("newhire","assistant_technical"))
    assert r.status_code==200,r.text
    uid=r.json()["id"]
    update={"display_name":"New Hire","phone":"05320000000","start_date":"2026-10-27",
            "job_title":"assistant_technical","active":False}
    assert http.put(f"/api/users/{uid}",headers=manager,json=update).status_code==200
    assert next(u for u in http.get("/api/users/manage",headers=manager).json() if u["id"]==uid)["active"]==0
    update["active"]=True
    assert http.put(f"/api/users/{uid}",headers=manager,json=update).status_code==200

def test_staff_cannot_manage_users(client):
    http,owner,manager=client
    r=http.post("/api/users",headers=manager,json=payload("employee","technical"))
    assert r.status_code==200,r.text
    auth=http.post("/api/login",json={"username":"employee","password":"Password12345"}).json()
    staff={"Authorization":"Bearer "+auth["token"]}
    assert http.get("/api/users/manage",headers=staff).status_code==403
    assert http.post("/api/users",headers=staff,json=payload("unauthorized","technical")).status_code==403
