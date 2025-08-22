import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from services.auth import router as auth_router
from services.post import router as post_router
from services.image import router as image_router
from services.review import router as review_router
from services.phishing import router as phishing_router
from fastapi.staticfiles import StaticFiles
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Web Rating API",
    description="웹사이트 리뷰 및 피싱 사이트 신고 플랫폼 백엔드 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
cors_origins = os.getenv("CORS_ORIGINS")
if not cors_origins:
    raise RuntimeError("CORS_ORIGINS environment variable must be set")
allowed_origins = [origin.strip() for origin in cors_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 예외 처리
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

# 라우터 등록
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])  # 로그인/회원가입/토큰 관리
app.include_router(post_router, prefix="/posts", tags=["Posts"])  # 자유게시판 (게시물 작성/조회/수정/삭제)
app.include_router(review_router, prefix="/api", tags=["Reviews"])  # 웹사이트 리뷰 (별점/댓글/평균 계산)
app.include_router(phishing_router, prefix="/api", tags=["Phishing Sites"])  # 피싱 사이트 신고 및 관리
app.include_router(image_router, tags=["File Upload"])  # 이미지 업로드/조회
# uploads 폴더는 Supabase Storage로 대체되어 제거됨

# 기본 라우트
@app.get("/", tags=["Root"])
def read_root():
    return {
        "message": "Web Rating Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }

# 헬스 체크 엔드포인트
@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "web-rating-backend"
    }

# 실행 부분
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000) 