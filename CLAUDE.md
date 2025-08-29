# Claude Code 프로젝트 설정

## 프로젝트 개요
**웹사이트 리뷰 및 피싱 사이트 신고 플랫폼 백엔드**
- FastAPI + Supabase 기반 REST API
- Docker Compose + Nginx 프록시 구성
- Google OAuth 2.0 소셜 로그인 지원
- 웹사이트 리뷰, 피싱 신고, 게시판 기능
- Supabase Storage를 통한 파일 업로드 관리
- AWS EC2 배포 환경

이 파일은 Claude Code가 이 프로젝트에서 작업할 때 따라야 할 가이드라인을 정의합니다.

## 코드 수정 시 필수 설명 형식

모든 코드 수정 시 다음 형식으로 설명을 제공해야 합니다:

### 🔍 기존 코드 분석
- 현재 코드의 상태와 구조
- 발견된 문제점이나 개선이 필요한 부분
- 보안, 성능, 가독성 관점에서의 이슈

### ⚠️ 수정이 필요한 이유
- 왜 이 수정이 필요한지 구체적인 이유
- 어떤 문제를 해결하거나 위험을 방지하는지
- 비즈니스 로직이나 사용자 경험 개선 측면

### ✨ 개선사항
- 수정 후 얻는 구체적인 장점들
- 보안 강화, 성능 향상, 유지보수성 개선 등
- 새로 추가된 기능이나 검증 로직의 설명

### 🛠️ 추가 설정 필요사항
- 새로 추가된 환경변수나 설정 파일
- 배포 시 주의사항이나 마이그레이션 필요사항
- 의존성 설치나 추가 설정이 필요한 경우

## 프로젝트별 코딩 규칙

### 보안 우선 원칙
- 모든 사용자 입력에 대한 검증 필수
- 민감한 정보는 환경변수로 관리
- 로깅 시 개인정보나 민감 데이터 노출 금지

### 코드 품질 기준
- 주석보다는 명확한 변수명과 함수명 사용
- 하드코딩된 값들은 환경변수나 상수로 분리
- 에러 처리는 구체적이고 의미있는 메시지 제공

### 환경변수 관리
- 모든 설정값은 환경변수로 관리
- 개발환경: ENVIRONMENT=development, 배포환경: ENVIRONMENT=production
- CORS_ORIGINS 설정으로 허용 도메인 관리
- 민감한 정보(.env 파일)는 Git에 커밋하지 않음
- Docker Compose에서 환경변수 오버라이드 활용

### 로깅 및 모니터링
- print 문 대신 적절한 로그 레벨 사용
- 개발환경: LOG_LEVEL=DEBUG, 운영환경: LOG_LEVEL=INFO
- 에러 발생 시 충분한 컨텍스트 정보 포함
- 로그 파일은 ./logs/ 디렉터리에 저장 (Docker 볼륨 마운트)
- 운영 환경에서 디버그 정보 노출 방지

## 특별 주의사항

### 인증 관련 코드
- JWT 토큰 처리 시 보안 검증 철저히
- 쿠키 설정 시 보안 플래그 적절히 설정
- OAuth 처리 시 상태 검증 및 에러 처리 강화

### 데이터베이스 작업
- SQL Injection 방지를 위한 파라미터 바인딩
- 트랜잭션 처리 시 롤백 로직 포함
- 데이터 검증 후 저장

### API 엔드포인트
- 입력 검증은 Pydantic 모델 활용
- 적절한 HTTP 상태 코드 반환
- API 문서화를 위한 태그와 설명 추가

## 성능 및 확장성 고려사항

### 데이터베이스 최적화
- 필요한 필드만 SELECT하여 네트워크 트래픽 최소화
- 인덱스 활용을 고려한 쿼리 작성
- N+1 쿼리 문제 방지

### API 응답 최적화
- 페이지네이션 구현으로 대용량 데이터 처리
- 캐싱 전략 고려 (적절한 경우)
- 응답 데이터 구조 최적화

