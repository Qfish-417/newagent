from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.db import connect
from app.auth import token_hash


def test_register_migrates_and_login_restores_data(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"data_dir",tmp_path)
    monkeypatch.setattr(settings,"openai_api_key","")
    with TestClient(app) as client:
        client.put('/api/subscription',json={"nickname":"Alice","custom_prompt":"关注开源Agent","enabled":True,"scheduled_time":"23:59"})
        guest_cookie = client.cookies.get('newagent_user')
        run_id = client.post('/api/runs').json()['id']
        response=client.post('/api/auth/register',json={"username":"Alice","password":"test-password-123"})
        assert response.status_code==201
        assert client.get('/api/auth/me').json()=={"authenticated":True,"username":"alice"}
        assert client.get('/api/subscription').json()['custom_prompt']=='关注开源Agent'
        assert client.get('/api/subscription').json()['enabled']==1
        assert client.get('/api/runs/'+run_id).status_code==200
        session = client.cookies.get('newagent_session')
        with connect() as conn:
            assert conn.execute('SELECT password_hash FROM accounts').fetchone()[0]!='test-password-123'
            assert conn.execute('SELECT token_hash FROM sessions').fetchone()[0]==token_hash(session)
            assert not conn.execute('SELECT id FROM users WHERE id=?',(guest_cookie,)).fetchone()
        assert client.post('/api/auth/logout').status_code==200
        assert client.get('/api/runs/'+run_id).status_code==404
        # Replaying the revoked session or retired guest cookie cannot regain access.
        client.cookies.clear()
        client.cookies.set('newagent_session',session)
        client.cookies.set('newagent_user',guest_cookie)
        assert client.get('/api/runs/'+run_id).status_code==404
        client.cookies.clear()
        client.put('/api/subscription',json={"nickname":"Guest","custom_prompt":"访客提示词"})
        guest_run=client.post('/api/runs').json()['id']
        assert client.post('/api/auth/login',json={"username":"alice","password":"wrong-password"}).status_code==401
        assert client.post('/api/auth/login',json={"username":"ALICE","password":"test-password-123"}).status_code==200
        assert client.get('/api/subscription').json()['custom_prompt']=='关注开源Agent'
        assert client.get('/api/runs/'+guest_run).status_code==200
        assert client.get('/api/runs/'+run_id).status_code==200
        # New device with no cookies can log in and retrieve the same account.
        client.cookies.clear()
        assert client.post('/api/auth/login',json={"username":"alice","password":"test-password-123"}).status_code==200
        assert client.get('/api/subscription').json()['custom_prompt']=='关注开源Agent'
        assert len(client.get('/api/runs').json())==2


def test_account_isolation_and_login_limits(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"data_dir",tmp_path)
    monkeypatch.setattr(settings,"openai_api_key","")
    with TestClient(app) as client:
        assert client.post('/api/auth/register',json={"username":"aaa","password":"test-password-123"}).status_code==201
        client.put('/api/subscription',json={"nickname":"A","custom_prompt":"private"})
        run=client.post('/api/runs').json()['id']
        client.post('/api/auth/logout')
        assert client.post('/api/auth/register',json={"username":"aaa","password":"test-password-123"}).status_code==409
        assert client.post('/api/auth/register',json={"username":"bbb","password":"test-password-456"}).status_code==201
        assert client.get('/api/runs/'+run).status_code==404
        assert client.get('/api/subscription').json() is None
        client.post('/api/auth/logout')
        for _ in range(8):
            assert client.post('/api/auth/login',json={"username":"aaa","password":"wrong-password"}).status_code==401
        assert client.post('/api/auth/login',json={"username":"aaa","password":"test-password-123"}).status_code==429
