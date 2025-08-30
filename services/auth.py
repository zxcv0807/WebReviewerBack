"""
인증 및 권한 관리 모듈

이 모듈은 웹사이트 리뷰 플랫폼의 사용자 인증을 담당합니다:
- 일반 회원가입/로그인 (이메일 + 패스워드)
- Google OAuth 2.0 소셜 로그인
- JWT 기반 액세스/리프레시 토큰 관리
- 역할 기반 접근 제어 (user/admin)
"""

import os
import logging
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Depends, Response, Cookie, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr, validator
from .db import supabase
import requests
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 로깅 설정
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 환경변수 로드
load_dotenv()

# JWT 토큰 관련 설정
_secret = os.getenv("SECRET_KEY")
if not _secret:
    raise RuntimeError("SECRET_KEY environment variable is not set")
SECRET_KEY: str = _secret  # JWT 서명을 위한 비밀키
ALGORITHM = os.getenv("ALGORITHM", "HS256")  # JWT 서명 알고리즘
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))  # 액세스 토큰 만료시간
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))  # 리프레시 토큰 만료시간
EMAIL_VERIFICATION_EXPIRE_HOURS = int(os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24"))  # 이메일 인증 토큰 만료시간

# 쿠키 보안 설정
COOKIE_SECURE = os.getenv("ENVIRONMENT", "development") == "production"

# SMTP 이메일 설정
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# Google OAuth 2.0 설정
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
# Google OAuth 설정이 없어도 앱이 시작되도록 경고만 출력
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    logger.warning("Google OAuth credentials not configured. Google OAuth will not work.")

# FastAPI 라우터 및 보안 설정
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")  # 패스워드 해싱
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")  # OAuth2 스킴 (Bearer 토큰)

# Google OAuth 2.0 API URLs
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# 평문 password, 해쉬된 password 비교하여 일치 여부 확인
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)
# password를 bcrypt로 해싱
def get_password_hash(password):
    return pwd_context.hash(password)
