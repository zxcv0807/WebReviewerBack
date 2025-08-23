# Web Rating Backend

**웹사이트 리뷰 및 피싱 사이트 신고 플랫폼 백엔드**

이 프로젝트는 웹사이트 리뷰 작성, 피싱 사이트 신고, 사용자 인증(Google OAuth 포함), 게시판 기능을 제공하는 FastAPI 기반 백엔드입니다. Supabase(PostgreSQL)를 데이터베이스로 사용합니다.

## Setup

1. 의존성 설치:
   ```bash
   pip install -r requirements.txt
   ```

2. Supabase 준비:
   - [Supabase 웹사이트](https://app.supabase.com/)에서 프로젝트를 생성합니다.
   - **Project Settings > API**에서 `SUPABASE_URL`과 `SUPABASE_ANON_KEY`를 확인합니다.
   - **Table Editor** 또는 **SQL Editor**에서 아래 예시처럼 테이블을 생성합니다.

   ```sql
   -- User 테이블 (Google OAuth 2.0 지원)
   CREATE TABLE "user" (
       id SERIAL PRIMARY KEY,
       username TEXT NOT NULL UNIQUE,
       email TEXT NOT NULL UNIQUE,
       password_hash TEXT,
       google_id TEXT UNIQUE,
       role TEXT NOT NULL DEFAULT 'user',
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
   );

   -- Post 테이블
   CREATE TABLE post (
       id SERIAL PRIMARY KEY,
       title TEXT NOT NULL,
       category TEXT NOT NULL,
       content TEXT NOT NULL,
       created_at TIMESTAMP NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
       user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
       user_name TEXT NOT NULL
   );

   -- Tag 테이블
   CREATE TABLE tag (
       id SERIAL PRIMARY KEY,
       name TEXT NOT NULL,
       post_id INTEGER NOT NULL REFERENCES post(id) ON DELETE CASCADE
   );

   -- Image 테이블
   CREATE TABLE image (
       id SERIAL PRIMARY KEY,
       url TEXT NOT NULL,
       filename TEXT NOT NULL,
       uploaded_at TIMESTAMP NOT NULL DEFAULT NOW()
   );

   -- Review 테이블
   CREATE TABLE review (
       id SERIAL PRIMARY KEY,
       site_name TEXT NOT NULL,
       url TEXT NOT NULL UNIQUE,
       summary TEXT NOT NULL,
       rating DOUBLE PRECISION NOT NULL CHECK (rating >= 0 AND rating <= 5),
       pros TEXT NOT NULL,
       cons TEXT NOT NULL,
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
   );

   -- Review Comment 테이블
   CREATE TABLE review_comment (
       id SERIAL PRIMARY KEY,
       review_id INTEGER NOT NULL REFERENCES review(id) ON DELETE CASCADE,
       content TEXT NOT NULL,
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
   );

   -- Phishing Site 테이블
   CREATE TABLE phishing_site (
       id SERIAL PRIMARY KEY,
       url TEXT NOT NULL,
       reason TEXT NOT NULL,
       description TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT '검토중',
       created_at TIMESTAMP NOT NULL DEFAULT NOW()
   );
   ```
   - 위의 모든 테이블을 Supabase SQL Editor에서 실행하세요.

3. 환경변수(.env) 파일 생성:
   프로젝트 루트(backend)에 `.env` 파일을 만들고 아래처럼 입력하세요.
   ```env
   # Supabase 설정
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_supabase_anon_key
   
   # JWT 설정
   SECRET_KEY=your_jwt_secret
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   REFRESH_TOKEN_EXPIRE_DAYS=7
   
   # Google OAuth 2.0 설정
   GOOGLE_CLIENT_ID=963128153800-njiad73pc1l3lbch8o9bf8ifk3kr6ui4.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_google_client_secret_here
   
   # CORS 설정
   CORS_ORIGINS=http://localhost:3000,http://localhost:5173,https://webreviewer.vercel.app
   
   # 애플리케이션 설정
   ENVIRONMENT=production
   LOG_LEVEL=INFO
   ```
   - 기존 DB_HOST, DB_NAME 등은 필요 없습니다.
   - Google OAuth 2.0을 사용하려면 Google Cloud Console에서 클라이언트 시크릿을 생성하고 설정해야 합니다.
   - `CORS_ORIGINS`에는 허용할 프론트엔드 도메인을 쉼표로 구분하여 입력하세요.

4. 서버 실행:
   
   **개발 환경**:
   ```bash
   uvicorn main:app --reload
   ```
   
   **프로덕션 환경 (Docker Compose)**:
   ```bash
   ./deploy_v2.sh
   ```

서버는 http://127.0.0.1:8000 에서 시작됩니다.

## 주요 기능

### 🔐 사용자 인증
- 일반 회원가입/로그인 (이메일 + 패스워드)
- Google OAuth 2.0 소셜 로그인
- JWT 기반 액세스 토큰 + 리프레시 토큰
- 역할 기반 접근 제어 (user/admin)

### 📝 웹사이트 리뷰
- 사이트별 리뷰 작성 (별점, 장단점, 요약)
- 리뷰 댓글 시스템 (별점 포함)
- 평균 별점 자동 계산
- 리뷰 수정/삭제 기능

### 🚨 피싱 사이트 신고
- 의심스러운 사이트 신고 접수
- 신고 사유 및 상세 설명 기록
- 신고 상태 관리 (검토중/확인됨/무시됨)
- 관리자 검토 시스템

### 📋 게시판
- 카테고리별 게시물 작성
- 태그 시스템
- 사용자별 게시물 관리
- JSON 형태의 리치 컨텐츠 지원

### 📁 파일 업로드
- 이미지 파일 업로드 (PNG, JPG, JPEG, GIF, WebP)
- 파일명 중복 방지 (타임스탬프 기반)
- 업로드 메타데이터 관리

## API Endpoints

### Authentication (`/auth`)
- `POST /auth/signup` - 회원가입
- `POST /auth/login` - 로그인
- `POST /auth/google/callback` - Google OAuth 2.0 콜백 (Authorization Code Flow)
- `POST /auth/refresh` - 토큰 갱신
- `POST /auth/logout` - 로그아웃
- `GET /auth/me` - 현재 사용자 정보
- `GET /auth/admin/only` - 관리자 전용 엔드포인트

### Reviews (`/api`)
- `POST /api/reviews` - 리뷰 등록
- `GET /api/reviews` - 모든 리뷰 목록 (댓글 포함)
- `GET /api/reviews/{review_id}` - 특정 리뷰 + 댓글
- `PUT /api/reviews/{review_id}` - 리뷰 수정
- `DELETE /api/reviews/{review_id}` - 리뷰 삭제
- `POST /api/reviews/{review_id}/comments` - 댓글 추가

### Phishing Sites (`/api`)
- `POST /api/phishing-sites` - 피싱 사이트 신고
- `GET /api/phishing-sites` - 피싱 사이트 목록 조회 (상태 필터링 가능)
- `GET /api/phishing-sites/{site_id}` - 특정 피싱 사이트 조회
- `PUT /api/phishing-sites/{site_id}` - 피싱 사이트 수정 (관리자)
- `DELETE /api/phishing-sites/{site_id}` - 피싱 사이트 삭제 (관리자)

### Posts (`/posts`)
- `POST /posts` - 게시물 작성 (인증 필요)
- `GET /posts` - 게시물 목록 (카테고리/태그 필터링 가능)
- `GET /posts/{post_id}` - 특정 게시물 조회
- `PUT /posts/{post_id}` - 게시물 수정
- `DELETE /posts/{post_id}` - 게시물 삭제
- `GET /categories` - 카테고리 목록
- `GET /tags` - 태그 목록

### File Upload
- `POST /upload` - 이미지 파일 업로드
- `GET /uploads/{filename}` - 업로드된 파일 제공

### Google OAuth 2.0 Callback Schema
```json
{
  "code": "authorization_code_from_google",
  "redirect_uri": "http://localhost:5173/callback",
  "state": "optional_state_parameter"
}
```

**응답 형식:**
```json
{
  "access_token": "jwt_token",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "username": "user_name",
    "email": "user@example.com",
    "role": "user"
  }
}
```

### Review Schema
```json
{
  "site_name": "Tana",
  "url": "https://tana.inc",
  "summary": "AI 기반 노트 앱",
  "rating": 4.5,
  "pros": "직관적인 인터페이스, 강력한 AI 기능",
  "cons": "가격이 다소 비쌈"
}
```

### Phishing Site Schema
```json
{
  "url": "https://fake-login.com",
  "reason": "가짜 로그인 페이지",
  "description": "페이스북 로그인 페이지를 위장한 피싱 사이트"
}
```

## 기술 스택

### Backend Framework
- **FastAPI** - 고성능 비동기 웹 프레임워워크
- **Uvicorn** - ASGI 서버

### Database
- **Supabase** - PostgreSQL 기반 백엔드 서비스
- **Supabase Python SDK** - 데이터베이스 연동

### Authentication & Security
- **JWT (JSON Web Tokens)** - 인증 토큰 관리
- **Google OAuth 2.0** - 소셜 로그인
- **BCrypt** - 패스워드 해싱
- **CORS** - 크로스 오리진 리소스 공유

### Data Validation
- **Pydantic** - 데이터 검증 및 직렬화

### Environment Management
- **python-dotenv** - 환경변수 관리

### Deployment & Infrastructure
- **Docker** - 컨테이너화
- **Docker Compose** - 멀티 컨테이너 오케스트레이션
- **Nginx** - 리버스 프록시 및 웹 서버
- **AWS EC2** - 클라우드 서버 호스팅

## 프로젝트 구조

```
backend/
├── main.py              # FastAPI 애플리케이션 엔트리포인트
├── requirements.txt     # Python 의존성
├── Dockerfile          # Docker 컨테이너 설정
├── docker-compose.yml   # Docker Compose 설정
├── nginx.conf          # Nginx 프록시 서버 설정
├── deploy_v2.sh        # 배포 스크립트 (docker-compose 기반)
├── CLAUDE.md           # Claude Code 프로젝트 설정 및 가이드라인
├── uploads/            # 업로드된 파일 저장소 (현재는 Supabase Storage 사용)
├── logs/               # 애플리케이션 로그 파일
├── services/           # 비즈니스 로직 모듈
│   ├── __init__.py     # 모듈 초기화
│   ├── auth.py         # 사용자 인증 및 권한 관리
│   ├── review.py       # 웹사이트 리뷰 관리
│   ├── phishing.py     # 피싱 사이트 신고 관리
│   ├── post.py         # 게시판 관리
│   ├── image.py        # 파일 업로드 관리
│   └── db.py           # 데이터베이스 연결 (필요시)
└── README.md           # 프로젝트 문서
```

## 배포 정보

### 배포 환경
- **프론트엔드**: Vercel (https://webreviewer.vercel.app)
- **백엔드**: AWS EC2 (SSL 인증 완료)
- **데이터베이스**: Supabase (PostgreSQL)
- **프록시 서버**: Nginx (리버스 프록시, 로드 밸런싱)

### 배포 방법

#### Docker Compose 사용 (권장)

현재 프로젝트는 Docker Compose를 사용하여 Nginx와 FastAPI 애플리케이션을 함께 실행합니다.

1. **환경변수 설정**:
   ```bash
   # .env 파일 생성 후 필요한 환경변수 설정
   cp .env.example .env
   # 환경변수 값 수정
   ```

2. **배포 스크립트 실행** (권장):
   ```bash
   # deploy_v2.sh 스크립트 사용 (자동화된 배포)
   chmod +x deploy_v2.sh
   ./deploy_v2.sh
   ```

3. **수동 배포** (필요시):
   ```bash
   # 기존 컨테이너 중지
   docker-compose down
   
   # 이미지 빌드
   docker-compose build
   
   # 컨테이너 시작
   docker-compose up -d
   ```

#### 서비스 구성
- **FastAPI 애플리케이션**: 내부적으로 8000포트에서 실행
- **Nginx**: 80포트로 외부 요청을 받아 FastAPI로 프록시
- **헬스체크**: 30초마다 `/health` 엔드포인트 확인
- **로그**: `./logs` 디렉터리에 애플리케이션 및 Nginx 로그 저장

#### 주의사항
- `deploy.sh`는 더 이상 사용하지 않습니다. `deploy_v2.sh`를 사용하세요.
- 배포 전 `.env` 파일의 모든 환경변수가 올바르게 설정되었는지 확인하세요.
- SSL 인증서는 별도로 관리되며, 필요시 `nginx.conf`에서 HTTPS 설정을 추가할 수 있습니다.

## 중요 안내 (Supabase 무료 플랜)
- 무료 플랜에서는 PostgreSQL에 직접 접속(5432 포트)이 불가능합니다.
- 반드시 Supabase Python SDK(`supabase-py`)를 사용해야 하며, 이미 본 프로젝트는 SDK 기반으로 동작합니다.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`는 반드시 .env에 입력해야 합니다.

## 개발 가이드

### API 문서 확인
서버 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:
- **Swagger UI**: http://127.0.0.1:8000/docs
- **ReDoc**: http://127.0.0.1:8000/redoc

### 로그 확인
FastAPI는 자동으로 요청/응답 로그를 출력하며, 각 서비스 모듈에서 추가적인 디버그 정보를 확인할 수 있습니다.

### 테스트
프로젝트에는 별도의 테스트 코드가 포함되어 있지 않습니다. API 테스트는 Swagger UI 또는 Postman 등을 활용하시기 바랍니다.