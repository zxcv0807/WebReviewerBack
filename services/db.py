"""
데이터베이스 연결 관리 모듈

이 모듈은 Supabase 클라이언트의 중앙화된 관리를 담당합니다:
- Supabase 클라이언트 인스턴스 생성 및 관리
- 환경변수 기반 데이터베이스 연결 설정
- 모든 서비스 모듈에서 공통으로 사용할 수 있는 DB 클라이언트 제공
"""

import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

# 로깅 설정
logger = logging.getLogger(__name__)

# 환경변수 로드
load_dotenv()

# Supabase 연결 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env")

# Supabase 클라이언트 인스턴스 생성
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

logger.info("Supabase client initialized successfully")