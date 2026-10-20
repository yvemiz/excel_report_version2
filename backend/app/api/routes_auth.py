import re
import sqlite3

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from app.core.auth_service import COOKIE_NAME, SESSION_SECONDS

router = APIRouter(prefix="/api/auth", tags=["Accounts"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9_]{3,32}", value):
            raise ValueError("用户名需为3至32位字母、数字或下划线")
        return value


class Registration(Credentials):
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(default="", max_length=40)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError("姓名不能包含控制字符")
        return value.strip()


def issue_session(request: Request, response: Response, user: dict):
    store = request.app.state.auth
    old_token = request.cookies.get(COOKIE_NAME)
    if old_token:
        store.revoke_session(old_token)
    token = store.create_session(user["id"])
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True, secure=request.url.scheme == "https", samesite="lax", path="/")
    return {"user": user}


def check_rate(request: Request, kind: str):
    address = request.client.host if request.client else "unknown"
    if not request.app.state.auth.allow_attempt(address, kind):
        raise HTTPException(status_code=429, detail="尝试次数过多，请稍后再试")


@router.post("/register", status_code=201)
def register(credentials: Registration, request: Request, response: Response):
    check_rate(request, "register")
    try:
        user = request.app.state.auth.register(credentials.username, credentials.display_name, credentials.password)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="该用户名已被使用")
    return issue_session(request, response, user)


@router.post("/login")
def login(credentials: Credentials, request: Request, response: Response):
    check_rate(request, "login")
    user = request.app.state.auth.login(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    return issue_session(request, response, user)


@router.get("/me")
def me(request: Request):
    return {"user": request.state.user}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        request.app.state.auth.revoke_session(token)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax")
    return {"success": True}
