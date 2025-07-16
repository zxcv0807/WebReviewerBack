import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from .db import get_db
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status

load_dotenv()
_secret = os.getenv("SECRET_KEY")
if not _secret:
    raise RuntimeError("SECRET_KEY environment variable is not set")
SECRET_KEY: str = _secret
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = data.copy()
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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
        # DB에서 id, username, role 조회
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, role FROM \"user\" WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        conn.close()
        if not user_row:
            raise HTTPException(status_code=401, detail="User not found")
        return {"id": user_row[0], "username": user_row[1], "role": user_row[2]}
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
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM \"user\" WHERE username = %s", (user.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")
    cursor.execute("SELECT * FROM \"user\" WHERE email = %s", (user.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user.password)
    created_at = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO \"user\" (username, email, password_hash, created_at, role) VALUES (%s, %s, %s, %s, %s)",
        (user.username, user.email, hashed_password, created_at, 'user')
    )
    conn.commit()
    conn.close()
    return {"msg": "User created successfully"}

@router.post("/login")
def login(user: UserLogin, response: Response):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM \"user\" WHERE email = %s", (user.email,))
    user_row = cursor.fetchone()
    conn.close()
    if not user_row or not verify_password(user.password, user_row[3]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user_row[1], "role": user_row[4]})
    refresh_token = create_refresh_token(data={"sub": user_row[1], "role": user_row[4]})
    
    # refresh_token을 HttpOnly 쿠키로 설정
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # HTTPS 사용 시 True로 변경
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60  # 초 단위
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
    
    # 새로운 access_token 생성
    new_access_token = create_access_token(data={"sub": username})
    
    # 새로운 refresh_token도 생성 (선택사항)
    new_refresh_token = create_refresh_token(data={"sub": username})
    
    # 새로운 refresh_token을 쿠키에 설정
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=False,  # HTTPS 사용 시 True로 변경
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
def logout(response: Response):
    # refresh_token 쿠키 삭제
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=False,  # HTTPS 사용 시 True로 변경
        samesite="lax"
    )
    return {"msg": "Logged out successfully"} 

# 관리자 전용 엔드포인트 예시
@router.get("/admin/only")
def admin_only_endpoint(current_user=Depends(admin_required)):
    return {"msg": "관리자만 접근 가능"} 

@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    # DB에서 유저 정보 조회
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role FROM \"user\" WHERE username = %s", (current_user["username"],))
    user_row = cursor.fetchone()
    conn.close()
    if not user_row:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "id": user_row[0],
        "username": user_row[1],
        "email": user_row[2],
        "role": user_row[3]
    } 