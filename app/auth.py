import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from .db import connect

router = APIRouter(prefix="/api/auth")
UTC = timezone.utc


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + digest


def verify_password(password, stored):
    return hmac.compare_digest(hash_password(password,stored.split(":")[0]),stored)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_account(token):
    if not token:
        return None
    with connect() as conn:
        row = conn.execute("SELECT a.user_id,a.username FROM sessions s JOIN accounts a ON a.user_id=s.user_id WHERE s.token_hash=? AND s.expires_at>?", (token_hash(token),datetime.now(UTC).isoformat())).fetchone()
    return dict(row) if row else None


def merge_guest(conn, guest_id, account_id):
    # Registered account preferences take priority; guest-only preferences migrate.
    conn.execute("INSERT OR IGNORE INTO user_subscriptions SELECT ?,nickname,topics,keywords,exclusions,scheduled_time,timezone,enabled,next_run_at FROM user_subscriptions WHERE user_id=?",(account_id,guest_id))
    conn.execute("INSERT OR IGNORE INTO user_prompts SELECT ?,custom_prompt FROM user_prompts WHERE user_id=?",(account_id,guest_id))
    conn.execute("UPDATE run_owners SET scheduled_for=NULL WHERE user_id=? AND scheduled_for IN (SELECT scheduled_for FROM run_owners WHERE user_id=?)",(guest_id,account_id))
    conn.execute("UPDATE run_owners SET user_id=? WHERE user_id=?",(account_id,guest_id))
    conn.execute("DELETE FROM user_subscriptions WHERE user_id=?",(guest_id,))
    conn.execute("DELETE FROM user_prompts WHERE user_id=?",(guest_id,))
    # Retire the old bearer cookie, so it cannot access migrated records.
    conn.execute("DELETE FROM users WHERE id=?",(guest_id,))


class Credentials(BaseModel):
    username: str = Field(min_length=3,max_length=40,pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8,max_length=128)


def set_session(conn, response, request, user_id):
    token = secrets.token_urlsafe(32)
    old = request.cookies.get("newagent_session")
    if old:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",(token_hash(old),))
    conn.execute("DELETE FROM sessions WHERE expires_at<=?",(datetime.now(UTC).isoformat(),))
    conn.execute("INSERT INTO sessions VALUES(?,?,?)",(token_hash(token),user_id,(datetime.now(UTC)+timedelta(days=30)).isoformat()))
    response.set_cookie("newagent_session",token,httponly=True,samesite="strict",secure=request.url.scheme=="https",max_age=30*86400)
    response.delete_cookie("newagent_user")


@router.get("/me")
def me(request: Request):
    account = getattr(request.state,"account",None)
    return {"authenticated":bool(account),"username":account["username"] if account else None}


@router.post("/register",status_code=201)
def register(body: Credentials, request: Request, response: Response):
    if request.state.account:
        raise HTTPException(409,"请先退出当前账号")
    username = body.username.lower()
    password_hash = hash_password(body.password)
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM accounts WHERE username=?",(username,)).fetchone():
            raise HTTPException(409,"用户名已被使用")
        user_id = uuid.uuid4().hex
        conn.execute("INSERT INTO users VALUES(?,?)",(user_id,datetime.now(UTC).isoformat()))
        conn.execute("INSERT INTO accounts VALUES(?,?,?)",(user_id,username,password_hash))
        merge_guest(conn,request.state.user_id,user_id)
        set_session(conn,response,request,user_id)
    request.state.auth_changed = True
    return {"authenticated":True,"username":username}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    if request.state.account:
        raise HTTPException(409,"请先退出当前账号")
    username = body.username.lower()
    now = datetime.now(UTC)
    limit_key = token_hash(username)
    with connect() as conn:
        attempt = conn.execute("SELECT * FROM auth_attempts WHERE key=?",(limit_key,)).fetchone()
        blocked = attempt and datetime.fromisoformat(attempt['window_start']) > now-timedelta(minutes=15)
        if blocked and attempt['failures'] >= 8:
            raise HTTPException(429,"尝试次数过多，请15分钟后重试")
        row = conn.execute("SELECT * FROM accounts WHERE username=?",(username,)).fetchone()
    # Also hash unknown accounts to reduce username timing leakage.
    valid = verify_password(body.password,row['password_hash']) if row else verify_password(body.password,hash_password('unmatched-placeholder'))
    if not row or not valid:
        with connect() as conn:
            count = attempt['failures']+1 if blocked else 1
            start = attempt['window_start'] if blocked else now.isoformat()
            conn.execute("INSERT OR REPLACE INTO auth_attempts VALUES(?,?,?)",(limit_key,count,start))
        raise HTTPException(401,"用户名或密码错误")
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM auth_attempts WHERE key=?",(limit_key,))
        merge_guest(conn,request.state.user_id,row['user_id'])
        set_session(conn,response,request,row['user_id'])
    request.state.auth_changed = True
    return {"authenticated":True,"username":username}


@router.post("/logout")
def logout(request: Request,response: Response):
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE token_hash=?",(token_hash(request.cookies.get('newagent_session','')),))
    response.delete_cookie('newagent_session')
    response.delete_cookie('newagent_user')
    request.state.auth_changed = True
    return {"ok":True}