# JWT 액세스 토큰 생성
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Args:
        data: 토큰에 포함할 데이터 (사용자명, 역할 등)
        expires_delta: 사용자 정의 만료시간 (선택사항)
    Returns:
        str: 인코딩된 JWT 토큰
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
# JWT refresh token 생성
# 이메일 인증 코드 생성 (6자리 숫자/영문 조합)
def create_email_verification_code(user_id: int):
    """
    이메일 인증용 6자리 코드 생성
    Args:
        user_id: 사용자 ID
    Returns:
        str: 6자리 인증 코드
    """
    import string
    import random
    
    # 6자리 코드 생성 (숫자+대문자 영문)
    characters = string.digits + string.ascii_uppercase
    code = ''.join(random.choices(characters, k=6))
    expires_at = datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS)
    
    # 데이터베이스에 코드 저장 (기존 코드가 있으면 덮어쓰기)
    try:
        # 기존 코드 삭제
        supabase.table("email_verification_token").delete().eq("user_id", user_id).execute()
        # 새 코드 삽입 (token 필드를 code로 재사용)
        supabase.table("email_verification_token").insert({
            "user_id": user_id,
            "token": code,  # code를 token 필드에 저장
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return code
    except Exception as e:
        logger.error(f"Failed to create email verification code: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create verification code")

# 이메일 인증 코드 검증
def verify_email_verification_code(code: str):
    """
    이메일 인증 코드 검증
    Args:
        code: 6자리 인증 코드
    Returns:
        int or None: 유효한 경우 사용자 ID, 무효한 경우 None
    """
    try:
        # 코드 형식 검증 (6자리 숫자+영문 대문자)
        if not code or len(code) != 6 or not code.isalnum():
            return None
        
        # 대문자로 변환하여 검색 (대소문자 구분 없이)
        code = code.upper()
        
        result = supabase.table("email_verification_token").select("user_id", "expires_at").eq("token", code).execute()
        if not result.data:
            return None
        
        code_data = result.data[0]
        expires_at = datetime.fromisoformat(code_data["expires_at"].replace("Z", "+00:00"))
        
        # 코드 만료 확인
        if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
            # 만료된 코드 삭제
            supabase.table("email_verification_token").delete().eq("token", code).execute()
            return None
        
        return code_data["user_id"]
    except Exception as e:
        logger.error(f"Failed to verify email verification code: {str(e)}")
        return None

# 이메일 인증 코드 전송 함수
def send_verification_code_email(email: str, username: str, code: str):
    """
    이메일 인증 코드 발송
    Args:
        email: 수신자 이메일
        username: 사용자명
        code: 6자리 인증 코드
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured. Email will not be sent.")
        return False
    
    try:
        # 이메일 내용 작성
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = email
        msg['Subject'] = "이메일 주소 인증 코드"
        
        body = f"""
        안녕하세요 {username}님,
        
        웹 리뷰 플랫폼에 가입해 주셔서 감사합니다.
        아래 인증 코드를 웹사이트에 입력하여 이메일 주소를 인증해 주세요.
        
        인증 코드: {code}
        
        이 코드는 24시간 후에 만료됩니다.
        보안을 위해 이 코드를 다른 사람과 공유하지 마세요.
        
        감사합니다.
        """
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # SMTP 서버 연결 및 이메일 발송
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        text = msg.as_string()
        server.sendmail(FROM_EMAIL, email, text)
        server.quit()
        
        logger.info(f"Verification code email sent to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send verification code email: {str(e)}")
        return False

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Args:
        data: 토큰에 포함할 데이터
        expires_delta: 사용자 정의 만료시간 (선택사항)
    Returns:
        str: 인코딩된 JWT 리프레시 토큰
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
# refresh token 유효성 검증
def verify_refresh_token(token: str):
    """
    Args:
        token: 검증할 JWT 리프레시 토큰
    Returns:
        int or None: 유효한 경우 사용자 ID, 무효한 경우 None
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return int(user_id)
    except (JWTError, ValueError):
        return None
# JWT 토큰에서 현재 사용자 정보 추출 (의존성 주입용)
def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Args:
        token: Bearer 토큰에서 추출된 JWT
    Returns:
        dict: 사용자 정보 (id, username, role)
    """
    try:
        # JWT 토큰 디코딩 및 검증
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        if user_id is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # 데이터베이스에서 사용자 정보 재확인 (보안 강화)
        try:
            user_result = supabase.table("user").select("id", "username", "role").eq("id", int(user_id)).execute()
            if not user_result.data:
                raise HTTPException(status_code=401, detail="User not found")
            user_row = user_result.data[0]
            return {"id": user_row["id"], "username": user_row["username"], "role": user_row["role"]}
        except Exception as e:
            raise HTTPException(status_code=401, detail="User not found")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

# 관리자 권한 확인 (의존성 주입용)
def admin_required(current_user=Depends(get_current_user)):
    """
    Args:
        current_user: get_current_user에서 반환된 사용자 정보
    Returns:
        dict: 관리자 사용자 정보
    Raises:
        HTTPException: 관리자 권한이 없는 경우 403 에러
    """
    if current_user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한 필요")
    return current_user

# Pydantic 모델 정의 (API 요청/응답 스키마)
class UserCreate(BaseModel):
    """회원가입 요청 모델"""
    username: str
    email: EmailStr
    password: str
    
    @validator('username')
    def validate_username(cls, v):
        """사용자명 유효성 검증: 3-20자, 영문/숫자만 허용"""
        if len(v) < 3 or len(v) > 20:
            raise ValueError('사용자명은 3-20자 사이여야 합니다')
        if not v.isalnum():
            raise ValueError('사용자명은 영문자와 숫자만 허용됩니다')
        return v
    
    @validator('password')
    def validate_password(cls, v):
        """패스워드 유효성 검증: 최소 8자"""
        if len(v) < 8:
            raise ValueError('비밀번호는 8자 이상이어야 합니다')
        return v

class UserLogin(BaseModel):
    """로그인 요청 모델"""
    email: EmailStr
    password: str

class GoogleCallbackRequest(BaseModel):
    """Google OAuth 콜백 요청 모델"""
    code: str  # Google에서 발급한 인증 코드
    redirect_uri: str  # 콜백 URI
    state: Optional[str] = None  # CSRF 방지용 state 파라미터

class UserUpdate(BaseModel):
    """사용자 정보 수정 요청 모델"""
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    
    @validator('username')
    def validate_username(cls, v):
        if v is not None:
            if len(v) < 3 or len(v) > 20:
                raise ValueError('사용자명은 3-20자 사이여야 합니다')
            if not v.isalnum():
                raise ValueError('사용자명은 영문자와 숫자만 허용됩니다')
        return v

class PasswordChange(BaseModel):
    """비밀번호 변경 요청 모델"""
    current_password: str
    new_password: str
    
    @validator('new_password')
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError('새 비밀번호는 8자 이상이어야 합니다')
        return v

class EmailVerificationCode(BaseModel):
    """이메일 인증 코드 요청 모델"""
    code: str
    
    @validator('code')
    def validate_code(cls, v):
        if not v or len(v) != 6:
            raise ValueError('인증 코드는 6자리여야 합니다')
        if not v.isalnum():
            raise ValueError('인증 코드는 숫자와 영문만 허용됩니다')
        return v.upper()  # 대문자로 변환

# 일반 회원가입 엔드포인트
@router.post("/signup")
def signup(user: UserCreate):
    try:
        # 1. 사용자명 중복 체크
        username_result = supabase.table("user").select("*").eq("username", user.username).execute()
        if username_result.data:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # 2. 이메일 중복 체크
        email_result = supabase.table("user").select("*").eq("email", user.email).execute()
        if email_result.data:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # 3. 패스워드 해싱
        hashed_password = get_password_hash(user.password)
        created_at = datetime.utcnow().isoformat()
        
        # 4. 사용자 데이터 삽입
        insert_result = supabase.table("user").insert({
            "username": user.username,
            "email": user.email,
            "password_hash": hashed_password,
            "created_at": created_at,
            "role": "user",  # 기본 역할
            "email_verified": False  # 일반 회원가입은 이메일 인증 필요
        }).execute()
        
        if not insert_result.data:
            raise HTTPException(status_code=500, detail="Failed to create user")
        
        # 5. 이메일 인증 코드 생성 및 발송
        try:
            user_id = insert_result.data[0]["id"]
            code = create_email_verification_code(user_id)
            send_verification_code_email(user.email, user.username, code)
        except Exception as e:
            logger.warning(f"Failed to send verification code email: {str(e)}")
            # 이메일 발송 실패해도 회원가입은 성공으로 처리
        
        return {"msg": "User created successfully. Please check your email for verification."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")

# 일반 로그인 엔드포인트
@router.post("/login")
def login(user: UserLogin, response: Response):
    try:
        # 1. 이메일로 사용자 검색
        user_result = supabase.table("user").select("*").eq("email", user.email).execute()
        if not user_result.data:
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        
        # 2. 패스워드 검증
        user_row = user_result.data[0]
        if not verify_password(user.password, user_row["password_hash"]):
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        
        # 3. JWT 토큰 생성
        access_token = create_access_token(data={"sub": str(user_row["id"]), "role": user_row["role"]})
        refresh_token = create_refresh_token(data={"sub": str(user_row["id"]), "role": user_row["role"]})
        
        # 4. 리프레시 토큰을 HttpOnly 쿠키로 설정 
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True, 
            secure=COOKIE_SECURE,  # HTTPS에서만 전송
            samesite="lax",  # CSRF 방지
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

# Google OAuth 콜백 처리 엔드포인트
@router.post("/google/callback")
async def google_callback(request: GoogleCallbackRequest, response: Response):
    """
    OAuth 흐름:
    1. Authorization code를 Google access token으로 교환
    2. Access token으로 사용자 정보 가져오기
    3. 기존 사용자 확인 또는 신규 사용자 생성
    4. JWT 토큰 발급
    """
    # Google OAuth 설정 확인
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    
    try:
        logger.info("Google OAuth callback received")
        
        # 1. Authorization code를 access token으로 교환
        token_data = {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "code": request.code,
            "grant_type": "authorization_code",
            "redirect_uri": request.redirect_uri
        }
        
        logger.info("Exchanging authorization code for access token")
        token_response = requests.post(GOOGLE_TOKEN_URL, data=token_data)
        
        if token_response.status_code != 200:
            error_response = token_response.json()
            error_detail = error_response.get("error_description", error_response.get("error", "Unknown error"))
            logger.error(f"Token exchange failed: {error_detail}")
            raise HTTPException(status_code=400, detail=f"Failed to exchange authorization code: {error_detail}")
        
        token_info = token_response.json()
        google_access_token = token_info.get("access_token")
        if not google_access_token:
            logger.error("No access token received from Google")
            raise HTTPException(status_code=400, detail="No access token received from Google")
        
        logger.info("Successfully received access token from Google")
        
        # 2. Access token으로 사용자 정보 가져오기
        logger.info("Getting user info from Google")
        headers = {"Authorization": f"Bearer {google_access_token}"}
        userinfo_response = requests.get(GOOGLE_USERINFO_URL, headers=headers)
        
        if userinfo_response.status_code != 200:
            logger.error("Failed to get user info from Google")
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        user_info = userinfo_response.json()
        google_id = user_info.get("id")
        email = user_info.get("email")
        name = user_info.get("name")
        
        logger.info("Google user info received successfully")
        
        if not google_id or not email:
            logger.error("Invalid user info from Google")
            raise HTTPException(status_code=400, detail="Invalid user info from Google")
        
        # 3. 사용자명 생성 및 중복 처리
        base_username = name or email.split("@")[0]
        username = base_username
        
        # 사용자명 중복 시 숫자 접미사 추가 (예: john -> john1, john2, ...)
        counter = 1
        while True:
            try:
                existing_user = supabase.table("user").select("id").eq("username", username).execute()
                if not existing_user.data:
                    break
                username = f"{base_username}{counter}"
                counter += 1
            except Exception:
                break
        
        # 4. 기존 사용자 확인 (2단계 검색: google_id -> email)
        user_row = None
        
        # 4-1. Google ID로 먼저 확인 (가장 정확한 매칭)
        try:
            user_result = supabase.table("user").select("*").eq("google_id", google_id).execute()
            if user_result.data:
                user_row = user_result.data[0]
        except Exception:
            pass
        
        # 4-2. Google ID로 찾지 못한 경우 이메일로 확인
        if not user_row:
            try:
                user_result = supabase.table("user").select("*").eq("email", email).execute()
                if user_result.data:
                    user_row = user_result.data[0]
                    # 기존 일반 계정에 Google ID 연동
                    if not user_row.get("google_id"):
                        supabase.table("user").update({"google_id": google_id}).eq("id", user_row["id"]).execute()
                        user_row["google_id"] = google_id
            except Exception:
                pass
        
        # 5. 신규 사용자 생성 (Google OAuth 전용 계정)
        if not user_row:
            created_at = datetime.utcnow().isoformat()
            try:
                insert_result = supabase.table("user").insert({
                    "username": username,
                    "email": email,
                    "google_id": google_id,
                    "password_hash": None,  # Google OAuth 사용자는 패스워드 없음
                    "created_at": created_at,
                    "role": "user",  # 기본 역할
                    "email_verified": True  # Google OAuth 사용자는 이미 이메일 인증됨
                }).execute()
                if insert_result.data:
                    user_row = insert_result.data[0]
                else:
                    raise HTTPException(status_code=500, detail="User creation failed")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
        
        # 6. JWT 토큰 발급 및 응답
        jwt_access_token = create_access_token(data={"sub": str(user_row["id"]), "role": user_row["role"]})
        refresh_token = create_refresh_token(data={"sub": str(user_row["id"]), "role": user_row["role"]})
        
        # 리프레시 토큰을 HttpOnly 쿠키로 설정
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        )
        
        logger.info(f"Google OAuth login successful for user: {user_row['username']}")
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

# refresh 토큰으로 새로운 access token 발급
@router.post("/refresh")
def refresh_token(response: Response, refresh_token: str = Cookie(None)):
    """
    - HttpOnly 쿠키에서 리프레시 토큰 추출
    - 토큰 유효성 검증 후 새로운 토큰 쌍 생성
    - 토큰 로테이션으로 보안 강화
    """
    # 1. 리프레시 토큰 존재 확인
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token not found")
    
    # 2. 리프레시 토큰 유효성 검증
    user_id = verify_refresh_token(refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    # 3. 사용자 정보 확인
    try:
        user_result = supabase.table("user").select("*").eq("id", user_id).execute()
        if not user_result.data:
            raise HTTPException(status_code=401, detail="User not found")
        user_row = user_result.data[0]
    except Exception:
        raise HTTPException(status_code=401, detail="User not found")
    
    # 4. 새로운 토큰 쌍 생성 (토큰 로테이션)
    new_access_token = create_access_token(data={"sub": str(user_id), "role": user_row["role"]})
    new_refresh_token = create_refresh_token(data={"sub": str(user_id), "role": user_row["role"]})
    
    # 5. 새로운 리프레시 토큰을 쿠키로 설정
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

# 로그아웃 (refresh token 쿠키 삭제)
@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax"
    )
    return {"msg": "Logged out successfully"}

# 관리자 전용 테스트 엔드포인트
@router.get("/admin/only")
def admin_only_endpoint(current_user=Depends(admin_required)):
    return {"msg": "관리자만 접근 가능"}

# 현재 로그인한 사용자 정보 조회
@router.get("/me")
def get_me(current_user=Depends(get_current_user)):
    try:
        user_result = supabase.table("user").select("id", "username", "email", "role").eq("id", current_user["id"]).execute()
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

# 사용자 정보 수정
@router.put("/me")
def update_me(user_update: UserUpdate, current_user=Depends(get_current_user)):
    try:
        update_data = {}
        
        # 사용자명 변경 처리
        if user_update.username is not None:
            # 사용자명 중복 체크 (자기 자신 제외)
            username_result = supabase.table("user").select("id").eq("username", user_update.username).neq("id", current_user["id"]).execute()
            if username_result.data:
                raise HTTPException(status_code=400, detail="Username already exists")
            update_data["username"] = user_update.username
        
        # 이메일 변경 처리  
        if user_update.email is not None:
            # 이메일 중복 체크 (자기 자신 제외)
            email_result = supabase.table("user").select("id").eq("email", user_update.email).neq("id", current_user["id"]).execute()
            if email_result.data:
                raise HTTPException(status_code=400, detail="Email already exists")
            update_data["email"] = user_update.email
        
        # 업데이트할 데이터가 없는 경우
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")
        
        # 사용자 정보 업데이트
        update_result = supabase.table("user").update(update_data).eq("id", current_user["id"]).execute()
        
        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update user")
        
        # 업데이트된 사용자 정보 반환
        updated_user = update_result.data[0]
        return {
            "id": updated_user["id"],
            "username": updated_user["username"],
            "email": updated_user["email"],
            "role": updated_user["role"],
            "message": "User information updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")

# 비밀번호 변경
@router.put("/password")
def change_password(password_change: PasswordChange, current_user=Depends(get_current_user)):
    try:
        # 현재 사용자 정보 조회
        user_result = supabase.table("user").select("password_hash", "google_id").eq("id", current_user["id"]).execute()
        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_row = user_result.data[0]
        
        # Google OAuth 전용 계정 체크 (비밀번호가 없는 경우)
        if not user_row["password_hash"]:
            raise HTTPException(status_code=400, detail="Cannot change password for Google OAuth account")
        
        # 현재 비밀번호 검증
        if not verify_password(password_change.current_password, user_row["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # 새 비밀번호 해싱
        new_password_hash = get_password_hash(password_change.new_password)
        
        # 비밀번호 업데이트
        update_result = supabase.table("user").update({"password_hash": new_password_hash}).eq("id", current_user["id"]).execute()
        
        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to update password")
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")

# 계정 삭제
@router.delete("/me")
def delete_account(current_user=Depends(get_current_user)):
    try:
        user_id = current_user["id"]
        
        # 관련 데이터 연쇄 삭제 (트랜잭션처럼 처리)
        # 1. 투표 기록 삭제
        supabase.table("review_vote").delete().eq("user_id", user_id).execute()
        supabase.table("post_vote").delete().eq("user_id", user_id).execute()
        supabase.table("phishing_vote").delete().eq("user_id", user_id).execute()
        
        # 2. 댓글 삭제
        supabase.table("review_comment").delete().eq("user_id", user_id).execute()
        supabase.table("post_comment").delete().eq("user_id", user_id).execute()
        supabase.table("phishing_comment").delete().eq("user_id", user_id).execute()
        
        # 3. 게시물/리뷰/피싱 신고 삭제
        supabase.table("post").delete().eq("user_id", user_id).execute()
        supabase.table("review").delete().eq("user_id", user_id).execute()
        supabase.table("phishing_site").delete().eq("user_id", user_id).execute()
        
        # 4. 사용자 계정 삭제
        delete_result = supabase.table("user").delete().eq("id", user_id).execute()
        
        if not delete_result.data:
            raise HTTPException(status_code=500, detail="Failed to delete account")
        
        return {"message": "Account deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

# 이메일 인증 메일 발송
@router.post("/send-verification-email")
def send_verification_email_api(current_user=Depends(get_current_user)):
    try:
        user_id = current_user["id"]
        
        # 사용자 정보 조회
        user_result = supabase.table("user").select("email", "username", "email_verified").eq("id", user_id).execute()
        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_data = user_result.data[0]
        
        # 이미 인증된 경우
        if user_data.get("email_verified"):
            raise HTTPException(status_code=400, detail="Email is already verified")
        
        # 인증 코드 생성
        code = create_email_verification_code(user_id)
        
        # 인증 코드 이메일 발송
        if send_verification_code_email(user_data["email"], user_data["username"], code):
            return {"message": "Verification code email sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send verification code email")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send verification email: {str(e)}")

# 이메일 인증 코드 처리
@router.post("/verify-email-code")
def verify_email_code_api(request: EmailVerificationCode):
    try:
        # 코드 검증
        user_id = verify_email_verification_code(request.code)
        if not user_id:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code")
        
        # 사용자 이메일 인증 상태 업데이트
        update_result = supabase.table("user").update({"email_verified": True}).eq("id", user_id).execute()
        
        if not update_result.data:
            raise HTTPException(status_code=500, detail="Failed to verify email")
        
        # 사용된 코드 삭제
        supabase.table("email_verification_token").delete().eq("token", request.code).execute()
        
        return {"message": "Email verified successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify email: {str(e)}")

# 이메일 인증 상태 확인
@router.get("/email-verification-status")
def get_email_verification_status(current_user=Depends(get_current_user)):
    try:
        user_result = supabase.table("user").select("email_verified").eq("id", current_user["id"]).execute()
        if not user_result.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {"email_verified": user_result.data[0]["email_verified"]}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get verification status: {str(e)}") 