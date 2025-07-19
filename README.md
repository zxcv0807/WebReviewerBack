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
   -- 예시: review, review_comment 테이블
   CREATE TABLE review (
       id SERIAL PRIMARY KEY,
       site_name TEXT NOT NULL,
       url TEXT NOT NULL,
       summary TEXT NOT NULL,
       rating DOUBLE PRECISION NOT NULL CHECK (rating >= 0 AND rating <= 5),
       pros TEXT NOT NULL,
       cons TEXT NOT NULL,
       created_at TIMESTAMP NOT NULL
   );

   CREATE TABLE review_comment (
       id SERIAL PRIMARY KEY,
       review_id INTEGER NOT NULL REFERENCES review(id) ON DELETE CASCADE,
       content TEXT NOT NULL,
       created_at TIMESTAMP NOT NULL
   );
   ```
   - 실제 사용 테이블 구조는 프로젝트에 맞게 추가/생성하세요.

3. 환경변수(.env) 파일 생성:
   프로젝트 루트(backend)에 `.env` 파일을 만들고 아래처럼 입력하세요.
   ```env
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_supabase_anon_key
   SECRET_KEY=your_jwt_secret
   ALGORITHM=HS256
   ```
   - 기존 DB_HOST, DB_NAME 등은 필요 없습니다.

4. 서버 실행:
   ```bash
   uvicorn main:app --reload
   ```

서버는 http://127.0.0.1:8000 에서 시작됩니다.

## API Endpoints

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