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

# Google OAuth 2.0 설정
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# Google OAuth 설정이 없어도 앱이 시작되도록 경고만 출력
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print("Warning: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are not set. Google OAuth will not work.")

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Google OAuth 2.0 API URLs
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

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
        
        try:
            user_result = supabase.table("user").select("id", "username", "role").eq("username", username).execute()
            if not user_result.data:
                raise HTTPException(status_code=401, detail="User not found")
            user_row = user_result.data[0]
            return {"id": user_row["id"], "username": user_row["username"], "role": user_row["role"]}
        except Exception as e:
            raise HTTPException(status_code=401, detail="User not found")
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

class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str

@router.post("/signup")
def signup(user: UserCreate):
    try:
        # username/email 중복 체크
        username_result = supabase.table("user").select("*").eq("username", user.username).execute()
        if username_result.data:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        email_result = supabase.table("user").select("*").eq("email", user.email).execute()
        if email_result.data:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user.password)
        created_at = datetime.utcnow().isoformat()
        
        insert_result = supabase.table("user").insert({
            "username": user.username,
            "email": user.email,
            "password_hash": hashed_password,
            "created_at": created_at,
            "role": "user"
        }).execute()
        
        if not insert_result.data:
            raise HTTPException(status_code=500, detail="Failed to create user")
        
        return {"msg": "User created successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

@router.post("/login")
def login(user: UserLogin, response: Response):
    try:
        user_result = supabase.table("user").select("*").eq("email", user.email).execute()
        if not user_result.data:
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        
        user_row = user_result.data[0]
        if not verify_password(user.password, user_row["password_hash"]):
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

@router.post("/google/callback")
async def google_callback(request: GoogleCallbackRequest, response: Response):
    # Google OAuth 설정 확인
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    
    try:
        # 1. Authorization code를 access token으로 교환
        token_data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": request.code,
            "grant_type": "authorization_code",
            "redirect_uri": request.redirect_uri
        }
        
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data)
        if token_response.status_code != 200:
            error_detail = token_response.json().get("error_description", "Unknown error")
            raise HTTPException(status_code=400, detail=f"Failed to exchange authorization code: {error_detail}")
        
        token_info = token_response.json()
        google_access_token = token_info.get("access_token")
        if not google_access_token:
            raise HTTPException(status_code=400, detail="No access token received from Google")
        
        # 2. Access token으로 사용자 정보 가져오기
        headers = {"Authorization": f"Bearer {google_access_token}"}
        userinfo_response = requests.get(GOOGLE_USERINFO_URL, headers=headers)
        if userinfo_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        user_info = userinfo_response.json()
        google_id = user_info.get("id")
        email = user_info.get("email")
        name = user_info.get("name")
        
        if not google_id or not email:
            raise HTTPException(status_code=400, detail="Invalid user info from Google")
        
        # 3. 사용자명 생성 (이메일에서 추출하거나 Google 이름 사용)
        username = name or email.split("@")[0]
        
        # 4. 기존 사용자 확인 (google_id 또는 email로)
        user_row = None
        try:
            # google_id로 먼저 확인
            user_result = supabase.table("user").select("*").eq("google_id", google_id).execute()
            if user_result.data:
                user_row = user_result.data[0]
        except Exception:
            pass
        
        if not user_row:
            try:
                # email로 확인
                user_result = supabase.table("user").select("*").eq("email", email).execute()
                if user_result.data:
                    user_row = user_result.data[0]
                    # 기존 사용자에 google_id 추가
                    if not user_row.get("google_id"):
                        supabase.table("user").update({"google_id": google_id}).eq("id", user_row["id"]).execute()
                        user_row["google_id"] = google_id
            except Exception:
                pass
        
        # 5. 신규 사용자인 경우 생성
        if not user_row:
            created_at = datetime.utcnow().isoformat()
            try:
                insert_result = supabase.table("user").insert({
                    "username": username,
                    "email": email,
                    "google_id": google_id,
                    "password_hash": None,
                    "created_at": created_at,
                    "role": "user"
                }).execute()
                if insert_result.data:
                    user_row = insert_result.data[0]
                else:
                    raise HTTPException(status_code=500, detail="User creation failed")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
        
        # 6. JWT 토큰 발급
        jwt_access_token = create_access_token(data={"sub": user_row["username"], "role": user_row["role"]})
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
            "access_token": jwt_access_token,
            "token_type": "bearer",
            "user": {
                "id": user_row["id"],
                "username": user_row["username"],
                "email": user_row["email"],
                "role": user_row["role"]
            }
        }
        
    except HTTPException:
        raise
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# 기존 Google 로그인 엔드포인트 비활성화 (주석 처리)
# @router.post("/login/google")
# async def google_login(request: Request, response: Response):
#     # 기존 코드는 주석 처리
#     pass

@router.post("/refresh")
def refresh_token(response: Response, refresh_token: str = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    username = verify_refresh_token(refresh_token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    try:
        user_result = supabase.table("user").select("*").eq("username", username).execute()
        if not user_result.data:
            raise HTTPException(status_code=401, detail="User not found")
        user_row = user_result.data[0]
    except Exception:
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
    try:
        user_result = supabase.table("user").select("id", "username", "email", "role").eq("username", current_user["username"]).execute()
        if not user_result.data:
            raise HTTPException(status_code=401, detail="User not found")
        user_row = user_result.data[0]
        return {
            "id": user_row["id"],
            "username": user_row["username"],
            "email": user_row["email"],
            "role": user_row["role"]
        }
    except Exception:
        raise HTTPException(status_code=401, detail="User not found") 