### 메모리 및 리소스 관리
- 파일 업로드 시 메모리 사용량 제한
- 외부 API 호출 시 타임아웃 설정
- 커넥션 풀 관리

## ⛔ Claude Code 테스트 금지 정책

### 테스트 실행 금지
- **절대 금지**: Claude Code에서 서버를 실행하거나 API 테스트를 수행하는 것을 금지합니다
- **이유**: 테스트는 사용자가 직접 수행해야 하며, Claude는 코드 작성에만 집중해야 합니다

## 🔍 필수 에러 검증 절차

### 코드 수정 후 반드시 수행해야 할 에러 검증

#### 1단계: Python 문법 검증
- **필수**: `python -m py_compile services/*.py` 명령으로 모든 서비스 파일의 문법 오류 확인
- **필수**: `python -m py_compile main.py` 명령으로 메인 파일 문법 오류 확인
- **목적**: 기본적인 Python 문법 오류나 들여쓰기 오류 사전 발견

#### 2단계: Import 오류 검증  
- **필수**: `python -c "from services import auth, post, review, phishing, image, pagination"` 명령으로 import 오류 확인
- **필수**: `python -c "import main"` 명령으로 메인 모듈 import 확인
- **목적**: 순환 import, 모듈 경로 오류, 누락된 의존성 사전 발견

#### 3단계: FastAPI 앱 초기화 검증
- **필수**: `python -c "from main import app; print('FastAPI app initialized successfully')"` 명령으로 앱 초기화 확인
- **목적**: FastAPI 앱 생성 과정에서 발생할 수 있는 설정 오류나 라우터 등록 오류 확인

### ⚠️ 에러 발견 시 대응
1. **문법 오류**: 해당 파일의 문법 오류 수정 후 재검증
2. **Import 오류**: 모듈 경로나 의존성 확인 후 수정
3. **앱 초기화 오류**: 라우터 등록이나 설정 관련 코드 검토

## 검증 가이드라인

### Claude Code 역할 제한
- 코드 작성 및 수정만 수행
- 문법 및 구조적 에러 검증만 수행
- **금지**: 서버 실행, API 호출, 기능 테스트 등 모든 형태의 테스트 수행

### 배포 관련 확인사항
- `deploy_v2.sh` 스크립트를 사용하여 배포
- 환경변수 설정 확인 (특히 CORS_ORIGINS, ENVIRONMENT)
- Docker 컨테이너 헬스체크 통과 확인
- SSL 인증서 및 도메인 연결 상태 확인

### 보안 검증 체크리스트
- 사용자 입력 검증 확인
- 인증이 필요한 엔드포인트 보호 확인
- 민감한 정보 로깅 여부 점검
- CORS 설정 적절성 확인

## 프로젝트 특화 규칙

### 웹사이트 리뷰 기능
- 리뷰 평점은 0-5 범위 검증 필수
- 댓글과 리뷰의 평균 평점 계산 로직 정확성 확인
- URL 형식 검증 및 정규화

### 피싱 사이트 신고 기능
- 신고된 URL의 안전성 검증
- 관리자 권한 검증 철저히
- 신고 상태 관리 워크플로우 준수

### 파일 업로드 기능 (Supabase Storage)
- Supabase Storage를 통한 파일 업로드 관리
- 허용된 파일 형식만 업로드 가능 (이미지 파일)
- 파일 크기 제한 준수
- 업로드 URL 보안 및 접근 권한 확인

### Google OAuth 연동
- 사용자명 중복 시 자동 처리 로직
- 기존 계정과 Google 계정 연동 처리
- OAuth 에러 상황별 적절한 응답

