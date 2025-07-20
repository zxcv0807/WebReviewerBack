import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from supabase import create_client, Client
import requests
from fastapi import Request

load_dotenv()
_secret = os.getenv("SECRET_KEY")
if not _secret:
    raise RuntimeError("SECRET_KEY environment variable is not set")
SECRET_KEY: str = _secret
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_refresh_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
        return str(username)
    except JWTError:
        return None

def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if username is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        user_row = supabase.table("user").select("id", "username", "role").eq("username", username).single().execute().data
        if not user_row:
            raise HTTPException(status_code=401, detail="User not found")
        return {"id": user_row["id"], "username": user_row["username"], "role": user_row["role"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def admin_required(current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한 필요")
    return current_user

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

@router.post("/signup")
def signup(user: UserCreate):
    # username/email 중복 체크
    if supabase.table("user").select("*").eq("username", user.username).execute().data:
        raise HTTPException(status_code=400, detail="Username already registered")
    if supabase.table("user").select("*").eq("email", user.email).execute().data:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    created_at = datetime.utcnow().isoformat()
    supabase.table("user").insert({
        "username": user.username,
        "email": user.email,
        "password_hash": hashed_password,
        "created_at": created_at,
        "role": "user"
    }).execute()
    return {"msg": "User created successfully"}

@router.post("/login")
def login(user: UserLogin, response: Response):
    try:
        user_row = supabase.table("user").select("*").eq("email", user.email).single().execute().data
    except Exception:
        # 이메일이 없거나 중복된 경우
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user_row or not verify_password(user.password, user_row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user_row["username"], "role": user_row["role"]})
    refresh_token = create_refresh_token(data={"sub": user_row["username"], "role": user_row["role"]})
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/login/google")
async def google_login(request: Request, response: Response):
    data = await request.json()
    id_token = data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="id_token is required")

    # 1. 구글 id_token 검증 및 사용자 정보 획득
    token_info = requests.get(GOOGLE_TOKEN_INFO_URL, params={"id_token": id_token}).json()
    if "error_description" in token_info or "sub" not in token_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    google_id = token_info["sub"]
    email = token_info["email"]
    username = token_info.get("name") or email.split("@")[0]

    # 2. user 테이블에서 google_id로 사용자 조회
    user_row = supabase.table("user").select("*").eq("google_id", google_id).single().execute().data
    if not user_row:
        # 신규 사용자 생성
        created_at = datetime.utcnow().isoformat()
        insert_result = supabase.table("user").insert({
            "username": username,
            "email": email,
            "google_id": google_id,
            "password_hash": None,
            "created_at": created_at,
            "role": "user"
        }).execute()
        user_row = insert_result.data[0] if insert_result.data else None
        if not user_row:
            raise HTTPException(status_code=500, detail="User creation failed")

    # 3. JWT 발급
    access_token = create_access_token(data={"sub": user_row["username"], "role": user_row["role"]})
    refresh_token = create_refresh_token(data={"sub": user_row["username"], "role": user_row["role"]})
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/refresh")
def refresh_token(response: Response, refresh_token: str = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    username = verify_refresh_token(refresh_token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_row = supabase.table("user").select("*").eq("username", username).single().execute().data
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    new_access_token = create_access_token(data={"sub": username, "role": user_row["role"]})
    new_refresh_token = create_refresh_token(data={"sub": username, "role": user_row["role"]})
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=False,
        samesite="lax"
    )
    return {"msg": "Logged out successfully"}

@router.get("/admin/only")
def admin_only_endpoint(current_user=Depends(admin_required)):
    return {"msg": "관리자만 접근 가능"}

@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    user_row = supabase.table("user").select("id", "username", "email", "role").eq("username", current_user["username"]).single().execute().data
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "id": user_row["id"],
        "username": user_row["username"],
        "email": user_row["email"],
        "role": user_row["role"]
    } 