# Backend

이 프로젝트는 FastAPI와 Supabase(PostgreSQL)를 사용하는 백엔드입니다.

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
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_supabase_anon_key
   SECRET_KEY=your_jwt_secret
   ALGORITHM=HS256
   
   # Google OAuth 2.0 설정
   GOOGLE_CLIENT_ID=963128153800-njiad73pc1l3lbch8o9bf8ifk3kr6ui4.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_google_client_secret_here
   ```
   - 기존 DB_HOST, DB_NAME 등은 필요 없습니다.
   - Google OAuth 2.0을 사용하려면 Google Cloud Console에서 클라이언트 시크릿을 생성하고 설정해야 합니다.

4. 서버 실행:
   ```bash
   uvicorn main:app --reload
   ```

서버는 http://127.0.0.1:8000 에서 시작됩니다.

## API Endpoints

### Authentication
- `POST /auth/signup` - 회원가입
- `POST /auth/login` - 로그인
- `POST /auth/google/callback` - Google OAuth 2.0 콜백 (Authorization Code Flow)
- `POST /auth/refresh` - 토큰 갱신
- `POST /auth/logout` - 로그아웃
- `GET /auth/me` - 현재 사용자 정보
- `GET /auth/admin/only` - 관리자 전용 엔드포인트

### Reviews
- `POST /api/reviews` - 리뷰 등록
- `GET /api/reviews` - 모든 리뷰 목록 (댓글 포함)
- `GET /api/reviews/{review_id}` - 특정 리뷰 + 댓글
- `PUT /api/reviews/{review_id}` - 리뷰 수정
- `DELETE /api/reviews/{review_id}` - 리뷰 삭제
- `POST /api/reviews/{review_id}/comments` - 댓글 추가

### Phishing Sites
- `POST /api/phishing-sites` - 피싱 사이트 신고
- `GET /api/phishing-sites` - 피싱 사이트 목록 조회
- `GET /api/phishing-sites/{site_id}` - 특정 피싱 사이트 조회
- `PUT /api/phishing-sites/{site_id}` - 피싱 사이트 수정
- `DELETE /api/phishing-sites/{site_id}` - 피싱 사이트 삭제

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

## 중요 안내 (Supabase 무료 플랜)
- 무료 플랜에서는 PostgreSQL에 직접 접속(5432 포트)이 불가능합니다.
- 반드시 Supabase Python SDK(`supabase-py`)를 사용해야 하며, 이미 본 프로젝트는 SDK 기반으로 동작합니다.
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`는 반드시 .env에 입력해야 합니다.