### 현재 데이터베이스 구조
| table_name       | column_name      | data_type                   | is_nullable |
| ---------------- | ---------------- | --------------------------- | ----------- |
| image            | id               | integer                     | NO          |
| image            | url              | text                        | NO          |
| image            | filename         | text                        | YES         |
| image            | uploaded_at      | timestamp without time zone | NO          |
| image            | storage_path     | character varying           | YES         |
| phishing_comment | id               | integer                     | NO          |
| phishing_comment | phishing_site_id | integer                     | YES         |
| phishing_comment | user_id          | integer                     | YES         |
| phishing_comment | content          | text                        | NO          |
| phishing_comment | created_at       | timestamp without time zone | YES         |
| phishing_comment | updated_at       | timestamp without time zone | YES         |
| phishing_site    | id               | integer                     | NO          |
| phishing_site    | url              | text                        | NO          |
| phishing_site    | reason           | text                        | NO          |
| phishing_site    | description      | text                        | YES         |
| phishing_site    | status           | text                        | NO          |
| phishing_site    | created_at       | timestamp without time zone | NO          |
| phishing_site    | view_count       | integer                     | YES         |
| phishing_site    | like_count       | integer                     | YES         |
| phishing_site    | dislike_count    | integer                     | YES         |
| phishing_site    | user_id          | integer                     | YES         |
| phishing_vote    | id               | integer                     | NO          |
| phishing_vote    | phishing_site_id | integer                     | YES         |
| phishing_vote    | user_id          | integer                     | YES         |
| phishing_vote    | vote_type        | character varying           | YES         |
| phishing_vote    | created_at       | timestamp without time zone | YES         |
| post             | id               | integer                     | NO          |
| post             | title            | text                        | NO          |
| post             | category         | text                        | NO          |
| post             | content          | text                        | NO          |
| post             | created_at       | timestamp without time zone | NO          |
| post             | updated_at       | timestamp without time zone | NO          |
| post             | user_name        | text                        | NO          |
| post             | user_id          | integer                     | YES         |
| post             | view_count       | integer                     | YES         |
| post             | like_count       | integer                     | YES         |
| post             | dislike_count    | integer                     | YES         |
| post_comment     | id               | integer                     | NO          |
| post_comment     | post_id          | integer                     | YES         |
| post_comment     | user_id          | integer                     | YES         |
| post_comment     | content          | text                        | NO          |
| post_comment     | created_at       | timestamp without time zone | YES         |
| post_comment     | updated_at       | timestamp without time zone | YES         |
| post_vote        | id               | integer                     | NO          |
| post_vote        | post_id          | integer                     | YES         |
| post_vote        | user_id          | integer                     | YES         |
| post_vote        | vote_type        | character varying           | YES         |
| post_vote        | created_at       | timestamp without time zone | YES         |
| review           | id               | integer                     | NO          |
| review           | site_name        | text                        | NO          |
| review           | url              | text                        | NO          |
| review           | summary          | text                        | NO          |
| review           | rating           | double precision            | NO          |
| review           | pros             | text                        | NO          |
| review           | cons             | text                        | NO          |
| review           | created_at       | timestamp without time zone | NO          |
| review           | view_count       | integer                     | YES         |
| review           | like_count       | integer                     | YES         |
| review           | dislike_count    | integer                     | YES         |
| review           | user_id          | integer                     | YES         |
| review_comment   | id               | integer                     | NO          |
| review_comment   | review_id        | integer                     | NO          |
| review_comment   | content          | text                        | NO          |
| review_comment   | created_at       | timestamp without time zone | NO          |
| review_comment   | user_id          | integer                     | YES         |
| review_comment   | updated_at       | timestamp without time zone | YES         |
| review_vote      | id               | integer                     | NO          |
| review_vote      | review_id        | integer                     | YES         |
| review_vote      | user_id          | integer                     | YES         |
| review_vote      | vote_type        | character varying           | YES         |
| review_vote      | created_at       | timestamp without time zone | YES         |
| tag              | id               | integer                     | NO          |
| tag              | name             | text                        | NO          |
| tag              | post_id          | integer                     | NO          |
| user             | id               | integer                     | NO          |
| user             | username         | text                        | NO          |
| user             | email            | text                        | NO          |
| user             | password_hash    | text                        | YES         |
| user             | created_at       | timestamp without time zone | NO          |
| user             | role             | text                        | NO          |
| user             | google_id        | text                        | YES         |